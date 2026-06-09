param(
    [string]$Server = $env:TGS_REMOTE_SERVER,
    [string]$KeyPath = $env:TGS_REMOTE_KEY_PATH,
    [int]$LocalDbPort = 15432,
    [int]$AdminPort = 9090
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Server)) {
    throw "Pass -Server or set TGS_REMOTE_SERVER."
}
if ([string]::IsNullOrWhiteSpace($KeyPath)) {
    throw "Pass -KeyPath or set TGS_REMOTE_KEY_PATH."
}

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv312\Scripts\python.exe"

Get-NetTCPConnection -LocalPort $AdminPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object {
        Write-Host "Stopping existing local admin process PID $_"
        Stop-Process -Id $_ -Force
    }

Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*$Root\run_admin.py*" } |
    ForEach-Object {
        Write-Host "Stopping stale local admin process PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force
    }

Get-CimInstance Win32_Process -Filter "Name = 'ssh.exe'" |
    Where-Object { $_.CommandLine -like "*127.0.0.1:$LocalDbPort`:127.0.0.1:5432*" } |
    ForEach-Object {
        Write-Host "Stopping existing SSH database tunnel PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force
    }

$SshArgs = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "ExitOnForwardFailure=yes",
    "-o", "ServerAliveInterval=30",
    "-N",
    "-L", "127.0.0.1:$LocalDbPort`:127.0.0.1:5432",
    "root@$Server"
)

if (!(Test-Path $Python)) {
    Write-Host "Creating Python 3.12 virtual environment..."
    py -3.12 -m venv (Join-Path $Root ".venv312")
}

Write-Host "Installing dependencies..."
& $Python -m pip install -r (Join-Path $Root "requirements.txt")

Write-Host "Reading remote database settings..."
$RemoteEnv = ssh -i $KeyPath -o BatchMode=yes "root@$Server" "python3 - <<'PY'
from pathlib import Path
keys = {
    'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_SCHEMA',
    'PAY_CURRENCY', 'BALANCE_CURRENCY', 'STARS_PER_VALUE'
}
for raw in Path('/opt/tgsellbot/.env').read_text(encoding='utf-8').splitlines():
    if '=' not in raw or raw.lstrip().startswith('#'):
        continue
    key, value = raw.split('=', 1)
    if key in keys:
        print(f'{key}={value}')
PY"

$RemoteValues = @{}
foreach ($Line in $RemoteEnv) {
    if ($Line -match '^([^=]+)=(.*)$') {
        $RemoteValues[$Matches[1]] = $Matches[2]
    }
}

foreach ($Name in @("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")) {
    if (!$RemoteValues.ContainsKey($Name) -or [string]::IsNullOrWhiteSpace($RemoteValues[$Name])) {
        throw "Remote $Name is missing."
    }
}

Write-Host "Opening SSH database tunnel on 127.0.0.1:$LocalDbPort..."
Start-Process -FilePath "ssh" -ArgumentList $SshArgs -WindowStyle Hidden
$TunnelReady = $false
for ($Attempt = 1; $Attempt -le 10; $Attempt++) {
    $TestClient = [System.Net.Sockets.TcpClient]::new()
    try {
        $Task = $TestClient.ConnectAsync("127.0.0.1", $LocalDbPort)
        if ($Task.Wait(2000) -and $TestClient.Connected) {
            $TunnelReady = $true
            break
        }
    } catch {
        if ($Attempt -eq 10) {
            throw "Cannot connect to SSH database tunnel on 127.0.0.1:$LocalDbPort. $($_.Exception.Message)"
        }
    } finally {
        $TestClient.Dispose()
    }
    Start-Sleep -Milliseconds 500
}
if (!$TunnelReady) {
    throw "Cannot connect to SSH database tunnel on 127.0.0.1:$LocalDbPort."
}

$env:TOKEN = "local-admin-no-bot"
$env:OWNER_ID = "1"
$env:POSTGRES_DB = $RemoteValues["POSTGRES_DB"]
$env:POSTGRES_USER = $RemoteValues["POSTGRES_USER"]
$env:POSTGRES_PASSWORD = $RemoteValues["POSTGRES_PASSWORD"]
$env:POSTGRES_HOST = "127.0.0.1"
$env:DB_PORT = [string]$LocalDbPort
$env:POSTGRES_SCHEMA = $RemoteValues["POSTGRES_SCHEMA"]
if ([string]::IsNullOrWhiteSpace($env:POSTGRES_SCHEMA)) {
    $env:POSTGRES_SCHEMA = "public"
}
$env:REDIS_ENABLED = "0"
$env:WEB_ADMIN_ENABLED = "1"
$env:WEBHOOK_ENABLED = "0"
$env:PAY_CURRENCY = if ($RemoteValues.ContainsKey("PAY_CURRENCY") -and $RemoteValues["PAY_CURRENCY"]) { $RemoteValues["PAY_CURRENCY"] } else { "USD" }
$env:BALANCE_CURRENCY = if ($RemoteValues.ContainsKey("BALANCE_CURRENCY") -and $RemoteValues["BALANCE_CURRENCY"]) { $RemoteValues["BALANCE_CURRENCY"] } else { $env:PAY_CURRENCY }
$env:STARS_PER_VALUE = if ($RemoteValues.ContainsKey("STARS_PER_VALUE") -and $RemoteValues["STARS_PER_VALUE"]) { $RemoteValues["STARS_PER_VALUE"] } else { "0.91" }
$env:ADMIN_HOST = "127.0.0.1"
$env:ADMIN_PORT = [string]$AdminPort
$env:ADMIN_SESSION_MAX_AGE_DAYS = "30"
$env:BOT_LOCALE = "zh"
$env:LOG_TO_STDOUT = "1"
$env:LOG_TO_FILE = "0"

Write-Host "Starting local web admin only. No Telegram polling will run."
Write-Host "Admin:  http://localhost:$AdminPort/admin/login"
Write-Host "Product operations: http://localhost:$AdminPort/admin/operations"
& $Python (Join-Path $Root "run_admin.py")
