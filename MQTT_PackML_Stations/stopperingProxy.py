from MQTT_classes import Proxy, ResponseAsync
import time
from PackMLSimulator import queue_command


BROKER_ADDRESS = "192.168.0.104"
BROKER_PORT = 1883
BASE_TOPIC = "NN/Nybrovej/InnoLab/Stoppering"


def stopper_process(duration=2.0, state_machine=None):
    """Simulate dispensing process with small increments for continuous progress updates"""
    step_size = 0.1  # Update every 100ms
    steps = int(duration / step_size)
    
    for i in range(steps):
        time.sleep(step_size)
        if state_machine and state_machine.total_duration:
            state_machine.elapsed_time = (i+1) * step_size

    remaining = duration - (steps * step_size)
    if remaining > 0:
        time.sleep(remaining)
        if state_machine and state_machine.total_duration:
            state_machine.elapsed_time = duration
    
    return {"dispensed": True}



def stopper_callback(topic, client, message, properties):
    """Callback handler for stopper commands"""
    try:
        # Make sure duration is properly set
        duration = message.get("duration", 2.0)
        
        # Create a copy of the message to modify
        message_copy = message.copy() if isinstance(message, dict) else {}
        
        # Ensure max_duration is set in the message
        if "max_duration" not in message_copy:
            message_copy["max_duration"] = duration
        queue_command((topic, client, message_copy, properties, stopper_process))
    except Exception as e:
        print(f"Error in stopper_callback: {e}")


def main():
    """Main entry point for the filling proxy"""
    response_async = ResponseAsync(
        BASE_TOPIC+"/DATA/State", 
        BASE_TOPIC+"/CMD/Stopper",
        "schemas/state.schema.json", 
        "schemas/command.schema.json", 
        0, 
        stopper_callback
    )
    
    stopperProxy = Proxy(
        BROKER_ADDRESS, 
        BROKER_PORT,
        "StopperingProxy", 
        [response_async]
    )
    
    stopperProxy.loop_forever()


if __name__ == "__main__":
    main()
