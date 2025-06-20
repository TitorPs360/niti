#!/bin/bash

echo "🧹 Cleaning up Detective Mystery Game..."

# Use docker compose or docker-compose
COMPOSE_CMD="docker compose"
if ! docker compose version > /dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
fi

# Stop and remove containers
$COMPOSE_CMD down -v

# Remove generated data
echo "🗑️ Removing generated game data..."
rm -rf game_data/* assets/*

echo "✅ Cleanup complete!"