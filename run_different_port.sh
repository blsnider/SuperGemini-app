#!/bin/bash

echo "🔄 Starting Flask on a different port to bypass CloudWorkstations cache..."
echo ""

# Kill any existing Flask processes
pkill -f "python.*app.py" 2>/dev/null || true
sleep 2

# Use a different port
export PORT=8888
export ENVIRONMENT=development
export FLASK_ENV=development

echo "Starting Flask on port $PORT..."
echo ""
echo "================================"
echo "IMPORTANT: Access your app at:"
echo "https://8888-${HOSTNAME}"
echo ""
echo "This uses a different port to bypass CloudWorkstations caching"
echo "================================"
echo ""

python3 app.py