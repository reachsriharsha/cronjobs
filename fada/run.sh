#!/bin/bash
# FADA Report Monitor - Cron Wrapper Script
# This script activates the uv virtual environment and runs the Python monitor

# Configuration
SCRIPT_DIR="$HOME/src/cronjobs/fada"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON_SCRIPT="$SCRIPT_DIR/fada_monitor.py"
LOG_FILE="$SCRIPT_DIR/logs/monitor_$(date +%Y%m%d).log"
ENV_FILE="$SCRIPT_DIR/.env"

# Create log directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/logs"

# Redirect all output to log file
exec >> "$LOG_FILE" 2>&1

echo "=========================================="
echo "FADA Monitor Started: $(date)"
echo "=========================================="

# Change to script directory
cd "$SCRIPT_DIR" || exit 1

# Load environment variables if .env file exists
if [ -f "$ENV_FILE" ]; then
    echo "Loading environment variables from .env"
    set -a  # automatically export all variables
    source "$ENV_FILE"
    set +a
fi

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "ERROR: Virtual environment not found at $VENV_DIR"
    echo "Please run 'uv sync' first to create the virtual environment"
    exit 1
fi

echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"


# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "ERROR: uv is not installed or not in PATH"
    exit 1
fi

# Run the Python script using uv
uv run python "$PYTHON_SCRIPT"

# Capture exit code
EXIT_CODE=$?

echo "Monitor completed with exit code: $EXIT_CODE"
echo "=========================================="
echo ""

# Optional: Clean up old logs (keep last 30 days)
find "$SCRIPT_DIR/logs" -name "monitor_*.log" -mtime +30 -delete 2>/dev/null

exit $EXIT_CODE