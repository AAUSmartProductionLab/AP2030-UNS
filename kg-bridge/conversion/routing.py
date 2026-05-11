from __future__ import annotations

import logging
from typing import Any

from .dispatcher import event_to_sparql
from .events import parse_event


class EventRouter:
    def __init__(self, aas_graph: str, kg_base_ns: str, id_strategy: str = "url-encode") -> None:
        self._aas_graph = aas_graph
        self._kg_base_ns = kg_base_ns
        self._id_strategy = id_strategy
        self._logger = logging.getLogger("kg-bridge.router")

    def route(self, raw_event: dict[str, Any], topic: str) -> list[str]:
        if not isinstance(raw_event, dict):
            raise ValueError("Kafka event must be a JSON object")

        payload = raw_event.get("event")
        if not isinstance(payload, dict):
            payload = raw_event

        meta = raw_event.get("meta") if isinstance(raw_event.get("meta"), dict) else {}
        provenance: dict[str, Any] = {}
        for key in ("sourceUrl", "registrationTime"):
            if key in meta:
                provenance[key] = meta[key]
            elif key in raw_event:
                provenance[key] = raw_event[key]

        event = parse_event(payload, topic)
        statements = event_to_sparql(
            event=event,
            base_uri=self._kg_base_ns,
            graph_iri=self._aas_graph,
            id_strategy=self._id_strategy,
            provenance=provenance or None,
        )
        self._logger.debug("Routed %s event on topic=%s to %d statement(s)", payload.get("type"), topic, len(statements))
        return statements
