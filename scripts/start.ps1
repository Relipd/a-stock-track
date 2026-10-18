# Start the local Five-Chain workbench, wait for health, warm cache, open browser.
$ErrorActionPreference = "Stop"
$root = Split-Path -Path $PSScriptRoot -Parent
if (-not $root) { $root = (Get-Location).Path }
Set-Location $root

# Keep local star/logic data safe: rolling backup before every start.
$stateDb = Join-Path $root "data\state.sqlite"
if (Test-Path $stateDb) {
  & (Join-Path $root ".venv\Scripts\python.exe") (Join-Path $root "scripts\backup_state.py") | Out-Null
}

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  Write-Host "Missing $python. Create .venv first." -ForegroundColor Red
  exit 1
}

$port = 8000
$busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if (-not $busy) {
  Write-Host "Starting backend on port $port ..."
  $log = Join-Path $root "data\server.log"
  Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", "$port") -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError (Join-Path $root "data\server.err.log") | Out-Null
}

$ok = $false
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Milliseconds 500
  try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 2
    if ($h.status -eq "ok") { $ok = $true; break }
  } catch { }
}
if (-not $ok) {
  Write-Host "Backend not ready. See data\server.err.log" -ForegroundColor Red
  exit 1
}

try { Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$port/api/warm?full=1" -TimeoutSec 3 | Out-Null } catch { }
Start-Sleep -Milliseconds 300
Write-Host "Opening http://127.0.0.1:$port/" -ForegroundColor Green
Start-Process "http://127.0.0.1:$port/"
