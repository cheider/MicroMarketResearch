# MicroMarketResearch

A Flask web application for analyzing point-of-sale data from a Clover POS micro-market. It pulls data from the Clover API, stores it locally in SQLite, and presents interactive dashboards for sales, inventory, and profit analysis.

## Architecture

```
Clover POS API
      │
      ▼
  ETL Pipeline (app/etl/)
  ├── ingest.py    — orchestrates API fetches
  ├── transform.py — normalizes & filters PII
  └── load.py      — writes to SQLite
      │
      ▼
  SQLite (analytics.db)
      │
      ▼
  Flask Dashboards (app/routes/)
  ├── Sales Dashboard
  ├── Inventory Turnover Dashboard
  ├── Profit Dashboard
  ├── Margins Analysis
  ├── Shrinkage Analysis
  └── Velocity Analysis
```

**Key modules:**

| Path | Purpose |
|---|---|
| `app/clover/` | Clover API client, paginator, endpoint definitions |
| `app/etl/` | Data ingestion, transformation, and loading pipeline |
| `app/analysis/` | Business logic for margins, shrinkage, and velocity |
| `app/routes/` | Flask blueprints for all web endpoints |
| `app/templates/` | Jinja2 HTML templates |

## Prerequisites

- Python 3.12+ (local run) **or** Docker (containerized run)
- Clover POS API credentials (API token + merchant ID)

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|---|---|---|
| `CLOVER_API_TOKEN` | Clover Bearer token | _(required)_ |
| `CLOVER_MERCHANT_ID` | Clover merchant ID | _(required)_ |
| `CLOVER_BASE_URL` | API base URL | `https://api.clover.com` |
| `FLASK_SECRET_KEY` | Flask session secret | _(required)_ |
| `ORDER_ID_HASH_SALT` | Salt for hashing order IDs | _(required)_ |
| `DB_PATH` | Path to SQLite database file | `analytics.db` |
| `MARGIN_ALERT_THRESHOLD` | Margin alert threshold (decimal) | `0.10` |

For sandbox/testing use `CLOVER_BASE_URL=https://apisandbox.dev.clover.com`.

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Start the app
python run.py
```

App will be available at `http://localhost:5000`.

## Running with Docker

### Build and run manually

```bash
# Build the image
docker build -t micromarket .

# Run the container
docker run -p 5000:5000 --env-file .env \
  -v $(pwd)/analytics.db:/app/analytics.db \
  -v $(pwd)/logs:/app/logs \
  micromarket
```

### Using Docker Compose (recommended)

```bash
# Start
docker compose up --build

# Start in background
docker compose up --build -d

# Stop
docker compose down
```

App will be available at `http://localhost:5000`.

> **Note:** The SQLite database (`analytics.db`) and logs are mounted as volumes so data persists between container restarts.

## Dashboards & Routes

| Route | Description |
|---|---|
| `/` | Redirects to sales dashboard |
| `/dashboards/sales` | Sales stats, category breakdown, top products |
| `/dashboards/sales/download` | CSV export of sales data |
| `/dashboards/inventory` | Stock levels, turnover by category, low stock alerts |
| `/dashboards/inventory/download` | CSV export of inventory data |
| `/dashboards/profit` | Profit margins, weekly trends |
| `/dashboards/profit/download` | CSV export of profit data |
| `/analysis/margins` | Items by margin band (negative / low / acceptable) |
| `/analysis/shrinkage` | Inventory loss vs. recorded sales |
| `/analysis/velocity` | Sales velocity (units/time) by product |
| `/item/<item_id>` | Individual product detail page |
| `/settings` | App configuration |

## Data Sync

Trigger a sync from the Settings page or via API:

```bash
# Full sync (all historical data)
curl -X POST http://localhost:5000/ingest \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "full"}'

# Incremental sync (new data since last sync)
curl -X POST http://localhost:5000/ingest \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "delta"}'

# Poll sync progress
curl http://localhost:5000/ingest/progress/<job_id>

# Check last sync status
curl http://localhost:5000/ingest/status
```

The sync pipeline fetches categories, items, orders, line items, stock levels, and payments from the Clover API in sequence, with automatic pagination (1000 records/page) and rate-limit retry logic.

## Project Structure

```
MicroMarketResearch/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── run.py                      # App entry point
├── app/
│   ├── __init__.py             # Flask app factory
│   ├── config.py               # Environment config
│   ├── database.py             # SQLite schema & connection
│   ├── clover/                 # Clover API client
│   │   ├── client.py
│   │   ├── endpoints.py
│   │   └── paginator.py
│   ├── etl/                    # Extract-Transform-Load
│   │   ├── ingest.py
│   │   ├── transform.py
│   │   └── load.py
│   ├── analysis/               # Business logic
│   │   ├── dashboard_analytics.py
│   │   ├── margins.py
│   │   ├── shrinkage.py
│   │   └── velocity.py
│   ├── routes/                 # Flask blueprints
│   └── templates/              # Jinja2 HTML templates
├── scripts/
│   ├── init_db.py              # Initialize database schema
│   └── seed_sandbox.py         # Seed sandbox with test data
└── tests/
```

## Running Tests

```bash
pytest
```
