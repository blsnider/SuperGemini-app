#!/bin/bash

# Test Super Gemini App locally with Docker
# This builds and runs the app locally for testing

set -e

echo "🐳 Building and testing Super Gemini locally..."
echo ""

# Build the Docker image
echo "📦 Building Docker image..."
docker build -t super-gemini-local:latest .

echo ""
echo "✅ Build complete!"
echo ""

# Check if container is already running
if docker ps | grep -q super-gemini-local; then
    echo "🛑 Stopping existing container..."
    docker stop super-gemini-local || true
    docker rm super-gemini-local || true
fi

# Run the container
echo "🚀 Starting container..."
echo "   Port: 8080"
echo "   URL: http://localhost:8080"
echo ""

# Create .env.docker file if it doesn't exist
if [ ! -f .env.docker ]; then
    echo "📝 Creating .env.docker file..."
    cat > .env.docker << EOF
# Local Docker environment variables
ENVIRONMENT=development
BQ_PROJECT=sis-data-marts
DEFAULT_MODEL=gemini-2.5-pro
ENABLE_AUTH=False
TOOLBOX_URL=https://toolbox-41815171183.us-central1.run.app

# Add your API keys here (copy from .env)
# GOOGLE_API_KEY=
# ANTHROPIC_API_KEY=
# OPENAI_API_KEY=
# XAI_API_KEY=
EOF
    echo "⚠️  Please edit .env.docker and add your API keys!"
fi

docker run -d \
    --name super-gemini-local \
    -p 8080:8080 \
    --env-file .env.docker \
    -v ${GOOGLE_APPLICATION_CREDENTIALS:-$HOME/.config/gcloud/application_default_credentials.json}:/app/credentials.json:ro \
    -e GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json \
    super-gemini-local:latest

echo ""
echo "✅ Container started!"
echo ""
echo "📊 Access the app at: http://localhost:8080"
echo ""
echo "📝 View logs:"
echo "   docker logs -f super-gemini-local"
echo ""
echo "🛑 Stop container:"
echo "   docker stop super-gemini-local"
echo ""
echo "🔄 Restart container:"
echo "   docker restart super-gemini-local"