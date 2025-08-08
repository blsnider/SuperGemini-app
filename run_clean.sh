#!/bin/bash

echo "Cleaning and restarting Flask..."

# Kill all Python processes
pkill -9 -f python 2>/dev/null
sleep 2

# Clear all caches
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

# Remove and recreate venv
rm -rf venv .venv
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --no-cache-dir flask gunicorn

# Set environment
export FLASK_APP=app.py
export FLASK_ENV=development
export FLASK_DEBUG=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1

# Create a minimal test app to verify
cat > test_app.py << 'EOF'
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('base.html')

@app.route('/test')
def test():
    return """
    <html>
    <head>
        <style>body { background: #ff6b6b; color: white; font-size: 24px; text-align: center; padding: 50px; }</style>
    </head>
    <body>
        <h1>Flask Test Route</h1>
        <p>If this is RED, Flask is working!</p>
        <p><a href="/" style="color: white;">Go to main page</a></p>
    </body>
    </html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
EOF

echo "Starting minimal Flask app..."
echo "Access at: https://8080-w-blsnider-mdk8d0vt.cluster-rg4hlmqyybggwv6jmu3tg6wun6.cloudworkstations.dev/"
echo "Test route: https://8080-w-blsnider-mdk8d0vt.cluster-rg4hlmqyybggwv6jmu3tg6wun6.cloudworkstations.dev/test"

python test_app.py