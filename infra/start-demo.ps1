# Starts the whole system for a demo or a test (owner: Student B, polish).
# Double-click infra\start-demo.cmd (or run this file in PowerShell).
#
# What it does, in order:
#  1. Frees memory: stops Oracle/MySQL if they run (Windows asks for permission) and
#     the Gradle/Kotlin build helpers left by "flutter run".
#  2. Checks the laptop's Wi-Fi IP and updates LAN_IP in .env if it changed
#     (MediaMTX needs it so the phone's video can reach the laptop).
#  3. Starts Docker Desktop if needed, then the database + video server.
#  4. Opens 3 windows: backend API, ingest worker, dashboard.
#     The worker runs at LOW CPU priority: a spoken question (someone is waiting)
#     goes first, the worker uses what is left. Measured: speech-to-text 10.5 s
#     instead of 127 s when the CPU is busy.
#  5. Prints the IP to type in the phone app.
# Stop everything with infra\stop-demo.cmd.

param([switch]$NoPause)  # -NoPause: do not wait for Enter at the end (used for testing)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Say($text, $color = 'White') { Write-Host $text -ForegroundColor $color }
function Step($text) { Write-Host ''; Write-Host "== $text" -ForegroundColor Cyan }

function Wait-Url($url, $seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Find-Process($pattern) {
    Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -match $pattern }
}

Say 'VA Eyes - starting the demo system' 'Yellow'

# ---------- 1. memory ----------
Step '1/5 Freeing memory'
$dbServices = Get-Service -ErrorAction SilentlyContinue -Name OracleServiceXE, OracleOraDB21Home1TNSListener, OracleOraDB21Home1MTSRecoveryService, MySQL80, mysql |
    Where-Object { $_.Status -eq 'Running' }
if ($dbServices) {
    $names = ($dbServices | ForEach-Object { $_.Name }) -join ','
    Say "Other databases are running ($names): they use about 2.5 GB. Stopping them..." 'Yellow'
    Say 'Windows will ask for permission: click Yes.'
    try {
        Start-Process powershell.exe -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList '-NoProfile', '-Command',
            "Stop-Service -Force -Name $names"
        Say 'Stopped.' 'Green'
    } catch {
        Say 'Not stopped (permission refused). Questions may fail with "failed to allocate memory".' 'Red'
    }
} else {
    Say 'Oracle / MySQL: not running. Good.' 'Green'
}
$buildHelpers = Get-CimInstance Win32_Process -Filter "Name='java.exe'" |
    Where-Object { $_.CommandLine -match 'GradleDaemon|KotlinCompileDaemon' }
foreach ($helper in $buildHelpers) { Stop-Process -Id $helper.ProcessId -Force -ErrorAction SilentlyContinue }
if ($buildHelpers) { Say "Stopped $(@($buildHelpers).Count) Flutter build helper(s) (Gradle/Kotlin)." 'Green' }
$os = Get-CimInstance Win32_OperatingSystem
$freeGb = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
Say "Free memory: $freeGb GB of $([math]::Round($os.TotalVisibleMemorySize / 1MB, 1)) GB"
if ($freeGb -lt 2.5) { Say 'Less than 2.5 GB free: close other apps (browser tabs, Adobe, games).' 'Yellow' }

# ---------- 2. Wi-Fi IP ----------
Step '2/5 Checking the Wi-Fi address'
$wifi = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.InterfaceAlias -like 'Wi-Fi*' -and $_.IPAddress -notlike '169.254*' } |
    Select-Object -First 1
if (-not (Test-Path .env)) { Say '.env is missing: copy .env.example to .env and fill it in first.' 'Red'; Read-Host 'Press Enter to close'; exit 1 }
$envLines = Get-Content .env
$lanLine = $envLines | Where-Object { $_ -match '^LAN_IP=' } | Select-Object -First 1
$lanIp = if ($lanLine) { $lanLine.Substring(7).Trim() } else { '' }
if (-not $wifi) {
    Say 'The laptop is not connected to Wi-Fi. Connect it to the same network as the phone.' 'Red'
    $ip = $lanIp
} else {
    $ip = $wifi.IPAddress
    if ($ip -ne $lanIp) {
        $newLines = if ($lanLine) { $envLines -replace '^LAN_IP=.*', "LAN_IP=$ip" } else { $envLines + "LAN_IP=$ip" }
        [IO.File]::WriteAllLines((Join-Path $root '.env'), $newLines, (New-Object Text.UTF8Encoding $false))
        Say "The Wi-Fi address changed: LAN_IP updated from '$lanIp' to $ip in .env." 'Yellow'
        Say 'Type the NEW address in the phone app (Settings).' 'Yellow'
    } else {
        Say "Wi-Fi address $ip = LAN_IP in .env. Good." 'Green'
    }
}

# ---------- 3. Docker ----------
Step '3/5 Database + video server (Docker)'
function Test-Docker {
    $ErrorActionPreference = 'Continue'  # docker's error text must not stop the script
    docker info *> $null
    return ($LASTEXITCODE -eq 0)
}
if (-not (Test-Docker)) {
    Say 'Docker Desktop is not running: starting it (about 1 minute)...'
    Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
    $deadline = (Get-Date).AddSeconds(180)
    while (-not (Test-Docker) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 3 }
    if (-not (Test-Docker)) { Say 'Docker did not start. Open Docker Desktop by hand, then run this again.' 'Red'; Read-Host 'Press Enter to close'; exit 1 }
}
$ErrorActionPreference = 'Continue'
docker compose up -d 2>&1 | ForEach-Object { "$_" } | Where-Object { $_ -match 'Started|Running|Created|Recreated|Error' } | ForEach-Object { Say "  $_" }
$ErrorActionPreference = 'Stop'
Say 'va-postgres and va-mediamtx are up.' 'Green'

# ---------- 4. the three windows ----------
Step '4/5 Backend, worker, dashboard'
$backendDir = Join-Path $root 'backend'
$activate = '.\.venv\Scripts\Activate.ps1'

if (Wait-Url 'http://localhost:8000/api/health' 1) {
    Say 'Backend already running.' 'Green'
} else {
    Start-Process powershell.exe -WorkingDirectory $backendDir -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command',
        "`$Host.UI.RawUI.WindowTitle = 'VA backend (keep open)'; . $activate; python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
    Say 'Backend window opened, waiting for it (loading the speech model takes up to a minute)...'
    if (Wait-Url 'http://localhost:8000/api/health' 120) { Say 'Backend ready.' 'Green' }
    else { Say 'The backend did not answer after 2 minutes: look at its window for an error.' 'Red' }
}

if (Find-Process 'app\.ingest\.worker') {
    Say 'Worker already running.' 'Green'
} else {
    # BelowNormal on this window is inherited by the python processes it starts.
    Start-Process powershell.exe -WorkingDirectory $backendDir -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command',
        "`$Host.UI.RawUI.WindowTitle = 'VA worker - low priority (keep open)'; [Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'BelowNormal'; . $activate; python -m app.ingest.worker"
    Say 'Worker window opened (low CPU priority, so questions go first).' 'Green'
}

if (Wait-Url 'http://localhost:5173' 1) {
    Say 'Dashboard already running.' 'Green'
} else {
    Start-Process powershell.exe -WorkingDirectory (Join-Path $root 'dashboard') -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command',
        "`$Host.UI.RawUI.WindowTitle = 'VA dashboard (keep open)'; npm run dev"
    if (Wait-Url 'http://localhost:5173' 60) { Start-Process 'http://localhost:5173'; Say 'Dashboard opened in the browser.' 'Green' }
    else { Say 'The dashboard did not start: look at its window.' 'Red' }
}

# ---------- 5. the phone ----------
Step '5/5 The phone'
Say "1. Phone on the same Wi-Fi as the laptop ($((Get-NetConnectionProfile -ErrorAction SilentlyContinue | Select-Object -First 1).Name))."
Say "2. Open VA Eyes. Settings -> server IP: $ip"
Say '3. Wait for "Ready" and "Camera connected", then tap the yellow button and ask.'
Write-Host ''
Say 'Everything is started. Keep the 3 windows open. Stop with infra\stop-demo.cmd.' 'Yellow'
if (-not $NoPause) { Read-Host 'Press Enter to close this window' }
