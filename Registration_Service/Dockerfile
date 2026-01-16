FROM python:3.11-slim

# Install Docker client (for restarting containers)
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

# Create mount points for databridge and operation-delegation configs
RUN mkdir -p /databridge
RUN mkdir -p /operation-delegation/config

# Note: AASDescriptions needs to be mounted or copied separately
# when building from project root context, or mount at runtime
# The AAS generator path can be configured via environment

ENV PYTHONUNBUFFERED=1

# Default command uses the new unified service
CMD ["python", "unified-registration-service.py", "listen", \
     "--mqtt-broker", "192.168.0.104", \
     "--mqtt-port", "1883", \
     "--databridge-name", "databridge"]
