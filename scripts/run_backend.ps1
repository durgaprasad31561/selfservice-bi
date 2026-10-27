# Start the FastAPI backend with auto-reload on http://localhost:8000 (docs at /docs).
. "$PSScriptRoot\_common.ps1"
Assert-Venv
Push-Location $Backend
try {
    Invoke-Checked $VenvPython @("-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000")
} finally { Pop-Location }
