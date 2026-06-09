param(
    [switch]$SkipConfigCheck
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv312\Scripts\python.exe"

if (!(Test-Path $Python)) {
    Write-Host "Creating Python 3.12 virtual environment..."
    py -3.12 -m venv (Join-Path $Root ".venv312")
}

Write-Host "Installing dependencies..."
& $Python -m pip install -r (Join-Path $Root "requirements.txt")

if (!(Test-Path (Join-Path $Root ".env"))) {
    Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env")
    Write-Error ".env was created from .env.example. Fill real credentials, then rerun this script."
}

if (!$SkipConfigCheck) {
    & $Python (Join-Path $Root "scripts\check_config.py") --check-db
}

Write-Host "Starting Telegram shop bot..."
& $Python (Join-Path $Root "run.py")
