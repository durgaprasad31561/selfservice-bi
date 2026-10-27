# Run the evaluation set through the real pipeline; writes docs\evaluation_report.md.
. "$PSScriptRoot\_common.ps1"
Assert-Venv
Push-Location $Backend
try { Invoke-Checked $VenvPython (@("-m", "tests.eval.run_eval") + $args) } finally { Pop-Location }
