# Shared helpers for the project scripts. Dot-source with: . "$PSScriptRoot\_common.ps1"
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"

function Assert-Venv {
    if (-not (Test-Path $VenvPython)) {
        throw "Python virtual environment not found at $VenvPython. Run scripts\setup.ps1 first."
    }
}

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Exe $($Arguments -join ' ')" }
}
