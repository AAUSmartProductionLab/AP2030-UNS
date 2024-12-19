from opcua import Server
from opcua import ua
from datetime import datetime
import random
import time

# Configure OPC-UA Server
server = Server()
server.set_endpoint("opc.tcp://172.20.66.217:4840/freeopcua/server/")  # Set endpoint URL
server.set_server_name("Python OPC-UA Test Server")

# Set namespaces
uri = "http://example.org/opcua"
idx = server.register_namespace(uri)

# Create objects folder and add variables
objects = server.nodes.objects

# Temperature variable
temperature = objects.add_variable(idx, "Temperature", 25.0, ua.VariantType.Double)
temperature.set_writable()  # Allow writes from clients

# Pressure variable
pressure = objects.add_variable(idx, "Pressure", 1.0, ua.VariantType.Double)
pressure.set_writable()  # Allow writes from clients

# A method for simulation
def randomize_variables(parent):
    temperature.set_value(random.uniform(20.0, 30.0))
    pressure.set_value(random.uniform(0.5, 2.0))

objects.add_method(idx, "RandomizeVariables", randomize_variables, [], [])

# Set mandatory attributes for objects and variables
temperature.set_attribute(ua.AttributeIds.DisplayName, ua.DataValue(ua.LocalizedText("Temperature")))
pressure.set_attribute(ua.AttributeIds.DisplayName, ua.DataValue(ua.LocalizedText("Pressure")))

# Start the server
if __name__ == "__main__":
    # Initialize the server
    server.start()
    print("OPC-UA Server started at opc.tcp://192.168.0.108:4840/freeopcua/server/")
    try:
        while True:
            # Update the variable values
            temperature.set_value(temperature.get_value() + random.uniform(-0.1, 0.1))
            pressure.set_value(pressure.get_value() + random.uniform(-0.05, 0.05))
            #print(f"Temperature NodeId: {temperature.nodeid}")
            #print(f"Pressure NodeId: {pressure.nodeid}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down OPC-UA Server...")
        server.stop()
