from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from runtime.kafka_consumer import KafkaEventConsumer
from conversion.routing import EventRouter
from runtime.fuseki_client import SparqlClient


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
    aas_graph: str
    kg_base_ns: str
    aas_id_strategy: str
    log_level: str



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
        aas_graph=os.getenv("AAS_GRAPH", "urn:kg:aas"),
        kg_base_ns=os.getenv("KG_BASE_NS", os.getenv("AAS_BASE_URI", "urn:kg:aas:")),
        aas_id_strategy=os.getenv("AAS_ID_STRATEGY", "url-encode"),
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

    sparql_client = SparqlClient(
        update_url=settings.fuseki_update_url,
        query_url=settings.fuseki_query_url,
        username=settings.fuseki_user,
        password=settings.fuseki_password,
    )
    event_router = EventRouter(
        aas_graph=settings.aas_graph,
        kg_base_ns=settings.kg_base_ns,
        id_strategy=settings.aas_id_strategy,
    )

    consumer = KafkaEventConsumer(
        kafka_bootstrap=settings.kafka_bootstrap,
        topic_pattern=settings.kafka_topic_pattern,
        consumer_group=settings.kafka_consumer_group,
        auto_offset_reset=settings.kafka_auto_offset_reset,
        event_router=event_router,
        sparql_client=sparql_client,
    )

    consumer.run_forever()


if __name__ == "__main__":
    main()
