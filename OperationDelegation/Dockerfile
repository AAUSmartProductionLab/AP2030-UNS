FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY operation_delegation_service.py .
COPY config/ ./config/

# Environment variables with defaults
ENV MQTT_BROKER=hivemq-broker
ENV MQTT_PORT=1883
ENV PORT=8087
ENV OPERATION_TIMEOUT=30
ENV TOPIC_CONFIG_PATH=/app/config/topics.json

# Expose the service port
EXPOSE 8087

# Health check
HEALTHCHECK --interval=30s --timeout=3s --retries=3 --start-period=10s \
    CMD curl --fail http://localhost:8087/health || exit 1

# Run the service
CMD ["python", "operation_delegation_service.py"]
