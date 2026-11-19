[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$SkipInstaller,
    [switch]$SkipExtension
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$release = Join-Path $root 'dist\release'
$build = Join-Path $root '.build-tmp'
$payload = Join-Path $build 'payload'
$setup = Join-Path $build 'setup'
$version = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'VERSION') -Raw).Trim()
$manifest = Get-Content -LiteralPath (Join-Path $root 'integrations\chrome-extension\manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$extensionVersion = $manifest.version

function Invoke-Checked([string]$label, [scriptblock]$script) {
    Write-Host "==> $label" -ForegroundColor Cyan
    & $script
    if ($LASTEXITCODE -ne 0) { throw "$label failed (exit $LASTEXITCODE)" }
}

function Ensure-Uv {
    $uv = Join-Path $PSScriptRoot 'vendor\uv.exe'
    if (Test-Path -LiteralPath $uv) { return $uv }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $uv) | Out-Null
    $archive = Join-Path $build 'uv-win.zip'
    $extract = Join-Path $build 'uv-win'
    if (Test-Path -LiteralPath $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
    Write-Host "==> 下载内置 uv（首次构建）" -ForegroundColor Cyan
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' -OutFile $archive -UseBasicParsing
    Expand-Archive -LiteralPath $archive -DestinationPath $extract -Force
    $source = Get-ChildItem -LiteralPath $extract -Recurse -Filter 'uv.exe' | Select-Object -First 1
    if (-not $source) { throw 'uv.exe 下载包不完整' }
    Copy-Item -LiteralPath $source.FullName -Destination $uv -Force
    return $uv
}

function New-TrayHost {
    $csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
    if (-not (Test-Path -LiteralPath $csc)) {
        Write-Warning '未找到 csc.exe，跳过原生托盘程序；仍可使用 Python 托盘。'
        return
    }
    $hostExe = Join-Path $build 'BiliNoteMiniTray.exe'
    if (Test-Path -LiteralPath $hostExe) { Remove-Item -LiteralPath $hostExe -Force }
    Write-Host "==> 编译原生托盘程序" -ForegroundColor Cyan
    & $csc /nologo /target:winexe /platform:anycpu /codepage:65001 "/out:$hostExe" "/win32icon:$(Join-Path $PSScriptRoot 'assets\bilinote.ico')" /r:System.Windows.Forms.dll /r:System.Drawing.dll (Join-Path $PSScriptRoot 'tray_host.cs')
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $hostExe)) {
        Write-Warning "托盘程序编译失败（exit $LASTEXITCODE）；仍可使用 Python 托盘。"
    }
}

function Copy-RuntimePayload {
    New-TrayHost
    if (Test-Path -LiteralPath $payload) { Remove-Item -LiteralPath $payload -Recurse -Force }
    New-Item -ItemType Directory -Force -Path (Join-Path $payload 'backend') | Out-Null
    Copy-Item -LiteralPath (Join-Path $root 'backend\app') -Destination (Join-Path $payload 'backend\app') -Recurse -Force
    Get-ChildItem -LiteralPath $payload -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -LiteralPath $payload -Recurse -File -Filter '*.pyc' -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
    foreach ($file in @('main.py', 'chat_worker.py', 'mcp_server.py', 'requirements.txt', 'requirements-mini.txt', 'requirements-gpu.txt', 'requirements-mcp.txt')) {
        $source = Join-Path $root "backend\$file"
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination (Join-Path $payload "backend\$file") -Force
        }
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $payload 'BillNote_frontend\dist') | Out-Null
    Copy-Item -Path (Join-Path $root 'BillNote_frontend\dist\*') -Destination (Join-Path $payload 'BillNote_frontend\dist') -Recurse -Force
    New-Item -ItemType Directory -Force -Path (Join-Path $payload 'packaging\assets') | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $payload 'packaging\vendor') | Out-Null
    foreach ($file in @('tray.py', 'install.ps1', 'install.cmd', 'uninstall.ps1', 'setup-runtime.ps1', 'stop.ps1', 'VERSION', 'README.md')) {
        Copy-Item -LiteralPath (Join-Path $root "packaging\$file") -Destination (Join-Path $payload "packaging\$file") -Force
    }
    Copy-Item -LiteralPath (Join-Path $root 'packaging\assets\bilinote.ico') -Destination (Join-Path $payload 'packaging\assets\bilinote.ico') -Force
    Copy-Item -LiteralPath (Ensure-Uv) -Destination (Join-Path $payload 'packaging\vendor\uv.exe') -Force
    $trayHost = Join-Path $build 'BiliNoteMiniTray.exe'
    if (Test-Path -LiteralPath $trayHost) {
        Copy-Item -LiteralPath $trayHost -Destination (Join-Path $payload 'BiliNoteMiniTray.exe') -Force
    }
    if (Test-Path -LiteralPath (Join-Path $root 'docs')) {
        Copy-Item -LiteralPath (Join-Path $root 'docs') -Destination (Join-Path $payload 'docs') -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $payload 'integrations\chrome-extension') | Out-Null
    Copy-Item -Path (Join-Path $root 'integrations\chrome-extension\*') -Destination (Join-Path $payload 'integrations\chrome-extension') -Recurse -Force
    foreach ($file in @('README.md', 'LICENSE', '.env.example')) {
        $source = Join-Path $root $file
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination (Join-Path $payload $file) -Force
        }
    }
    foreach ($dir in @('data', 'config', 'logs', 'note_results', 'models', 'uploads', '.run')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $payload "backend\$dir") | Out-Null
    }
}

function New-PayloadZip {
    $zip = Join-Path $setup 'payload.zip'
    if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
    Push-Location $payload
    try {
        Compress-Archive -Path '*' -DestinationPath $zip -CompressionLevel Optimal
    } finally {
        Pop-Location
    }
}

function New-Installer {
    if (Test-Path -LiteralPath $setup) { Remove-Item -LiteralPath $setup -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $setup | Out-Null
    Copy-Item -LiteralPath (Join-Path $root 'packaging\install.ps1') -Destination (Join-Path $setup 'install.ps1') -Force
    Copy-Item -LiteralPath (Join-Path $root 'packaging\install.cmd') -Destination (Join-Path $setup 'install.cmd') -Force
    New-PayloadZip
    @"
BiliNote Mini $version - Windows 安装说明

1. 双击 install.cmd（或直接运行 BiliNoteMini-Setup-$version.exe）。
2. 安装到 %LOCALAPPDATA%\BiliNote Mini，创建通知区域图标、桌面/开始菜单快捷方式，并默认开机自启动。
3. 包内自带 uv，首次安装会下载 Python 3.12 和依赖，需要联网；不要求系统预装 Python。
4. 托盘右键：打开工作台、打开数据/日志、重启后端、开机自启动、退出。
5. 卸载：运行安装目录里的 packaging\uninstall.ps1，-PurgeData 可删除数据。

工作台：http://127.0.0.1:8483
"@ | Set-Content -LiteralPath (Join-Path $setup 'README-INSTALL.txt') -Encoding UTF8

    $portableZip = Join-Path $release "BiliNoteMini-$version-Setup.zip"
    Get-ChildItem -LiteralPath $release -File -Filter 'BiliNoteMini-Setup-*.exe' -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem -LiteralPath $release -File -Filter 'BiliNoteMini-*-Setup.zip' -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $portableZip) { Remove-Item -LiteralPath $portableZip -Force }
    Compress-Archive -Path (Join-Path $setup '*') -DestinationPath $portableZip -CompressionLevel Optimal

    # The installer is a tiny .NET EXE with payload.zip embedded. It extracts
    # directly into %LOCALAPPDATA% and runs install.ps1 -RuntimeOnly, so it does
    # not need Inno/7z to create a temp directory first.
    $csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
    if (-not (Test-Path -LiteralPath $csc)) {
        Write-Warning '未找到 .NET Framework csc.exe，跳过 Setup.exe；Setup.zip 仍可用。'
        return
    }
    $setupExe = Join-Path $release "BiliNoteMini-Setup-$version.exe"
    if (Test-Path -LiteralPath $setupExe) { Remove-Item -LiteralPath $setupExe -Force }
    $icon = Join-Path $PSScriptRoot 'assets\bilinote.ico'
    $source = Join-Path $PSScriptRoot 'installer.cs'
    Write-Host "==> 编译安装程序" -ForegroundColor Cyan
    & $csc /nologo /target:exe /platform:anycpu /codepage:65001 "/out:$setupExe" "/win32icon:$icon" "/resource:$(Join-Path $setup 'payload.zip'),payload.zip" /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll $source
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $setupExe)) {
        Write-Warning "安装程序编译失败（exit $LASTEXITCODE）；Setup.zip 仍可用。"
    } else {
        Write-Host "Setup: $setupExe"
    }
}

function New-ExtensionPackage {
    if (Test-Path -LiteralPath $release) { New-Item -ItemType Directory -Force -Path $release | Out-Null }
    Get-ChildItem -LiteralPath $release -File -Filter 'BiliNoteMini-Extension-*' -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
    $stage = Join-Path $build 'extension\bilinote-extension'
    if (Test-Path -LiteralPath (Join-Path $build 'extension')) { Remove-Item -LiteralPath (Join-Path $build 'extension') -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    foreach ($file in @('manifest.json', 'background.js', 'common.js', 'popup.html', 'popup.css', 'popup.js', 'options.html', 'options.css', 'options.js', 'zhihu-content.js', 'README.md')) {
        Copy-Item -LiteralPath (Join-Path $root "integrations\chrome-extension\$file") -Destination (Join-Path $stage $file) -Force
    }
    Copy-Item -LiteralPath (Join-Path $root 'integrations\chrome-extension\icons') -Destination (Join-Path $stage 'icons') -Recurse -Force
    $zip = Join-Path $release "BiliNoteMini-Extension-$extensionVersion.zip"
    if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
    Push-Location $stage
    try {
        Compress-Archive -Path '*' -DestinationPath $zip -CompressionLevel Optimal
    } finally {
        Pop-Location
    }
    Write-Host "Extension ZIP: $zip"

    $chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
    if (-not (Test-Path -LiteralPath $chrome)) {
        Write-Warning 'Chrome 未找到，跳过 CRX。'
        return
    }
    $keyDir = Join-Path $PSScriptRoot 'keys'
    New-Item -ItemType Directory -Force -Path $keyDir | Out-Null
    $key = Join-Path $keyDir 'bilinote-extension.pem'
    $chromeArgs = @("--pack-extension=$stage", '--no-message-box', "--user-data-dir=$build\chrome-pack-profile")
    if (Test-Path -LiteralPath $key) {
        $chromeArgs += "--pack-extension-key=$key"
    }
    & $chrome @chromeArgs 2>&1 | Out-Null
    $generatedKey = "$stage.pem"
    if (-not (Test-Path -LiteralPath $key) -and (Test-Path -LiteralPath $generatedKey)) {
        Move-Item -LiteralPath $generatedKey -Destination $key -Force
        & $chrome @chromeArgs 2>&1 | Out-Null
    }
    $generatedCrx = "$stage.crx"
    if (Test-Path -LiteralPath $generatedCrx) {
        $crx = Join-Path $release "BiliNoteMini-Extension-$extensionVersion.crx"
        Copy-Item -LiteralPath $generatedCrx -Destination $crx -Force
        Write-Host "Extension CRX: $crx"
        Write-Host "CRX key: $key（请妥善保存，用于后续同 ID 更新；不要公开）"
    } else {
        Write-Warning 'Chrome 未生成 CRX。'
    }
}

New-Item -ItemType Directory -Force -Path $release | Out-Null
New-Item -ItemType Directory -Force -Path $build | Out-Null

if (-not $SkipFrontend) {
    $pnpm = $null
    foreach ($name in @('pnpm.cmd', 'pnpm.exe', 'pnpm')) {
        $candidate = Get-Command $name -ErrorAction SilentlyContinue
        if ($candidate) { $pnpm = $candidate; break }
    }
    if (-not $pnpm) { throw '未找到 pnpm。请安装 pnpm 后重试。' }
    $oldTmp = $env:TMP
    $oldTemp = $env:TEMP
    $localTmp = Join-Path $build 'tmp'
    New-Item -ItemType Directory -Force -Path $localTmp | Out-Null
    $env:TMP = $localTmp
    $env:TEMP = $localTmp
    try {
        Push-Location (Join-Path $root 'BillNote_frontend')
        try {
            Invoke-Checked '构建前端' { & $pnpm.Source exec vite build }
        } finally {
            Pop-Location
        }
    } finally {
        $env:TMP = $oldTmp
        $env:TEMP = $oldTemp
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $root 'BillNote_frontend\dist\index.html'))) {
    throw 'BillNote_frontend/dist/index.html 不存在。'
}

Copy-RuntimePayload
if (-not $SkipInstaller) { New-Installer }
if (-not $SkipExtension) { New-ExtensionPackage }

Write-Host ""
Write-Host "发布目录: $release" -ForegroundColor Green
Get-ChildItem -LiteralPath $release -File | Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}} | Format-Table -AutoSize
