$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot 'backend/.venv/Scripts/python.exe'

if (!(Test-Path -LiteralPath $python)) {
    throw 'Missing backend/.venv. Create a Python 3.12 virtual environment and install requirements-mini.txt first.'
}

& $python -c 'import sys; sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12)) and sys.maxsize > 2**32 else 1)'
if ($LASTEXITCODE -ne 0) {
    throw 'Use 64-bit Python 3.11 or 3.12 to recreate backend/.venv.'
}

$pnpm = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
if (!$pnpm) { $pnpm = Get-Command pnpm -ErrorAction SilentlyContinue }
if (!$pnpm) { throw 'pnpm was not found. Install pnpm and reopen PowerShell.' }

$originalLocation = Get-Location
$env:BACKEND_HOST = '127.0.0.1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$logDir = Join-Path $projectRoot 'backend/logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stdoutLog = Join-Path $logDir 'startup.stdout.log'
$stderrLog = Join-Path $logDir 'startup.stderr.log'
$backend = Start-Process -FilePath $python -ArgumentList '-u', 'main.py' -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru
try {
    Write-Host 'Waiting for backend at http://127.0.0.1:8483 ...'
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $backend.Refresh()
        if ($backend.HasExited) { break }
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8483/api/sys_check' -TimeoutSec 1
            if ($health.code -eq 0) { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (!$ready) {
        if (Test-Path -LiteralPath $stderrLog) { Get-Content -LiteralPath $stderrLog -Encoding UTF8 -Tail 30 }
        if (Test-Path -LiteralPath $stdoutLog) { Get-Content -LiteralPath $stdoutLog -Encoding UTF8 -Tail 15 }
        throw 'Backend did not become ready. See backend/logs/startup.stderr.log.'
    }
    Write-Host 'Backend ready. Starting frontend...'
    Set-Location -LiteralPath (Join-Path $projectRoot 'BillNote_frontend')
    & $pnpm.Source dev
}
finally {
    if (!$backend.HasExited) { & taskkill.exe /PID $backend.Id /T /F 2>$null | Out-Null }
    Set-Location -LiteralPath $originalLocation.Path
}