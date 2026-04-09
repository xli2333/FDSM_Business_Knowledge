$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot | Split-Path -Parent)

while ($true) {
  Clear-Host
  Write-Host "Round65 Progress Monitor" -ForegroundColor Cyan
  Write-Host "Refreshing every 10 seconds..." -ForegroundColor DarkGray
  Write-Host ""
  python backend/scripts/report_round65_progress.py
  Start-Sleep -Seconds 10
}
