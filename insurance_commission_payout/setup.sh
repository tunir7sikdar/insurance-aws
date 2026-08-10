#!/bin/bash

set -e

echo "========================================"
echo "Commission Payout Pipeline - Setup"
echo "========================================"
echo ""

echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python $PYTHON_VERSION"

if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt

if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env file..."
    cp .env.example .env
    echo "(please fill in your values)"
fi

echo ""
echo "Running tests..."
make test || true

echo ""
echo "========================================"
echo "Setup complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Edit .env with your AWS configuration"
echo "2. Generate PGP keys: gpg --gen-key"
echo "3. Deploy infrastructure: make deploy"
echo ""
