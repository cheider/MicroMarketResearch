# Team token smoke test — GET /v3/merchants/current (production).
# Loads CLOVER_API_TOKEN from repo .env when run from MicroMarketResearch root.
# See docs/CLOVER_API.md

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $RepoRoot ".env"

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            Set-Item -Path "env:$($matches[1].Trim())" -Value $matches[2].Trim()
        }
    }
}

$TOKEN = $env:CLOVER_API_TOKEN
if (-not $TOKEN) {
    Write-Error "Set CLOVER_API_TOKEN in .env or assign `$TOKEN before running."
    exit 1
}

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
    Write-Host "  Merchant ID:   $($merchant.id)"
    Write-Host "  Merchant name: $($merchant.name)"
    if ($env:CLOVER_MERCHANT_ID -and $env:CLOVER_MERCHANT_ID -ne $merchant.id) {
        Write-Warning "CLOVER_MERCHANT_ID in .env ($($env:CLOVER_MERCHANT_ID)) does not match token merchant ($($merchant.id))"
    }
    $merchant | ConvertTo-Json -Depth 5
}
catch {
    Write-Host "FAILED"
    Write-Host $_.Exception.Message

    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader(
            $_.Exception.Response.GetResponseStream()
        )
        $reader.BaseStream.Position = 0
        $reader.DiscardBufferedData()
        $reader.ReadToEnd()
    }
    exit 1
}
