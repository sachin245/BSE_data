#!/bin/bash
# start.sh

# Exit on error
set -e

echo "Starting BSE Scraper Backend..."

# Use the PORT environment variable provided by Railway, defaulting to 8000
PORT=${PORT:-8000}

# Run the FastAPI app using Uvicorn
# We use backend.server.main:app because the Dockerfile sets WORKDIR to /app
# and the package structure starts from the root.
exec uvicorn backend.server.main:app --host 0.0.0.0 --port "$PORT"
