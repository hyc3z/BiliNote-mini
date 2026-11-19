# BiliNote 省流 · Chrome 扩展

给本地 BiliNote Mini 加的 Chrome 右键入口：在支持的视频站点右键 **省流不看**，后台调用工作台同款接口生成笔记；工具栏图标显示百分比 / ✓，点图标可以随时打开任务和报告。图标会随当前页面在 BiliNote / YouTube / B 站 / 知乎之间切换。

在知乎问题页还支持 **按需判断**：选中一句话/一段字、右键一条回答、或右键问题标题，页面内直接弹出类似词典的小卡片，判断这段话/这条回答/这个问题是否合理；不预加载、不整篇总结、不保存。

![工具栏弹窗](docs/popup.png)

## 安装

1. 先启动本地工作台（安装版托盘会自动启动；开发版运行 `start-mini.ps1`），确认 `http://127.0.0.1:8483/api/sys_check` 返回 `code: 0`。
2. 安装扩展，任选一种：
   - **CRX**：`dist/release/BiliNoteMini-Extension-0.6.3.crx`（Chrome 对商店外 CRX 有限制，装不上就用下面两种）；
   - **ZIP**：解压 `dist/release/BiliNoteMini-Extension-0.6.3.zip`，打开 `chrome://extensions` → 开发者模式 → **加载已解压的扩展程序**；
   - **源码**：直接加载 `integrations/chrome-extension`。
3. 点扩展的“详情 → 扩展程序选项”，确认后端地址（默认 `http://127.0.0.1:8483`）和工作台地址（安装版默认 `http://127.0.0.1:8483`；开发版可改成 `http://127.0.0.1:3015`），点“测试连接”。
4. 建议点工具栏图标，在弹窗顶部点 **同步**：扩展会从当前 Chrome 读取当前页面平台（B 站 / YouTube）的 Cookie 并写入本地后端，不需要再 F12 复制。YouTube 页面显示的是 YouTube Cookie，不会再显示成 B 站账号。

> 扩展申请了 `cookies` 权限和 `bilibili.com` / `youtube.com` / `zhihu.com` 的站点权限，用来读取登录 Cookie（知乎只读页面内容，不需要 Cookie 同步）。Cookie 只会发送到本机 `127.0.0.1:8483`，不会写入扩展存储，也不会上传到其它地方。

> Chrome 137 起已移除 `--load-extension` 启动参数，只能用上面的“加载已解压”方式，或使用 Chrome for Testing。

## 使用

1. 打开 B 站、YouTube（watch / Shorts / live）或 Instagram（p / reel / tv）视频页。
2. 右键 → **省流不看**；也可以右键视频/帖子里的链接。
3. 工具栏图标：
   - `…`：已提交，等待/处理中，还不知道百分比；
   - `42`：当前阶段 42%；
   - `✓`：完成；`!`：失败。
4. 点扩展图标打开弹窗：进行中的任务有真实进度条和已用时；**已完成任务直接显示“省流：……”摘要**，感兴趣再点卡片打开完整报告；失败任务显示错误原因。鼠标悬浮在完成/失败卡片上时，右上角出现 ×，可把该条从扩展列表移除（不会删除工作台的笔记）。
5. 完成后会收到系统通知，点通知也能直接打开报告。
6. 弹窗顶部按当前页面显示平台账号：B 站页显示“B 站登录”，YouTube 页显示“YouTube Cookie”，只显示已登录/已同步状态，不展示账号名。登录状态失效时点 **同步** 即可。

## 知乎按需判断

在知乎问题页（`zhihu.com/question/...`）右键只有 **一个** `BiliNote 判断` 项，扩展会根据你右键的位置自动判断：

- 如果当前有文字选中 → 判断选中的内容（带问题标题和所在回答上下文）；
- 否则如果右键在一条回答里 → 判断这条回答；
- 否则如果右键在问题标题/描述上 → 判断问题本身；
- 都不是时提示在回答正文或问题标题上右键。

不再预加载、不扫全页、不保存结果。判断卡片可以拖动标题栏移动，只有点右上角 × 或按 Esc 才关闭，点页面其它地方不会误关；同一段内容在页面生命周期内会缓存，重复右键直接秒出。

卡片包含一句话概括、结论标签、可取之处、不足之处、值得思考点和需要核实的断言；不写入工作台、不持久化。默认优先使用名字里带 `flash` 的模型，并在后端以低推理强度调用，目标 3–5 秒返回。

> 判断的是论证质量（相关性、论据、逻辑、立场、可验证性），不是联网事实核查；`需核实` 是提示，不是“造谣”结论。

## 实现说明

- 右键菜单在支持的站点页面出现；提交前会把链接收敛成单个视频地址（B 站只保留 BV + p，YouTube 去掉 `list/index` 等参数），不会提交整个列表。
- 工具栏图标随当前页面切换：BiliNote 工作台/其它页面用闪电图标，YouTube 用红色播放图标，B 站用电视图标。YouTube / B 站 / 工作台页面右键有 **同步 B 站登录** / **同步 YouTube 登录**，都是平铺的一级项；Chrome 会把同一扩展的所有项统一收进“BiliNote 省流”分组里，这是浏览器行为，扩展自身不再嵌套子菜单。
- 平台账号通过 `common.js` 里的 `ACCOUNT_PROVIDERS` 注册：B 站、YouTube 已接入，后续加知乎只需要补一条 provider + 对应后端实现。
- 提交走 `POST /api/generate_note`（与网页工作台相同参数，一次只建一个任务），轮询走 `GET /api/task_status/{id}`。
- 模型来自 `GET /api/model_list`；在扩展设置里选“默认模型”，不选则用第一个已启用的模型。没有模型时会提示去工作台设置。
- 平台登录同步：用 `chrome.cookies` 读取当前 Chrome 对应平台的 Cookie，在 service worker 内拼成请求头后 POST 到 `/api/update_downloader_cookie`；不会写入扩展存储，也不会回传给弹窗。状态来自 `/api/account_status?platform=...`，只显示已登录/已同步，不展示账号名。YouTube Cookie 会由后端 `ExternalDownloader` 注入 yt-dlp。
- 弹窗右上角显示版本号；后台协议/版本不一致时提示“立即重新加载”或“扩展管理页”。底部也有“重载”按钮，代码更新后可一键重载扩展。
- 任务记录存在 `chrome.storage.local`，只保留进行中 + 最近 20 条；完成任务的摘要来自后端 `/api/task_summary/{id}`（只返回省流段落，不返回逐字稿）。弹窗里的 × 只移除扩展列表记录，不删除工作台笔记。
- 知乎判断：`zhihu-content.js` 只监听一个 `BiliNote 判断` 菜单项，按右键位置自动区分选中文字/回答/问题；只采集当前目标，通过 `zhihu-judge` 消息交给 service worker；后端 `/api/zhihu/judge` 一次 LLM 调用返回 JSON，不建任务、不落库。模型自动优先 `flash`，`ZHIHU_REASONING_EFFORT` 默认 `low`；不支持 `reasoning_effort`/JSON 模式的供应商会自动降级。卡片可拖动、不响应外部点击，关闭后才消失。
- **关于“进度条”**：Chrome 工具栏没有给扩展的进度条 API，所以用百分比徽标近似下载提示；弹窗里是真正的进度条。MV3 的 service worker 会被浏览器休眠，扩展用 `chrome.alarms`（30 秒）兜底、醒着时 2 秒软轮询，所以徽标最快约 2 秒、最慢约 30 秒更新一次；弹窗打开时是实时刷新。
- 工作台前端新增了 `#task=<id>&url=&title=` 深链：已完成的笔记直接打开；还在处理的任务会落到工作台的“处理中”视图，由工作台自己的轮询接管。若工作台是后端托管的 `8483` 静态构建，需要先 `pnpm build` 让新前端生效。深链使用 hash 而不是 query，避免 Vite dev server 对 query 里的 URL 做路径校验而返回 403。

## 文件结构

```
manifest.json      MV3 清单（0.6.x）
background.js      右键菜单、平台账号同步、任务提交/轮询、徽标、通知
common.js          共享常量 / storage / URL 工具 / 平台注册表
zhihu-content.js   知乎按需采集 + 页面内判断浮层
popup.html|css|js  工具栏弹窗（版本号 / 重载 / 当前平台 Cookie）
options.html|css|js 扩展设置
icons/             默认 BiliNote 图标
icons/youtube/     YouTube 页面图标
icons/bilibili/    B 站页面图标
icons/zhihu/       知乎页面图标
docs/popup.png     弹窗截图
tools/make-icons.py 图标生成
```

## 排错

- 弹窗显示“本地后端未连接”：先跑 `start-mini.ps1`，或在扩展设置里改后端地址后“测试连接”。
- 弹窗显示“未知消息：...”或“扩展后台未响应”：修改扩展代码后 service worker 还在跑旧版本。点弹窗里的“立即重新加载”（或底部“重载” / 到 `chrome://extensions` 刷新），然后重新打开弹窗；Chrome 不需要重启。
- 版本号旁边/警告条里可以点“扩展管理页”，直接打开本扩展在 `chrome://extensions` 的详情。
- 点“同步”提示找不到 SESSDATA / SID：确认当前 Chrome profile 已登录对应平台（B 站 / YouTube）；扩展只能读取安装所在 profile 的 Cookie。
- 弹窗显示“状态未知”：后端还没重启，`/api/account_status`、`/api/zhihu/judge` 是新接口；重启一次后端即可。
- 知乎右键没有反应：重载扩展后刷新知乎页面；如果标签页是旧页面，扩展会自动补注入 `zhihu-content.js`，仍失败时刷新页面。
- 知乎判断很慢：后端会自动优先 `flash` 模型；如果当前供应商不支持低推理参数，会降级重试。可在后端环境变量调整 `ZHIHU_REASONING_EFFORT`（默认 `low`）。
- 右键菜单没出现：确认页面的站点在支持范围内；扩展详情里看“网站访问权限”是否包含 `127.0.0.1`、`bilibili.com`、`youtube.com`；必要时重载扩展。
- 任务一直排队：这是后端串行/并行队列在忙，去工作台看队列状态即可。
- 改了前端深链后打开报告仍停在列表：确认访问的是有热更新的 `3015`，或是重新 `pnpm build` 后的 `8483` 静态版。
- 扩展只为“平台登录同步”读取 B 站 / YouTube 的 Cookie，并只发送到本机 `127.0.0.1` / `localhost`；知乎只读取右键回答/选中文字的文本，不采集整页。不会上传到第三方（除了你配置的 LLM 供应商）。
