#!/bin/bash
# Milan Laser Intelligence - Setup Script

set -e

echo "======================================"
echo "Milan Intel - Layer 1 Collector Setup"
echo "======================================"
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python 3.11 or higher is required. Found: $python_version"
    exit 1
fi
echo "✓ Python $python_version"
echo ""

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -e .
echo "✓ Python packages installed"
echo ""

# Install Playwright browsers
echo "Installing Playwright browsers..."
playwright install chromium
echo "✓ Playwright browsers installed"
echo ""

# Create config file
if [ ! -f "config.yaml" ]; then
    echo "Creating configuration file..."
    cp config.example.yaml config.yaml
    echo "✓ Created config.yaml from example"
else
    echo "✓ config.yaml already exists"
fi
echo ""

# Create directories
echo "Creating directories..."
mkdir -p data artifacts logs imports/google_ads imports/meta_ads
echo "✓ Directories created"
echo ""

# Initialize database
echo "Initializing database..."
python -m milanintel init-db --config config.yaml
echo "✓ Database initialized"
echo ""

echo "======================================"
echo "Setup Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Review and customize config.yaml"
echo "2. Run your first collection:"
echo "   python -m milanintel run"
echo ""
echo "For email collection, set these environment variables:"
echo "   export MILANINTEL_EMAIL_HOST='imap.gmail.com'"
echo "   export MILANINTEL_EMAIL_USERNAME='your-seed@gmail.com'"
echo "   export MILANINTEL_EMAIL_PASSWORD='your-app-password'"
echo ""
echo "For ads collection, drop JSON exports into:"
echo "   imports/google_ads/"
echo "   imports/meta_ads/"
echo ""
echo "See QUICKSTART.md for more information."
