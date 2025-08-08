#!/bin/bash

echo "🧹 Starting fresh Flask app with cache busting..."
echo ""

# Kill any existing Flask processes
echo "1. Stopping any existing Flask processes..."
pkill -f "python.*app.py" 2>/dev/null
sleep 2

# Set environment variable to force development mode
export ENVIRONMENT=development
export FLASK_ENV=development
export FLASK_DEBUG=1
export PYTHONDONTWRITEBYTECODE=1

echo "2. Environment set to development mode"
echo ""

# Clear Python cache
echo "3. Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null

# Start Flask with explicit no-cache
echo "4. Starting Flask app..."
echo ""
echo "================================"
echo "IMPORTANT: In your browser:"
echo "1. Open an INCOGNITO/PRIVATE window"
echo "2. Navigate to: http://localhost:8080"
echo "3. You should see the Seasonality Config button"
echo "================================"
echo ""

# Run Flask
python3 app.py