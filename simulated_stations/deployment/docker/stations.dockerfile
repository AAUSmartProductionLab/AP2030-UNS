# python 3.12: asyncua 2.x (OPC UA binding) requires python>=3.10
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies (asyncua pinned per simulated_stations/requirements.txt).
# pydantic, basyx-python-sdk and requests are aas-model's: stations build the
# AAS they register from the aas-model sources mounted at /aas-model.
RUN pip install --no-cache-dir paho-mqtt jsonschema numpy opencv-python asyncua==2.0.1 \
    "pydantic>=2.6" "basyx-python-sdk>=2.0.1" "requests>=2.31"
RUN apt-get update && apt-get install ffmpeg libsm6 libxext6  -y

# Define entrypoint with a default command that can be overridden
ENTRYPOINT ["python"]