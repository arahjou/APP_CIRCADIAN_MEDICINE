#!/bin/bash

# Circadian Medicine Analysis Platform - Setup Script
# This script automates the installation process

echo "🔬 Circadian Medicine Analysis Platform - Setup"
echo "================================================"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
REQUIRED_VERSION="3.8"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then 
    echo -e "${RED}✗ Python 3.8+ is required. Current: $PYTHON_VERSION${NC}"
    exit 1
else
    echo -e "${GREEN}✓ Python $PYTHON_VERSION detected${NC}"
fi

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip install -r requirements.txt
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Python dependencies installed${NC}"
else
    echo -e "${RED}✗ Failed to install Python dependencies${NC}"
    exit 1
fi

# Check if Ollama is installed
echo ""
echo "Checking for Ollama..."
if command -v ollama &> /dev/null; then
    echo -e "${GREEN}✓ Ollama is installed${NC}"
else
    echo -e "${YELLOW}⚠ Ollama not found${NC}"
    echo "To install Ollama:"
    echo "  macOS: brew install ollama"
    echo "  Or visit: https://ollama.ai"
    echo ""
    read -p "Skip Ollama installation? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if Ollama is running
echo ""
echo "Checking Ollama service..."
if pgrep -x "ollama" > /dev/null; then
    echo -e "${GREEN}✓ Ollama is running${NC}"
else
    echo -e "${YELLOW}⚠ Ollama is not running${NC}"
    echo "Starting Ollama..."
    ollama serve &
    sleep 3
fi

# Download recommended model
echo ""
echo "Checking AI models..."
MODELS=$(ollama list 2>/dev/null)
if echo "$MODELS" | grep -q "phi4:14b"; then
    echo -e "${GREEN}✓ phi4:14b model found${NC}"
else
    echo -e "${YELLOW}⚠ phi4:14b model not found${NC}"
    read -p "Download phi4:14b model (~8GB)? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ollama pull phi4:14b
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Model downloaded successfully${NC}"
        else
            echo -e "${RED}✗ Failed to download model${NC}"
        fi
    else
        echo "You can download it later with: ollama pull phi4:14b"
    fi
fi

# Create data directory if it doesn't exist
echo ""
echo "Setting up directories..."
mkdir -p data
mkdir -p image
echo -e "${GREEN}✓ Directories created${NC}"

# Setup complete
echo ""
echo "================================================"
echo -e "${GREEN}✓ Setup complete!${NC}"
echo ""
echo "To run the application:"
echo "  streamlit run app.py"
echo ""
echo "For more information, see README.md"
echo ""
