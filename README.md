# Self-Service BI with a Semantic Layer and Natural-Language Queries

Ask questions about the Olist Brazilian e-commerce dataset in plain English. The system
interprets them through a YAML semantic layer, generates and validates SQL, runs it on a
read-only PostgreSQL connection, checks the result, and shows the answer as a KPI, chart or table.
If the data cannot answer a question, it says so and explains why.

> Full documentation is completed in Phase 9. Current status: **Phase 0 (project setup)**.

## Quick start (Windows, no Docker)

Prerequisites: Python 3.11–3.12 (`py` launcher), Node.js 20+, PostgreSQL 16+ running locally on port 5432.

```powershell
# 1. Create .env (first run copies .env.example and stops so you can edit it)
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# 2. Edit .env: POSTGRES_SUPERUSER_PASSWORD, GEMINI_API_KEY (or OPENAI_API_KEY)
# 3. Re-run setup: creates the venv, installs packages, creates bi_db + roles
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

| Script | Purpose |
|---|---|
| `scripts\setup.ps1` | venv, pip install, npm install, database + roles |
| `scripts\load_data.ps1` | Load CSVs into PostgreSQL |
| `scripts\run_backend.ps1` | FastAPI on http://localhost:8000 |
| `scripts\run_frontend.ps1` | React app on http://localhost:5173 |
| `scripts\test.ps1` | Backend + frontend tests |
| `scripts\eval.ps1` | Evaluation report |
