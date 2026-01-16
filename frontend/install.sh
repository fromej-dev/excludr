#!/bin/bash

# Excludr Frontend Installation Script

set -e

echo "Installing Excludr Frontend..."
echo "=============================="
echo

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "Error: Node.js is not installed. Please install Node.js 18+ first."
    exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "Error: Node.js version must be 18 or higher. Current version: $(node -v)"
    exit 1
fi

echo "Node.js version: $(node -v)"
echo "npm version: $(npm -v)"
echo

# Install dependencies
echo "Installing dependencies..."
npm install

echo
echo "=============================="
echo "Installation complete!"
echo
echo "To start the development server:"
echo "  npm run dev"
echo
echo "To build for production:"
echo "  npm run build"
echo
echo "Make sure the backend API is running at http://localhost:8000"
echo "=============================="
