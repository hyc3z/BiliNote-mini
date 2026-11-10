# BiliNote Mini

个人使用的 B 站回放笔记工具：字幕优先，无字幕时获取音轨并本地转录，再调用 DeepSeek 等兼容 OpenAI 的接口总结。保留时间戳、逐字稿、本地搜索和聊天工具接口。

## 启动

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

打开 http://127.0.0.1:3015 ，在设置中填写 DeepSeek 的接口地址、API Key、模型名称；必要时填写 B 站 Cookie。凭据仅在本地保存，请勿提交配置文件。

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

前端仅 React/Vite 工作台和设置；后端仅 B 站、faster-whisper、兼容 OpenAI 的总结、本地 SQLite 和可选 MCP。已移除其他平台、桌面壳、浏览器扩展、截图、向量聊天、其他转录引擎和旧部署资源。`requirements-mini.txt` 仅为兼容旧安装命令的入口。

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

## DeepSeek Harness 插件构建

在 BillNote_frontend 运行 pnpm build，会同时生成前端和插件目录 dist/deepseek-harness/bilinote-mini，以及同目录下的 hyc3z-dsh-bilinote-mini-0.1.0.tgz。此包绑定构建机器上的项目路径，复用 Python 虚拟环境、模型和数据，不包含用户凭据。

在 Harness 的插件管理中安装生成的本地组合包；CLI 示例：`dsh plugin --profile 你的配置名 add C:/Users/Administrator/source/BiliNote-mini/dist/deepseek-harness/hyc3z-dsh-bilinote-mini-0.1.0.tgz`。配置名应使用当前 Harness 的 profile，不要直接编辑 profile 文件。

启用后在聊天输入区展开“BiliNote 工作台”即可操作。插件自动复用或启动本地 8483 后端，前端成品由后端托管，无需另开 Vite。首次配置仍需安装 backend/requirements.txt 和可选的 requirements-mcp.txt。MCP 提供现有的搜索、阅读及极客湾回放工具。具体说明见 integrations/deepseek-harness/README.md。

当前已验证构建、插件脚本语法、包清单、后端工作台路由和 MCP 握手；尚未在连接的 Harness profile 内验证安装及实际 UI 渲染。

## 停止全部任务

批次管理页的“停止全部任务”会取消持久队列中的排队任务，并向正在执行的任务发送停止标记。排队任务立即显示“已停止”，执行中任务显示“停止中”，在当前下载/转录片段或模型请求返回后的检查点退出，不继续执行后续步骤。已发出的模型请求不保证能够撤回或免除费用。已完成笔记、音轨、逐字稿和总结检查点不删除；之后可显式重试。

升级此功能需要重新加载网页后端和独立的 chat_worker.py 执行器；升级前已启动的旧执行器不具备停止检查能力。取消状态保存在本地，服务重启不会自动恢复用户取消的任务。评论分析是独立流程，不包含在视频队列的“停止全部任务”中。
