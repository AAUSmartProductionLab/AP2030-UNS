from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from runtime.kafka_consumer import KafkaEventConsumer
from conversion.routing import EventRouter
from runtime.fuseki_client import SparqlClient
from runtime.materialization import MaterializationRunner


@dataclass(frozen=True)
class Settings:
    kafka_bootstrap: str
    kafka_topic_pattern: str
    kafka_consumer_group: str
    kafka_auto_offset_reset: str
    fuseki_update_url: str
    fuseki_query_url: str
    fuseki_user: str | None
    fuseki_password: str | None
    abox_graph: str
    tbox_graph: str
    shacl_graph: str
    kg_base_ns: str
    aas_id_strategy: str
    log_level: str
    enable_projection: bool
    materialization_rules_dir: str | None
    enable_materialization: bool


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    return Settings(
        kafka_bootstrap=os.getenv("KAFKA_BOOTSTRAP", "kafka:9092"),
        kafka_topic_pattern=os.getenv("KAFKA_TOPIC_PATTERN", "(aas-events|submodel-events)"),
        kafka_consumer_group=os.getenv("KAFKA_CONSUMER_GROUP", "kg-bridge"),
        kafka_auto_offset_reset=os.getenv("KAFKA_AUTO_OFFSET_RESET", "earliest"),
        fuseki_update_url=os.getenv("FUSEKI_UPDATE_URL", "http://kg-fuseki:3030/kg/update"),
        fuseki_query_url=os.getenv("FUSEKI_QUERY_URL", "http://kg-fuseki:3030/kg/sparql"),
        fuseki_user=os.getenv("FUSEKI_USER", "admin"),
        fuseki_password=os.getenv("FUSEKI_PASSWORD", "admin"),
        abox_graph=os.getenv("KG_ABOX_GRAPH", os.getenv("AAS_GRAPH", "urn:kg:abox")),
        tbox_graph=os.getenv("KG_TBOX_GRAPH", "urn:kg:tbox"),
        shacl_graph=os.getenv("KG_SHACL_GRAPH", "urn:kg:shacl"),
        kg_base_ns=os.getenv("KG_BASE_NS", os.getenv("AAS_BASE_URI", "urn:kg:aas:")),
        aas_id_strategy=os.getenv("AAS_ID_STRATEGY", "url-encode"),
        enable_projection=_as_bool(os.getenv("KG_ENABLE_ARSO_APEX_PROJECTION", "true"), default=True),
        materialization_rules_dir=os.getenv("KG_MATERIALIZATION_RULES_DIR", "/app/sparql/materialization"),
        enable_materialization=_as_bool(os.getenv("KG_ENABLE_MATERIALIZATION", "true"), default=True),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )



def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )



def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)

    logger = logging.getLogger("kg-bridge")
    logger.info("Starting kg-bridge consumer")
    logger.info("Kafka bootstrap=%s topic_pattern=%s", settings.kafka_bootstrap, settings.kafka_topic_pattern)
    logger.info(
        "Named graphs: abox=%s tbox=%s shacl=%s",
        settings.abox_graph,
        settings.tbox_graph,
        settings.shacl_graph,
    )

    sparql_client = SparqlClient(
        update_url=settings.fuseki_update_url,
        query_url=settings.fuseki_query_url,
        username=settings.fuseki_user,
        password=settings.fuseki_password,
    )
    event_router = EventRouter(
        aas_graph=settings.abox_graph,
        kg_base_ns=settings.kg_base_ns,
        id_strategy=settings.aas_id_strategy,
        enable_projection=settings.enable_projection,
    )

    materialization_runner = MaterializationRunner(
        rules_dir=settings.materialization_rules_dir,
        enabled=settings.enable_materialization,
        abox_graph_iri=settings.abox_graph,
        tbox_graph_iri=settings.tbox_graph,
        shacl_graph_iri=settings.shacl_graph,
    )

    consumer = KafkaEventConsumer(
        kafka_bootstrap=settings.kafka_bootstrap,
        topic_pattern=settings.kafka_topic_pattern,
        consumer_group=settings.kafka_consumer_group,
        auto_offset_reset=settings.kafka_auto_offset_reset,
        event_router=event_router,
        sparql_client=sparql_client,
        materialization_runner=materialization_runner,
    )

    consumer.run_forever()


if __name__ == "__main__":
    main()
