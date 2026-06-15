# Clover API — team runbook

**Source of truth:** working production tests for **NSC MICRO MARKET** (`H9XRT0SG797A1`).

## `.env` (repo root, not committed)

```env
CLOVER_API_TOKEN=your_clover_api_token
CLOVER_MERCHANT_ID=H9XRT0SG797A1
CLOVER_BASE_URL=https://api.clover.com
FLASK_SECRET_KEY=your_secret
```

`CLOVER_MERCHANT_ID` must match the `id` returned by `GET /v3/merchants/current` for your token.  
For NSC MICRO MARKET that id is **`H9XRT0SG797A1`** (note `0` not letter `O`).

---

## Step 1 — Token smoke test (team verified)

Run from repo root:

```powershell
cd MicroMarketResearch
.\scripts\test_clover_token.ps1
```

Or paste manually (same as team):

```powershell
$TOKEN = "your_clover_api_token"
$H = @{
    Authorization = "Bearer $TOKEN"
    Accept        = "application/json"
}

Write-Host "Testing token against merchants/current..."

try {
    $merchant = Invoke-RestMethod `
        -Uri "https://api.clover.com/v3/merchants/current" `
        -Headers $H `
        -Method Get

    Write-Host "SUCCESS"
    $merchant | ConvertTo-Json -Depth 10
}
catch {
    Write-Host "FAILED"
    Write-Host $_.Exception.Message
}
```

**Success:** JSON with `"id": "H9XRT0SG797A1"`, `"name": "NSC MICRO MARKET"`.

Python equivalent:

```powershell
python scripts/check_clover_connection.py
```

---

## Step 2 — Catalog / orders (team script)

After Step 1 passes, set `$MID` from the `id` field (or `.env`):

```powershell
$TOKEN = $env:CLOVER_API_TOKEN   # or paste token
$MID   = "H9XRT0SG797A1"
$BASE  = "https://api.clover.com"
$H     = @{ Authorization = "Bearer $TOKEN"; Accept = "application/json" }

# Categories
Invoke-RestMethod "$BASE/v3/merchants/$MID/categories?limit=1000&offset=0" -Headers $H

# Items (with stock)
Invoke-RestMethod "$BASE/v3/merchants/$MID/items?limit=1000&offset=0&expand=itemStock" -Headers $H

# Orders (set your own timestamps in ms)
$START = 1748649600000   # example: 2025-05-31 00:00:00 UTC
$END   = 1748735999000   # example: 2025-05-31 23:59:59 UTC
Invoke-RestMethod "$BASE/v3/merchants/$MID/orders?limit=1000&offset=0&filter=createdTime>=$START&filter=createdTime<=$END&expand=lineItems" -Headers $H

# Line Items for a specific order
$ORDER_ID = "your_order_id"
Invoke-RestMethod "$BASE/v3/merchants/$MID/orders/$ORDER_ID/line_items?limit=1000&offset=0&expand=item" -Headers $H

# Item Stocks
Invoke-RestMethod "$BASE/v3/merchants/$MID/item_stocks?limit=1000&offset=0" -Headers $H

# Payments
Invoke-RestMethod "$BASE/v3/merchants/$MID/payments?limit=1000&offset=0&filter=createdTime>=$START&filter=createdTime<=$END" -Headers $H
```

Full copy: [`scripts/clover_api_reference.ps1`](../scripts/clover_api_reference.ps1)

---

## Step 3 — Load data into the app

```powershell
python scripts/seed_sandbox.py --days 90 --mode full
python run.py
```

Open http://127.0.0.1:5000/dashboards/sales

---

## Python ETL mapping

| Team call | Python |
|-----------|--------|
| `merchants/current` | `client.get_current_merchant()` |
| `categories?limit=1000&offset=0` | `fetch_categories()` |
| `items?...&expand=itemStock` | `fetch_items()` |
| `orders?...&expand=lineItems` | `fetch_orders()` |
| `orders/{id}/line_items?...&expand=item` | `fetch_line_items()` |
| `item_stocks?...` | `fetch_item_stocks()` |
| `payments?...` | `fetch_payments()` |
