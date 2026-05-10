# --- Stage 1: Build Frontend ---
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Final Image ---
FROM python:3.12-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy python requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the built frontend from Stage 1
# backend/server/main.py expects it at "frontend/dist"
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Copy the rest of the application
COPY . .

# Ensure start.sh is executable
RUN chmod +x start.sh

# Expose the default port
EXPOSE 8000

# Start the application
CMD ["./start.sh"]