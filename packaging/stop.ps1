[CmdletBinding()]
param()

$ErrorActionPreference = 'SilentlyContinue'
$app = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $app 'backend\.run\backend.pid'

if (Test-Path -LiteralPath $pidFile) {
    $oldPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    if ($oldPid -match '^\d+$') {
        Stop-Process -Id ([int]$oldPid) -Force
    }
}

$trayPath = Join-Path $app 'packaging\tray.py'
$trayHost = Join-Path $app 'BiliNoteMiniTray.exe'
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($trayPath) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Get-CimInstance Win32_Process -Filter "Name = 'BiliNoteMiniTray.exe'" |
    Where-Object { $_.ExecutablePath -and $_.ExecutablePath -ieq $trayHost } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
