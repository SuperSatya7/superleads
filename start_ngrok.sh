#!/bin/bash

# Start ngrok tunnel for RB2B webhook local testing
echo "Starting ngrok tunnel on port 5001..."
echo "========================================"
echo ""
echo "Your webhook URL will be displayed below."
echo "Copy the HTTPS URL and add '/rb2b-webhook' to the end."
echo "Example: https://xxxx-xx-xx-xxx-xxx.ngrok-free.app/rb2b-webhook"
echo ""
echo "========================================"

ngrok http 5001

