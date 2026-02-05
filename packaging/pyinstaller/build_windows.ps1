# Build script for Windows PyInstaller executable
# Outputs: dist\windows\cursor-otel-hook.exe

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$BuildDir = Join-Path $ProjectRoot "dist\windows"
$Version = if (Test-Path "$ProjectRoot\VERSION") {
    (Get-Content "$ProjectRoot\VERSION" -Raw).Trim()
} else {
    "0.1.0"
}

Write-Host "========================================"
Write-Host "Building cursor-otel-hook for Windows"
Write-Host "Version: $Version"
Write-Host "========================================"

# Check for Python
try {
    $pythonVersion = & python --version 2>&1
    Write-Host "Python version: $pythonVersion"
} catch {
    Write-Host "ERROR: Python 3 is required" -ForegroundColor Red
    exit 1
}

# Create clean build environment
if (Test-Path $BuildDir) {
    Remove-Item -Recurse -Force $BuildDir
}
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null

# Create virtual environment for build
$VenvDir = Join-Path $ProjectRoot ".build_venv"
if (Test-Path $VenvDir) {
    Remove-Item -Recurse -Force $VenvDir
}

Write-Host ""
Write-Host "Creating build virtual environment..."
python -m venv $VenvDir

# Activate virtual environment
$activateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
. $activateScript

# Install dependencies
Write-Host "Installing dependencies..."
pip install --upgrade pip --quiet
pip install pyinstaller --quiet
pip install -e $ProjectRoot --quiet

# Verify installation
Write-Host "Installed packages:"
pip list | Select-String -Pattern "(pyinstaller|opentelemetry|cursor)"

# Run PyInstaller
Write-Host ""
Write-Host "Running PyInstaller..."
Set-Location $ScriptDir
pyinstaller --clean --noconfirm cursor_otel_hook.spec

# Move output to dist directory
$exePath = Join-Path $ScriptDir "dist\cursor-otel-hook.exe"
if (Test-Path $exePath) {
    Move-Item -Path $exePath -Destination $BuildDir -Force
    Write-Host ""
    Write-Host "Build successful!" -ForegroundColor Green
} else {
    Write-Host "ERROR: PyInstaller output not found" -ForegroundColor Red
    exit 1
}

# Create version file
Set-Content -Path (Join-Path $BuildDir "version.txt") -Value $Version

# Get file info
$exeFile = Join-Path $BuildDir "cursor-otel-hook.exe"
$fileSize = [math]::Round((Get-Item $exeFile).Length / 1MB, 2)

# Cleanup PyInstaller artifacts
$distDir = Join-Path $ScriptDir "dist"
$buildArtifactDir = Join-Path $ScriptDir "build"
if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir }
if (Test-Path $buildArtifactDir) { Remove-Item -Recurse -Force $buildArtifactDir }

# Deactivate and remove build venv
deactivate
Remove-Item -Recurse -Force $VenvDir

Write-Host ""
Write-Host "========================================"
Write-Host "Build complete!"
Write-Host "========================================"
Write-Host "Output: $exeFile"
Write-Host "Size: $fileSize MB"
Write-Host "Version: $Version"
Write-Host ""
Write-Host "To test the executable:"
Write-Host "  & `"$exeFile`" --help"
Write-Host ""
Write-Host "Next step: Run build_msi.ps1 to create the installer package"

# Optional: Sign the executable (uncomment when ready)
# Write-Host ""
# Write-Host "To sign the executable:"
# Write-Host "  signtool sign /n 'Your Certificate Name' /t http://timestamp.digicert.com /fd sha256 `"$exeFile`""
