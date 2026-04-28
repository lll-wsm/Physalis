#!/bin/bash
#
# Physalis Linux .deb Build Script
#

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "   Physalis .deb Packaging Script"
echo "=========================================="

# 1. Environment Check
echo "[1/7] Checking system dependencies..."
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed."
    exit 1
fi

if ! command -v dpkg-deb &> /dev/null; then
    echo "Error: dpkg-deb is not installed. Install dpkg package."
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
echo "[2/7] Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# 3. Clean previous builds
echo "[3/7] Cleaning old build artifacts..."
rm -rf build dist

# 4. PyInstaller Build
echo "[4/7] Starting PyInstaller build (OneDir mode)..."
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

# 5. Extract version from app.py
echo "[5/7] Extracting app version..."
APP_VERSION=$(grep -oP 'setApplicationVersion\("\K[^"]+' app.py)
if [ -z "$APP_VERSION" ]; then
    echo "Error: Could not extract version from app.py"
    exit 1
fi
echo "  Version: $APP_VERSION"

# 6. Assemble .deb package structure
echo "[6/7] Assembling .deb package structure..."
PKG_DIR="dist/physalis_${APP_VERSION}_amd64"
PKG_NAME="physalis_${APP_VERSION}_amd64.deb"

rm -rf "$PKG_DIR"

# Create directory structure
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/opt/Physalis"
mkdir -p "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/16x16/apps"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/32x32/apps"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/128x128/apps"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/512x512/apps"

# Copy PyInstaller output to /opt/Physalis/
cp -r dist/Physalis/* "$PKG_DIR/opt/Physalis/"

# Generate DEBIAN/control
cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: physalis
Version: $APP_VERSION
Section: video
Priority: optional
Architecture: amd64
Depends: libgl1, libxkbcommon0, libxcb-xinerama0, libxcb-cursor0
Recommends: ffmpeg, yt-dlp
Maintainer: Physalis <physalis@example.com>
Description: Cross-platform Video Downloader
 A video downloader built with PyQt6 that wraps yt-dlp
 as the download engine and provides an embedded browser
 for sniffing video URLs.
EOF

# Generate DEBIAN/postinst
cat > "$PKG_DIR/DEBIAN/postinst" <<'EOF'
#!/bin/bash
gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true
update-desktop-database /usr/share/applications/ 2>/dev/null || true
EOF
chmod 755 "$PKG_DIR/DEBIAN/postinst"

# Generate /usr/bin/physalis wrapper
cat > "$PKG_DIR/usr/bin/physalis" <<'EOF'
#!/bin/bash
export PATH="/usr/local/bin:/usr/bin:$PATH"
exec /opt/Physalis/Physalis "$@"
EOF
chmod 755 "$PKG_DIR/usr/bin/physalis"

# Generate .desktop file
cat > "$PKG_DIR/usr/share/applications/Physalis.desktop" <<EOF
[Desktop Entry]
Name=Physalis
Comment=Cross-platform Video Downloader
Exec=/usr/bin/physalis
Icon=Physalis
Type=Application
Categories=Video;Network;
Terminal=false
StartupNotify=true
EOF

# Install icons
cp icon.iconset/icon_16x16.png "$PKG_DIR/usr/share/icons/hicolor/16x16/apps/Physalis.png"
cp icon.iconset/icon_32x32.png "$PKG_DIR/usr/share/icons/hicolor/32x32/apps/Physalis.png"
cp icon.iconset/icon_128x128.png "$PKG_DIR/usr/share/icons/hicolor/128x128/apps/Physalis.png"
cp icon.iconset/icon_256x256.png "$PKG_DIR/usr/share/icons/hicolor/256x256/apps/Physalis.png"
cp icon.iconset/icon_512x512.png "$PKG_DIR/usr/share/icons/hicolor/512x512/apps/Physalis.png"

# Set ownership
find "$PKG_DIR" -type d -exec chmod 755 {} \;

# 7. Build .deb
echo "[7/7] Building .deb package..."
dpkg-deb --build "$PKG_DIR"

echo ""
echo "=========================================="
echo "Build Successful!"
echo "Package: $SCRIPT_DIR/dist/$PKG_NAME"
echo ""
echo "To install:"
echo "  sudo dpkg -i dist/$PKG_NAME"
echo ""
echo "To uninstall:"
echo "  sudo dpkg -r physalis"
echo ""
echo "To inspect package:"
echo "  dpkg-deb -I dist/$PKG_NAME    # metadata"
echo "  dpkg-deb -c dist/$PKG_NAME    # file list"
echo "=========================================="
