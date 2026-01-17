from MQTT_classes import Proxy, ResponseAsync
from PackMLSimulator import PackMLStateMachine
from xml.etree import ElementTree as ET
from PackML_Stations.planning_standalone import planning_process as generate_bt
from aas_client import AASClient
import traceback

BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "NN/Nybrovej/InnoLab/ProductionPlanner"
AAS_SERVER_URL = "http://192.168.0.104:8081"

# Initialize AAS client
aas_client = AASClient(AAS_SERVER_URL)


def planning_process(duration=0.0, asset_ids=None, product_aas_id=None):
    try:
        generate_bt(asset_ids=asset_ids, product_aas_id=product_aas_id)
    except Exception as e:
        print(f"Error in planning_process: {e}")
        traceback.print_exc()


def planning_callback(topic, client, message, properties):
    """Callback handler for planning commands
    
    Expected message format:
    {
        "command": "plan",
        "assetIds": ["asset_id_1", "asset_id_2", ...],
        "productAasId": "https://smartproductionlab.aau.dk/aas/ProductAAS"
    }
    """
    try:
        # Parse message to extract asset IDs and product
        asset_ids = None
        product_aas_id = None
        
        if isinstance(message, dict):
            asset_ids = message.get('assetIds')
            product_aas_id = message.get('productAasId')
        
        # Execute planning process with parameters
        state_machine.execute_command(
            message, 
            plan, 
            lambda duration: planning_process(duration, asset_ids, product_aas_id)
        )
    except Exception as e:
        print(f"Error in planning_callback: {e}")
        import traceback
        traceback.print_exc()


plan = ResponseAsync(
    BASE_TOPIC+"/DATA/Plan",
    BASE_TOPIC+"/CMD/Plan",
    "./MQTTSchemas/commandResponse.schema.json",
    "./MQTTSchemas/command.schema.json",
    2,
    planning_callback
)

productionPlanner = Proxy(
    BROKER_ADDRESS, 
    BROKER_PORT,
    "ProductionPlanner", 
    [plan]
)

state_machine = PackMLStateMachine(BASE_TOPIC, productionPlanner, None)
state_machine.failureChance=0

def main():
    """Main entry point for the production planner"""
    productionPlanner.loop_forever()


if __name__ == "__main__":
    main()
