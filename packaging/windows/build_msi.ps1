# Build Windows MSI installer for Cursor OTEL Hook
# Prerequisites: Run build_windows.ps1 first to create the executable
# Requires: WiX Toolset v3.11+ (https://wixtoolset.org/)

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
Write-Host "Building Windows MSI: cursor-otel-hook"
Write-Host "Version: $Version"
Write-Host "========================================"

# Find WiX Toolset
$WixPaths = @(
    "$env:WIX\bin",
    "${env:ProgramFiles(x86)}\WiX Toolset v3.14\bin",
    "${env:ProgramFiles(x86)}\WiX Toolset v3.11\bin",
    "${env:ProgramFiles}\WiX Toolset v3.14\bin",
    "${env:ProgramFiles}\WiX Toolset v3.11\bin"
)

$WixPath = $null
foreach ($path in $WixPaths) {
    if (Test-Path (Join-Path $path "candle.exe")) {
        $WixPath = $path
        break
    }
}

if ($null -eq $WixPath) {
    Write-Host "ERROR: WiX Toolset not found." -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install WiX Toolset v3.11 or later from:"
    Write-Host "  https://wixtoolset.org/releases/"
    Write-Host ""
    Write-Host "Or install via Chocolatey:"
    Write-Host "  choco install wixtoolset"
    exit 1
}

Write-Host "Using WiX Toolset at: $WixPath"

# Verify PyInstaller build exists
$ExePath = Join-Path $BuildDir "cursor-otel-hook.exe"
if (!(Test-Path $ExePath)) {
    Write-Host "ERROR: PyInstaller build not found at $ExePath" -ForegroundColor Red
    Write-Host "Run build_windows.ps1 first to create the executable"
    exit 1
}

# Create output directory for intermediate files
$MsiOutputDir = Join-Path $BuildDir "msi_build"
if (Test-Path $MsiOutputDir) {
    Remove-Item -Recurse -Force $MsiOutputDir
}
New-Item -ItemType Directory -Path $MsiOutputDir -Force | Out-Null

# Compile WiX source
Write-Host ""
Write-Host "Compiling WiX source..."

$CandleExe = Join-Path $WixPath "candle.exe"
$CandleArgs = @(
    "-dProductVersion=$Version",
    "-dBuildDir=$BuildDir",
    "-out", "$MsiOutputDir\",
    "-ext", "WixUtilExtension",
    "-ext", "WixUIExtension",
    "$ScriptDir\Product.wxs"
)

Write-Host "Running: candle.exe $($CandleArgs -join ' ')"
& $CandleExe @CandleArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: WiX candle failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit 1
}

# Link MSI
Write-Host ""
Write-Host "Linking MSI..."

$LightExe = Join-Path $WixPath "light.exe"
$MsiPath = Join-Path $BuildDir "cursor-otel-hook-$Version.msi"
$LightArgs = @(
    "-out", $MsiPath,
    "-ext", "WixUtilExtension",
    "-ext", "WixUIExtension",
    "-spdb",  # Suppress PDB file
    "$MsiOutputDir\Product.wixobj"
)

Write-Host "Running: light.exe $($LightArgs -join ' ')"
& $LightExe @LightArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: WiX light failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit 1
}

# Cleanup intermediate files
Write-Host ""
Write-Host "Cleaning up..."
Remove-Item -Recurse -Force $MsiOutputDir

# Get MSI info
$MsiSize = [math]::Round((Get-Item $MsiPath).Length / 1MB, 2)

Write-Host ""
Write-Host "========================================"
Write-Host "MSI build complete!" -ForegroundColor Green
Write-Host "========================================"
Write-Host "Package: $MsiPath"
Write-Host "Size: $MsiSize MB"
Write-Host "Version: $Version"
Write-Host ""
Write-Host "To install silently (for testing):"
Write-Host "  msiexec /i `"$MsiPath`" /qn"
Write-Host ""
Write-Host "To install with MDM configuration:"
Write-Host "  msiexec /i `"$MsiPath`" /qn ^"
Write-Host "    OTEL_ENDPOINT=`"https://your-endpoint:4318/v1/traces`" ^"
Write-Host "    SERVICE_NAME=`"cursor-agent-prod`" ^"
Write-Host "    OTEL_HEADERS=`"{```"Authorization```": ```"Bearer YOUR_KEY```"}`""
Write-Host ""
Write-Host "To uninstall:"
Write-Host "  msiexec /x `"$MsiPath`" /qn"
Write-Host ""
Write-Host "To sign for distribution (when ready):"
Write-Host "  signtool sign /n `"Your Certificate Name`" /t http://timestamp.digicert.com /fd sha256 `"$MsiPath`""
