FROM python:3.11-slim

# Install Docker client (for restarting databridge container)
# and git (if needed for pip install git+...)
RUN apt-get update && apt-get install -y \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create the databridge directory mount point (this is where we expect the volume)
RUN mkdir -p /databridge

# Default command matches the user's listen command
CMD ["python", "aas-registration-service.py", "listen", \
     "--mqtt-broker", "192.168.0.104", \
     "--mqtt-port", "1883", \
     "--databridge-name", "databridge"]
