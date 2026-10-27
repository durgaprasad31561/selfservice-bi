# Run backend (pytest) and frontend (Vitest) test suites.
. "$PSScriptRoot\_common.ps1"
Assert-Venv
Write-Host "== Backend tests (pytest) ==" -ForegroundColor Cyan
Push-Location $Backend
try { Invoke-Checked $VenvPython @("-m", "pytest", "-q", "tests", "--ignore=tests/eval") } finally { Pop-Location }
Write-Host "== Frontend tests (Vitest) ==" -ForegroundColor Cyan
Push-Location $Frontend
try { Invoke-Checked "npm" @("run", "test", "--", "--run") } finally { Pop-Location }
Write-Host "All tests passed." -ForegroundColor Green
