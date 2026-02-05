#!/bin/bash
# Build macOS PKG installer for Cursor OTEL Hook
# Prerequisites: Run build_macos.sh first to create the executable
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/dist/macos"
PKG_ROOT="$BUILD_DIR/pkg_root"
VERSION=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null || echo "0.1.0")
IDENTIFIER="com.langguard.cursor-otel-hook"

echo "========================================"
echo "Building macOS PKG: cursor-otel-hook"
echo "Version: $VERSION"
echo "========================================"

# Verify we're on macOS
if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "ERROR: This script must be run on macOS"
    exit 1
fi

# Verify PyInstaller build exists
if [ ! -f "$BUILD_DIR/cursor-otel-hook" ]; then
    echo "ERROR: PyInstaller build not found at $BUILD_DIR/cursor-otel-hook"
    echo "Run build_macos.sh first to create the executable"
    exit 1
fi

# Clean and create package root
echo "Creating package structure..."
rm -rf "$PKG_ROOT"
mkdir -p "$PKG_ROOT/Library/Application Support/CursorOtelHook"
mkdir -p "$PKG_ROOT/Library/LaunchAgents"

# Copy files to package root
echo "Copying files..."

# Executable
cp "$BUILD_DIR/cursor-otel-hook" "$PKG_ROOT/Library/Application Support/CursorOtelHook/"

# Configuration templates
cp "$SCRIPT_DIR/../config/otel_config.template.json" "$PKG_ROOT/Library/Application Support/CursorOtelHook/"
cp "$SCRIPT_DIR/../config/hooks.template.json" "$PKG_ROOT/Library/Application Support/CursorOtelHook/"

# User setup script
cp "$SCRIPT_DIR/scripts/setup-user.sh" "$PKG_ROOT/Library/Application Support/CursorOtelHook/"

# LaunchAgent
cp "$SCRIPT_DIR/launchagent/com.langguard.cursor-otel-hook-setup.plist" "$PKG_ROOT/Library/LaunchAgents/"

# Set permissions
echo "Setting permissions..."
chmod 755 "$PKG_ROOT/Library/Application Support/CursorOtelHook/cursor-otel-hook"
chmod 755 "$PKG_ROOT/Library/Application Support/CursorOtelHook/setup-user.sh"
chmod 644 "$PKG_ROOT/Library/Application Support/CursorOtelHook/"*.json
chmod 644 "$PKG_ROOT/Library/LaunchAgents/com.langguard.cursor-otel-hook-setup.plist"

# Create scripts directory for pkgbuild
SCRIPTS_DIR="$BUILD_DIR/scripts"
rm -rf "$SCRIPTS_DIR"
mkdir -p "$SCRIPTS_DIR"
cp "$SCRIPT_DIR/scripts/preinstall" "$SCRIPTS_DIR/"
cp "$SCRIPT_DIR/scripts/postinstall" "$SCRIPTS_DIR/"
chmod 755 "$SCRIPTS_DIR/preinstall"
chmod 755 "$SCRIPTS_DIR/postinstall"

# Build component package
echo ""
echo "Building component package..."
pkgbuild \
    --root "$PKG_ROOT" \
    --identifier "$IDENTIFIER" \
    --version "$VERSION" \
    --scripts "$SCRIPTS_DIR" \
    --install-location "/" \
    "$BUILD_DIR/cursor-otel-hook-component.pkg"

# Update version in Distribution.xml
echo "Creating distribution..."
sed "s/{{VERSION}}/$VERSION/g" "$SCRIPT_DIR/Distribution.xml" > "$BUILD_DIR/Distribution.xml"

# Build product archive (distribution package)
productbuild \
    --distribution "$BUILD_DIR/Distribution.xml" \
    --resources "$SCRIPT_DIR/resources" \
    --package-path "$BUILD_DIR" \
    "$BUILD_DIR/cursor-otel-hook-$VERSION.pkg"

# Cleanup intermediate files
echo "Cleaning up..."
rm -rf "$PKG_ROOT"
rm -rf "$SCRIPTS_DIR"
rm -f "$BUILD_DIR/cursor-otel-hook-component.pkg"
rm -f "$BUILD_DIR/Distribution.xml"

# Get package info
PKG_FILE="$BUILD_DIR/cursor-otel-hook-$VERSION.pkg"
PKG_SIZE=$(du -h "$PKG_FILE" | cut -f1)

echo ""
echo "========================================"
echo "PKG build complete!"
echo "========================================"
echo "Package: $PKG_FILE"
echo "Size: $PKG_SIZE"
echo "Version: $VERSION"
echo ""
echo "To install locally (for testing):"
echo "  sudo installer -pkg '$PKG_FILE' -target /"
echo ""
echo "To install with MDM configuration:"
echo "  export OTEL_ENDPOINT='https://your-endpoint:4318/v1/traces'"
echo "  export SERVICE_NAME='cursor-agent-prod'"
echo "  export OTEL_HEADERS='{\"Authorization\": \"Bearer YOUR_KEY\"}'"
echo "  sudo installer -pkg '$PKG_FILE' -target /"
echo ""
echo "To sign for distribution (when ready):"
echo "  productsign --sign 'Developer ID Installer: YourName (TEAMID)' \\"
echo "    '$PKG_FILE' \\"
echo "    '${PKG_FILE%.pkg}-signed.pkg'"
echo ""
echo "To notarize (after signing):"
echo "  xcrun notarytool submit '${PKG_FILE%.pkg}-signed.pkg' \\"
echo "    --apple-id 'your@email.com' \\"
echo "    --password '@keychain:AC_PASSWORD' \\"
echo "    --team-id 'TEAMID' --wait"
echo ""
echo "  xcrun stapler staple '${PKG_FILE%.pkg}-signed.pkg'"
