# Uninstall-UserHook.ps1
# Per-user cleanup script for Cursor OTEL Hook
# Can be run to remove user-level files

param(
    [switch]$Force,
    [switch]$KeepConfig
)

$ErrorActionPreference = "SilentlyContinue"

$LogFile = "$env:TEMP\cursor-otel-hook-uninstall.log"

function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -Append -FilePath $LogFile -Encoding UTF8
    Write-Host $Message
}

Write-Log "=========================================="
Write-Log "Cursor OTEL Hook user cleanup"
Write-Log "User: $env:USERNAME"
Write-Log "=========================================="

$UserCursorDir = "$env:USERPROFILE\.cursor"
$UserHooksDir = "$UserCursorDir\hooks"

# Files to remove
$FilesToRemove = @(
    (Join-Path $UserHooksDir "cursor-otel-hook.exe"),
    (Join-Path $UserHooksDir "cursor_otel_hook.log")
)

# Optionally remove config
if (!$KeepConfig) {
    $FilesToRemove += (Join-Path $UserHooksDir "otel_config.json")
}

# Remove files
foreach ($file in $FilesToRemove) {
    if (Test-Path $file) {
        Remove-Item -Path $file -Force
        Write-Log "Removed: $file"
    }
}

# Handle hooks.json - remove our entries but keep the file if it has other hooks
$HooksJson = Join-Path $UserCursorDir "hooks.json"
if (Test-Path $HooksJson) {
    try {
        $hooks = Get-Content $HooksJson -Raw | ConvertFrom-Json

        # Check if this is our hooks.json (all hooks point to cursor-otel-hook)
        $isOurHooksOnly = $true
        $hookTypes = @("sessionStart", "sessionEnd", "postToolUse", "afterShellExecution",
                       "afterMCPExecution", "beforeReadFile", "afterFileEdit",
                       "beforeSubmitPrompt", "subagentStart", "subagentStop", "stop")

        foreach ($hookType in $hookTypes) {
            if ($hooks.hooks.$hookType) {
                foreach ($hook in $hooks.hooks.$hookType) {
                    if ($hook.command -notmatch "cursor-otel-hook") {
                        $isOurHooksOnly = $false
                        break
                    }
                }
            }
            if (!$isOurHooksOnly) { break }
        }

        if ($isOurHooksOnly -or $Force) {
            Remove-Item -Path $HooksJson -Force
            Write-Log "Removed: $HooksJson"
        } else {
            Write-Log "hooks.json contains other hooks, not removing"
            Write-Log "Use -Force to remove anyway, or manually edit the file"
        }
    } catch {
        Write-Log "WARNING: Could not parse hooks.json: $($_.Exception.Message)"
    }
}

# Remove hooks directory if empty
if ((Test-Path $UserHooksDir) -and ((Get-ChildItem $UserHooksDir | Measure-Object).Count -eq 0)) {
    Remove-Item -Path $UserHooksDir -Force
    Write-Log "Removed empty directory: $UserHooksDir"
}

Write-Log "=========================================="
Write-Log "User cleanup completed"
Write-Log "=========================================="
