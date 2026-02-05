# Process-Config.ps1
# Processes the configuration template with MDM values during MSI installation
# Called by WiX custom action

param(
    [Parameter(Mandatory=$true)]
    [string]$InstallDir,

    [Parameter(Mandatory=$false)]
    [string]$OtelEndpoint = "http://localhost:4318/v1/traces",

    [Parameter(Mandatory=$false)]
    [string]$ServiceName = "cursor-agent",

    [Parameter(Mandatory=$false)]
    [string]$OtelProtocol = "http/json",

    [Parameter(Mandatory=$false)]
    [string]$OtelInsecure = "false",

    [Parameter(Mandatory=$false)]
    [string]$MaskPrompts = "false",

    [Parameter(Mandatory=$false)]
    [string]$OtelTimeout = "30",

    [Parameter(Mandatory=$false)]
    [string]$OtelHeaders = "null"
)

$ErrorActionPreference = "Stop"

# Normalize InstallDir (remove trailing dot if present from WiX)
$InstallDir = $InstallDir.TrimEnd('.')

$LogFile = "$env:TEMP\cursor-otel-hook-install.log"

function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -Append -FilePath $LogFile -Encoding UTF8
}

Write-Log "=========================================="
Write-Log "Processing configuration template"
Write-Log "Install directory: $InstallDir"
Write-Log "=========================================="

try {
    $TemplatePath = Join-Path $InstallDir "otel_config.template.json"
    $OutputPath = Join-Path $InstallDir "otel_config.json"

    if (!(Test-Path $TemplatePath)) {
        Write-Log "ERROR: Template not found at $TemplatePath"
        exit 1
    }

    Write-Log "Reading template: $TemplatePath"
    $ConfigContent = Get-Content $TemplatePath -Raw

    # Log the values being applied
    Write-Log "Applying configuration:"
    Write-Log "  OTEL_ENDPOINT: $OtelEndpoint"
    Write-Log "  SERVICE_NAME: $ServiceName"
    Write-Log "  OTEL_PROTOCOL: $OtelProtocol"
    Write-Log "  OTEL_INSECURE: $OtelInsecure"
    Write-Log "  MASK_PROMPTS: $MaskPrompts"
    Write-Log "  OTEL_TIMEOUT: $OtelTimeout"
    Write-Log "  OTEL_HEADERS: $OtelHeaders"

    # Perform substitutions
    $ConfigContent = $ConfigContent -replace '\{\{OTEL_ENDPOINT\}\}', $OtelEndpoint
    $ConfigContent = $ConfigContent -replace '\{\{SERVICE_NAME\}\}', $ServiceName
    $ConfigContent = $ConfigContent -replace '\{\{OTEL_PROTOCOL\}\}', $OtelProtocol
    $ConfigContent = $ConfigContent -replace '\{\{OTEL_INSECURE\}\}', $OtelInsecure
    $ConfigContent = $ConfigContent -replace '\{\{MASK_PROMPTS\}\}', $MaskPrompts
    $ConfigContent = $ConfigContent -replace '\{\{OTEL_TIMEOUT\}\}', $OtelTimeout

    # Handle OTEL_HEADERS specially - it can be JSON or null
    if ($OtelHeaders -eq "null" -or [string]::IsNullOrWhiteSpace($OtelHeaders)) {
        $ConfigContent = $ConfigContent -replace '\{\{OTEL_HEADERS\}\}', 'null'
    } else {
        # Assume it's already valid JSON
        $ConfigContent = $ConfigContent -replace '\{\{OTEL_HEADERS\}\}', $OtelHeaders
    }

    # Write the processed configuration
    Write-Log "Writing configuration: $OutputPath"
    Set-Content -Path $OutputPath -Value $ConfigContent -Encoding UTF8

    Write-Log "Configuration processed successfully"

} catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    Write-Log "Stack trace: $($_.ScriptStackTrace)"
    # Don't fail the installation, just log the error
    # User can manually configure later
}

Write-Log "=========================================="
exit 0
