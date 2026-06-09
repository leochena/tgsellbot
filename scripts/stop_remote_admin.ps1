param(
    [int]$AdminPort = 9090,
    [int]$LocalDbPort = 15432
)

$ErrorActionPreference = "Stop"

Get-NetTCPConnection -LocalPort $AdminPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object {
        Write-Host "Stopping local admin process PID $_"
        Stop-Process -Id $_ -Force
    }

$Root = Split-Path -Parent $PSScriptRoot
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*$Root\run_admin.py*" } |
    ForEach-Object {
        Write-Host "Stopping stale local admin process PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force
    }

Get-CimInstance Win32_Process -Filter "Name = 'ssh.exe'" |
    Where-Object { $_.CommandLine -like "*127.0.0.1:$LocalDbPort`:127.0.0.1:5432*" } |
    ForEach-Object {
        Write-Host "Stopping SSH tunnel PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force
    }
