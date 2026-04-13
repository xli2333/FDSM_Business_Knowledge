$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\LXG\fdsmarticles'

while ($true) {
  Clear-Host
  Write-Host ("Round67 Progress @ " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
  python -m backend.scripts.report_round67_progress
  Start-Sleep -Seconds 20
}
