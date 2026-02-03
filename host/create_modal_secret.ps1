# Load .env file
Get-Content .env | ForEach-Object {
    if ($_ -notmatch '^\s*#' -and $_ -match '^([^=]+)=["'']?([^"'']+)["'']?$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        [System.Environment]::SetEnvironmentVariable($key, $value, 'Process')
        Write-Host "Loaded: $key"
    }
}

Write-Host "`n=== Deploying Modal Secrets ===`n"

# Delete old secret (suppress errors if doesn't exist)
Write-Host "Removing old secrets (if any)..."
& modal secret delete my-secrets --yes 2>$null

# Create new secret with environment variables
Write-Host "Creating new secret 'my-secrets'..."

$secretArgs = @(
    'secret', 'create', 'my-secrets'
)

# Add each variable if it exists
$variables = @('GH_TOKEN', 'HF_TOKEN', 'CLOUDFLARED_TOKEN', 'SSH_KEY')
foreach ($var in $variables) {
    $value = [System.Environment]::GetEnvironmentVariable($var, 'Process')
    if ($value) {
        $secretArgs += "$var=$value"
        Write-Host "  - Added $var"
    } else {
        Write-Host "  - Skipped $var (not found in .env)" -ForegroundColor Yellow
    }
}

# Execute modal command
& modal @secretArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Secrets deployed successfully!" -ForegroundColor Green
    Write-Host "`nVerify with: modal secret list`n"
} else {
    Write-Host "`n❌ Failed to deploy secrets" -ForegroundColor Red
    exit 1
}
