#!/bin/bash
#
# Physalis Linux App Build Script
# 

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "   Physalis Linux Packaging Script"
echo "=========================================="

# 1. Environment Check
echo "[1/6] Checking system dependencies..."
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed."
    exit 1
fi

# Check for ffmpeg and yt-dlp
MISSING_TOOLS=()
command -v ffmpeg &> /dev/null || MISSING_TOOLS+=("ffmpeg")
command -v yt-dlp &> /dev/null || MISSING_TOOLS+=("yt-dlp")

if [ ${#MISSING_TOOLS[@]} -ne 0 ]; then
    echo "Warning: The following tools are missing: ${MISSING_TOOLS[*]}"
    echo "You should install them via your package manager (e.g., sudo apt install ${MISSING_TOOLS[*]})"
fi

# 2. Virtual Environment Setup
echo "[2/6] Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# 3. Clean previous builds
echo "[3/6] Cleaning old build artifacts..."
rm -rf build dist

# 4. PyInstaller Build
echo "[4/6] Starting PyInstaller build (OneDir mode)..."
# We use OneDir mode on Linux for better compatibility with different distros
pyinstaller --name "Physalis" \
            --windowed \
            --onedir \
            --clean \
            --noconfirm \
            --add-data "core:core" \
            --add-data "ui:ui" \
            --add-data "utils:utils" \
            --icon "icon.iconset/icon_256x256.png" \
            main.py

# 5. Create Desktop Entry
echo "[5/6] Generating .desktop launcher..."
# Note: Exec path uses a wrapper or relative path logic
cat > "dist/Physalis.desktop" <<EOF
[Desktop Entry]
Name=Physalis
Comment=Cross-platform Video Downloader (PyQt6)
Exec=sh -c "cd \$(dirname %k) && ./Physalis/Physalis"
Icon=Physalis
Type=Application
Categories=Video;Network;
Terminal=false
StartupNotify=true
EOF

# Copy icon for the desktop entry
cp "icon.iconset/icon_256x256.png" "dist/Physalis.png"

# 6. Finalizing
echo "[6/6] Finalizing..."
chmod +x dist/Physalis/Physalis
chmod +x dist/Physalis.desktop

echo ""
echo "=========================================="
echo "Build Successful!"
echo "App Directory: $SCRIPT_DIR/dist/Physalis/"
echo "Desktop Entry: $SCRIPT_DIR/dist/Physalis.desktop"
echo ""
echo "To run:"
echo "  cd dist && ./Physalis/Physalis"
echo ""
echo "To install (menu shortcut):"
echo "  cp dist/Physalis.desktop ~/.local/share/applications/"
echo "=========================================="
