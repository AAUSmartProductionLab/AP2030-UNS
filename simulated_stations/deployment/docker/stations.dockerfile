# python 3.12: asyncua 2.x (OPC UA binding) requires python>=3.10
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies (asyncua pinned per simulated_stations/requirements.txt).
# The stations register the static exports in simulated_stations/resources.
RUN pip install --no-cache-dir paho-mqtt jsonschema numpy opencv-python asyncua==2.0.1
RUN apt-get update && apt-get install ffmpeg libsm6 libxext6  -y

# Define entrypoint with a default command that can be overridden
ENTRYPOINT ["python"]