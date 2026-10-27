# One-time setup: Python venv, backend packages, frontend packages, .env, database + roles.
. "$PSScriptRoot\_common.ps1"

Write-Host "== 1/5 Checking Python 3.11+ ==" -ForegroundColor Cyan
$py = $null
foreach ($v in @("3.12", "3.11", "3.13")) {
    & py "-$v" -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = @("py", "-$v"); break }
}
if (-not $py) { $py = @("python") }
Write-Host "Using: $($py -join ' ')"

Write-Host "== 2/5 Creating backend virtual environment ==" -ForegroundColor Cyan
if (-not (Test-Path $VenvPython)) {
    $pyArgs = @()
    if ($py.Length -gt 1) { $pyArgs = $py[1..($py.Length - 1)] }
    Invoke-Checked $py[0] ($pyArgs + @("-m", "venv", (Join-Path $Backend ".venv")))
}
Invoke-Checked $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked $VenvPython @("-m", "pip", "install", "-r", (Join-Path $Backend "requirements.txt"))

Write-Host "== 3/5 Installing frontend packages ==" -ForegroundColor Cyan
Push-Location $Frontend
try { Invoke-Checked "npm" @("install") } finally { Pop-Location }

Write-Host "== 4/5 Checking .env ==" -ForegroundColor Cyan
$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $Root ".env.example") $envFile
    Write-Host "Created .env from .env.example. Edit it (PostgreSQL password, API key), then re-run this script." -ForegroundColor Yellow
    exit 0
}

Write-Host "== 5/5 Creating database, schemas and roles ==" -ForegroundColor Cyan
Invoke-Checked $VenvPython @((Join-Path $PSScriptRoot "setup_db.py"))

Write-Host "Setup complete. Next: scripts\load_data.ps1" -ForegroundColor Green
