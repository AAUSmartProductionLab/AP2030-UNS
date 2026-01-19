FROM python:3.11-slim

# Install Docker client (for restarting containers) and curl (for healthcheck)
RUN apt-get update && apt-get install -y \
    docker.io \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY Registration_Service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Registration Service application code
COPY Registration_Service/ .

# Remove the copied databridge directory to avoid confusion
# The actual databridge configs should be in the mounted volume at /databridge
RUN rm -rf /app/databridge

# Create mount points for databridge configs
RUN mkdir -p /databridge

# Copy MQTT schemas from project root (needed for schema-based message generation)
COPY MQTTSchemas /app/MQTTSchemas

# Note: AASDescriptions needs to be mounted or copied separately
# when building from project root context, or mount at runtime
# The AAS generator path can be configured via environment

ENV PYTHONUNBUFFERED=1

# Port for Operation Delegation HTTP API
EXPOSE 8087

# Default command runs the unified service with both:
# - MQTT registration listener
# - Operation Delegation HTTP API (on port 8087)
# Override via docker-compose.yml or docker run -e
CMD ["python", "unified-registration-service.py", "listen", \
     "--databridge-name", "databridge", \
     "--delegation-port", "8087"]
