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
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from packml_runtime.aas_client import AASClient
from packml_runtime.mqtt import Proxy, ResponseAsync
from packml_runtime.simulator import PackMLStateMachine

from .aas_to_pddl_conversion import collect_planning_context, run_ai_planning_pipeline
from .bt_synthesis.api import generate_bt_filename, save_bt_xml
from .process_aas_generation_publishing.process_aas_generator import (
    ProcessAASConfig,
    ProcessAASGenerator,
)
from .run_metrics import (
    env_metrics_dir,
    env_metrics_topic_prefix,
    publish_stage_metrics,
    write_stage_metrics,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


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

    aas_server_url: str = "http://aas-env:8081"
    aas_registry_url: str = "http://aas-registry:8080"

    mqtt_broker: str = "hivemq-broker"
    mqtt_port: int = 1883
    registration_topic: str = "NN/Nybrovej/InnoLab/Registration/Config"

    process_aas_output_dir: str = "../AASDescriptions/Process/configs"
    bt_output_dir: str = "../BTDescriptions"
    ai_artifacts_dir: Optional[str] = None

    bt_base_url: str = "https://aausmartproductionlab.github.io/AP2030-UNS/BTDescriptions"
    planning_timeout_seconds: float = 30.0
    strict_semantic_solve: bool = True
    metrics_dir: Optional[str] = "/data/run_metrics"
    metrics_topic_prefix: Optional[str] = "NN/Nybrovej/InnoLab/Stats"

    save_intermediate_files: bool = True


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
        self.context_collector = collect_planning_context
        self.pipeline_runner = run_ai_planning_pipeline
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

        logger.info("Step 1-4: Collecting planning context from AAS models...")
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

        logger.info("Step 5: Running planning sequence...")
        try:
            pipeline_result = self._run_planning_pipeline(
                planning_sources,
                bop_config=planning_context.order_config.get("BillOfProcesses"),
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
            return PlanningResult(
                success=False,
                order_aas_id=order_aas_id,
                planner_mode=getattr(solve_result, "mode", None),
                planner_backend=getattr(solve_result, "backend_name", None),
                solver_status=getattr(solve_result, "status", None),
                planner_warnings=pipeline_result.warnings,
                planning_artifacts=pipeline_result.artifacts,
                error_message="Planning unsolved in strict mode",
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
        bt_path = os.path.join(self.config.bt_output_dir, bt_filename)

        if self.config.save_intermediate_files:
            save_bt_xml(bt_xml, bt_path)
            logger.info("Saved behavior tree to %s", bt_path)

        logger.info("Step 7: Generating Process AAS configuration...")
        process_bundle = self.process_generator.generate_process_aas_bundle(
            pipeline_result.capabilities,
            order_aas_id,
            planning_context.order_config,
            planning_context.requirements,
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

    def _run_planning_pipeline(
        self,
        planning_sources: List[Any],
        *,
        bop_config: Optional[Dict[str, Any]] = None,
    ):
        return self.pipeline_runner(
            planning_sources,
            planning_timeout_seconds=self.config.planning_timeout_seconds,
            strict_semantic_solve=self.config.strict_semantic_solve,
            bop_config=bop_config,
            artifacts_dir=self.config.ai_artifacts_dir,
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
        service_config = PlannerConfig(
            aas_server_url=self.config.aas_server_url,
            aas_registry_url=self.config.aas_registry_url,
            mqtt_broker=self.config.broker_address,
            mqtt_port=self.config.broker_port,
            registration_topic=self.config.registration_topic,
            process_aas_output_dir="./AASDescriptions/Process/configs",
            bt_output_dir="./BTDescriptions",
            metrics_dir=env_metrics_dir(),
            metrics_topic_prefix=env_metrics_topic_prefix(),
            save_intermediate_files=True,
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
            logger.error("Error in planning process: %s", exc)
            traceback.print_exc()
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
            logger.error("Error in planning callback: %s", exc)
            traceback.print_exc()

    def _on_mqtt_ready(self) -> None:
        self._initialize_planner_service()
        self.state_machine.register_asset()
        logger.info("Production Planner service ready")

    def run(self) -> None:
        self.proxy.loop_forever()


def create_planner_from_env() -> PlannerService:
    """Create PlannerService with configuration from environment variables."""
    aas_client = AASClient(
        os.getenv("AAS_SERVER_URL", "http://aas-env:8081"),
        os.getenv("AAS_REGISTRY_URL", "http://aas-registry:8080"),
    )
    config = PlannerConfig(
        aas_server_url=os.getenv("AAS_SERVER_URL", "http://aas-env:8081"),
        aas_registry_url=os.getenv("AAS_REGISTRY_URL", "http://aas-registry:8080"),
        mqtt_broker=os.getenv("MQTT_BROKER", "hivemq-broker"),
        mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
        planning_timeout_seconds=float(os.getenv("PLANNING_TIMEOUT_SECONDS", "30")),
        strict_semantic_solve=os.getenv("STRICT_SEMANTIC_SOLVE", "true").lower() in {"1", "true", "yes"},
        ai_artifacts_dir=os.getenv("AI_ARTIFACTS_DIR") or None,
        metrics_dir=env_metrics_dir(),
        metrics_topic_prefix=env_metrics_topic_prefix(),
    )
    return PlannerService(aas_client, config=config)


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
