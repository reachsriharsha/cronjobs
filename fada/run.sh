#!/bin/bash
# FADA Report Monitor - Cron Wrapper Script
# This script activates the uv virtual environment and runs the Python monitor

# Configuration
SCRIPT_DIR="$HOME/src/cronjobs/fada"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON_SCRIPT="$SCRIPT_DIR/fada_monitor.py"
LOG_FILE="$SCRIPT_DIR/logs/monitor_$(date +%Y%m%d).log"

# Create log directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/logs"

# Redirect all output to log file
exec >> "$LOG_FILE" 2>&1

echo "=========================================="
echo "FADA Monitor Started: $(date)"
echo "=========================================="

# Change to script directory
cd "$SCRIPT_DIR" || exit 1

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