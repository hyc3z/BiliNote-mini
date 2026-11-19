[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$app = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $app 'backend'
$venv = Join-Path $backend '.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
$uv = Join-Path $app 'packaging\vendor\uv.exe'
$env:UV_CACHE_DIR = Join-Path $app 'packaging\uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $app 'packaging\python'
$logDir = Join-Path $backend 'logs'
$log = Join-Path $logDir 'install-runtime.log'

New-Item -ItemType Directory -Force -Path $env:UV_CACHE_DIR, $env:UV_PYTHON_INSTALL_DIR | Out-Null

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $backend 'data') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $backend 'config') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $backend 'note_results') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $backend 'models') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $backend 'uploads') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $backend '.run') | Out-Null

function Write-Log([string]$text) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $text"
    Add-Content -LiteralPath $log -Value $line -Encoding UTF8
    Write-Host $text
}

try {
    Write-Log "BiliNote Mini runtime setup"
    if (-not (Test-Path -LiteralPath $uv)) {
        throw "找不到内置 uv：$uv"
    }
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Log "创建 Python 3.12 虚拟环境"
        $ErrorActionPreference = 'Continue'
        & $uv venv --python 3.12 $venv 2>&1 | Tee-Object -FilePath $log -Append
        $code = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($code -ne 0) { throw "uv venv 失败（exit $code）" }
    }
    Write-Log "安装 Python 依赖"
    $ErrorActionPreference = 'Continue'
    & $uv pip install --python $venvPython -r (Join-Path $backend 'requirements.txt') 2>&1 | Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($code -ne 0) { throw "依赖安装失败（exit $code）" }
    Write-Log "完成"
    exit 0
} catch {
    Write-Log "失败：$($_.Exception.Message)"
    exit 1
}
