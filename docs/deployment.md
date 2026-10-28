# Free deployment guide

Deploy the whole system for **$0** using free tiers:

| Part | Service (free plan) | What runs there |
|---|---|---|
| Database | **Neon** | PostgreSQL with the `analytics` model (~165 MB after loading) and the `app` tables |
| Backend | **Render** (free web service) | FastAPI (`backend/`), started from `render.yaml` |
| Frontend | **Vercel** (Hobby) | The React build (`frontend/`) |
| AI | **Groq** (free tier) | The LLM, via your existing `GROQ_API_KEY` |

```mermaid
flowchart LR
    U([Browser]) --> V[Vercel<br/>React app]
    V -- "HTTPS /api" --> R[Render<br/>FastAPI]
    R -- "read-only role" --> N[(Neon<br/>PostgreSQL)]
    R --> G[Groq API]
```

Time needed: about 45 minutes. Free plans change over time - check each provider's pricing
page if something below does not match what you see.

---

## 0. Before you start

- The project runs locally (`scripts\run_backend.ps1` works) and the Olist CSVs are in `data\`.
- Accounts (all free; signing in with GitHub is easiest): **GitHub**, **Neon** (neon.tech),
  **Render** (render.com), **Vercel** (vercel.com). Keep your **Groq API key** at hand.

## 1. Put the code on GitHub

1. On github.com create a new repository, e.g. `selfservice-bi` (private is fine).
2. In PowerShell, in the project folder:

   ```powershell
   git remote add origin https://github.com/<your-user>/selfservice-bi.git
   git branch -M main
   git push -u origin main
   ```

3. Check on GitHub that **`.env` is NOT in the repository** (it is git-ignored). The CSVs are
   not uploaded either; the data goes straight from your PC to Neon in step 3.

## 2. Create the database on Neon

1. Neon → **New project**. Name `selfservice-bi`, Postgres version **16 or newer**, region
   closest to you. Create.
2. Open **Connection details** (Dashboard → *Connect*):
   - Database: `neondb` (default), Role: the owner role shown (e.g. `neondb_owner`).
   - **Turn "Connection pooling" OFF** so you get the *direct* host (the host name must
     **not** contain `-pooler`).
   - Copy the connection string. It looks like
     `postgresql://neondb_owner:XXXX@ep-cool-name-123456.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
3. Choose a long random password for the read-only role, e.g. in PowerShell:

   ```powershell
   -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object {[char]$_})
   ```

## 3. Prepare the database and load the data (from your PC)

In PowerShell, in the project folder (use your own values):

```powershell
$OWNER = "postgresql://neondb_owner:XXXX@ep-cool-name-123456.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
$READER_PW = "your-24-char-reader-password"

# 3a. schemas + read-only role bi_reader
backend\.venv\Scripts\python.exe scripts\setup_cloud_db.py --owner-url $OWNER --reader-password $READER_PW

# 3b. clean + load the CSVs, build analytics, verify, then drop raw tables to stay small
backend\.venv\Scripts\python.exe database\load_data.py --database-url $OWNER --drop-raw
```

- 3a prints two lines, **`ADMIN_DATABASE_URL=...`** and **`READER_DATABASE_URL=...`**.
  Save them; you paste them into Render in step 4.
- 3b takes a few minutes over the internet and must end with
  **"All verification checks passed."** and a database size of about **165 MB**
  (Neon's free storage is 0.5 GB).

## 4. Deploy the backend on Render

1. Render → **New** → **Blueprint** → connect GitHub and select your repository.
   Render reads `render.yaml` and proposes the service **`selfservice-bi-api`** (free plan).
2. Fill in the values it asks for:

   | Variable | Value |
   |---|---|
   | `ADMIN_DATABASE_URL` | the `ADMIN_DATABASE_URL` line from step 3a |
   | `READER_DATABASE_URL` | the `READER_DATABASE_URL` line from step 3a |
   | `GROQ_API_KEY` | your Groq key |
   | `DEMO_ADMIN_PASSWORD` / `DEMO_ANALYST_PASSWORD` / `DEMO_VIEWER_PASSWORD` | `Admin@123`, `Analyst@123`, `Viewer@123` (or your own) |
   | `CORS_ORIGINS` | `http://localhost:5173` for now (fixed in step 6) |

   Everything else (`PYTHON_VERSION`, Groq models, a random `JWT_SECRET`, limits) is
   already set by the blueprint.
3. Click **Apply**. The first build takes ~5-10 minutes.
4. When it shows **Live**, open `https://selfservice-bi-api.onrender.com/api/health`
   (your URL may differ). You should see `"status":"ok"` with the database `ok: true` and
   `"provider":"groq"`. Interactive API docs: `.../docs`.

## 5. Deploy the frontend on Vercel

1. Vercel → **Add New… → Project** → import your repository.
2. Settings:
   - **Root Directory: `frontend`** (click *Edit* and choose the folder).
   - Framework preset: **Vite** (detected automatically; build `npm run build`, output `dist`).
   - **Environment Variables**: `VITE_API_BASE_URL` = your Render URL, e.g.
     `https://selfservice-bi-api.onrender.com` (no trailing slash).
3. **Deploy**. After ~1 minute you get a URL such as `https://selfservice-bi.vercel.app`.

## 6. Connect the two (CORS)

1. Render → your service → **Environment** → set
   `CORS_ORIGINS` = your Vercel URL, e.g. `https://selfservice-bi.vercel.app`
   (exact, no trailing slash; separate several URLs with commas).
2. **Save Changes** - Render redeploys automatically (~2 minutes).

## 7. Test it

1. Open your Vercel URL → sign in with a demo account (e.g. **Analyst**).
2. You should see the "Preparing your workspace" sequence, then the Overview with
   99.4K orders and 96.1K customers.
3. Ask: *"Show total sales in São Paulo in 2018"* → R$ 1,270,521.80.
4. Ask: *"What is our profit?"* → refused with the reason.

## 8. Updating later

`git push` to `main` → Render and Vercel both redeploy automatically.
If you change the data model (`database/*.sql`), re-run step 3b against Neon.

---

## Free-tier limits to know

| Service | Limit | What you notice |
|---|---|---|
| Render free | Sleeps after ~15 min without traffic; 750 instance-hours/month | The first request after a pause takes ~30-60 s (the sign-in preparation screen waits for it). |
| Neon free | 0.5 GB storage; compute scales to zero when idle | ~1 s extra on the first query after idling. The loaded data uses ~165 MB. |
| Groq free | Requests/tokens per minute and per day | Back-to-back questions may wait a few seconds; the app waits and retries automatically. |
| Vercel Hobby | Personal, non-commercial use | Nothing for this project. |

**Before a demo:** open `https://<your-render-url>/api/health` a minute in advance to wake
the backend. Optionally, a free uptime monitor (e.g. UptimeRobot) pinging `/api/health`
every 10 minutes keeps it awake; one always-on service stays within 750 hours/month.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Browser console: *CORS policy* error | `CORS_ORIGINS` on Render must equal the Vercel URL exactly (https, no trailing slash). |
| Sign-in says "Cannot reach the server" | `VITE_API_BASE_URL` missing/wrong on Vercel → set it and **Redeploy** (it is baked in at build time). Or the backend is still waking up - wait 60 s. |
| `/api/health` shows the database not ok / app logs "SSL" errors | Use the **direct** Neon host (no `-pooler`) and keep `?sslmode=require` at the end of both URLs. |
| `password authentication failed for user "bi_reader"` | `READER_DATABASE_URL` password differs from the one used in step 3a - re-run 3a with the same password, or update the variable. |
| Questions return "The AI model is not configured" | `GROQ_API_KEY` missing on Render. |
| Refreshing a page on Vercel gives 404 | Root Directory must be `frontend` so `frontend/vercel.json` (SPA rewrite) is used. |
| Render build fails on a package | Make sure `PYTHON_VERSION` is `3.12.10` (set by the blueprint; also `backend/.python-version`). |
| Loader stops with "VERIFICATION FAILED" | Do not use `--drop-raw` until the cause is fixed; re-run step 3b. |

## Security notes

- Secrets live only in the Render/Vercel dashboards and your local `.env`, never in git.
- User queries run as `bi_reader`: SELECT on `analytics` only, read-only by default, with
  statement timeouts - the same guarantees as locally (verified by `setup_cloud_db.py`'s grants).
- The demo passwords are shown on the login page. For a private deployment, set your own
  `DEMO_*_PASSWORD` values on Render (or create real users on the Admin page and change the
  demo users' roles/deactivate them).
