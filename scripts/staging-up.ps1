<#
.SYNOPSIS
Starts Spendroo staging on this machine and opens a Cloudflare quick tunnel to it.

.DESCRIPTION
Runs the API with production settings, waits until it answers, then starts
`cloudflared tunnel --url` and prints the public https address to paste into
the app's Settings -> Server. Ctrl+C stops the tunnel; scripts/staging-down.ps1
stops the rest. See docs/staging-local.md.

.PARAMETER Mode
docker (default): PostgreSQL, the API and the worker in Docker.
venv: this machine's PostgreSQL and the project's .venv, served by waitress.

.EXAMPLE
./scripts/staging-up.ps1
./scripts/staging-up.ps1 -Mode venv
#>
param(
    [ValidateSet('docker', 'venv')][string]$Mode = 'docker',
    [int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
$api = Split-Path -Parent $PSScriptRoot
Set-Location $api

if (-not (Test-Path .env.staging)) { throw 'Copy .env.staging.example to .env.staging and fill it in first.' }
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    throw 'cloudflared is not installed. Run: winget install Cloudflare.cloudflared'
}

if ($Mode -eq 'docker') {
    if ($Port -ne 8000) { throw 'Docker mode publishes port 8000 (docker-compose.staging.yml).' }
    docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --build
    if ($LASTEXITCODE) { throw 'docker compose failed.' }
}
else {
    # Same steps as the container, with .env.staging loaded into this process
    # (child processes inherit it; values already set here win over .env).
    # waitress drops X-Forwarded-* from proxies it does not trust; cloudflared
    # connects from 127.0.0.1, so it is trusted and Django sees HTTPS.
    foreach ($line in Get-Content .env.staging) {
        if ($line -match '^\s*([A-Z0-9_]+)\s*=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim())
        }
    }
    $env:PROJECT_ENVIRONMENT = 'production'
    $env:TRUSTED_PROXY_COUNT = '1'
    $env:STAGING_TUNNEL = '1'

    $python = Join-Path $api '.venv\Scripts\python.exe'
    & $python manage.py migrate --noinput
    if ($LASTEXITCODE) { throw 'migrate failed.' }
    & $python manage.py collectstatic --noinput | Out-Null

    $logs = Join-Path $api 'logs'
    New-Item -ItemType Directory -Force $logs | Out-Null
    Start-Process $python -WindowStyle Hidden `
        -ArgumentList '-m', 'waitress', '--listen', "127.0.0.1:$Port", '--threads', '8', `
            '--trusted-proxy', '127.0.0.1', '--trusted-proxy-headers', '"x-forwarded-proto x-forwarded-for"', `
            'spendroo.wsgi:application' `
        -RedirectStandardOutput "$logs\staging-web.out.log" -RedirectStandardError "$logs\staging-web.err.log"
    Start-Process $python -WindowStyle Hidden `
        -ArgumentList 'manage.py', 'procrastinate', 'worker' `
        -RedirectStandardOutput "$logs\staging-worker.out.log" -RedirectStandardError "$logs\staging-worker.err.log"
}

Write-Host 'Waiting for the API...'
$healthy = $false
for ($i = 0; $i -lt 45 -and -not $healthy; $i++) {
    try {
        $healthy = (Invoke-RestMethod "http://127.0.0.1:$Port/health/?db=1" -TimeoutSec 3).database -eq 'ok'
    }
    catch { Start-Sleep -Seconds 2 }
}
if (-not $healthy) { throw "The API did not come up on port $Port. Check the logs (docker compose logs web, or logs\staging-web.err.log)." }
Write-Host "API is up on http://127.0.0.1:$Port" -ForegroundColor Green

Write-Host 'Starting the tunnel. Ctrl+C stops the tunnel only; scripts/staging-down.ps1 stops the API.'
cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$Port" 2>&1 | ForEach-Object {
    $text = "$_"
    if ($text -match 'https://[a-z0-9-]+\.trycloudflare\.com') {
        Write-Host ''
        Write-Host "  Server address for the app (Settings -> Server): $($Matches[0])" -ForegroundColor Green
        Write-Host ''
    }
    elseif ($text -match 'ERR|error') {
        Write-Host $text -ForegroundColor Yellow
    }
}
