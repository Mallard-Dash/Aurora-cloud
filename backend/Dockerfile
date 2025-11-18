FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ /app/app

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create a non-root user and pre-create data directories
RUN useradd -m -u 1000 aurora && \
    chown -R aurora:aurora /app && \
    mkdir -p /data/storage && \
    mkdir -p /data && \
    chmod -R 777 /data

# Expose port
EXPOSE 8000

# Run the application
ENTRYPOINT ["/entrypoint.sh"]
