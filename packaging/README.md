# BiliNote Mini 安装 / 打包说明

## 用户安装

发布产物在 `dist/release/`：

| 文件 | 用途 |
| --- | --- |
| `BiliNoteMini-Setup-<ver>.exe` | 自解压安装程序，按当前用户安装，无需管理员权限 |
| `BiliNoteMini-<ver>-Setup.zip` | 同内容 ZIP；解压后双击 `install.cmd` |
| `BiliNoteMini-Extension-<ver>.crx` / `.zip` | Chrome 扩展，CRX 受限时用 ZIP 加载 |

Setup 会：

- 安装到 `%LOCALAPPDATA%\BiliNote Mini`；如果该目录不可写，会自动尝试 `%LOCALAPPDATA%\BiliNoteMini`、`%APPDATA%\BiliNoteMini`、用户目录、文档、桌面、当前目录，最后自动请求管理员权限，或使用 `/DIR=C:\BiliNoteMini` 指定；
- **直接把内嵌 payload 解压到安装目录，不使用 `%TEMP%`**（避免 Inno/7z 自解压在部分机器上 `is-*.tmp` / `7z...` 的 Error 5）；
- 在 `packaging\vendor\uv.exe` 的帮助下准备 Python 3.12 和依赖，不要求系统预装 Python；
- 创建桌面/开始菜单快捷方式、通知区域图标；
- 默认写 `HKCU\...\Run` 开机自启动（安装时可在任务页取消）；HKCU 被策略拒绝时自动改用任务计划程序里的 `BiliNoteMini` 登录任务；
- 启动原生 WinForms 托盘 `BiliNoteMiniTray.exe`，前端由后端在 `http://127.0.0.1:8483` 托管。

Windows 11 新托盘图标默认在任务栏 `^` 溢出区。安装目录同时生成：

- `Start-BiliNoteMini.cmd`：启动托盘（`--open` 会打开工作台）；
- `Open-BiliNoteMini.cmd`：只打开工作台；
- `Stop-BiliNoteMini.cmd`：停止托盘和后端。

如果系统禁止写 Desktop/AppData/HKCU，安装仍会完成并生成上述脚本；托盘会启动，但快捷方式/自启动会被跳过并打印警告。恢复这些权限后重新运行安装即可。

托盘菜单：打开工作台、打开数据目录、打开日志、重启后端、开机自启动开关、退出。退出托盘会停止它启动的后端。

这不是 Windows Service，而是登录用户级别的自启动托盘进程；只有这样才能显示通知区域图标并与桌面交互。

## 卸载

- Windows“应用”里的 BiliNote Mini；或
- 运行安装目录下的 `packaging\uninstall.ps1`；`-PurgeData` 连同数据一起删除。

如果 ZIP 安装时默认目录被锁，可指定目录：

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -InstallDir C:\BiliNoteMini
```

## 构建

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build-release.ps1
```

参数：

- `-SkipFrontend`：复用 `BillNote_frontend/dist`；
- `-SkipInstaller`：只构建前端/扩展；
- `-SkipExtension`：只构建安装包；
- 首次构建会下载 `uv.exe` 到 `packaging/vendor/`（已在 `.gitignore`）。

依赖工具：Node/pnpm（前端）、.NET Framework 4.x 的 `csc.exe`（Setup.exe）。CRX 需要本机 Chrome。

## 测试

托盘无界面冒烟：

```powershell
backend\.venv\Scripts\python.exe packaging\tray.py --check
```

从 ZIP 安装到临时目录（不启动、不装依赖）：

```powershell
$env:BILINOTE_INSTALL_DIR = "$env:LOCALAPPDATA\bn-test"
$env:BILINOTE_SKIP_DEPS = "1"
$env:BILINOTE_NO_AUTOSTART = "1"
$env:BILINOTE_NO_SHORTCUTS = "1"
$env:BILINOTE_NO_LAUNCH = "1"
powershell -ExecutionPolicy Bypass -File .build-tmp\setup\install.ps1
```

## 安全

- `packaging/keys/bilinote-extension.pem` 是 CRX 私钥，已忽略，不要公开；更换会改变扩展 ID。
- 安装包读取的 Cookie 只发给本机 `127.0.0.1`；不需要用户提交到仓库。
