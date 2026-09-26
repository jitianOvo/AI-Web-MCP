# GPT Web MCP 协议基线

协议版本：`1.0`

本文件是 V1 到后续版本共同使用的契约。浏览器选择器可以变化，但 MCP 工具和 Bridge 消息应保持向后兼容；有破坏性变更时递增协议主版本。

## 通用消息封装

扩展与 Bridge 的 WebSocket 消息使用 JSON：

```json
{
  "protocol_version": "1.0",
  "type": "message_type",
  "timestamp": 0,
  "request_id": "optional-request-id"
}
```

## Bridge → 扩展

| type | 作用 | 主要字段 |
|---|---|---|
| `bridge_ready` | WebSocket 建立完成 | `status` |
| `task` | 请求页面发送消息 | `request_id`, `conversation_id`, `prompt`, `timeout_ms` |
| `cancel` | 停止当前任务 | `request_id` |
| `sync` | 请求当前页面消息快照 | `request_id`, `conversation_id` |
| `bind_tab` | 请求绑定指定 ChatGPT 标签页 | `request_id`, `tab_id` |

## 扩展 → Bridge

| type | 作用 | 主要字段 |
|---|---|---|
| `hello` / `status` | 扩展和页面状态 | `tab_bound`, `page_ready`, `target_id`, `tab_id` |
| `hello` / `status`（补充） | 页面生成状态与标签页快照 | `generating`, `conversation_title`, `tabs[]` |
| `result` | 一次发送任务完成 | `request_id`, `result`, `conversation_id`, `message_id` |
| `error` | 页面任务或同步失败 | `request_id`, `code`, `message` |
| `message_event` | 新发现或更新的消息 | `conversation_id`, `message` |
| `sync_result` | 页面快照返回 | `request_id`, `conversation_id`, `messages` |
| `heartbeat` | 保持 Service Worker 与 Bridge 活跃 | `timestamp` |
| `bound_result` | 绑定指定标签页完成 | `request_id`, `target_id`, `title` |

## 消息对象

```json
{
  "message_id": "page-message-id",
  "role": "user|assistant|system",
  "content": "normalized rendered text",
  "content_hash": "dedupe-hash"
}
```

同一 `conversation_id + message_id` 的内容更新应覆盖旧内容，用于处理 Assistant 流式生成；相同内容哈希不重复插入。

`hello` / `status` 消息中的 `tabs` 是当前浏览器内全部 ChatGPT 标签页快照数组，每项包含 `tab_id`、`tab_title`、`tab_url`、`active`、`window_id`；Bridge 按 `tab_id` 去重合并，并标记哪个标签页已被绑定（`bound_target_id`）。

`target_id` 用于选择具体浏览器目标。省略时使用当前第一个就绪目标；V1 只有一个默认目标，V2 支持多个独立目标。

## MCP 工具

### `browser_status`

返回 Bridge、扩展、标签页和页面就绪状态。

### `list_chatgpt_tabs`
返回全部 ChatGPT 标签页快照（`tab_id`、标题、URL、`active`、`window_id`、`bound_target_id`、页面就绪和生成状态）。

### `bind_chatgpt_tab`
按 `tab_id` 绑定指定标签页，返回该标签页的 `target_id`；多标签页时由 Agent 自行选择。

### `get_bound_chatgpt_tab`
返回当前绑定标签页信息；未绑定时 `bound_target_id` 为空。

### `get_latest_message`
返回指定会话最近一条已采集消息和 `response_state`（`idle` / `streaming`）。

### `ask_chatgpt`
高层一体化接口：确认绑定标签页、发送问题、等待完整回答并返回；底层 `chat_send` 等工具保留用于调试。

### `chat_send`

```json
{
  "content": "message text",
  "conversation_id": "current",
  "expected_format": "text",
  "timeout_ms": 600000,
  "target_id": "optional-target"
}
```

返回 `request_id`、`conversation_id` 和完整 Assistant 结果。

### `chat_read`

使用 `after_sequence` 增量读取本地数据库中的消息。

### `chat_search` / `chat_export`

`chat_search` 在本地按文本片段、会话和角色过滤；`chat_export` 返回指定会话的 Markdown 或 JSON 内容，不直接写入项目外文件。

扩展连接断开时，`message_event` 可先进入扩展本地事件缓冲；重连后按目标回放，Bridge 仍按消息 ID/内容哈希去重。

### `chat_wait_event`

在指定游标后等待新消息；超时返回 `timed_out=true`，不把超时当作 Bridge 故障。

### `chat_sync`

请求绑定页面当前已渲染消息的快照，并写入本地数据库。

### `chat_cancel`

取消排队或执行中的任务。

### 人格工具

- `persona_upsert`：保存或更新 `persona_id`、名称、系统提示词和扩展配置。
- `persona_list`：列出本地人格配置。

### 任务组工具

- `task_group_submit`：提交最多 32 个带 `persona_id` / `target_id` 的任务项，等待并返回逐项结果。
- `task_group_status`：读取任务组状态和已持久化任务详情。

`task_group_submit` 额外返回 `merged_markdown` 和 `conflict_candidates`；冲突候选仅依据同一输入产生的不同结果标记。
- `chat_task_status`：读取单任务状态；Bridge 重启后的未完成任务状态为 `interrupted`。

## V1 状态模型

```text
queued -> running -> completed
queued -> cancelled
running -> cancelled
running -> failed
running -> timed_out
```

同一标签页只允许一个 `running` 任务；后续任务必须排队或由调用方显式取消。

V2 已为每个就绪目标建立独立队列和 Worker；同一目标串行，不同目标可并行，但受 `max_active_jobs` 全局活动任务上限和可选 `rate_limit_per_minute` 约束。未绑定目标仍进入回退队列并在执行时报告连接状态。

## V4 协议扩展

### Bridge → 扩展新增

| type | 作用 | 主要字段 |
|---|---|---|
| `open_tab` | 新建 ChatGPT 标签页并等待可交互 | `request_id` |
| `new_chat` | 进入新聊天 | `request_id`, `target_id` |
| `check_state` | 查询页面实际状态 | `request_id`, `target_id`, `prompt` |

### 扩展 → Bridge 新增

| type | 作用 | 主要字段 |
|---|---|---|
| `open_result` | 新建标签页完成 | `request_id`, `tab_id`, `target_id`, `ready` |
| `new_chat_result` | 新聊天完成 | `request_id`, `conversation_id`, `is_new_chat` |
| `state_result` | 页面状态快照 | `request_id`, `state{}` |
| `progress` | 任务生命周期阶段 | `request_id`, `stage` |

生命周期阶段：`CREATED -> INPUT_READY -> SUBMITTED -> USER_MESSAGE_CONFIRMED -> STREAMING -> STABILIZING -> COMPLETED`；超时后按页面状态分类 `still_generating / send_failed / completed_but_missed / confirmed_no_reply / extension_offline / state_unreachable`，`USER_MESSAGE_CONFIRMED` 后禁止重复发送。

### 新增 HTTP 端点

- `POST /api/tabs/open`：新建标签页并等待就绪绑定。
- `POST /api/chat/new`：`{
  "target_id": ""` } 进入新聊天。
- `POST /api/chat/sync-state`：重新同步消息并返回页面状态。
- `POST /api/pause` / `POST /api/resume`：暂停/恢复接受新任务。

### 新增 MCP 工具

- `open_chatgpt_tab`：无标签页时自动新建。
- `new_chat`：主动进入空白新会话。
- `sync_chat_state`：恢复现场，不重发。
- `wait_for_response(request_id)`：等待任务终态。
- `get_chat_history`：读取会话历史。
- `ask_chatgpt(..., new_chat=False)`：高层一体，可选先开新聊天再提问；无标签页时自动打开。

### 统一入口

`build/GPT Web MCP.exe`（MinGW C++）：单实例、控制台日志、托盘图标；左键显示/隐藏控制台，右键 启动/暂停、关闭；关闭窗口缩托盘不退出；退出时停止子进程并清理。

## Backend 路由（UI / 官方 API）

`ask_chatgpt` 统一走 `BackendRouter`，返回结构一致：`success / text / backend / elapsed / error / error_code`。

- `backend=auto`（默认）：UI 优先，UI 提交失败/超时自动 fallback 到官方 API。
- `backend=ui`：只走网页标签页通道（bridge → 扩展/CDP）。
- `backend=api`：只走官方 Responses API（流式、重试、超时、会话历史）。

API Key 来源：环境变量 `OPENAI_API_KEY`、`config/api_key.local.json`（已 gitignore）或 `config.json` 的 `openai_api_key`；日志只显示 `API backend configured`，绝不打印 Key。API 与网页 ChatGPT 会话互相独立，API 结果不回填网页历史。

Bridge 状态增加 `backend` 字段（`configured` / `last` / `api_key_configured`），托盘可展示。
