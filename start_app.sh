#!/bin/bash

# Activate virtual environment and start Flask app
cd "$(dirname "$0")"

echo "Activating virtual environment..."
source venv/bin/activate

echo "Starting Flask application..."
echo "========================================"
echo "Server will run on http://127.0.0.1:5001"
echo "Webhook endpoint: /rb2b-webhook"
echo "========================================"
echo ""

python app.py

