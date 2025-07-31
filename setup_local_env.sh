#!/bin/bash

# Setup script for local development environment

echo "🔧 Setting up local development environment for Super Gemini..."

# Check if pip is available for user installs
if ! python3 -m pip --version >/dev/null 2>&1; then
    echo "❌ pip is not available. Installing pip for user..."
    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
    python3 get-pip.py --user
    rm get-pip.py
fi

# Install dependencies with user flag
echo "📦 Installing dependencies..."
python3 -m pip install --user --break-system-packages -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file template..."
    cat > .env << 'EOF'
# Local development environment variables
ENVIRONMENT=development
FLASK_ENV=development
FLASK_DEBUG=1

# API Keys (add your keys here for local testing)
# GOOGLE_API_KEY=your-key-here
# OPENAI_API_KEY=your-key-here
# ANTHROPIC_API_KEY=your-key-here
# XAI_API_KEY=your-key-here

# GCP Configuration
GCP_PROJECT=sis-sandbox-463113
BQ_PROJECT=scheels-data-marts

# Optional: Override default model
# DEFAULT_MODEL=gemini-2.5-pro
EOF
    echo "✅ Created .env template. Add your API keys for local testing."
else
    echo "✅ .env file already exists"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "📚 Next steps:"
echo "1. Edit .env file and add your API keys (if testing locally)"
echo "2. Run ./run_local.sh to start the app"
echo ""
echo "💡 For production, the app will use Google Secret Manager instead of .env"