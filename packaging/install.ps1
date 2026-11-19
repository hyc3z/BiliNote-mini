[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'BiliNote Mini'),
    [string]$Python = '',
    [switch]$SkipDeps,
    [switch]$NoAutostart,
    [switch]$NoLaunch,
    [switch]$NoShortcuts,
    [switch]$NoUninstallEntry,
    [switch]$RuntimeOnly,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$packageDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$payloadZip = Join-Path $packageDir 'payload.zip'
$tempRoot = $null

# Environment overrides are used by the release smoke test and silent deployment.
if ($env:BILINOTE_INSTALL_DIR) { $InstallDir = $env:BILINOTE_INSTALL_DIR }
if ($env:BILINOTE_SKIP_DEPS -eq '1') { $SkipDeps = $true }
if ($env:BILINOTE_NO_AUTOSTART -eq '1') { $NoAutostart = $true }
if ($env:BILINOTE_NO_LAUNCH -eq '1') { $NoLaunch = $true }
if ($env:BILINOTE_NO_SHORTCUTS -eq '1') { $NoShortcuts = $true }
if ($env:BILINOTE_NO_UNINSTALL_ENTRY -eq '1') { $NoUninstallEntry = $true }

function Write-Step([string]$text) {
    Write-Host ""
    Write-Host "==> $text" -ForegroundColor Cyan
}

function Resolve-Python {
    if ($Python) {
        if (-not (Test-Path -LiteralPath $Python)) { throw "指定的 Python 不存在：$Python" }
        return @{ Exe = $Python; Args = @() }
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($version in @('3.12', '3.11')) {
            & $py.Source "-$version" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == tuple(map(int, '$version'.split('.'))) and sys.maxsize > 2**32 else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                return @{ Exe = $py.Source; Args = @("-$version") }
            }
        }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        & $python.Source -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,11),(3,12)) and sys.maxsize > 2**32 else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return @{ Exe = $python.Source; Args = @() }
        }
    }
    throw "没有找到 64 位 Python 3.11/3.12。请先安装 Python（https://www.python.org/downloads/windows/），安装时勾选 Add python.exe to PATH，然后重新运行安装包。"
}

function Stop-OldProcesses {
    $pidFile = Join-Path $InstallDir 'backend\.run\backend.pid'
    if (Test-Path -LiteralPath $pidFile) {
        $oldPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
        if ($oldPid -match '^\d+$') {
            Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue
        }
    }
    $trayPath = Join-Path $InstallDir 'packaging\tray.py'
    Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains($trayPath) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 500
}

try {
    if ($RuntimeOnly) {
        $source = $InstallDir
        $payloadZip = $null
    } elseif (Test-Path -LiteralPath $payloadZip) {
        New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
        $tempRoot = Join-Path $InstallDir '.install-temp'
        if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
        Write-Step "解压安装文件"
        Expand-Archive -LiteralPath $payloadZip -DestinationPath $tempRoot -Force
        $source = $tempRoot
    } else {
        $source = Split-Path -Parent $packageDir
    }

    foreach ($required in @('backend\main.py', 'BillNote_frontend\dist\index.html', 'packaging\tray.py')) {
        if (-not (Test-Path -LiteralPath (Join-Path $source $required))) {
            throw "安装包不完整，缺少 $required"
        }
    }

    if (-not $RuntimeOnly) {
        Write-Step "安装到 $InstallDir"
        Stop-OldProcesses
        New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
        Get-ChildItem -LiteralPath $source -Force | Copy-Item -Destination $InstallDir -Recurse -Force
    }

    foreach ($folder in @('backend\data', 'backend\config', 'backend\logs', 'backend\note_results', 'backend\models', 'backend\uploads', 'backend\.run', 'backend\static')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir $folder) | Out-Null
    }

    Write-Step "准备 Python 环境"
    $venv = Join-Path $InstallDir 'backend\.venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    $uv = Join-Path $InstallDir 'packaging\vendor\uv.exe'
    $env:UV_CACHE_DIR = Join-Path $InstallDir 'packaging\uv-cache'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $InstallDir 'packaging\python'
    New-Item -ItemType Directory -Force -Path $env:UV_CACHE_DIR, $env:UV_PYTHON_INSTALL_DIR | Out-Null
    if ($Force -and (Test-Path -LiteralPath $venv)) {
        Remove-Item -LiteralPath $venv -Recurse -Force
    }
    if (-not (Test-Path -LiteralPath $venvPython)) {
        if (Test-Path -LiteralPath $uv) {
            Write-Step "使用内置 uv 准备 Python 3.12（首次会下载运行时）"
            $ErrorActionPreference = 'Continue'
            & $uv venv --python 3.12 $venv
            $code = $LASTEXITCODE
            $ErrorActionPreference = 'Stop'
            if ($code -ne 0) { throw "uv 创建 Python 环境失败（exit $code）。请检查网络后重试。" }
        } else {
            $pythonInfo = Resolve-Python
            & $pythonInfo.Exe @($pythonInfo.Args) -m venv $venv
            if ($LASTEXITCODE -ne 0) { throw "创建虚拟环境失败" }
        }
    }

    if (-not $SkipDeps) {
        Write-Step "安装/更新依赖（首次需要几分钟）"
        if (Test-Path -LiteralPath $uv) {
            $ErrorActionPreference = 'Continue'
            & $uv pip install --python $venvPython -r (Join-Path $InstallDir 'backend\requirements.txt')
            $code = $LASTEXITCODE
            $ErrorActionPreference = 'Stop'
        } else {
            & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $InstallDir 'backend\requirements.txt')
            $code = $LASTEXITCODE
        }
        if ($code -ne 0) { throw "依赖安装失败（exit $code）。请检查网络后重新运行安装包。" }
    }

    $pythonw = Join-Path $venv 'Scripts\pythonw.exe'
    if (-not (Test-Path -LiteralPath $pythonw)) { $pythonw = $venvPython }
    $tray = Join-Path $InstallDir 'packaging\tray.py'
    $icon = Join-Path $InstallDir 'packaging\assets\bilinote.ico'
    $trayHost = Join-Path $InstallDir 'BiliNoteMiniTray.exe'
    $useHost = Test-Path -LiteralPath $trayHost

    # A launcher inside the install directory is always writable when the rest
    # of the profile is locked down by ACL/security software.
    $launcher = Join-Path $InstallDir 'Start-BiliNoteMini.cmd'
    $pythonRel = 'backend\.venv\Scripts\pythonw.exe'
    if (-not (Test-Path -LiteralPath (Join-Path $InstallDir $pythonRel))) {
        $pythonRel = 'backend\.venv\Scripts\python.exe'
    }
    if ($useHost) {
        $bat = "@echo off`r`nstart `"`" `"%~dp0BiliNoteMiniTray.exe`" --open`r`n"
        $launchTarget = $trayHost
        $launchArgs = @('--open')
        $autostartValue = '"' + $trayHost + '" --autostart'
    } else {
        $bat = "@echo off`r`nstart `"`" `"%~dp0$pythonRel`" `"%~dp0packaging\tray.py`" --open`r`n"
        $launchTarget = $pythonw
        $launchArgs = @($tray, '--open')
        $autostartValue = '"' + $pythonw + '" "' + $tray + '" --autostart'
    }
    Set-Content -LiteralPath $launcher -Value $bat -Encoding ASCII
    $openScript = Join-Path $InstallDir 'Open-BiliNoteMini.cmd'
    Set-Content -LiteralPath $openScript -Value "@echo off`r`nstart `"`" `"http://127.0.0.1:8483/`"`r`n" -Encoding ASCII
    $stopScript = Join-Path $InstallDir 'Stop-BiliNoteMini.cmd'
    Set-Content -LiteralPath $stopScript -Value "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"%~dp0packaging\stop.ps1`"`r`n" -Encoding ASCII

    if (-not $NoShortcuts) {
        try {
            $shell = New-Object -ComObject WScript.Shell
            $desktop = [Environment]::GetFolderPath('Desktop')
            $startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
            foreach ($link in @((Join-Path $desktop 'BiliNote Mini.lnk'), (Join-Path $startMenu 'BiliNote Mini.lnk'))) {
                try {
                    $shortcut = $shell.CreateShortcut($link)
                    $shortcut.TargetPath = $launchTarget
                    $shortcut.Arguments = if ($useHost) { '--open' } else { '"' + $tray + '" --open' }
                    $shortcut.WorkingDirectory = $InstallDir
                    $shortcut.IconLocation = $icon
                    $shortcut.Description = 'BiliNote Mini 本地回放笔记'
                    $shortcut.Save()
                } catch {
                    Write-Warning "无法创建快捷方式 $link：$($_.Exception.Message)"
                }
            }
        } catch {
            Write-Warning "无法创建快捷方式：$($_.Exception.Message)"
        }
    }

    if (-not $NoAutostart) {
        $runOk = $false
        try {
            $runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
            New-Item -Path $runKey -Force | Out-Null
            Set-ItemProperty -Path $runKey -Name 'BiliNoteMini' -Value $autostartValue
            $runOk = $true
        } catch {
            Write-Warning "无法写入 HKCU Run：$($_.Exception.Message)"
        }
        if ($runOk) {
            Unregister-ScheduledTask -TaskName 'BiliNoteMini' -Confirm:$false -ErrorAction SilentlyContinue
        } else {
            try {
                $arg = if ($useHost) { '--autostart' } else { '"' + $tray + '" --autostart' }
                $action = New-ScheduledTaskAction -Execute $launchTarget -Argument $arg
                $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
                $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
                Register-ScheduledTask -TaskName 'BiliNoteMini' -Action $action -Trigger $trigger -Principal $principal -Description 'BiliNote Mini 托盘/后端' -Force | Out-Null
                Write-Host "已通过任务计划程序设置开机自启动。"
            } catch {
                Write-Warning "无法设置开机自启动：$($_.Exception.Message)。可运行：$launcher"
            }
        }
    }

    $version = '0.7.5'
    $versionFile = Join-Path $InstallDir 'packaging\VERSION'
    if (Test-Path -LiteralPath $versionFile) { $version = (Get-Content -LiteralPath $versionFile -Raw).Trim() }
    if (-not $NoUninstallEntry) {
        try {
            $uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\BiliNoteMini'
            New-Item -Path $uninstallKey -Force | Out-Null
            Set-ItemProperty -Path $uninstallKey -Name 'DisplayName' -Value 'BiliNote Mini'
            Set-ItemProperty -Path $uninstallKey -Name 'DisplayVersion' -Value $version
            Set-ItemProperty -Path $uninstallKey -Name 'InstallLocation' -Value $InstallDir
            Set-ItemProperty -Path $uninstallKey -Name 'UninstallString' -Value ('"powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $InstallDir 'packaging\uninstall.ps1') + '"')
        } catch {
            Write-Warning "无法写入卸载信息：$($_.Exception.Message)"
        }
    }

    if (-not $NoLaunch) {
        Write-Step "启动 BiliNote Mini"
        try {
            Start-Process -FilePath $launchTarget -ArgumentList $launchArgs -WorkingDirectory $InstallDir
        } catch {
            Write-Warning "自动启动失败，请运行：$launcher"
        }
    }

    Write-Host ""
    Write-Host "安装完成：$InstallDir" -ForegroundColor Green
    Write-Host "启动脚本：$launcher" -ForegroundColor Green
    Write-Host "托盘图标在通知区域（可能在右下角 ^ 溢出区）；右键可打开工作台、重启后端或退出。" -ForegroundColor Green
    Write-Host "开机自启动：" + $(if ($NoAutostart) { '未设置' } else { '已尝试设置；若被安全软件拦截，可用启动脚本' })
    if ($tempRoot) { Start-Sleep -Seconds 1 }
} catch {
    Write-Host ""
    Write-Host "安装失败：$($_.Exception.Message)" -ForegroundColor Red
    if ($tempRoot -and (Test-Path -LiteralPath $tempRoot)) { Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }
    exit 1
} finally {
    if ($tempRoot -and (Test-Path -LiteralPath $tempRoot)) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
