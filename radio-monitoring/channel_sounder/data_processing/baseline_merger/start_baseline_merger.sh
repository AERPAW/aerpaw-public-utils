#!/bin/bash
# Baseline Merger Web App - Launcher

# This script starts the interactive baseline merger web application.
# The app allows you to:
# 1. Load two baseline CSV files (old and new)
# 2. View side-by-side comparison of metrics
# 3. Toggle between power and quality metrics
# 4. Select which baseline values to keep (old, new, or custom)
# 5. Preview and export the merged baseline CSV

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

#VENV_DIR="${SCRIPT_DIR}/venv"
# Check if virtual environment exists
#if [ ! -d "$VENV_DIR" ]; then
#    echo "Error: Virtual environment not found at $VENV_DIR"
#    echo "Please set up the virtual environment first."
#    exit 1
#fi

# Activate virtual environment
#source "$VENV_DIR/bin/activate"

echo "Starting Baseline Merger Web App..."
echo ""
echo "Press Ctrl+C to stop the server."
echo ""

# Start the Flask app
cd "$SCRIPT_DIR"
python3 baseline_merger_app.py
