#!/bin/sh
set -e

# Ensure /data directories exist with proper permissions
mkdir -p /data/storage
mkdir -p /data

# Fix permissions (allow rwx for everyone)
chmod -R 777 /data

# Run uvicorn
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
