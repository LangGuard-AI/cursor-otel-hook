#!/bin/bash
# Build script for macOS PyInstaller executable
# Outputs: dist/macos/cursor-otel-hook
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/dist/macos"
VERSION=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null || echo "0.1.0")

echo "========================================"
echo "Building cursor-otel-hook for macOS"
echo "Version: $VERSION"
echo "========================================"

# Verify we're on macOS
if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "ERROR: This script must be run on macOS"
    exit 1
fi

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required"
    exit 1
fi

echo "Python version: $(python3 --version)"

# Create clean build environment
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Create virtual environment for build
VENV_DIR="$PROJECT_ROOT/.build_venv"
if [ -d "$VENV_DIR" ]; then
    rm -rf "$VENV_DIR"
fi

echo ""
echo "Creating build virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip --quiet
pip install pyinstaller --quiet
pip install -e "$PROJECT_ROOT" --quiet

# Verify installation
echo "Installed packages:"
pip list | grep -E "(pyinstaller|opentelemetry|cursor)"

# Run PyInstaller
echo ""
echo "Running PyInstaller..."
cd "$SCRIPT_DIR"
pyinstaller --clean --noconfirm cursor_otel_hook.spec

# Move output to dist directory
if [ -f "$SCRIPT_DIR/dist/cursor-otel-hook" ]; then
    mv "$SCRIPT_DIR/dist/cursor-otel-hook" "$BUILD_DIR/"
    echo ""
    echo "Build successful!"
else
    echo "ERROR: PyInstaller output not found"
    exit 1
fi

# Create version file
echo "$VERSION" > "$BUILD_DIR/version.txt"

# Get file info
FILE_SIZE=$(du -h "$BUILD_DIR/cursor-otel-hook" | cut -f1)

# Cleanup PyInstaller artifacts
rm -rf "$SCRIPT_DIR/dist" "$SCRIPT_DIR/build"

# Deactivate and remove build venv
deactivate
rm -rf "$VENV_DIR"

echo ""
echo "========================================"
echo "Build complete!"
echo "========================================"
echo "Output: $BUILD_DIR/cursor-otel-hook"
echo "Size: $FILE_SIZE"
echo "Version: $VERSION"
echo ""
echo "To test the executable:"
echo "  $BUILD_DIR/cursor-otel-hook --help"
echo ""
echo "Next step: Run build_pkg.sh to create the installer package"

# Optional: Sign the executable (uncomment when ready)
# echo ""
# echo "To sign the executable:"
# echo "  codesign --sign 'Developer ID Application: YourName (TEAMID)' \\"
# echo "    --options runtime --timestamp \\"
# echo "    '$BUILD_DIR/cursor-otel-hook'"
