from MQTT_classes import Proxy, ResponseAsync
import time
from PackMLSimulator import PackMLStateMachine


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
        duration = message.get("duration", 2.0)
        
        state_machine = PackMLStateMachine(topic, client, properties)
        state_machine.CommandUuid = message.get("CommandUuid")
        state_machine.run_state_machine(stopper_process, max_duration=duration, duration=duration)
    except Exception as e:
        print(f"Error in dispense_callback: {e}")


def main():
    """Main entry point for the filling proxy"""
    response_async = ResponseAsync(
        BASE_TOPIC, 
        "schemas/state.schema.json", 
        "schemas/stopper.schema.json", 
        2, 
        stopper_callback
    )
    
    fillProxy = Proxy(
        BROKER_ADDRESS, 
        BROKER_PORT,
        "FillingProxy", 
        [response_async]
    )
    
    fillProxy.loop_forever()


if __name__ == "__main__":
    main()
