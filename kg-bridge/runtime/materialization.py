from __future__ import annotations

import logging
from pathlib import Path

import rdflib

from runtime.fuseki_client import SparqlClient


class MaterializationRunner:
    def __init__(
        self,
        rules_dir: str | None,
        enabled: bool = True,
        graph_iri: str | None = None,
        abox_graph_iri: str | None = None,
        tbox_graph_iri: str | None = None,
        shacl_graph_iri: str | None = None,
        disabled_rule_prefixes: tuple[str, ...] = (),
    ) -> None:
        self._logger = logging.getLogger("kg-bridge.materialization")
        self._rules: list[tuple[str, str]] = []
        self._template_values: dict[str, str] = {}

        # Keep backward compatibility with legacy callers that pass graph_iri.
        resolved_abox_graph = abox_graph_iri or graph_iri

        if graph_iri:
            self._template_values["{{AAS_GRAPH}}"] = graph_iri
            self._template_values["{{AAS_GRAPH_N3}}"] = rdflib.URIRef(graph_iri).n3()

        if resolved_abox_graph:
            self._template_values["{{ABOX_GRAPH}}"] = resolved_abox_graph
            self._template_values["{{ABOX_GRAPH_N3}}"] = rdflib.URIRef(resolved_abox_graph).n3()

            # Preserve existing templates if only ABOX_GRAPH is configured.
            if "{{AAS_GRAPH}}" not in self._template_values:
                self._template_values["{{AAS_GRAPH}}"] = resolved_abox_graph
                self._template_values["{{AAS_GRAPH_N3}}"] = rdflib.URIRef(resolved_abox_graph).n3()

        if tbox_graph_iri:
            self._template_values["{{TBOX_GRAPH}}"] = tbox_graph_iri
            self._template_values["{{TBOX_GRAPH_N3}}"] = rdflib.URIRef(tbox_graph_iri).n3()

        if shacl_graph_iri:
            self._template_values["{{SHACL_GRAPH}}"] = shacl_graph_iri
            self._template_values["{{SHACL_GRAPH_N3}}"] = rdflib.URIRef(shacl_graph_iri).n3()

        if not enabled:
            self._logger.info("Materialization disabled")
            return

        if not rules_dir:
            self._logger.info("No materialization rules directory configured")
            return

        directory = Path(rules_dir)
        if not directory.exists() or not directory.is_dir():
            self._logger.warning("Materialization rules directory does not exist: %s", rules_dir)
            return

        for file_path in sorted(directory.glob("*.rq")):
            if disabled_rule_prefixes and file_path.name.startswith(disabled_rule_prefixes):
                self._logger.info("Skipping disabled materialization rule: %s", file_path.name)
                continue

            query = file_path.read_text(encoding="utf-8").strip()
            if not query:
                continue

            rendered_query = query
            for token, replacement in self._template_values.items():
                rendered_query = rendered_query.replace(token, replacement)

            if "{{" in rendered_query and "}}" in rendered_query:
                self._logger.warning("Skipping materialization rule with unresolved template tokens: %s", file_path)
                continue

            self._rules.append((str(file_path), rendered_query))

        self._logger.info("Loaded %d materialization rule file(s) from %s", len(self._rules), rules_dir)

    @property
    def enabled(self) -> bool:
        return bool(self._rules)

    def apply(self, sparql_client: SparqlClient) -> None:
        for path, query in self._rules:
            self._logger.info("Applying materialization rule: %s", path)
            # Log the full query (it's a SPARQL UPDATE, we need to see all parts)
            lines = query.split('\n')
            self._logger.info("Rendered query (%d lines):", len(lines))
            for i, line in enumerate(lines[:60]):
                self._logger.info("  L%03d: %s", i, line)
            if len(lines) > 60:
                self._logger.info("  ... (%d more lines)", len(lines) - 60)
            try:
                sparql_client.update(query)
                self._logger.info("Materialization rule succeeded: %s", path)
            except Exception as exc:
                self._logger.error("Materialization rule FAILED: %s — %s", path, exc)
