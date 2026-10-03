<#
.SYNOPSIS
Stops staging started by scripts/staging-up.ps1. Data is kept.
#>
param([ValidateSet('docker', 'venv')][string]$Mode = 'docker')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

if ($Mode -eq 'docker') {
    docker compose -f docker-compose.yml -f docker-compose.staging.yml down
}
else {
    Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -match 'waitress.+spendroo\.wsgi|manage\.py procrastinate worker' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Confirm:$false; Write-Host "Stopped $($_.ProcessId)" }
}
