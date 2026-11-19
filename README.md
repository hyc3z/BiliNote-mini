# BiliNote Mini

个人使用的 B 站回放笔记工具：字幕优先，无字幕时获取音轨并本地转录，再调用 DeepSeek 等兼容 OpenAI 的接口总结。保留时间戳、逐字稿、本地搜索和聊天工具接口。

![工作台](docs/workbench.png)

## Windows 安装（推荐）

发布包在 `dist/release/`：

- `BiliNoteMini-Setup-0.7.5.exe`：自解压安装程序，按用户安装，不需要管理员权限；
- `BiliNoteMini-0.7.5-Setup.zip`：同内容的 ZIP；双击 `install.cmd` 也能安装；
- `BiliNoteMini-Extension-0.6.3.crx` / `.zip`：Chrome 扩展。

双击 Setup 后：

1. 默认安装到 `%LOCALAPPDATA%\BiliNote Mini`；
2. 自动创建桌面/开始菜单快捷方式和通知区域图标；
3. 默认写入 `HKCU\...\Run` 实现开机自启动（安装时可以在任务页取消）；如果 HKCU 被策略拒绝，会自动改用在“任务计划程序”里创建 `BiliNoteMini` 的登录任务；
4. 首次安装会用包内自带的 `uv` 下载 Python 3.12 并安装依赖，**不需要预先安装 Python**，但需要联网；
5. 安装程序直接解压到安装目录，不使用 `%TEMP%` 做自解压，避免部分机器 Temp 权限/安全软件导致的 `is-*.tmp` 错误；
6. 如果 `%LOCALAPPDATA%\BiliNote Mini` 被安全软件/ACL 锁定，安装器会自动尝试 `%LOCALAPPDATA%\BiliNoteMini`、`%APPDATA%\BiliNoteMini`、用户目录、文档、桌面、当前目录，最后自动请求管理员权限；也可以手动指定：
   ```powershell
   BiliNoteMini-Setup-0.7.5.exe /DIR=C:\BiliNoteMini
   ```
7. 安装完成后自动启动原生托盘 `BiliNoteMiniTray.exe`；右键可打开工作台、打开日志、重启后端、开关自启动或退出。
8. Windows 11 默认把新托盘图标放进任务栏右下角的 `^` 溢出区，可点开 `^` 找到并拖到常显区。
9. 如果系统连 Desktop/AppData/HKCU 都禁止写入，安装器会装到唯一可写目录，并生成 `Start-BiliNoteMini.cmd` / `Open-BiliNoteMini.cmd` / `Stop-BiliNoteMini.cmd`；此时托盘仍会启动，但快捷方式和开机自启动会被跳过。需要放开这些权限或安全软件白名单后重装，才能恢复自启动。

如果 Setup.exe 被 SmartScreen/企业策略拦截，解压 `BiliNoteMini-0.7.5-Setup.zip` 后双击 `install.cmd` 即可，内容是同一套文件和运行时。

托盘不是 Windows Service：它需要和当前登录用户的通知区域交互，所以采用“用户登录后自启动 + 托盘进程”的方式，退出托盘会一并停止后端。数据/配置/模型在安装目录的 `backend\data`、`backend\config`、`backend\models`。

升级时重新运行新版本 Setup 即可；安装脚本会先停止旧后端，保留运行时数据。卸载可在 Windows“应用”里进行，或运行安装目录的 `packaging\uninstall.ps1`（`-PurgeData` 会连数据一起删除）。

## 开发启动

Windows 使用 64 位 Python 3.11/3.12、Node.js 和 pnpm。

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ../BillNote_frontend
pnpm install --frozen-lockfile
cd ..
.\start-mini.ps1
```

打开 http://127.0.0.1:3015 ，在设置中填写 DeepSeek 的 API Key；接口地址和模型名称已默认填好 `https://api.deepseek.com` / `deepseek-chat`，也可以改成其它兼容 OpenAI 的接口。必要时填写 B 站 Cookie。凭据仅在本地保存，请勿提交配置文件。

后端通过 `imageio-ffmpeg` 自带 ffmpeg（已写入 `requirements.txt`），不需要单独安装系统 ffmpeg；如果你更想用系统版本，可设置 `FFMPEG_LOCATION` 指向 ffmpeg 可执行文件。

NVIDIA GPU 可额外安装 `backend/requirements-gpu.txt`，然后在设置中选择 GPU。首次使用需要下载转录模型；下载、加载、转录与总结分别显示阶段信息。下载失败可保留断点重试，或清理当前模型下载缓存后重试。运行日志在 `backend/logs`。

## 视频选集与批量整理

粘贴 BV 号或链接后会自动读取选集，显示各项标题、时长和已选总时长，默认勾选全部。可取消个别条目，或使用全选/清空，然后点击“整理选中 N 项”。同一 BV 的多分 P 优先展示全部分 P；单 P 视频所属的多 BV 合集也会展开。

每项独立保存并串行处理，重复提交会复用已有笔记或正在执行的任务。不限制一次选择的数量，所有选中条目进入本地队列串行处理。即使链接带 `?p=2`，初次解析也会默认选中这个 BV 的全部分 P；重试已有任务仍然只处理该任务。

解析只读取元数据，不会自动下载或调用总结 API；点击整理才开始处理。B 站访问限制或不完整的合集信息可能导致解析失败，可补充 Cookie 后重试。截图本身不包含 BV，请粘贴原视频链接。

## 型号识别与校正

设置中的数码术语表会作为 Whisper 的 initial_prompt / hotwords 提示，用于新转录；不是强制替换，也不保证识别正确。修改词表不会重新转录已有缓存。

已有逐字稿可点击“校正术语”：填写错误词与正确词 → 预览原句 → 确认本篇替换 → 点击右上角“重新总结”。例如将本篇确认过的 `8.15` 改为 `8E5`。不会将同一规则自动应用到其他视频。

原始转录保存在 `*_transcript.original.json`，校正记录保存在逐字稿 raw.corrections；旧摘要保留并标记待更新。请先听原片核对歧义型号，避免误改日期、价格等数字。

## 本地资料

- `backend/data/library.sqlite3`：完成的笔记与逐字稿，可搜索标题、摘要和正文。
- `backend/note_results`：结果 JSON、Markdown、带时间戳 TXT、逐字稿缓存和总结检查点。
- `backend/config`：本地设置；`backend/models`：模型权重。
- 最近整理支持右键菜单或省略号删除。进行中的任务不能删除。共享模型和转录缓存不会随单篇笔记删除。

重新总结复用当前任务的逐字稿，校正后的内容会进入新的总结。字幕、转录和总结仍可能有误，没有说话人分离。

## 聊天调用

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-mcp.txt
codex mcp add bilinote-mini --env PYTHONUTF8=1 --env PYTHONIOENCODING=utf-8 -- C:\Users\Administrator\source\BiliNote-mini\backend\.venv\Scripts\python.exe C:\Users\Administrator\source\BiliNote-mini\backend\mcp_server.py
```

重启聊天客户端后可用 search_notes、read_note、find_geekerwan_replays、inspect_replay、prepare_replays、get_replay_jobs。按需发现回放、枚举分 P、读取缓存或发起处理，没有定时检查。默认切片 UP 主 UID 为 2090606494，可在调用时指定。

B 站 UP 列表可能被风控拦截；此时返回缓存和告警，不能保证找到完整的最新回放。可以直接提供 BV 链接。后台处理串行执行，网页与聊天共用本地资料。总结会使用已配置的收费 API。

## 代码范围

前端仅 React/Vite 工作台和设置；后端仅 B 站、faster-whisper、兼容 OpenAI 的总结、本地 SQLite 和可选 MCP。已移除其他平台、桌面壳、截图、向量聊天、其他转录引擎和旧部署资源。浏览器扩展单独放在 `integrations/chrome-extension`（可选，不参与工作台构建）。`requirements-mini.txt` 仅为兼容旧安装命令的入口。

## 验证

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
.\.venv\Scripts\python.exe tests/check_mcp_connection.py
cd ../BillNote_frontend
pnpm exec tsc -p tsconfig.app.json --noEmit
pnpm build
```

保留上游 LICENSE。


### 批量并行

默认最多 3 个任务并行，下载与在线总结可交错执行，本地转录使用跨进程锁保持单任务。`MINI_TASK_CONCURRENCY=1` 可恢复串行，允许范围 1–6；修改后重启后端和队列工作进程。

## 评论区分析

笔记页提供独立的“评论区分析”Tab。同一 BV 的分 P 共用评论快照，保存于 backend/data/comments.sqlite3。可设置最多 100–5000 条、热度/时间顺序和是否包含楼中楼。重新采集会刷新该 BV 的快照并清空旧分析；采集中断会保留已取得的部分数据。

统计包括采集数、主评论、楼中楼、参与账号数、累计获赞及发布时间分布，支持原文搜索与 JSON 导出。完整标记仅表示遍历了本次接口可见分页，不保证覆盖平台所有评论。

LLM 分析单独点击触发，使用工作台所选模型与现有密钥。最多选择 100–1000 条高赞与均匀混合样本，分批生成主题、赞同/反对、纠错补充及原评 ID；分析中显示批次进度。不会自动发送全部评论。服务重启后进行中的评论任务需手动重试，已保存内容仍可读取。

## YouTube 与 Instagram

输入框支持 YouTube 单个视频（watch/Shorts/live 回放）及 Instagram 视频帖/Reels 链接，自动识别来源并在笔记标题下显示来源标签。使用本地 Whisper 自动识别音频语言，调用已配置的文字模型生成中文笔记。外站当前走音频转录；B 站保留原有字幕优先与多分 P 选择。

外站暂不支持播放列表、正在直播的视频、评论采集或自动登录。Instagram 无独立音轨时可能需要获取含画面的媒体文件。私密、登录要求、地区限制及平台反爬可能导致获取失败，页面会显示原因。Instagram 原片链接跳回视频，不能承诺定位到秒。截图与笔记仍保存在本地。

## Chrome 右键省流与知乎判断

`integrations/chrome-extension` 提供 Chrome MV3 扩展：

- 在 B 站 / YouTube 视频页右键 **省流不看**，调用本地 `/api/generate_note` 排队生成笔记；
- 在知乎问题页右键只有一个 **BiliNote 判断**：有选中文字就判断选中内容，否则自动判断当前回答或问题本身；
- 工具栏图标随页面在 BiliNote / YouTube / B 站 / 知乎之间切换，徽标显示百分比或 ✓；
- 点图标打开弹窗：进行中原生进度，已完成直接展示“省流：……”摘要，失败显示原因；悬浮卡片右上角 × 可只从扩展列表移除；
- 任务记录保存在扩展本地，只保留进行中与最近 20 条；摘要通过 `/api/task_summary/{id}` 读取，不保存逐字稿到扩展。

安装方式：

- **CRX**：`dist/release/BiliNoteMini-Extension-0.6.3.crx`。Chrome 对商店外 CRX 有额外限制，无法安装时用下面两种；
- **ZIP/解压**：解压 `dist/release/BiliNoteMini-Extension-0.6.3.zip`，打开 `chrome://extensions` → 开发者模式 → 加载已解压的扩展程序；
- **开发目录**：直接加载 `integrations/chrome-extension`。

在扩展选项里确认后端地址（默认 `127.0.0.1:8483`）和工作台地址（默认 `127.0.0.1:8483`，安装版由后端托管前端）。弹窗按当前页面显示平台登录（B 站 / YouTube），点 **同步** 一键从 Chrome 更新对应平台 Cookie。工作台深链 `#task=<id>` 可直接打开对应报告。

## 打包发布

在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build-release.ps1
```

会依次：

1. 用 pnpm 构建 `BillNote_frontend/dist`；
2. 打包后端源码、前端成品、托盘脚本、扩展和安装脚本到 `.build-tmp/payload`；
3. 生成 `dist/release/BiliNoteMini-<version>-Setup.zip`；
4. 用内置 csc 编译 `BiliNoteMini-Setup-<version>.exe`（安装程序把 payload 嵌在自身，直接解压到安装目录，不使用临时目录）；
5. 生成扩展 ZIP 和 CRX（CRX 私钥保存在 `packaging/keys/bilinote-extension.pem`，已忽略，不要公开；更换私钥会改变扩展 ID）。

可加 `-SkipFrontend` / `-SkipInstaller` / `-SkipExtension` 单独构建。首次构建会自动下载 `uv.exe` 到 `packaging/vendor`。

托盘入口是 `packaging/tray.py`，安装包会把它放到 `packaging\tray.py` 并用 `pythonw.exe` 启动。无图形界面的冒烟测试：

```powershell
backend\.venv\Scripts\python.exe packaging\tray.py --check
```

## 目录结构

```text
backend/                 FastAPI 后端、转录、下载、SQLite
BillNote_frontend/       React/Vite 工作台；dist 由后端托管
integrations/chrome-extension/  Chrome 扩展源码与图标
packaging/               托盘、安装/卸载、打包脚本、uv 与图标
docs/                    工作台截图等文档资源
scripts/                 构建辅助脚本
dist/release/            安装包、扩展包（发布产物）
backend/data|config|logs|models|note_results/  运行时数据
```

## DeepSeek Harness 插件构建

在 BillNote_frontend 运行 pnpm build，会同时生成前端和插件目录 dist/deepseek-harness/bilinote-mini，以及同目录下的 hyc3z-dsh-bilinote-mini-0.1.0.tgz。此包绑定构建机器上的项目路径，复用 Python 虚拟环境、模型和数据，不包含用户凭据。

在 Harness 的插件管理中安装生成的本地组合包；CLI 示例：`dsh plugin --profile 你的配置名 add C:/Users/Administrator/source/BiliNote-mini/dist/deepseek-harness/hyc3z-dsh-bilinote-mini-0.1.0.tgz`。配置名应使用当前 Harness 的 profile，不要直接编辑 profile 文件。

启用后在聊天输入区展开“BiliNote 工作台”即可操作。插件自动复用或启动本地 8483 后端，前端成品由后端托管，无需另开 Vite。首次配置仍需安装 backend/requirements.txt 和可选的 requirements-mcp.txt。MCP 提供现有的搜索、阅读及极客湾回放工具。具体说明见 integrations/deepseek-harness/README.md。

当前已验证构建、插件脚本语法、包清单、后端工作台路由和 MCP 握手；尚未在连接的 Harness profile 内验证安装及实际 UI 渲染。

## 停止全部任务

批次管理页的“停止全部任务”会取消持久队列中的排队任务，并向正在执行的任务发送停止标记。排队任务立即显示“已停止”，执行中任务显示“停止中”，在当前下载/转录片段或模型请求返回后的检查点退出，不继续执行后续步骤。已发出的模型请求不保证能够撤回或免除费用。已完成笔记、音轨、逐字稿和总结检查点不删除；之后可显式重试。

升级此功能需要重新加载网页后端和独立的 chat_worker.py 执行器；升级前已启动的旧执行器不具备停止检查能力。取消状态保存在本地，服务重启不会自动恢复用户取消的任务。评论分析是独立流程，不包含在视频队列的“停止全部任务”中。
