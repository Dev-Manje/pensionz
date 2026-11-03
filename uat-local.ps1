<#
.SYNOPSIS
  Runs Pensionz UAT on this development machine, reachable from testers' machines on the network.
  UAT uses its own database (pensionz_uat) next to the dev one, so dev data is untouched. See UAT.md.

.EXAMPLE
  .\uat-local.ps1 reset            # fresh pensionz_uat database: tables + UAT data (about 3-5 minutes)
  .\uat-local.ps1 start            # API, worker and web app in UAT mode on this machine's network address
  .\uat-local.ps1 status           # what is running and the URLs to give testers
  .\uat-local.ps1 stop             # stop the API, worker and web app
  .\uat-local.ps1 dev              # back to normal development (dev database, localhost only)

  -Address 192.168.11.162          # the address testers use (default: this machine's LAN IPv4 address)
  -WebPort 5278                    # the web app's port in UAT mode (default 5278; dev mode uses 5178)

  Ports testers need: the web app (5278), the API (8002) and Mailpit (8026).
#>
param(
    [Parameter(Position = 0)][ValidateSet("reset", "start", "stop", "status", "dev")][string]$Command = "status",
    [string]$Address = "",
    # Port testers open the web app on (dev mode keeps 5178).
    [int]$WebPort = 5278
)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Py = Join-Path $Backend ".venv\Scripts\python.exe"
$Logs = Join-Path $env:TEMP "pensionz-uat"
$UatDb = "pensionz_uat"
New-Item -ItemType Directory -Force $Logs | Out-Null

function Say([string]$text) { Write-Host "==> $text" -ForegroundColor Cyan }

function Get-Address {
    if ($Address) { return $Address }
    $ip = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.PrefixOrigin -in @("Dhcp", "Manual") -and $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.InterfaceAlias -notlike "vEthernet*" } |
        Select-Object -First 1
    if (-not $ip) { throw "Couldn't find this machine's network address - pass -Address <ip or name>" }
    return $ip.IPAddress
}

function Get-DevDatabaseUrl {
    $line = Get-Content (Join-Path $Backend ".env") | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
    if (-not $line) { throw "backend\.env has no DATABASE_URL" }
    return $line.Substring("DATABASE_URL=".Length).Trim()
}

function Get-UatDatabaseUrl { return (Get-DevDatabaseUrl) -replace '/[^/]+$', "/$UatDb" }

function Set-UatEnv([string]$ip) {
    $env:DATABASE_URL = Get-UatDatabaseUrl
    $env:MINIO_PUBLIC_ENDPOINT = "http://$($ip):9002"
    $env:BACKEND_CORS_ORIGINS = "http://$($ip):$WebPort,http://localhost:$WebPort"
    $env:APP_BASE_URL = "http://$($ip):$WebPort"
    $env:VITE_API_BASE_URL = "http://$($ip):8002/api/v1"
}

function Clear-UatEnv {
    foreach ($n in "DATABASE_URL", "MINIO_PUBLIC_ENDPOINT", "BACKEND_CORS_ORIGINS", "APP_BASE_URL", "VITE_API_BASE_URL") {
        Remove-Item "Env:\$n" -ErrorAction SilentlyContinue
    }
}

function Ensure-Containers {
    Say "Database, document storage and Mailpit (Docker)"
    Push-Location $Root
    try { & docker compose up -d db minio mailpit; if ($LASTEXITCODE -ne 0) { throw "docker compose failed - is Docker Desktop running?" } }
    finally { Pop-Location }
}

function Stop-App {
    $procs = Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -in @("python.exe", "node.exe")) -and $_.CommandLine -and
        ($_.CommandLine -match 'pensionz') -and ($_.CommandLine -match 'uvicorn|app\.worker|vite')
    }
    foreach ($p in $procs) { & taskkill /PID $p.ProcessId /T /F 2>$null | Out-Null }
    Start-Sleep -Seconds 2
}

function Start-Hidden([string]$name, [string]$exe, [string[]]$arguments, [string]$dir) {
    Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $dir -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Logs "$name.log") -RedirectStandardError (Join-Path $Logs "$name.err.log") | Out-Null
}

function Wait-Port([int]$port, [string]$what) {
    for ($i = 0; $i -lt 45; $i++) {
        $c = New-Object Net.Sockets.TcpClient
        try { $c.Connect("127.0.0.1", $port); return } catch { Start-Sleep -Seconds 2 } finally { $c.Dispose() }
    }
    throw "$what didn't start on port $port - see $Logs"
}

function Start-App([string]$bindHost, [int]$webPort) {
    $node = (Get-Command node).Source
    Start-Hidden "api" $Py @("-m", "uvicorn", "app.main:app", "--host", $bindHost, "--port", "8002") $Backend
    Start-Hidden "worker" $Py @("-m", "app.worker") $Backend
    Start-Hidden "web" $node @("node_modules\vite\bin\vite.js", "--host", $bindHost, "--port", "$webPort", "--strictPort") $Frontend
    Wait-Port 8002 "The API"
    Wait-Port $webPort "The web app"
}

function Open-Firewall {
    try {
        if (-not (Get-NetFirewallRule -DisplayName "Pensionz UAT" -ErrorAction SilentlyContinue)) {
            New-NetFirewallRule -DisplayName "Pensionz UAT" -Direction Inbound -Protocol TCP -LocalPort $WebPort, 8002, 8026 -Action Allow -Profile Any | Out-Null
            Say "Firewall: opened ports $WebPort, 8002, 8026"
        }
    } catch {
        Write-Warning "Couldn't add the firewall rule (needs an administrator PowerShell). Run once as administrator:"
        Write-Warning '  New-NetFirewallRule -DisplayName "Pensionz UAT" -Direction Inbound -Protocol TCP -LocalPort 5278,8002,8026 -Action Allow -Profile Any'
    }
}

function Show-Urls([string]$ip) {
    Write-Host ""
    Write-Host "Testers open:  http://$($ip):$WebPort    (logins in UAT.md)"
    Write-Host "Mailpit:       http://$($ip):8026    (sign-in codes and every email the app sends)"
    Write-Host "Logs:          $Logs"
}

function Invoke-Docker-Psql([string]$sql) {
    $user = ((Get-DevDatabaseUrl) -replace '^[^:]+://([^:]+):.*$', '$1')
    & docker exec pensionz-db-1 psql -U $user -d postgres -v ON_ERROR_STOP=1 -qc $sql
    if ($LASTEXITCODE -ne 0) { throw "psql failed: $sql" }
}

switch ($Command) {
    "reset" {
        $ip = Get-Address
        Ensure-Containers
        Stop-App
        Say "Fresh $UatDb database"
        Invoke-Docker-Psql "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$UatDb' and pid <> pg_backend_pid();"
        Invoke-Docker-Psql "drop database if exists $UatDb;"
        Invoke-Docker-Psql "create database $UatDb;"
        Set-UatEnv $ip
        Push-Location $Backend
        try {
            Say "Tables"; & $Py -m alembic upgrade head; if ($LASTEXITCODE -ne 0) { throw "migration failed" }
            Say "UAT data (a few minutes)"; & $Py -m app.seed_uat; if ($LASTEXITCODE -ne 0) { throw "seed failed" }
        } finally { Pop-Location }
        Say "Starting in UAT mode"
        Start-App "0.0.0.0" $WebPort; Open-Firewall; Show-Urls $ip
    }
    "start" {
        $ip = Get-Address
        Ensure-Containers
        Stop-App
        Set-UatEnv $ip
        Say "Starting in UAT mode on $ip"
        Start-App "0.0.0.0" $WebPort; Open-Firewall; Show-Urls $ip
    }
    "stop" { Stop-App; Write-Host "Stopped the API, worker and web app (databases and Docker containers left running)." }
    "dev" {
        Stop-App; Clear-UatEnv
        Say "Starting in dev mode (dev database, localhost only)"
        Start-App "127.0.0.1" 5178
        Write-Host "Dev: http://localhost:5178"
    }
    "status" {
        $ip = Get-Address
        $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'pensionz' -and $_.CommandLine -match 'uvicorn|app\.worker|vite' }
        foreach ($p in $procs) { Write-Host ("{0,-7} {1}" -f $p.ProcessId, ($p.CommandLine -replace '^.*?(uvicorn|app\.worker|vite\.js)', '$1')) }
        if (-not $procs) { Write-Host "Nothing running." }
        Show-Urls $ip
    }
}
