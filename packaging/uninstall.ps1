[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'BiliNote Mini'),
    [switch]$PurgeData
)

$ErrorActionPreference = 'Stop'

function Remove-Shortcut([string]$path) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
}

try {
    $pidFile = Join-Path $InstallDir 'backend\.run\backend.pid'
    if (Test-Path -LiteralPath $pidFile) {
        $oldPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
        if ($oldPid -match '^\d+$') { Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue }
    }
    $trayPath = Join-Path $InstallDir 'packaging\tray.py'
    Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains($trayPath) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    $trayHost = Join-Path $InstallDir 'BiliNoteMiniTray.exe'
    Get-CimInstance Win32_Process -Filter "Name = 'BiliNoteMiniTray.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath -ieq $trayHost } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

    Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'BiliNoteMini' -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName 'BiliNoteMini' -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\BiliNoteMini' -Recurse -Force -ErrorAction SilentlyContinue

    Remove-Shortcut (Join-Path ([Environment]::GetFolderPath('Desktop')) 'BiliNote Mini.lnk')
    Remove-Shortcut (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\BiliNote Mini.lnk')

    if ($PurgeData) {
        Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "已卸载并删除 $InstallDir" -ForegroundColor Green
    } else {
        Write-Host "已移除开机自启动、快捷方式和卸载项。" -ForegroundColor Green
        Write-Host "代码和数据仍保留在：$InstallDir"
        Write-Host "如需彻底删除，请运行：uninstall.ps1 -PurgeData"
    }
} catch {
    Write-Host "卸载失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
