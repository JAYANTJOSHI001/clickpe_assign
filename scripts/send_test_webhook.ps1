# ==============================================================================
# Dispatch a test webhook payload directly to n8n Workflow B (PowerShell)
# Uses the fixed test batch seeded from sql/seed_test_users.sql
# Reads N8N_WEBHOOK_URL and N8N_WEBHOOK_SECRET from .env
# ==============================================================================

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
$envFile = Join-Path $rootDir ".env"

if (-not (Test-Path $envFile)) {
    Write-Error ".env file not found at $envFile"
    exit 1
}

# Parse .env file
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $val = $parts[1].Trim()
        [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
    }
}

$webhookUrl = $env:N8N_WEBHOOK_URL
$webhookSecret = $env:N8N_WEBHOOK_SECRET

if (-not $webhookUrl) {
    Write-Error "N8N_WEBHOOK_URL is not set in .env"
    exit 1
}
if (-not $webhookSecret) {
    Write-Error "N8N_WEBHOOK_SECRET is not set in .env"
    exit 1
}

Write-Host "Sending test webhook to: $webhookUrl"

$body = @{
    batch_id       = "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
    user_count     = 30
    rejected_count = 0
    filename       = "uploads/seed_test_users.csv"
} | ConvertTo-Json

$headers = @{
    "Content-Type"     = "application/json"
    "X-Webhook-Secret" = $webhookSecret
}

try {
    $response = Invoke-RestMethod -Uri $webhookUrl -Method Post -Headers $headers -Body $body
    Write-Host "SUCCESS: Test webhook accepted by n8n."
    Write-Host "Response: $($response | ConvertTo-Json -Compress)"
}
catch {
    Write-Error "FAILED: Webhook request failed: $_"
    exit 1
}
