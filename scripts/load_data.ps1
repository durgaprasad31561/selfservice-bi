# Load the Olist CSVs from data\ into PostgreSQL (raw + analytics schemas). Idempotent.
. "$PSScriptRoot\_common.ps1"
Assert-Venv
Invoke-Checked $VenvPython (@((Join-Path $Root "database\load_data.py")) + $args)
