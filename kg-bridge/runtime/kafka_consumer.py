from __future__ import annotations

import json
import logging
from typing import Any

from confluent_kafka import Consumer, KafkaError
from pydantic import ValidationError

from conversion.routing import EventRouter
from runtime.fuseki_client import SparqlClient
from runtime.materialization import MaterializationRunner


class KafkaEventConsumer:
    def __init__(
        self,
        kafka_bootstrap: str,
        topic_pattern: str,
        consumer_group: str,
        auto_offset_reset: str,
        event_router: EventRouter,
        sparql_client: SparqlClient,
        materialization_runner: MaterializationRunner | None = None,
    ) -> None:
        self._logger = logging.getLogger("kg-bridge.consumer")
        self._topic_pattern = topic_pattern
        self._event_router = event_router
        self._sparql_client = sparql_client
        self._materialization_runner = materialization_runner
        self._running = True

        config = {
            "bootstrap.servers": kafka_bootstrap,
            "group.id": consumer_group,
            "auto.offset.reset": auto_offset_reset,
            "enable.auto.commit": False,
        }
        self._consumer = Consumer(config)

    def run_forever(self) -> None:
        subscription = self._topic_pattern
        if not subscription.startswith("^"):
            subscription = f"^{subscription}$"

        self._consumer.subscribe([subscription])
        self._logger.info("Subscribed to Kafka topic regex: %s", subscription)

        try:
            while self._running:
                msg = self._consumer.poll(1.0)
                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        self._logger.debug("Reached partition EOF for %s", msg.topic())
                        continue

                    self._logger.error("Kafka error: %s", msg.error())
                    continue

                payload = msg.value()
                if payload is None:
                    self._logger.warning("Received tombstone event on %s", msg.topic())
                    self._consumer.commit(message=msg, asynchronous=False)
                    continue

                try:
                    decoded = json.loads(payload.decode("utf-8"))
                except Exception:
                    self._logger.exception("Skipping non-JSON Kafka message on topic=%s", msg.topic())
                    self._consumer.commit(message=msg, asynchronous=False)
                    continue

                try:
                    statements = self._event_router.route(decoded, msg.topic())
                except ValidationError as exc:
                    event_payload = decoded.get("event") if isinstance(decoded.get("event"), dict) else decoded
                    event_type = event_payload.get("type") if isinstance(event_payload, dict) else None
                    event_id = event_payload.get("id") if isinstance(event_payload, dict) else None
                    self._logger.warning(
                        "Skipping invalid Kafka event on topic=%s type=%s id=%s validation_errors=%s",
                        msg.topic(),
                        event_type,
                        event_id,
                        exc.errors(),
                    )
                    self._consumer.commit(message=msg, asynchronous=False)
                    continue
                except Exception:
                    self._logger.exception("Skipping unroutable Kafka event on topic=%s", msg.topic())
                    self._consumer.commit(message=msg, asynchronous=False)
                    continue

                if not statements:
                    self._logger.debug("No SPARQL statements emitted for topic=%s", msg.topic())
                    self._consumer.commit(message=msg, asynchronous=False)
                    continue

                try:
                    for statement in statements:
                        self._sparql_client.update(statement)

                    if self._materialization_runner and self._materialization_runner.enabled:
                        self._materialization_runner.apply(self._sparql_client)
                except Exception:
                    # Keep offset uncommitted so transient SPARQL failures are retried.
                    self._logger.exception("SPARQL UPDATE failed for topic=%s offset=%s", msg.topic(), msg.offset())
                    continue

                self._consumer.commit(message=msg, asynchronous=False)
                self._logger.debug("Committed offset for topic=%s partition=%s offset=%s", msg.topic(), msg.partition(), msg.offset())

        except KeyboardInterrupt:
            self._logger.info("Keyboard interrupt received, shutting down consumer")
        finally:
            self._consumer.close()
            self._logger.info("Kafka consumer closed")
