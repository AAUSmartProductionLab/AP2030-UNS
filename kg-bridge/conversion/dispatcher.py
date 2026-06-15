from __future__ import annotations

from typing import Any

import rdflib

from .events import AasEvent, AasEventType, SubmodelEvent, SubmodelEventType
from .projection import projection_statements_for_event


def event_to_sparql(
    event: AasEvent | SubmodelEvent,
    base_uri: str,
    graph_iri: str | None = None,
    id_strategy: str = "url-encode",
) -> list[str]:
    """Convert a typed Kafka event to SPARQL UPDATE statements.

    Delegates entirely to the compact projection layer. The legacy full-mirror
    path (build_upsert / enable_projection) has been removed — all event types
    are handled by projection_statements_for_event.
    """
    return list(
        projection_statements_for_event(
            event=event,
            base_uri=base_uri,
            graph_iri=graph_iri,
            id_strategy=id_strategy,
        )
    )
