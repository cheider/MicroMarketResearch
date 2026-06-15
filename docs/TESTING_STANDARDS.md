# Testing standards

How we test MicroMarketResearch without damaging local data, calling Clover unnecessarily, or leaving side effects behind.

## Goals

| Goal | How we meet it |
|------|----------------|
| **Reversible** | Automated tests use a **temporary SQLite file** that is deleted after each test session. No writes to `analytics.db` during `pytest`. |
| **No data damage** | Production/dev DB (`DB_PATH` / `analytics.db`) is never opened by the default test suite. Destructive scripts are **manual only**. |
| **No unnecessary pulls** | `pytest` does **not** call the Clover API. HTTP is mocked (`unittest.mock.patch` on `requests`). Live ingest is **Layer 6** in [VERIFICATION.md](VERIFICATION.md), run only when you choose. |

## What is safe to run (default workflow)

```powershell
pytest -v
```

- Uses `tests/conftest.py` → `tempfile.mkstemp(suffix=".db")` per test app fixture.
- `TestConfig` token is fake (`test-token`); merchant `test-merchant`.
- Ingest route tests swap in `MagicMock()` for `clover_client` — **zero network**.
- Settings POST tests monkeypatch `set_key` — **`.env` is not modified**.
- Golden/seasonal tests seed an isolated temp DB via `tests/test_helpers.seed_demo_pattern()`.

**After `pytest`:** your real `analytics.db`, `.env`, and Clover data are unchanged.

## What is NOT part of automated tests

| Command / action | Risk | When to use |
|------------------|------|-------------|
| `python scripts/seed_sandbox.py` | Network + **overwrites/updates** `analytics.db` | Manual verification with valid `.env` |
| `python scripts/seed_demo_data.py` | **Deletes** demo tables then repopulates `analytics.db` | Local UI demo only; backup first if unsure |
| `python scripts/check_clover_connection.py` | Single Clover GET (minimal pull) | Credential check only |
| `Sync Now` in browser | Background ingest against live API | Operator-driven |
| `pytest -m live` | Reserved for opt-in live tests (none by default) | Only if explicitly marked and approved |

## Reversibility checklist

Before running anything that touches `analytics.db`:

1. **Backup (optional):** `copy analytics.db analytics.db.bak` (PowerShell: `Copy-Item analytics.db analytics.db.bak`)
2. Run the script or sync.
3. To undo: stop the app, restore the backup file, or re-run a known-good `seed_sandbox.py` / `seed_demo_data.py`.

`pytest` never requires step 1–3 for normal development.

## Writing new tests

### Required patterns

1. **Database:** Use the `app` / `client` fixtures from `conftest.py`. Do not point `Config.DB_PATH` at `analytics.db` in tests.
2. **Clover:** Mock `app.extensions["clover_client"]` or patch `Session.get` — never call production/sandbox URLs in tests.
3. **Filesystem:** Do not read/write `.env` in tests without monkeypatching `dotenv.set_key` (see `test_routes.py`).
4. **Time:** Monkeypatch `app.analysis.periods.today` for date-bound assertions (see `test_analytics_golden.py`).
5. **Scope:** Prefer unit tests on `app/analysis/*` functions; add one route smoke test per new page.

### Forbidden in default tests

- Real HTTP to `api.clover.com` or `apisandbox.dev.clover.com`
- Using `Config()` loaded from your real `.env` for integration tests
- Deleting or copying the developer’s `analytics.db`
- Committing tokens, merchant IDs, or PII in fixtures
- Broad `seed_sandbox.py` invocations from `conftest` or CI without an opt-in marker

### Opt-in live / integration tests (future)

If a test must hit Clover:

```python
import pytest

@pytest.mark.live
def test_sandbox_smoke():
    ...
```

Register in `pytest.ini`. **Do not** include `live` in default `pytest` runs:

```powershell
pytest -v -m "not live"
```

(Plain `pytest -v` is fine while no `live` tests exist.)

## Script safety classes

| Class | Examples | Touches `analytics.db`? | Network? |
|-------|----------|-------------------------|----------|
| **Safe automated** | `pytest` | No (temp file only) | No (mocked) |
| **Schema only** | `scripts/init_db.py` | Creates/alters schema; does not delete sales rows by itself | No |
| **Destructive local** | `seed_demo_data.py` | Yes (DELETE + INSERT) | No |
| **Live ETL** | `seed_sandbox.py`, Sync Now | Yes | Yes |
| **Read-only check** | `check_clover_connection.py` | No | One items GET |
| **API battery** | `run_clover_api_battery.py` | No | Seven minimal GETs; JSON report optional |
| **Auth probe** | `probe_clover_auth.py` | No | Raw GET matrix on prod + sandbox; run when battery 401s |

## Clover API battery (manual)

If the battery returns **401 on all checks**, run the auth probe first (same `.env`, no DB writes):

```powershell
python scripts/probe_clover_auth.py
```

This tests merchant root + items on both production and sandbox URLs and warns about quoted tokens or wrong merchant ID length.

Seven read-only probes (see `app/clover/health_checks.py`). Does not touch `analytics.db`.

```powershell
python scripts/run_clover_api_battery.py
python scripts/run_clover_api_battery.py --json logs/clover_battery_latest.json
```

Opt-in pytest (after battery passes locally):

```powershell
$env:RUN_CLOVER_API_TESTS = "1"
pytest tests/test_clover_api_live.py -v -m live
```

Compare production vs sandbox URL without editing `.env`:

```powershell
python scripts/run_clover_api_battery.py --base-url https://api.clover.com --json logs/battery_prod.json
python scripts/run_clover_api_battery.py --base-url https://apisandbox.dev.clover.com --json logs/battery_sandbox.json
python scripts/compare_clover_battery_reports.py logs/battery_prod.json logs/battery_sandbox.json
```

## Golden fixtures

- File: `tests/fixtures/golden_demo_expectations.json`
- Tied to `seed_demo_pattern(anchor_date)` — not to your live Clover data.
- Update JSON **only** when you intentionally change the demo seed algorithm.

## CI / agent guidance

- Run: `pytest -v` (and optionally `pytest -m "not live"` when live markers exist).
- Do **not** run `seed_sandbox.py` or `seed_demo_data.py` in unattended CI unless using a disposable DB path in `.env`.
- See [VERIFICATION.md](VERIFICATION.md) for layered manual checks after automated tests pass.

## Quick reference

```powershell
# Safe — run anytime
pytest -v

# Manual — mutates analytics.db
python scripts/seed_demo_data.py

# Manual — network + analytics.db
python scripts/seed_sandbox.py --days 90 --mode full

# Manual — one API call, no DB writes
python scripts/check_clover_connection.py
```
