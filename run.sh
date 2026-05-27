#!/bin/bash

# Workplan Generator - Startup Script

set -e

echo "=================================="
echo "Workplan Generator - Startup"
echo "=================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if dependencies are installed
if [ ! -f "venv/bin/uvicorn" ]; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "WARNING: .env file not found!"
    echo "Please copy .env.example to .env and configure your API keys."
    echo ""
    echo "  cp .env.example .env"
    echo "  nano .env  # Add your ANTHROPIC_API_KEY"
    echo ""
    exit 1
fi

# Check if docker-compose services are running
echo "Checking services..."
if ! docker-compose ps | grep -q "Up"; then
    echo "Starting Docker services (PostgreSQL, Redis, MinIO)..."
    docker-compose up -d
    echo "Waiting for services to be ready..."
    sleep 5
fi

echo ""
echo "✓ Virtual environment: activated"
echo "✓ Dependencies: installed"
echo "✓ Environment: configured"
echo "✓ Services: running"
echo ""
echo "Starting FastAPI server..."
echo "API will be available at: http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Run the application
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
