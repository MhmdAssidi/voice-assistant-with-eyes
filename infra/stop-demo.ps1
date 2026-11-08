# Stops what infra\start-demo.ps1 started (owner: Student B, polish).
# Double-click infra\stop-demo.cmd. Stored frames and the question history stay
# in the database ("docker compose stop", not "down -v").

param([switch]$NoPause)  # -NoPause: do not wait for Enter at the end (used for testing)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Stop-Tree($processId) { taskkill /PID $processId /T /F 2>&1 | Out-Null }

$parts = [ordered]@{
    # name       = (window title set by start-demo.ps1, fallback for a hand-started one)
    'backend'   = @('VA backend', 'uvicorn app\.main')
    'worker'    = @('VA worker', 'app\.ingest\.worker')
    'dashboard' = @('VA dashboard', 'node_modules[\\/]vite|vite\.js')
}
foreach ($name in $parts.Keys) {
    $title, $fallback = $parts[$name]
    $all = Get-CimInstance Win32_Process
    # 1) our window (and everything started from it)
    $windows = $all | Where-Object { $_.Name -eq 'powershell.exe' -and $_.CommandLine -match [regex]::Escape($title) }
    foreach ($w in $windows) { Stop-Tree $w.ProcessId }
    # 2) started by hand in another terminal
    $loose = $all | Where-Object { $_.Name -in 'python.exe', 'node.exe' -and $_.CommandLine -match $fallback }
    foreach ($p in $loose) { Stop-Tree $p.ProcessId }
    if ($windows -or $loose) { Write-Host "Stopped the $name." -ForegroundColor Green }
    else { Write-Host "The $name was not running." }
}

docker compose stop 2>&1 | Out-Null
Write-Host 'Stopped the database and the video server (data kept).' -ForegroundColor Green
if (-not $NoPause) { Read-Host 'Press Enter to close this window' }
