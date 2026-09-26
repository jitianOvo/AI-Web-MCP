# GPT Web MCP

通过 Edge / Chrome 扩展连接已登录的 ChatGPT 网页，并为 Codex / Agent 提供标准 MCP 工具。

## 当前状态

- 项目阶段：V1 单标签页闭环实施中
- 当前实现：文档基线、Bridge、MCP facade、扩展骨架和 SQLite 已建立
- 已实现：唯一标签页自动绑定、标签页枚举/指定绑定、`ask_chatgpt` 高层接口和回答状态上报
- 浏览器目标：Edge 优先，兼容 Chrome/Chromium
- Agent 接口：MCP stdio
- 扩展通信：本地 WebSocket + JSON
- 本地服务：回环地址上的 Bridge HTTP 服务
- 长期目标：按版本、浏览器形态和工作模块逐项实现、测试、记录和清理

## 架构原则

```text
Codex / Agent
    -> MCP stdio
MCP 工具层
    -> 本地 HTTP / WebSocket
Bridge 服务
    -> WebSocket
Edge / Chrome 扩展
    -> Content Script
ChatGPT 网页
```

MCP 只负责 Agent-facing 工具契约；WebSocket 只负责扩展与 Bridge 的实时通信；网页选择器和 DOM 变化隔离在扩展适配器内。

## 长期工作文件

总路线与状态见 [docs/ROADMAP.md](docs/ROADMAP.md)，所有版本和运行形态的 Markdown 工作文件见 [docs/WORK_FILES.md](docs/WORK_FILES.md)。

首次使用见 [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)。

协议契约见 [docs/PROTOCOL.md](docs/PROTOCOL.md)。

V2 人格和任务组格式见 [docs/PERSONA_FORMAT.md](docs/PERSONA_FORMAT.md)。

本地初始化和打包入口见 [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)。

版本与现场验收证据见 [docs/ACCEPTANCE_MATRIX.md](docs/ACCEPTANCE_MATRIX.md)。

真实浏览器现场步骤见 [docs/REAL_BROWSER_RUNBOOK.md](docs/REAL_BROWSER_RUNBOOK.md)。

## 文件管理

所有源代码、依赖、配置、测试、构建产物、日志和临时文件均归属于本项目根目录 `D:\桌面\Work\GPT Web MCP`。不得把本项目文件散落到其他项目目录。
