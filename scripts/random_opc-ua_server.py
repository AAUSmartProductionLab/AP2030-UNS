from opcua import Server
import random
import time

# Create an instance of the OPC-UA server
server = Server()

# Set the endpoint for the server
server.set_endpoint("opc.tcp://0.0.0.0:4840/freeopcua/server/") # opc.tcp://192.168.0.108:4840/freeopcua/server/Objects/MyObject/RandomValue1

# Register a new namespace
uri = "http://examples.freeopcua.github.io"
idx = server.register_namespace(uri)
print(idx)
# Get the Objects node
objects = server.get_objects_node()

# Add a new object to the address space
myobj = objects.add_object(idx, "MyObject")

# Add two variables to the object with random values
var1 = myobj.add_variable(idx, "RandomValue1", 0)
var2 = myobj.add_variable(idx, "RandomValue2", 0)

# Set the variables to be writable by clients
var1.set_writable()
var2.set_writable()

# Start the server
server.start()
print("Server started at opc.tcp://0.0.0.0:4840/freeopcua/server/")

try:
    while True:
        # Update the variables with random values
        var1.set_value(random.randint(0, 100))
        var2.set_value(random.randint(0, 100))
        time.sleep(5)
except KeyboardInterrupt:
    # Stop the server when interrupted
    server.stop()
    print("Server stopped")