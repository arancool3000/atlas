#!/bin/bash
# Double-click this file to run Atlas on macOS.
# First run installs dependencies automatically; later runs just launch.
cd "$(dirname "$0")"

echo "Starting Atlas…"
if ! python3 -c "import PyQt6, google.genai" >/dev/null 2>&1; then
    echo "First-time setup: installing Atlas dependencies (this takes a few minutes)…"
    python3 -m pip install --upgrade pip >/dev/null 2>&1
    if ! python3 -m pip install -r requirements.txt; then
        echo ""
        echo "Dependency install failed. Make sure Python 3.10+ is installed:"
        echo "  brew install python@3.12"
        echo "Press Enter to close."
        read _
        exit 1
    fi
fi

exec python3 main.py
