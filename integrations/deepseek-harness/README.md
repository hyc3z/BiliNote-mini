# BiliNote Harness 插件

构建后安装生成的目录或 tgz，不要安装模板源目录。插件使用此机器的 BiliNote 本地项目路径，不能直接移到另一台机器。

安装后聊天输入区出现 BiliNote 工作台按钮，展开后操作笔记页面。插件优先复用端口 8483 的现有后端，否则自动启动本地 Python 后端；首次启动几秒后刷新内嵌页面。当前需要已安装 backend/.venv、requirements.txt 和 requirements-mcp.txt。模型、设置和资料均复用原项目。

MCP 提供搜索/阅读笔记、极客湾回放发现与分 P 入队工具。现有 MCP 的回放入队仅针对已配置的极客湾切片 UP；其他平台通过工作台操作。整理视频可能调用收费文字模型；插件不会自动发起视频分析。

在 Harness 插件管理中安装本地组合包；也可使用 CLI：dsh plugin --profile 你的配置名 add 生成的目录或tgz路径。不要直接修改 profile 文件。

日志：backend/logs/harness.stdout.log、harness.stderr.log。卸载仅停止插件自己启动的后端，不删除数据；复用的已有后端不会停止。

不包含凭据、数据库、音频或模型。工作台是本地页面嵌入，保留 BiliNote 自身样式。
