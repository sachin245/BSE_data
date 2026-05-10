# Use Python base image
FROM python:3.12-slim

# Install Node.js
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy frontend and build
COPY frontend ./frontend
WORKDIR /app/frontend
RUN npm install && npm run build

# Move dist to root
WORKDIR /app
RUN mv frontend/dist ./dist

# Copy the rest of the app
COPY . .

# Expose port
EXPOSE 8000

# Start command
CMD ["sh", "start.sh"]