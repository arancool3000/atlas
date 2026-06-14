#!/bin/bash
# Build Atlas.app on macOS via PyInstaller.

set -e
cd "$(dirname "$0")"

echo "==========================================="
echo "  Building Atlas.app (takes 2-5 min)"
echo "==========================================="

python3 -m pip install --quiet --upgrade pyinstaller

rm -rf build dist

python3 -m PyInstaller --noconfirm Atlas.spec

echo ""
echo "==========================================="
echo "  Build complete!"
echo "  Bundle:  dist/Atlas.app"
echo "  Drag it to Applications, then grant:"
echo "  - Screen Recording"
echo "  - Accessibility"
echo "  - Input Monitoring (for the global hotkey)"
echo "==========================================="
