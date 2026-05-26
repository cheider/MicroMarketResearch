# Main branch merge checklist

Reference copy of team `main` lives at:

`../backup_of_micromarket/MicroMarketResearch`

## Merge steps

```powershell
cd MicroMarketResearch
git fetch origin
git checkout your-branch
git merge origin/main
```

## Conflict resolution (API paramount)

| Path | Rule |
|------|------|
| `app/clover/*` | Prefer **main** |
| `app/etl/*` | Prefer **main** |
| `app/config.py` | Prefer **main** for Clover keys; keep new keys (`AUTO_SYNC_*`, `UX_VARIANT_*`) if additive |
| `app/routes/ingest.py`, `scripts/seed_sandbox.py` | Prefer **main** |
| `app/templates/*`, `app/routes/insights.py`, `app/analysis/*`, `app/ux/*` | Keep **your** UX/analytics work |
| `tests/*` | Merge both; run `pytest -v` |

## Verify

```powershell
python scripts/verify_post_merge.py
python scripts/verify_post_merge.py --main-dir "../backup_of_micromarket/MicroMarketResearch"
pytest -v
```

With a team-valid `.env`:

```powershell
python scripts/check_clover_connection.py
python scripts/seed_sandbox.py --days 7 --mode incremental
```

## What main had vs your branch

- **Main:** Sidebar = Sales, Inventory, Profit, Settings, Sync. Sales period = This Week / Last Week only. No Insights route in nav.
- **Your branch:** Adds Analysis section, unified period presets, Insights hub, calendar in Settings. Clover client matches main (Bearer + `/v3/merchants/{id}/...`).

UX variants let you demo **team_main** without removing code.
