# UX demo walkthrough (10 minutes)

## Setup

```powershell
cd MicroMarketResearch
.\.venv\Scripts\Activate.ps1
python scripts/seed_demo_data.py
python run.py
```

Open http://127.0.0.1:5000/dashboards/sales

## 1. Team baseline (2 min)

- Sidebar → **UI demo preset** → **Team baseline (main-style)**
- Point at: only three dashboards; period chips = This Week / Last Week
- Say: “This is what `main` felt like—same Sync Now, same Clover path.”

## 2. Dashboard refresh (2 min)

- Preset → **Dashboard refresh**
- Click **30d**, **Semester** on Sales
- Open Inventory and Profit—same filter bar
- Open **Margins** from Analysis

## 3. Insights core (3 min)

- Preset → **Insights (core)**
- Open **Insights**
- Show: WoW tile, day-of-week chart, reorder table, CSV button

## 4. Insights full (3 min)

- Preset → **Insights (full)**
- Show: forecast + stockout KPIs, category mix, exam event dropdown
- Settings → academic calendar (optional)

## Data freshness (30 sec)

- Sidebar footer: last sync time
- Click **Sync Now** (needs valid Clover `.env`) → modal → **Close & Refresh**
- Note: without sync, F5 only re-reads the local DB

## Shareable URLs

- `?ux=team_main`
- `?ux=dashboards_plus`
- `?ux=insights_core`
- `?ux=insights_full`
