# MicroMarketResearch

NSC Micro Market capstone analytics: Clover ETL into SQLite, Flask dashboards, and margin/shrinkage/velocity reports.

## Quick start

```powershell
cd MicroMarketResearch
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Set FLASK_SECRET_KEY, CLOVER_API_TOKEN, CLOVER_MERCHANT_ID in .env
# ORDER_ID_HASH_SALT is optional (unused by current ETL; leave blank)
python scripts/init_db.py
pytest -v
```

Use the venv Python for all commands (`.\.venv\Scripts\python` or activate first). System `python` will not have Flask/dotenv installed.

**Local UI without Clover:** `python scripts/seed_demo_data.py` then `python run.py` → http://127.0.0.1:5000/dashboards/sales (Insights at `/analysis/insights`)

**Live Clover ETL:** set credentials in `.env`, `INGEST_LOOKBACK_DAYS=90`, then `python scripts/seed_sandbox.py --days 90 --mode full`

**Verification:** see [docs/VERIFICATION.md](docs/VERIFICATION.md)

**UI demo presets:** [docs/UX_OPTIONS.md](docs/UX_OPTIONS.md) — sidebar selector to compare main-style UI vs Insights (for team review).

**Merge with main:** [docs/MAIN_MERGE_CHECKLIST.md](docs/MAIN_MERGE_CHECKLIST.md)

## Testing standards

**Default command (safe, reversible):**

```powershell
pytest -v
```

- Uses a **temporary** SQLite database per test — does **not** read or write your `analytics.db`.
- Does **not** call the Clover API (HTTP is mocked).
- Does **not** modify `.env`.

**Manual only (mutates `analytics.db` or pulls from Clover):** `seed_demo_data.py`, `seed_sandbox.py`, browser **Sync Now**. Back up `analytics.db` first if you are unsure.

Full rules: **[docs/TESTING_STANDARDS.md](docs/TESTING_STANDARDS.md)**

**Clover API (read-only, minimal pulls):**

```powershell
python scripts/check_clover_connection.py
python scripts/probe_clover_auth.py
python scripts/run_clover_api_battery.py --json logs/clover_battery_latest.json
```

See `agent-guide-readme/08_CLOVER_API_TESTING.md` (local) for the 7-check battery, visualization options, and troubleshooting 401s.

## Layout

- `app/routes/` — Flask blueprints (dashboards, insights, ingest, analysis, settings)
- `app/analysis/` — periods, seasonal, projections, dashboards, margins, shrinkage, velocity
- `config/academic_calendar.json` — midterms, finals, breaks (overridable in Settings)
- `app/etl/` — Clover ingest, PII stripping, SQLite load
- `app/templates/` — Jinja + Bootstrap 5 UI
- `scripts/` — `init_db.py`, `seed_sandbox.py`, `seed_demo_data.py`
- `tests/` — pytest (`pytest.ini` sets `pythonpath = .`); see [tests/README.md](tests/README.md)
- `docs/TESTING_STANDARDS.md` — reversible tests, no data damage, no unnecessary API pulls
