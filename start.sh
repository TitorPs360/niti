#!/bin/bash

echo "🕵️ Starting niti - Detective Mystery Game..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if Docker Compose is available
if ! command -v docker-compose > /dev/null 2>&1 && ! docker compose version > /dev/null 2>&1; then
    echo "❌ Docker Compose is not available. Please install Docker Compose."
    exit 1
fi

# Use docker compose or docker-compose
COMPOSE_CMD="docker compose"
if ! docker compose version > /dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
fi

echo "🏗️ Building and starting services..."
$COMPOSE_CMD up --build -d

echo "⏳ Waiting for services to start..."
sleep 10

echo "🔍 Checking service health..."
echo "Frontend: http://localhost:3000"
echo "Backend: http://localhost:8001/docs"
echo "Flux API: http://localhost:8000/docs"
echo "Ollama: http://localhost:11434"

echo ""
echo "🎮 Game is starting up! Open http://localhost:3000 in your browser"
echo "📝 To view logs: $COMPOSE_CMD logs -f"
echo "🛑 To stop: $COMPOSE_CMD down"