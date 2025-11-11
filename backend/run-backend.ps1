param(
    [string]$SinceFast = "2025-11-01",
    [string]$SinceSlow = "2025-10-01",
    [string]$SinceWeekly = "2023-01-01",
    [switch]$SkipServer
)

Set-Location "$PSScriptRoot"

function Run-Step {
    param([string]$cmd)
    Write-Host ">>> $cmd" -ForegroundColor Cyan
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host " Error en: $cmd" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

$steps = @(
    "python -m app.scripts.backfill --interval 15m --since $SinceFast",
    "python -m app.scripts.backfill --interval 30m --since $SinceFast",
    "python -m app.scripts.backfill --interval 1h --since $SinceFast",
    "python -m app.scripts.backfill --interval 4h --since $SinceSlow",
    "python -m app.scripts.backfill --interval 1d --since $SinceFast",
    "python -m app.scripts.backfill --interval 1w --since $SinceWeekly",
    "python -m app.scripts.curate --interval all",
    "python -m app.scripts.regenerate_signal"
)

foreach ($cmd in $steps) {
    Run-Step $cmd
}

if (-not $SkipServer) {
    Run-Step "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
}
