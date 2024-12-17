from opcua import Server
from datetime import datetime
import random
import time

# Configure OPC-UA Server
server = Server()
server.set_endpoint("opc.tcp://0.0.0.0:4840/freeopcua/server/")  # Set endpoint URL
server.set_server_name("Python OPC-UA Test Server")

# Set namespaces
uri = "http://example.org/opcua"
idx = server.register_namespace(uri)

# Create objects folder and add variables
objects = server.nodes.objects

# Temperature variable
temperature = objects.add_variable(idx, "Temperature", 25.0)
temperature.set_writable()  # Allow writes from clients

# Pressure variable
pressure = objects.add_variable(idx, "Pressure", 1.0)
pressure.set_writable()  # Allow writes from clients

# A method for simulation
def randomize_variables(parent):
    temperature.set_value(random.uniform(20.0, 30.0))
    pressure.set_value(random.uniform(0.5, 2.0))

objects.add_method(idx, "RandomizeVariables", randomize_variables, [], [])

# Start the server
if __name__ == "__main__":
    # Initialize the server
    server.start()
    print("OPC-UA Server started at opc.tcp://0.0.0.0:4840/freeopcua/server/")
    try:
        while True:
            # Update the variable values
            temperature.set_value(temperature.get_value() + random.uniform(-0.1, 0.1))
            pressure.set_value(pressure.get_value() + random.uniform(-0.05, 0.05))
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down OPC-UA Server...")
        server.stop()
