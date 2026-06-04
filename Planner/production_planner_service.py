#!/usr/bin/env python3
"""Top-level production planner service and runtime launcher.

This module is the single orchestration entrypoint for production planning:
1. Read runtime and planner configuration.
2. Fetch and prepare product/resource AAS inputs.
3. Execute parse -> merge -> build -> solve -> export planning sequence.
4. Generate and register Process AAS.
5. Expose PackML/MQTT planning command endpoint and run service loop.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable, Dict, List, Optional

import requests

from packml_runtime.aas_client import AASClient
from packml_runtime.mqtt import Proxy, ResponseAsync
from packml_runtime.simulator import PackMLStateMachine

from .step1_aas_input import collect_planning_context, collect_planning_context_from_kg
from .step1_aas_input.parsing import parse_source
from .step2_pddl_construction import (
    build_capabilities,
    build_up_problem,
    compile_bop_ordering,
    export_problem_artifacts,
    merge_sources,
    write_text_artifact,
)
from .step2_pddl_construction.models import AIPlanningPipelineResult
from .step3_pddl_solving import export_policy_visualization, solve_with_reduced_fallback
from .step4_policy_to_bt import build_trivial_bt
from .step4_policy_to_bt.plan_converters import deterministic_plan_to_bt_xml, extract_plan_text
from .step5_bt_optimization import optimize_bt
from .step6_bt_serialization import bt_to_xml, count_bt_nodes, generate_bt_filename, save_bt_xml
from .step7_process_aas_publishing.process_aas_generator import (
    ProcessAASConfig,
    ProcessAASGenerator,
)
from .run_metrics import (
    env_metrics_dir,
    env_metrics_topic_prefix,
    publish_stage_metrics,
    write_stage_metrics,
)
from .step0_validation import ShaclGateConfig, run_pre_planning_shacl_gate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_bool_env(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _is_shacl_graph_available(
    query_endpoint: str,
    shacl_graph: str,
    timeout_seconds: float,
) -> bool:
    ask_query = f"""
ASK
FROM <{shacl_graph}>
WHERE {{ ?s ?p ?o }}
""".strip()

    try:
        response = requests.post(
            query_endpoint,
            data={"query": ask_query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.info("SHACL gate auto-detect probe failed against %s: %s", query_endpoint, exc)
        return False

    return bool(payload.get("boolean", False))


def _resolve_shacl_gate_enabled(
    gate_env: Optional[str],
    query_endpoint: str,
    shacl_graph: str,
    timeout_seconds: float,
) -> bool:
    if gate_env is not None and gate_env.strip():
        raw = gate_env.strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
        if raw in {"0", "false", "no", "off"}:
            return False
        if raw != "auto":
            logger.warning(
                "Unsupported PLANNER_SHACL_GATE_ENABLED=%r. Falling back to auto mode.",
                gate_env,
            )

    return _is_shacl_graph_available(query_endpoint, shacl_graph, timeout_seconds)


def _build_context_collector(config: "PlannerConfig") -> Callable[..., Any]:
    mode = str(config.input_mode or "aas").strip().lower()
    if mode == "kg":
        return partial(
            collect_planning_context_from_kg,
            query_endpoint=config.kg_query_endpoint,
            abox_graph=config.kg_abox_graph,
            tbox_graph=config.kg_tbox_graph,
            timeout_seconds=config.kg_query_timeout_seconds,
            enable_capability_matching=config.kg_capability_matching_enabled,
        )
    if mode != "aas":
        logger.warning("Unsupported planner input mode '%s'; falling back to AAS mode", mode)
    return collect_planning_context


@dataclass
class PlanningResult:
    """Result of the planning operation."""

    success: bool
    process_aas_id: Optional[str] = None
    order_aas_id: Optional[str] = None
    error_message: Optional[str] = None
    process_config: Optional[Dict[str, Any]] = None
    planner_mode: Optional[str] = None
    planner_backend: Optional[str] = None
    solver_status: Optional[str] = None
    planner_warnings: List[str] = field(default_factory=list)
    planning_artifacts: Dict[str, str] = field(default_factory=dict)
    capabilities: List[Dict[str, Any]] = field(default_factory=list)
    run_id: Optional[str] = None
    run_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_response_dict(self) -> Dict[str, Any]:
        """Convert to MQTT response format."""
        response = {
            "State": "SUCCESS" if self.success else "FAILURE",
            "OrderAASId": self.order_aas_id,
        }

        if self.success and self.process_aas_id:
            response["ProcessAasId"] = self.process_aas_id

        if self.run_id:
            response["RunId"] = self.run_id

        if self.error_message:
            response["ErrorMessage"] = self.error_message

        if self.planner_mode or self.planner_backend or self.solver_status:
            response["PlanningSummary"] = {
                "Mode": self.planner_mode,
                "Backend": self.planner_backend,
                "Status": self.solver_status,
                "WarningsCount": len(self.planner_warnings),
            }

        if self.planner_warnings:
            response["PlanningWarnings"] = self.planner_warnings

        if self.capabilities:
            response["PlannedCapabilities"] = self.capabilities

        if self.planning_artifacts:
            response["PlanningArtifacts"] = self.planning_artifacts

        if self.run_metrics:
            response["RunMetrics"] = self.run_metrics

        return response


@dataclass
class PlannerConfig:
    """Configuration for planner orchestration and artifacts."""

    registration_topic: str = "NN/Nybrovej/InnoLab/Registration/Config"

    process_aas_output_dir: str = "../AASDescriptions/Process/configs"
    bt_output_dir: str = "../BTDescriptions"
    ai_artifacts_dir: Optional[str] = None

    bt_base_url: str = "https://aausmartproductionlab.github.io/AP2030-UNS/BTDescriptions"
    planning_timeout_seconds: float = 30.0
    strict_semantic_solve: bool = True
    input_mode: str = "aas"
    kg_query_endpoint: str = "http://kg-fuseki:3030/kg/sparql"
    kg_abox_graph: str = "urn:kg:abox"
    kg_tbox_graph: str = "urn:kg:tbox"
    kg_query_timeout_seconds: float = 10.0
    kg_capability_matching_enabled: bool = True
    shacl_gate_enabled: bool = False
    shacl_query_endpoint: str = "http://kg-fuseki:3030/kg/sparql"
    shacl_abox_graph: str = "urn:kg:abox"
    shacl_tbox_graph: str = "urn:kg:tbox"
    shacl_shapes_graph: str = "urn:kg:shacl"
    shacl_gate_timeout_seconds: float = 20.0
    shacl_gate_inference: str = "rdfs"
    metrics_dir: Optional[str] = "/data/run_metrics"
    metrics_topic_prefix: Optional[str] = "NN/Nybrovej/InnoLab/Stats"

    save_intermediate_files: bool = True

    def to_shacl_gate_config(self) -> ShaclGateConfig:
        return ShaclGateConfig(
            enabled=self.shacl_gate_enabled,
            sparql_endpoint=self.shacl_query_endpoint,
            abox_graph_iri=self.shacl_abox_graph,
            tbox_graph_iri=self.shacl_tbox_graph,
            shacl_graph_iri=self.shacl_shapes_graph,
            timeout_seconds=self.shacl_gate_timeout_seconds,
            inference=self.shacl_gate_inference,
        )


@dataclass(frozen=True)
class RuntimeConfig:
    """Configuration for MQTT/PackML runtime host."""

    broker_address: str = "hivemq-broker"
    broker_port: int = 1883
    base_topic: str = "NN/Nybrovej/InnoLab/ProductionPlanner"
    aas_server_url: str = "http://aas-env:8081"
    aas_registry_url: str = "http://aas-registry:8080"
    registration_topic: str = "NN/Nybrovej/InnoLab/Registration/Config"


class PlannerService:
    """Main orchestrator for production planning and Process AAS registration."""

    def __init__(self, aas_client, mqtt_client=None, config: Optional[PlannerConfig] = None):
        self.aas_client = aas_client
        self.mqtt_client = mqtt_client
        self.config = config or PlannerConfig()
        self.context_collector = _build_context_collector(self.config)
        logger.info("Planner input mode: %s", self.config.input_mode)
        self.process_generator = ProcessAASGenerator(
            ProcessAASConfig(bt_base_url=self.config.bt_base_url)
        )

    def plan_and_register(
        self,
        asset_ids: List[str],
        order_aas_id: str,
        run_id: Optional[str] = None,
        requested_product_instances: Optional[int] = None,
    ) -> PlanningResult:
        effective_run_id = str(run_id or uuid.uuid4())
        overall_started = time.perf_counter()
        logger.info("Starting planning for order: %s", order_aas_id)
        logger.info("Initial asset IDs: %s", asset_ids)
        logger.info("Run ID: %s", effective_run_id)

        if self.config.shacl_gate_enabled:
            logger.info("Step 0: Running SHACL fail-fast gate before planning...")
            try:
                gate_result = run_pre_planning_shacl_gate(self.config.to_shacl_gate_config())
            except Exception as exc:
                logger.error("SHACL pre-planning gate failed with error: %s", exc)
                return PlanningResult(
                    success=False,
                    order_aas_id=order_aas_id,
                    error_message=f"SHACL pre-planning gate error: {exc}",
                    run_id=effective_run_id,
                )

            logger.info(
                "SHACL pre-planning gate executed: conforms=%s data_triples=%d shape_triples=%d",
                gate_result.conforms,
                gate_result.data_triples,
                gate_result.shape_triples,
            )

            if not gate_result.conforms:
                report_excerpt = "\n".join(gate_result.report_text.strip().splitlines()[:25]).strip()
                return PlanningResult(
                    success=False,
                    order_aas_id=order_aas_id,
                    error_message="SHACL pre-planning gate failed; planning aborted.",
                    planner_warnings=[report_excerpt or "SHACL validation reported non-conformance."],
                    run_id=effective_run_id,
                )

        logger.info("Step 1: Collecting planning context from AAS models...")
        planning_context = self.context_collector(self.aas_client, order_aas_id, asset_ids)
        if not planning_context:
            return PlanningResult(
                success=False,
                order_aas_id=order_aas_id,
                error_message=f"Could not fetch order AAS: {order_aas_id}",
                run_id=effective_run_id,
            )

        logger.info("Resolved to %d assets", len(planning_context.resolved_asset_ids))
        planning_sources = planning_context.planning_sources
        if not planning_sources:
            return PlanningResult(
                success=False,
                order_aas_id=order_aas_id,
                error_message="No AIPlanning submodels found across product/assets",
                run_id=effective_run_id,
            )

        logger.info("Step 2-6: Parsing, building, solving, and synthesizing behavior tree...")
        try:
            warnings: list[str] = []
            metrics: dict[str, Any] = {
                "source_count": len(planning_sources),
                "parse_time_s": 0.0,
                "build_time_s": 0.0,
                "planning_time_s": 0.0,
                "bt_synthesis_time_s": 0.0,
                "pipeline_total_time_s": 0.0,
                "policy_rule_count": 0,
                "plan_action_count": 0,
                "bt_nodes_trivial": 0,
                "bt_nodes_hoisted": 0,
            }

            pipeline_started = time.perf_counter()

            asset_types_by_aas_id = getattr(planning_context, "asset_types_by_aas_id", None)
            asset_type_lookup: Dict[str, str] = dict(asset_types_by_aas_id or {})
            for source in planning_sources:
                if source.aas_id and source.asset_type:
                    asset_type_lookup.setdefault(source.aas_id, source.asset_type)

            logger.info("Step 2: Parsing AI planning sources...")
            parse_started = time.perf_counter()
            pre_parsed = getattr(planning_context, "pre_parsed_sources", None) or []
            if pre_parsed:
                # Phase 4 KG path: domain + init already assembled from KG projections.
                logger.info("Using %d KG-pre-parsed source(s) (bypassing AAS parse)", len(pre_parsed))
                parsed_sources = list(pre_parsed)
            else:
                parsed_sources = [
                    parse_source(source, asset_type_by_aas_id=asset_type_lookup)
                    for source in planning_sources
                ]
            metrics["parse_time_s"] = time.perf_counter() - parse_started

            for parsed in parsed_sources:
                warnings.extend(parsed.warnings)

            logger.info("Step 3: Building UP planning problem...")
            build_started = time.perf_counter()
            merged = merge_sources(parsed_sources, warnings)
            compile_bop_ordering(
                merged,
                planning_context.order_config.get("BillOfProcesses"),
                warnings,
            )
            up_problem = build_up_problem(merged, warnings, semantic_natural_transitions=True)
            artifacts = export_problem_artifacts(up_problem, self.config.ai_artifacts_dir, warnings)
            metrics["build_time_s"] = time.perf_counter() - build_started

            if artifacts.get("domain_pddl"):
                logger.info("PDDL domain written to: %s", artifacts["domain_pddl"])
            if artifacts.get("problem_pddl"):
                logger.info("PDDL problem written to: %s", artifacts["problem_pddl"])

            logger.info("Step 4: Solving planning problem...")
            solve_started = time.perf_counter()
            solve_result = solve_with_reduced_fallback(
                up_problem,
                timeout=self.config.planning_timeout_seconds,
                warnings=warnings,
                allow_reduced_fallback=not self.config.strict_semantic_solve,
                build_reduced_problem=lambda: build_up_problem(
                    merged,
                    warnings,
                    semantic_natural_transitions=False,
                    drop_natural_transitions=True,
                    include_trajectory_constraints=False,
                ),
                reduced_model_stats={
                    "events": sum(
                        1
                        for action in merged.get("actions", [])
                        if str(action.get("action_kind") or "") == "Event"
                    ),
                    "processes": sum(
                        1
                        for action in merged.get("actions", [])
                        if str(action.get("action_kind") or "") == "Process"
                    ),
                    "constraints": len(merged.get("constraints_terms", [])),
                },
            )
            metrics["planning_time_s"] = time.perf_counter() - solve_started

            planner_metadata: Dict[str, Any] = {}
            solve_problem = getattr(solve_result, "metadata", {}).get("problem")
            if solve_problem is not None:
                planner_metadata = dict(getattr(solve_problem, "_planner_metadata", {}) or {})
            if not planner_metadata:
                planner_metadata = dict(getattr(up_problem, "_planner_metadata", {}) or {})
            if hasattr(solve_result, "metadata") and isinstance(getattr(solve_result, "metadata", None), dict):
                solve_result.metadata["planner_metadata"] = planner_metadata

            policy_trivial_bt = None
            policy_hoisted_bt = None
            if getattr(solve_result, "is_policy", False):
                try:
                    metrics["policy_rule_count"] = int(len(solve_result.policy))
                except Exception as exc:
                    warnings.append(f"Could not count policy rules: {exc}")

                try:
                    policy_result = solve_result.require_policy_result()
                    problem_obj = getattr(solve_result, "metadata", {}).get("problem")
                    policy_trivial_bt = build_trivial_bt(
                        policy_result,
                        problem=problem_obj,
                        planner_metadata=planner_metadata,
                    )
                    policy_hoisted_bt = optimize_bt(policy_trivial_bt)
                    metrics["bt_nodes_hoisted"] = int(count_bt_nodes(policy_hoisted_bt.root))
                    metrics["bt_nodes_trivial"] = int(count_bt_nodes(policy_trivial_bt.root))
                except Exception as exc:
                    warnings.append(f"Could not derive hoisted/trivial BT node counts: {exc}")

            if getattr(solve_result, "is_plan", False):
                try:
                    up_result = solve_result.require_plan_result()
                    plan = getattr(up_result, "plan", None)
                    actions = list(getattr(plan, "actions", [])) if plan is not None else []
                    metrics["plan_action_count"] = len(actions)
                except Exception as exc:
                    warnings.append(f"Could not count deterministic plan actions: {exc}")

            logger.info("Step 5: Converting solve result to behavior tree...")
            bt_started = time.perf_counter()
            bt_xml = ""
            if not getattr(solve_result, "is_solved", False):
                warnings.append("Solve result unsolved; skipping BT synthesis.")
            else:
                if getattr(solve_result, "is_policy", False):
                    if policy_hoisted_bt is None:
                        policy_result = solve_result.require_policy_result()
                        problem_obj = getattr(solve_result, "metadata", {}).get("problem")
                        policy_trivial_bt = build_trivial_bt(
                            policy_result,
                            problem=problem_obj,
                            planner_metadata=planner_metadata,
                        )
                        policy_hoisted_bt = optimize_bt(policy_trivial_bt)
                    bt_xml = bt_to_xml(policy_hoisted_bt, planner_metadata=planner_metadata)
                elif getattr(solve_result, "is_plan", False):
                    bt_xml = deterministic_plan_to_bt_xml(solve_result, planner_metadata=planner_metadata)
                    if bt_xml:
                        warnings.append("Generated reactive BT from deterministic UP plan.")
                    else:
                        raise RuntimeError(
                            "Deterministic solve result produced an empty BT XML payload."
                        )
                else:
                    raise RuntimeError(
                        "Unexpected solve result mode. Expected either policy or deterministic plan output."
                    )
                if not bt_xml:
                    raise RuntimeError("BT conversion produced an empty XML payload.")
            metrics["bt_synthesis_time_s"] = time.perf_counter() - bt_started

            logger.info("Step 6: Serializing planning artifacts...")
            if bt_xml:
                bt_path = write_text_artifact(artifacts, "behavior_tree_xml", "behavior_tree.xml", bt_xml, warnings)
                if bt_path:
                    logger.info("Behavior tree written to: %s", bt_path)

            if getattr(solve_result, "is_plan", False):
                plan_text = extract_plan_text(solve_result)
                if plan_text:
                    plan_path = write_text_artifact(
                        artifacts,
                        "deterministic_plan",
                        "deterministic_plan.txt",
                        plan_text,
                        warnings,
                    )
                    if plan_path:
                        logger.info("Deterministic plan written to: %s", plan_path)

            if getattr(solve_result, "is_policy", False):
                export_policy_visualization(solve_result, artifacts, warnings)
                try:
                    policy_lines = [str(rule) for rule in solve_result.policy]
                    policy_text = "\n".join(policy_lines)
                    rules_path = write_text_artifact(
                        artifacts,
                        "policy_rules",
                        "policy_rules.txt",
                        policy_text,
                        warnings,
                    )
                    if rules_path:
                        logger.info("Policy rules written to: %s", rules_path)
                except Exception as exc:
                    warnings.append(f"Could not export policy rules text: {exc}")

            capabilities = build_capabilities(merged)
            metrics["pipeline_total_time_s"] = time.perf_counter() - pipeline_started

            pipeline_result = AIPlanningPipelineResult(
                bt_xml=bt_xml,
                solve_result=solve_result,
                warnings=warnings,
                capabilities=capabilities,
                artifacts=artifacts,
                planner_metadata=planner_metadata,
                metrics=metrics,
            )
        except Exception as exc:
            logger.error("Planning sequence failed: %s", exc)
            return PlanningResult(
                success=False,
                order_aas_id=order_aas_id,
                error_message=f"AI planning failed: {exc}",
                run_id=effective_run_id,
            )

        run_metrics = dict(getattr(pipeline_result, "metrics", {}) or {})
        run_metrics["run_id"] = effective_run_id
        run_metrics["order_aas_id"] = order_aas_id
        run_metrics["resolved_asset_count"] = len(planning_context.resolved_asset_ids)
        run_metrics["planning_source_count"] = len(planning_sources)
        run_metrics["end_to_end_planning_s"] = time.perf_counter() - overall_started
        if requested_product_instances is not None:
            run_metrics["product_instance_count"] = int(requested_product_instances)

        run_metrics_path = write_stage_metrics(
            metrics_dir=self.config.metrics_dir,
            run_id=effective_run_id,
            stage="planner",
            payload=run_metrics,
        )
        if run_metrics_path:
            pipeline_result.artifacts["planner_metrics"] = run_metrics_path

        publish_stage_metrics(
            mqtt_client=self.mqtt_client,
            topic_prefix=self.config.metrics_topic_prefix,
            stage="planner",
            run_id=effective_run_id,
            payload=run_metrics,
        )

        solve_result = pipeline_result.solve_result
        if not getattr(solve_result, "is_solved", False):
            unsolved_message = (
                "Planning unsolved in strict mode"
                if self.config.strict_semantic_solve
                else "Planning unsolved"
            )
            return PlanningResult(
                success=False,
                order_aas_id=order_aas_id,
                planner_mode=getattr(solve_result, "mode", None),
                planner_backend=getattr(solve_result, "backend_name", None),
                solver_status=getattr(solve_result, "status", None),
                planner_warnings=pipeline_result.warnings,
                planning_artifacts=pipeline_result.artifacts,
                error_message=unsolved_message,
                run_id=effective_run_id,
                run_metrics=run_metrics,
            )

        bt_xml = pipeline_result.bt_xml
        if not bt_xml:
            return PlanningResult(
                success=False,
                order_aas_id=order_aas_id,
                planner_mode=getattr(solve_result, "mode", None),
                planner_backend=getattr(solve_result, "backend_name", None),
                solver_status=getattr(solve_result, "status", None),
                planner_warnings=pipeline_result.warnings,
                planning_artifacts=pipeline_result.artifacts,
                error_message="Planner solved but did not produce BT XML",
                run_id=effective_run_id,
                run_metrics=run_metrics,
            )

        planar_table_id = planning_context.planar_table_id
        bt_filename = generate_bt_filename(planning_context.order_config)

        if self.config.save_intermediate_files:
            bt_path = os.path.join(self.config.bt_output_dir, bt_filename)
            save_bt_xml(bt_xml, bt_path)
            logger.info("Saved behavior tree to %s", bt_path)

        logger.info("Step 7: Generating Process AAS configuration...")
        process_bundle = self.process_generator.generate_process_aas_bundle(
            pipeline_result.capabilities,
            order_aas_id,
            planning_context.order_config,
            bt_filename,
            planar_table_id,
            run_id=effective_run_id,
            output_dir=self.config.process_aas_output_dir if self.config.save_intermediate_files else None,
        )
        if process_bundle.output_path:
            logger.info("Saved Process AAS config to %s", process_bundle.output_path)

        logger.info("Step 8: Registering Process AAS via MQTT...")
        self.process_generator.publish_bundle_registration(
            self.mqtt_client,
            self.config.registration_topic,
            process_bundle,
        )

        logger.info("Planning complete. Process AAS ID: %s", process_bundle.process_aas_id)

        return PlanningResult(
            success=True,
            process_aas_id=process_bundle.process_aas_id,
            order_aas_id=order_aas_id,
            process_config=process_bundle.config,
            planner_mode=getattr(solve_result, "mode", None),
            planner_backend=getattr(solve_result, "backend_name", None),
            solver_status=getattr(solve_result, "status", None),
            planner_warnings=pipeline_result.warnings,
            planning_artifacts=pipeline_result.artifacts,
            capabilities=[
                {
                    "Name": cap.name,
                    "SemanticId": cap.semantic_id,
                    "Resources": cap.resources,
                }
                for cap in pipeline_result.capabilities
            ],
            run_id=effective_run_id,
            run_metrics=run_metrics,
        )

class ProductionPlannerRuntime:
    """Runtime host that exposes the production planner service over MQTT."""

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.aas_client = AASClient(config.aas_server_url, config.aas_registry_url)
        self.planner_service: Optional[PlannerService] = None

        self.plan_endpoint = ResponseAsync(
            f"{config.base_topic}/DATA/Plan",
            f"{config.base_topic}/CMD/Plan",
            "./MQTTSchemas/planningResponse.schema.json",
            "./MQTTSchemas/planningCommand.schema.json",
            2,
            self._planning_callback,
        )

        self.proxy = Proxy(
            config.broker_address,
            config.broker_port,
            "ProductionPlanner",
            [self.plan_endpoint],
        )

        self.state_machine = PackMLStateMachine(
            config.base_topic,
            self.proxy,
            None,
            config_path="productionPlanner.yaml",
            enable_occupation=False,
            auto_execute=True,
        )
        self.state_machine.failureChance = 0
        self.proxy.on_ready(self._on_mqtt_ready)

    def _initialize_planner_service(self) -> None:
        planner_input_mode = os.getenv("PLANNER_INPUT_MODE", "aas")
        kg_query_endpoint = os.getenv("PLANNER_KG_QUERY_ENDPOINT", "http://kg-fuseki:3030/kg/sparql")
        kg_abox_graph = os.getenv("PLANNER_KG_ABOX_GRAPH", os.getenv("KG_ABOX_GRAPH", "urn:kg:abox"))
        kg_tbox_graph = os.getenv("PLANNER_KG_TBOX_GRAPH", os.getenv("KG_TBOX_GRAPH", "urn:kg:tbox"))
        kg_query_timeout_seconds = float(os.getenv("PLANNER_KG_QUERY_TIMEOUT_SECONDS", "10"))
        kg_capability_matching_enabled = _parse_bool_env(
            os.getenv("PLANNER_KG_CAPABILITY_MATCHING_ENABLED", "true")
        )

        shacl_query_endpoint = os.getenv("PLANNER_SHACL_QUERY_ENDPOINT", "http://kg-fuseki:3030/kg/sparql")
        shacl_abox_graph = os.getenv("PLANNER_SHACL_ABOX_GRAPH", os.getenv("KG_ABOX_GRAPH", "urn:kg:abox"))
        shacl_tbox_graph = os.getenv("PLANNER_SHACL_TBOX_GRAPH", os.getenv("KG_TBOX_GRAPH", "urn:kg:tbox"))
        shacl_shapes_graph = os.getenv(
            "PLANNER_SHACL_SHAPES_GRAPH",
            os.getenv("KG_SHACL_GRAPH", "urn:kg:shacl"),
        )
        shacl_gate_timeout_seconds = float(os.getenv("PLANNER_SHACL_TIMEOUT_SECONDS", "20"))
        shacl_gate_enabled = _resolve_shacl_gate_enabled(
            gate_env=os.getenv("PLANNER_SHACL_GATE_ENABLED", "auto"),
            query_endpoint=shacl_query_endpoint,
            shacl_graph=shacl_shapes_graph,
            timeout_seconds=min(shacl_gate_timeout_seconds, 3.0),
        )

        service_config = PlannerConfig(
            registration_topic=self.config.registration_topic,
            process_aas_output_dir="./AASDescriptions/Process/configs",
            bt_output_dir="./BTDescriptions",
            metrics_dir=env_metrics_dir(),
            metrics_topic_prefix=env_metrics_topic_prefix(),
            save_intermediate_files=True,
            planning_timeout_seconds=float(os.getenv("PLANNING_TIMEOUT_SECONDS", "30")),
            strict_semantic_solve=_parse_bool_env(os.getenv("STRICT_SEMANTIC_SOLVE", "true")),
            input_mode=planner_input_mode,
            kg_query_endpoint=kg_query_endpoint,
            kg_abox_graph=kg_abox_graph,
            kg_tbox_graph=kg_tbox_graph,
            kg_query_timeout_seconds=kg_query_timeout_seconds,
            kg_capability_matching_enabled=kg_capability_matching_enabled,
            shacl_gate_enabled=shacl_gate_enabled,
            shacl_query_endpoint=shacl_query_endpoint,
            shacl_abox_graph=shacl_abox_graph,
            shacl_tbox_graph=shacl_tbox_graph,
            shacl_shapes_graph=shacl_shapes_graph,
            shacl_gate_timeout_seconds=shacl_gate_timeout_seconds,
            shacl_gate_inference=os.getenv("PLANNER_SHACL_INFERENCE", "rdfs"),
        )

        self.planner_service = PlannerService(
            aas_client=self.aas_client,
            mqtt_client=self.proxy,
            config=service_config,
        )

    def _planning_process(
        self,
        duration: float = 0.0,
        asset_ids: Optional[List[str]] = None,
        order_aas_id: Optional[str] = None,
        run_id: Optional[str] = None,
        product_instance_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        del duration

        if not self.planner_service:
            logger.error("Planner service not initialized")
            return {
                "State": "FAILURE",
                "ErrorMessage": "Planner service not initialized",
            }

        if not asset_ids or not order_aas_id:
            logger.error("Missing required parameters: asset_ids and order_aas_id")
            return {
                "State": "FAILURE",
                "OrderAASId": order_aas_id,
                "ErrorMessage": "Missing required parameters: Assets and Order",
            }

        try:
            logger.info("Starting planning process for product: %s", order_aas_id)
            logger.info("Available assets: %s", asset_ids)

            result = self.planner_service.plan_and_register(
                asset_ids=asset_ids,
                order_aas_id=order_aas_id,
                run_id=run_id,
                requested_product_instances=product_instance_count,
            )

            if result.success:
                logger.info("Planning complete. Process AAS: %s", result.process_aas_id)
            else:
                logger.warning("Planning failed: %s", result.error_message)

            return result.to_response_dict()

        except Exception as exc:
            logger.exception("Error in planning process: %s", exc)
            return {
                "State": "FAILURE",
                "OrderAASId": order_aas_id,
                "ErrorMessage": f"Unexpected error during planning: {exc}",
            }

    def _planning_callback(self, topic, client, message, properties) -> None:
        del topic, client, properties

        try:
            request_uuid = message.get("Uuid", "no-uuid") if isinstance(message, dict) else "no-uuid"
            logger.info("[%s] Received planning command: %s", request_uuid, json.dumps(message, indent=2))

            asset_ids = None
            order_aas_id = None
            run_id = request_uuid
            product_instance_count = None
            if isinstance(message, dict):
                asset_ids = message.get("Assets") or message.get("assetIds")
                order_aas_id = message.get("Order") or message.get("OrderAASId")
                run_id = message.get("RunId") or request_uuid
                maybe_count = message.get("ProductInstanceCount")
                if maybe_count is None:
                    maybe_count = message.get("ProductInstances")
                if maybe_count is not None:
                    try:
                        product_instance_count = int(maybe_count)
                    except (TypeError, ValueError):
                        logger.warning("Ignoring non-integer ProductInstanceCount=%r", maybe_count)

            if not asset_ids or not order_aas_id:
                logger.error("Invalid planning command: missing Assets or Order")
                return

            self.state_machine.execute_command(
                message,
                self.plan_endpoint,
                self._planning_process,
                0.0,
                asset_ids,
                order_aas_id,
                run_id,
                product_instance_count,
            )

        except Exception as exc:
            logger.exception("Error in planning callback: %s", exc)

    def _on_mqtt_ready(self) -> None:
        self._initialize_planner_service()
        self.state_machine.register_asset()
        logger.info("Production Planner service ready")

    def run(self) -> None:
        self.proxy.loop_forever()


def config_from_env() -> RuntimeConfig:
    """Build runtime config from environment variables."""
    return RuntimeConfig(
        broker_address=os.getenv("MQTT_BROKER", "hivemq-broker"),
        broker_port=int(os.getenv("MQTT_PORT", "1883")),
        base_topic=os.getenv("PRODUCTION_PLANNER_TOPIC", "NN/Nybrovej/InnoLab/ProductionPlanner"),
        aas_server_url=os.getenv("AAS_SERVER_URL", "http://aas-env:8081"),
        aas_registry_url=os.getenv("AAS_REGISTRY_URL", "http://aas-registry:8080"),
        registration_topic=os.getenv("REGISTRATION_TOPIC", "NN/Nybrovej/InnoLab/Registration/Config"),
    )


def main() -> None:
    runtime = ProductionPlannerRuntime(config_from_env())
    runtime.run()


if __name__ == "__main__":
    main()
