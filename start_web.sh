#!/bin/bash

# Sentry Solver Web Interface Starter

set -e

echo "🌐 Starting Sentry Solver Web Interface..."

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "📥 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp .env.example .env
    echo "✏️  Please edit .env file with your configuration if needed."
fi

# Initialize database
echo "🗄️  Initializing database..."
python -c "from database import Database; Database()"

# Make api.py executable
chmod +x api.py

echo ""
echo "🚀 Starting Sentry Solver Web Interface..."
echo "🌐 Access the dashboard at: http://localhost:8000"
echo "📚 API documentation at: http://localhost:8000/docs"
echo "⏹️  Press Ctrl+C to stop"
echo ""

# Start the web server
python api.py