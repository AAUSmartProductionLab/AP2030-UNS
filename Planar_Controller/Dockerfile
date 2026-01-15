# Use python 3.9 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# python3-tk is required for matplotlib's TkAgg backend
# mono-complete is required for pythonnet/pmclib to interact with .NET DLLs on Linux
# libpython3-dev helps with header/linking issues in slim images
RUN apt-get update && apt-get install -y \
    python3-tk \
    mono-complete \
    libpython3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# --- PMCLIB Handling ---
# Copy dependencies folder (containing the wheel)
COPY dependencies/ ./dependencies/
# Install pmclib from the local wheel file
RUN pip install --no-cache-dir dependencies/pmclib-117.9.1-py3-none-any.whl

# Copy application source code (including library/ and xbot_planner.py)
COPY . .

# Make entrypoint script executable
RUN chmod +x entrypoint.sh

# Set environment variable to ensure output is flushed immediately
ENV PYTHONUNBUFFERED=1
# Add the library folder to PYTHONPATH so imports in xbot_planner.py work as-is
ENV PYTHONPATH="${PYTHONPATH}:/app/library"

RUN chmod +x entrypoint.sh

# Default command runs the entrypoint script
# Use "--no-viz" by default to avoid display errors in headless environments
ENTRYPOINT ["./entrypoint.sh"]
CMD ["--no-viz"]
