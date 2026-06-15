# UI options (demo presets)

The sidebar **UI demo preset** dropdown switches between four layouts so you can compare what shipped on `main` with what we added—without maintaining separate branches for a presentation.

Data does **not** auto-update from Clover on a timer unless you turn that on in `.env` (see below). Numbers come from the local database after the last successful **Sync Now**. Refresh the page to see the latest SQLite aggregates.

## Presets

### Team baseline (main-style)

Matches how the repo looked on `main` for navigation and period chips.

- Dashboards only: Sales, Inventory, Profit
- Period filters: **This Week** and **Last Week** (no 30d / 90d / semester on dashboards)
- No Insights link (the route still exists if you type the URL; you get redirected to Sales)

Use this to show the team nothing broke their Clover workflow.

### Dashboard refresh

Everything in the baseline, plus:

- Full period presets on Sales, Inventory, Profit (7d, 30d, 90d, semester, prior week)
- Margins, Shrinkage, Velocity back in the sidebar

Still no Insights page in the nav—good for “we improved dashboards first.”

### Insights (core)

Adds the **Insights** page with:

- Week-over-week revenue
- Average revenue by day of week (chart)
- Reorder suggestions table + CSV export

Hides forecast, stockout risk, category mix, and exam-week comparison—less clutter for a first walkthrough.

### Insights (full) — default

The full capstone view:

- All core Insights blocks
- 14-day revenue forecast and stockout risk KPIs
- Category mix shift table
- Academic calendar event comparison and top sellers during an event

## Why these options matter for the micro market

We are not building this only to maximize profit. The market exists so students have convenient food on campus. The UI options line up with that:

| Area | What it helps with |
|------|-------------------|
| Period filters | See a real week or a full semester without exporting spreadsheets |
| Profit / margins | Protect average margin; spot categories that drag it down |
| Shrinkage | Less waste from product that never moves |
| Velocity / sales | Stock what students actually buy |
| Insights reorder | Popular items stay on the shelf |
| Day-of-week chart | Staffing and ordering match when students shop |
| Calendar / exam uplift | Set quarter start/end in Settings; app estimates midterm and finals weeks |
| Category mix | Keep the assortment feeling like one market—not random one-offs; when you run a special, you can see if the rest of the mix supports it or dilutes it |

## When numbers update

1. **Sync Now** pulls from Clover into `analytics.db` (same as `main`).
2. **Reload the page**—Flask recomputes charts and KPIs from SQLite.
3. Optional: set `AUTO_SYNC_INTERVAL_MINUTES=5` in `.env` to run incremental sync in the background while `python run.py` is running. Default is `0` (off).

The sidebar shows a short **last synced** timestamp so you know how fresh the view is.

## Try a preset in the browser

1. `python scripts/seed_demo_data.py` (or run a real sync)
2. `python run.py`
3. Use the **UI demo preset** dropdown above Settings
4. Or add `?ux=insights_core` to any URL when screen-sharing

See [UX_DEMO_WALKTHROUGH.md](UX_DEMO_WALKTHROUGH.md) for a step-by-step demo script.
