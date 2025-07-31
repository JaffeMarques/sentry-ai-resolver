#!/bin/bash

# Sentry Solver Runner Script

set -e

echo "🔧 Starting Sentry Solver..."

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
    echo "⚠️  .env file not found. Please copy .env.example to .env and configure it."
    echo "📋 Creating .env from template..."
    cp .env.example .env
    echo "✏️  Please edit .env file with your configuration and run again."
    exit 1
fi

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    echo "⚠️  Not in a Git repository. Initializing..."
    git init
    echo "📝 Don't forget to add your remote repository:"
    echo "    git remote add origin <your-repo-url>"
fi

# Make main.py executable
chmod +x main.py

# Run the application
echo "🚀 Starting Sentry Solver..."
echo "📊 Logs will be saved to sentry_solver.log"
echo "⏹️  Press Ctrl+C to stop"
echo ""

if [ "$1" = "--once" ]; then
    echo "🔄 Running single cycle..."
    python main.py --once
else
    echo "⏰ Running in scheduler mode..."
    python main.py
fi