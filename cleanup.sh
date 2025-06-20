#!/bin/bash

echo "🧹 Cleaning up Detective Mystery Game..."

# Use docker compose or docker-compose
COMPOSE_CMD="docker compose"
if ! docker compose version > /dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
fi

# Stop and remove containers
echo "🛑 Stopping containers..."
$COMPOSE_CMD down -v

# Remove generated data with proper permission handling
echo "🗑️ Removing generated game data..."

# Clean game_data directory
if [ -d "game_data" ]; then
    echo "Cleaning game_data directory..."
    find game_data -type f -exec rm -f {} \; 2>/dev/null || {
        echo "Permission issue detected. Trying with elevated permissions..."
        sudo find game_data -type f -exec rm -f {} \; 2>/dev/null || {
            echo "⚠️ Could not clean game_data. You may need to manually run: sudo rm -rf game_data/*"
        }
    }
else
    echo "game_data directory does not exist, skipping..."
fi

# Clean assets directory
if [ -d "assets" ]; then
    echo "Cleaning assets directory..."
    find assets -type f -exec rm -f {} \; 2>/dev/null || {
        echo "Permission issue detected. Trying with elevated permissions..."
        sudo find assets -type f -exec rm -f {} \; 2>/dev/null || {
            echo "⚠️ Could not clean assets. You may need to manually run: sudo rm -rf assets/*"
        }
    }
else
    echo "assets directory does not exist, skipping..."
fi

echo "✅ Cleanup complete!"
echo "💡 If you encountered permission issues, you may need to run: sudo ./cleanup.sh"