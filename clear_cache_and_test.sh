#!/bin/bash

# Script to help with cache issues during development

echo "🧹 Clearing browser cache workarounds..."
echo ""

# 1. Add timestamp to environment to force different cache keys
export CACHE_BUST_TIME=$(date +%s)
echo "✅ Set CACHE_BUST_TIME=$CACHE_BUST_TIME"

# 2. Touch all static files to update their modification time
find static/ -type f \( -name "*.css" -o -name "*.js" \) -exec touch {} \;
echo "✅ Updated modification times for all CSS and JS files"

# 3. If running locally, restart the Flask app
if pgrep -f "python.*app.py" > /dev/null; then
    echo "🔄 Restarting Flask app..."
    pkill -f "python.*app.py"
    sleep 2
    python3 app.py &
    echo "✅ Flask app restarted"
else
    echo "ℹ️  Flask app not running locally"
fi

echo ""
echo "📝 Additional steps to ensure changes are visible:"
echo "1. In your browser, open Developer Tools (F12)"
echo "2. Go to Network tab"
echo "3. Check 'Disable cache' checkbox"
echo "4. Keep DevTools open while testing"
echo ""
echo "Alternative browser shortcuts:"
echo "  - Chrome/Edge: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)"
echo "  - Firefox: Ctrl+F5 (Windows/Linux) or Cmd+Shift+R (Mac)"
echo "  - Safari: Cmd+Option+R"
echo ""
echo "🔗 Direct link to seasonality page:"
echo "  http://localhost:8080/seasonality"