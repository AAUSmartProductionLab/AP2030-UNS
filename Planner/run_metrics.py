from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional


logger = logging.getLogger(__name__)


def _safe_run_id(run_id: str) -> str:
    text = str(run_id or "run-unknown").strip()
    if not text:
        text = "run-unknown"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", text)


def write_stage_metrics(
    *,
    metrics_dir: Optional[str],
    run_id: str,
    stage: str,
    payload: dict[str, Any],
) -> Optional[str]:
    """Persist stage metrics to <metrics_dir>/<run_id>/<stage>.json."""
    if not metrics_dir:
        return None

    safe_run_id = _safe_run_id(run_id)
    safe_stage = re.sub(r"[^A-Za-z0-9_.-]", "_", str(stage or "stage"))

    try:
        output_dir = Path(metrics_dir) / safe_run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{safe_stage}.json"

        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)

        return str(output_path)
    except Exception as exc:
        logger.warning("Failed writing stage metrics for %s/%s: %s", safe_run_id, safe_stage, exc)
        return None


def publish_stage_metrics(
    *,
    mqtt_client: Any,
    topic_prefix: Optional[str],
    stage: str,
    run_id: str,
    payload: dict[str, Any],
) -> None:
    """Publish stage metrics payload on MQTT if a client is available."""
    if mqtt_client is None or not topic_prefix:
        return

    safe_run_id = _safe_run_id(run_id)
    safe_stage = re.sub(r"[^A-Za-z0-9_.-]", "_", str(stage or "stage"))
    topic = f"{topic_prefix.rstrip('/')}/{safe_stage}/{safe_run_id}"

    try:
        if hasattr(mqtt_client, "publish_message"):
            mqtt_client.publish_message(topic, payload, 1, False)
            return

        if hasattr(mqtt_client, "publish"):
            mqtt_client.publish(topic, json.dumps(payload), qos=1)
            return

        logger.debug("MQTT client does not expose publish APIs used by metrics helper")
    except Exception as exc:
        logger.warning("Failed publishing stage metrics to %s: %s", topic, exc)


def env_metrics_dir(default: str = "/data/run_metrics") -> str:
    return os.getenv("METRICS_DIR", default)


def env_metrics_topic_prefix(default: str = "NN/Nybrovej/InnoLab/Stats") -> str:
    return os.getenv("METRICS_TOPIC_PREFIX", default)
