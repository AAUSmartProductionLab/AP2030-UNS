#!/usr/bin/env python3
"""
Production Planner Service

MQTT-based service that:
1. Receives planning commands with asset IDs and product AAS ID
2. Matches product BillOfProcesses to resource capabilities
3. Generates behavior tree and Process AAS
4. Registers the Process AAS via MQTT to Registration Service

Message format (planningCommand schema):
{
    "Uuid": "unique-request-id",
    "Timestamp": "2026-01-20T10:00:00.000Z",
    "Assets": ["https://smartproductionlab.aau.dk/aas/aauFillingLine"],
    "Product": "https://smartproductionlab.aau.dk/aas/HgHAAS"
}
"""

import os
import json
import logging
import traceback

from MQTT_classes import Proxy, ResponseAsync, Subscriber
from PackMLSimulator import PackMLStateMachine
from aas_client import AASClient
from planning import PlannerService, PlannerConfig, PlanningResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
    """Initialize the planner service with MQTT client"""
    global planner_service
    
    config = PlannerConfig(
        aas_server_url=AAS_SERVER_URL,
        aas_registry_url=AAS_REGISTRY_URL,
        mqtt_broker=BROKER_ADDRESS,
        mqtt_port=BROKER_PORT,
        registration_topic=REGISTRATION_TOPIC,
        process_aas_output_dir="../AASDescriptions/Process/configs",
        bt_output_dir="../BTDescriptions",
        save_intermediate_files=True
    )
    
    planner_service = PlannerService(
        aas_client=aas_client,
        mqtt_client=mqtt_client,
        config=config
    )
    
    logger.info("Planner service initialized")


def planning_process(duration=0.0, asset_ids=None, product_aas_id=None):
    """
    Execute the planning process.
    
    Args:
        duration: Simulated duration (unused, for PackML compatibility)
        asset_ids: List of AAS IDs of available assets
        product_aas_id: AAS ID of the product to produce
        
    Returns:
        dict: Response conforming to planningResponse.schema.json
    """
    global planner_service
    
    if not planner_service:
        logger.error("Planner service not initialized")
        return {
            'State': 'FAILURE',
            'ErrorMessage': 'Planner service not initialized'
        }
    
    if not asset_ids or not product_aas_id:
        logger.error("Missing required parameters: asset_ids and product_aas_id")
        return {
            'State': 'FAILURE',
            'ProductAasId': product_aas_id,
            'ErrorMessage': 'Missing required parameters: Assets and Product'
        }
    
    try:
        logger.info(f"Starting planning process for product: {product_aas_id}")
        logger.info(f"Available assets: {asset_ids}")
        
        # Execute planning workflow - returns PlanningResult
        result = planner_service.plan_and_register(
            asset_ids=asset_ids,
            product_aas_id=product_aas_id
        )
        
        if result.success:
            logger.info(f"Planning complete! Process AAS: {result.process_aas_id}")
        else:
            logger.warning(f"Planning failed: {result.error_message}")
        
        # Return response conforming to planningResponse.schema.json
        return result.to_response_dict()
        
    except Exception as e:
        logger.error(f"Error in planning_process: {e}")
        traceback.print_exc()
        return {
            'State': 'FAILURE',
            'ProductAasId': product_aas_id,
            'ErrorMessage': f'Unexpected error during planning: {str(e)}'
        }


def planning_callback(topic, client, message, properties):
    """
    Callback handler for planning commands.
    
    Expected message format (planningCommand schema):
    {
        "Uuid": "unique-request-id",
        "Timestamp": "2026-01-20T10:00:00.000Z",
        "Assets": ["https://smartproductionlab.aau.dk/aas/aauFillingLine"],
        "Product": "https://smartproductionlab.aau.dk/aas/HgHAAS"
    }
    """
    try:
        logger.info(f"Received planning command: {json.dumps(message, indent=2)}")
        
        # Parse message according to planningCommand schema
        asset_ids = None
        product_aas_id = None

        if isinstance(message, dict):
            # New schema: Assets and Product
            asset_ids = message.get('Assets')
            product_aas_id = message.get('Product')
            
            # Fallback to old schema for backwards compatibility
            if not asset_ids:
                asset_ids = message.get('assetIds')
            if not product_aas_id:
                product_aas_id = message.get('productAasId')
        
        if not asset_ids or not product_aas_id:
            logger.error("Invalid planning command: missing Assets or Product")
            return

        # Execute planning process with parameters
        state_machine.execute_command(
            message,
            plan,
            lambda duration: planning_process(
                duration, asset_ids, product_aas_id
            )
        )
        
    except Exception as e:
        logger.error(f"Error in planning_callback: {e}")
        traceback.print_exc()


# MQTT topic handlers
plan = ResponseAsync(
    BASE_TOPIC + "/DATA/Plan",
    BASE_TOPIC + "/CMD/Plan",
    "./MQTTSchemas/planningResponse.schema.json",  # Extended planning response schema
    "./MQTTSchemas/planningCommand.schema.json",   # Planning command schema
    2,
    planning_callback
)

# Create MQTT proxy
productionPlanner = Proxy(
    BROKER_ADDRESS,
    BROKER_PORT,
    "ProductionPlanner",
    [plan]
)

# State machine for PackML-style operation
state_machine = PackMLStateMachine(
    BASE_TOPIC, 
    productionPlanner, 
    None, 
    config_path="productionPlanner.yaml"
)
state_machine.failureChance = 0


def on_mqtt_ready():
    """Callback when MQTT connection is established"""
    # Initialize planner with MQTT client (Proxy is the client itself)
    initialize_planner(productionPlanner)
    
    # Register asset
    state_machine.register_asset()
    
    logger.info("Production Planner service ready")


# Register callbacks
productionPlanner.on_ready(on_mqtt_ready)


def main():
    """Main entry point for the production planner"""
    productionPlanner.loop_forever()


if __name__ == "__main__":
    main()
