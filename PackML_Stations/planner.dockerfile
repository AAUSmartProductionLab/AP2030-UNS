FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies first (changes rarely)
RUN apt-get update && apt-get install -y ffmpeg libsm6 libxext6 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies (changes occasionally)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Define entrypoint with a default command that can be overridden
ENTRYPOINT ["python"]