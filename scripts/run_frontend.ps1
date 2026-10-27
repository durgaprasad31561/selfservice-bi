# Start the React (Vite) dev server on http://localhost:5173.
. "$PSScriptRoot\_common.ps1"
Push-Location $Frontend
try { Invoke-Checked "npm" @("run", "dev", "--", "--port", "5173") } finally { Pop-Location }
