#!/usr/bin/env python3
"""
Production planner PackML/MQTT runtime entrypoint.

This module contains the service runtime previously hosted directly in
`productionPlanner.py`.
"""

import json
import logging
import os
import traceback

from packml_runtime.aas_client import AASClient
from packml_runtime.mqtt import Proxy, ResponseAsync
from packml_runtime.simulator import PackMLStateMachine

from ..core.planner_service import PlannerConfig, PlannerService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Environment configuration
BROKER_ADDRESS = os.getenv("MQTT_BROKER", "hivemq-broker")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE_TOPIC = "NN/Nybrovej/InnoLab/ProductionPlanner"
AAS_SERVER_URL = os.getenv("AAS_SERVER_URL", "http://aas-env:8081")
AAS_REGISTRY_URL = os.getenv("AAS_REGISTRY_URL", "http://aas-registry:8080")
REGISTRATION_TOPIC = os.getenv("REGISTRATION_TOPIC", "NN/Nybrovej/InnoLab/Registration/Config")

# Initialize AAS client
aas_client = AASClient(AAS_SERVER_URL, AAS_REGISTRY_URL)

# Planner service (initialized after MQTT client is ready)
planner_service = None


def initialize_planner(mqtt_client):
    """Initialize the planner service with MQTT client."""
    global planner_service

    config = PlannerConfig(
        aas_server_url=AAS_SERVER_URL,
        aas_registry_url=AAS_REGISTRY_URL,
        mqtt_broker=BROKER_ADDRESS,
        mqtt_port=BROKER_PORT,
        registration_topic=REGISTRATION_TOPIC,
        process_aas_output_dir="./AASDescriptions/Process/configs",
        bt_output_dir="./BTDescriptions",
        save_intermediate_files=True,
    )

    planner_service = PlannerService(
        aas_client=aas_client,
        mqtt_client=mqtt_client,
        config=config,
    )

    logger.info("Planner service initialized")


def planning_process(duration=0.0, asset_ids=None, product_aas_id=None):
    """Execute planning and return a planning-response-schema payload."""
    global planner_service

    if not planner_service:
        logger.error("Planner service not initialized")
        return {
            "State": "FAILURE",
            "ErrorMessage": "Planner service not initialized",
        }

    if not asset_ids or not product_aas_id:
        logger.error("Missing required parameters: asset_ids and product_aas_id")
        return {
            "State": "FAILURE",
            "ProductAasId": product_aas_id,
            "ErrorMessage": "Missing required parameters: Assets and Product",
        }

    try:
        logger.info(f"Starting planning process for product: {product_aas_id}")
        logger.info(f"Available assets: {asset_ids}")

        result = planner_service.plan_and_register(
            asset_ids=asset_ids,
            product_aas_id=product_aas_id,
        )

        if result.success:
            logger.info(f"Planning complete! Process AAS: {result.process_aas_id}")
        else:
            logger.warning(f"Planning failed: {result.error_message}")

        return result.to_response_dict()

    except Exception as exc:
        logger.error(f"Error in planning_process: {exc}")
        traceback.print_exc()
        return {
            "State": "FAILURE",
            "ProductAasId": product_aas_id,
            "ErrorMessage": f"Unexpected error during planning: {exc}",
        }


def planning_callback(topic, client, message, properties):
    """Callback handler for planning commands."""
    try:
        request_uuid = message.get("Uuid", "no-uuid") if isinstance(message, dict) else "no-uuid"
        logger.info(f"[{request_uuid}] Received planning command: {json.dumps(message, indent=2)}")

        asset_ids = None
        product_aas_id = None

        if isinstance(message, dict):
            asset_ids = message.get("Assets")
            product_aas_id = message.get("Product")

            # Backward-compatible field names.
            if not asset_ids:
                asset_ids = message.get("assetIds")
            if not product_aas_id:
                product_aas_id = message.get("productAasId")

        if not asset_ids or not product_aas_id:
            logger.error("Invalid planning command: missing Assets or Product")
            return

        state_machine.execute_command(
            message,
            plan,
            planning_process,
            0.0,
            asset_ids,
            product_aas_id,
        )

    except Exception as exc:
        logger.error(f"Error in planning_callback: {exc}")
        traceback.print_exc()


plan = ResponseAsync(
    BASE_TOPIC + "/DATA/Plan",
    BASE_TOPIC + "/CMD/Plan",
    "./MQTTSchemas/planningResponse.schema.json",
    "./MQTTSchemas/planningCommand.schema.json",
    2,
    planning_callback,
)

productionPlanner = Proxy(
    BROKER_ADDRESS,
    BROKER_PORT,
    "ProductionPlanner",
    [plan],
)

state_machine = PackMLStateMachine(
    BASE_TOPIC,
    productionPlanner,
    None,
    config_path="productionPlanner.yaml",
    enable_occupation=False,
    auto_execute=True,
)
state_machine.failureChance = 0


def on_mqtt_ready():
    """Callback when MQTT connection is established."""
    initialize_planner(productionPlanner)
    state_machine.register_asset()
    logger.info("Production Planner service ready")


productionPlanner.on_ready(on_mqtt_ready)


def main():
    """Main entry point for the production planner runtime."""
    productionPlanner.loop_forever()


if __name__ == "__main__":
    main()
