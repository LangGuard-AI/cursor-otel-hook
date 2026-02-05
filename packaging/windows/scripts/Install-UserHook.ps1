# Install-UserHook.ps1
# Per-user setup script for Cursor OTEL Hook
# Runs via Active Setup at first user login after MSI installation
# Also can be run manually for testing

param(
    [Parameter(Mandatory=$false)]
    [string]$InstallDir = "$env:ProgramFiles\CursorOtelHook"
)

$ErrorActionPreference = "SilentlyContinue"

# Log file in user's temp directory
$LogFile = "$env:TEMP\cursor-otel-hook-setup.log"

function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -Append -FilePath $LogFile -Encoding UTF8
}

Write-Log "=========================================="
Write-Log "Starting Cursor OTEL Hook user setup"
Write-Log "Install directory: $InstallDir"
Write-Log "User: $env:USERNAME"
Write-Log "User profile: $env:USERPROFILE"
Write-Log "=========================================="

try {
    # Define paths
    $UserCursorDir = "$env:USERPROFILE\.cursor"
    $UserHooksDir = "$UserCursorDir\hooks"

    # Create directories if they don't exist
    if (!(Test-Path $UserHooksDir)) {
        New-Item -ItemType Directory -Path $UserHooksDir -Force | Out-Null
        Write-Log "Created hooks directory: $UserHooksDir"
    }

    # Copy executable
    $SourceExe = Join-Path $InstallDir "cursor-otel-hook.exe"
    $DestExe = Join-Path $UserHooksDir "cursor-otel-hook.exe"

    if (Test-Path $SourceExe) {
        $sourceTime = (Get-Item $SourceExe).LastWriteTime
        $destExists = Test-Path $DestExe

        if (!$destExists -or ($sourceTime -gt (Get-Item $DestExe).LastWriteTime)) {
            Copy-Item -Path $SourceExe -Destination $DestExe -Force
            Write-Log "Installed executable to: $DestExe"
        } else {
            Write-Log "Executable is up to date"
        }
    } else {
        Write-Log "ERROR: Source executable not found: $SourceExe"
        exit 1
    }

    # Copy configuration
    $SourceConfig = Join-Path $InstallDir "otel_config.json"
    $DestConfig = Join-Path $UserHooksDir "otel_config.json"

    if (Test-Path $SourceConfig) {
        $sourceTime = (Get-Item $SourceConfig).LastWriteTime
        $destExists = Test-Path $DestConfig

        if (!$destExists -or ($sourceTime -gt (Get-Item $DestConfig).LastWriteTime)) {
            Copy-Item -Path $SourceConfig -Destination $DestConfig -Force
            Write-Log "Installed configuration to: $DestConfig"
        } else {
            Write-Log "Configuration is up to date"
        }
    } else {
        Write-Log "WARNING: No system configuration found at $SourceConfig"
        Write-Log "User will need to configure otel_config.json manually"
    }

    # Create hooks.json if it doesn't exist
    $HooksJson = Join-Path $UserCursorDir "hooks.json"
    $HooksTemplate = Join-Path $InstallDir "hooks.template.json"

    if (!(Test-Path $HooksJson)) {
        if (Test-Path $HooksTemplate) {
            # Read template
            $HooksContent = Get-Content $HooksTemplate -Raw

            # Build hook command with escaped backslashes for JSON
            $HookCommand = "$DestExe --config `"$DestConfig`""
            $HookCommandEscaped = $HookCommand -replace '\\', '\\'
            $HookTimeout = "5"

            # Substitute placeholders
            $HooksContent = $HooksContent -replace '\{\{HOOK_COMMAND\}\}', $HookCommandEscaped
            $HooksContent = $HooksContent -replace '\{\{HOOK_TIMEOUT\}\}', $HookTimeout

            # Write hooks.json
            Set-Content -Path $HooksJson -Value $HooksContent -Encoding UTF8
            Write-Log "Created hooks.json at: $HooksJson"
        } else {
            Write-Log "ERROR: hooks.template.json not found at $HooksTemplate"
        }
    } else {
        Write-Log "hooks.json already exists at $HooksJson"
        Write-Log "NOTE: Manual merge may be needed if you have custom hooks"
    }

    Write-Log "=========================================="
    Write-Log "User setup completed successfully"
    Write-Log "Restart Cursor IDE for changes to take effect"
    Write-Log "=========================================="

} catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    Write-Log "Stack trace: $($_.ScriptStackTrace)"
    exit 1
}

exit 0
