# GPT Web MCP 长期路线

## 目标

建立一套本地优先的 Agent-to-ChatGPT Web 桥接系统：

1. Agent 通过标准 MCP 发送任务和读取结果。
2. Edge/Chrome 扩展操作用户已经登录的 ChatGPT 页面。
3. Bridge 负责队列、状态、取消、重连、采集和持久化。
4. Codex 可以编排连续对话、多角色分析和多标签页任务。
5. 每个版本都拥有独立的 Markdown 工作文件、验收条件和变更记录。

## 固定架构决策

| 项目 | 决策 |
|---|---|
| Agent 接入 | MCP stdio，后续可增加 Streamable HTTP |
| 扩展通信 | 本地 WebSocket + JSON 消息 |
| Bridge API | 本地 HTTP，用于状态、任务、取消和诊断 |
| 浏览器 | Edge 优先，Chrome/Chromium 复用同一 MV3 扩展 |
| 初始并发 | 单标签页单任务串行 |
| 采集方式 | Content Script + MutationObserver + 增量游标 |
| 数据存储 | 本地 SQLite，日志与聊天正文分离 |
| 安全边界 | 仅监听回环地址，扩展与 Bridge 使用安装级 token |
| 会话策略 | 默认保持当前对话，新建会话必须显式请求 |
| 项目根目录 | `D:\桌面\Work\GPT Web MCP` |

## 版本路线

### V1：单标签页桥接

目标：完成最小可用闭环。

- Edge 扩展加载、连接和绑定当前 ChatGPT 标签页。
- MCP 工具发送一条消息并等待回答。
- MCP 工具读取当前页面的新消息。
- Bridge 自动启动、排队、取消、超时、重连。
- SQLite 保存任务、会话和消息。
- 提供状态与诊断信息。

验收：Codex 可以通过 MCP 调用已绑定的 ChatGPT 页面完成一次稳定的发送、回答返回和增量读取。

工作文件：[V1_SINGLE_TAB.md](V1_SINGLE_TAB.md)

### V1-B：Chrome/Chromium 兼容形态

目标：验证同一扩展包在 Chrome 及 Chromium 内核浏览器中运行。

- 抽离浏览器差异配置。
- 提供 Edge/Chrome 安装说明。
- 增加扩展版本和协议版本诊断。
- 建立两套浏览器页面适配验收记录。

工作文件：[V1B_CHROMIUM_COMPAT.md](V1B_CHROMIUM_COMPAT.md)

### V2：多标签页与多人格编排

目标：让 Codex 为不同角色使用不同 ChatGPT 标签页，并统一收集结果。

- `target_id`、`persona_id`、`task_group_id`。
- 每个标签页独立队列。
- 全局限流和失败隔离。
- 角色提示词配置与结果汇总。
- 多标签页状态恢复。

工作文件：[V2_MULTI_TARGET_PERSONA.md](V2_MULTI_TARGET_PERSONA.md)

### V3：长期采集与恢复

目标：把网页对话变成可查询的本地知识流。

- 页面初始快照和增量同步。
- 游标、断点续采和重复消息去重。
- 会话搜索、过滤、导出。
- 页面刷新、浏览器重启后的状态恢复。
- 可配置数据保留周期。

工作文件：[V3_LONG_RUNNING_CAPTURE.md](V3_LONG_RUNNING_CAPTURE.md)

### V4：桌面化和分发

目标：降低日常使用成本。

- 一键启动器或托盘程序。
- 自动生成扩展配置和 token。
- Bridge、MCP、扩展版本检查。
- 安装、升级、回滚和诊断包。
- 面向普通使用者的操作文档。

工作文件：[V4_PACKAGING_OPERATIONS.md](V4_PACKAGING_OPERATIONS.md)

## 实施顺序

```text
V1 文档基线
  -> V1 Bridge/MCP/扩展闭环
  -> V1 测试和诊断
  -> V1-B Chrome 兼容
  -> V2 多标签页/多人格
  -> V3 长期采集/恢复
  -> V4 桌面化/分发
```

每完成一个版本，必须更新：

- 对应版本工作文件的状态和验收记录。
- [WORK_FILES.md](WORK_FILES.md) 索引。
- [WORK_LOG.md](WORK_LOG.md) 实施日志。
- 项目根目录结构和清理记录。
