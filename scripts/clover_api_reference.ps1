# Canonical Clover REST smoke tests (production).
# Set CLOVER_API_TOKEN and CLOVER_MERCHANT_ID in .env, or fill in below.
# Python ETL uses the same paths/params via app/clover/query_params.py.

$TOKEN = $env:CLOVER_API_TOKEN
$MID   = $env:CLOVER_MERCHANT_ID
$BASE  = if ($env:CLOVER_BASE_URL) { $env:CLOVER_BASE_URL } else { "https://api.clover.com" }
$H     = @{ Authorization = "Bearer $TOKEN"; Accept = "application/json" }

if (-not $TOKEN -or -not $MID) {
    Write-Error "Set CLOVER_API_TOKEN and CLOVER_MERCHANT_ID (e.g. from .env)"
    exit 1
}

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
