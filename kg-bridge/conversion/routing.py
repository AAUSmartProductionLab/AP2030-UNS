from __future__ import annotations

import logging
from typing import Any

from .dispatcher import event_to_sparql
from .events import parse_event


class EventRouter:
    def __init__(
        self,
        aas_graph: str,
        kg_base_ns: str,
        id_strategy: str = "url-encode",
        enable_projection: bool = True,
    ) -> None:
        self._aas_graph = aas_graph
        self._kg_base_ns = kg_base_ns
        self._id_strategy = id_strategy
        self._enable_projection = enable_projection
        self._logger = logging.getLogger("kg-bridge.router")

    def route(self, raw_event: dict[str, Any], topic: str) -> list[str]:
        if not isinstance(raw_event, dict):
            raise ValueError("Kafka event must be a JSON object")

        payload = raw_event.get("event")
        if not isinstance(payload, dict):
            payload = raw_event

        event = parse_event(payload, topic)
        self._logger.info("Routed %s event type=%s id=%s", topic, event.type.value if hasattr(event, 'type') else '?', getattr(event, 'id', '?'))
        statements = event_to_sparql(
            event=event,
            base_uri=self._kg_base_ns,
            graph_iri=self._aas_graph,
            id_strategy=self._id_strategy,
        )
        self._logger.info("Routed %s event type=%s: produced %d SPARQL statement(s)", topic, getattr(event, 'type', '?'), len(statements))
        return statements
