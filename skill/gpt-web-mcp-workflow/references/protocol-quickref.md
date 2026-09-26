# GPT Web MCP 速查

## 本地入口

- 项目根目录：`D:\桌面\Work\GPT Web MCP`
- Bridge：`http://127.0.0.1:8765`（token 在 `config/config.json` 的 `bridge_token`）
- 启动：`scripts\start_bridge.ps1`；停止：`scripts\stop_bridge.ps1`；托盘：`scripts\start_bridge_tray.cmd`
- 健康自检：`python scripts/health_report.py`；统一校验：`python scripts/release_check.py`
- 扩展目录：`extension\`（Edge 开发者模式加载未解压扩展；版本必须与 Bridge 一致）

## MCP 工具

| 工具 | 作用 |
|---|---|
| `browser_status` | Bridge/扩展/标签页/生成状态 |
| `list_chatgpt_tabs` | 全部 ChatGPT 标签页快照 |
| `bind_chatgpt_tab(tab_id)` | 绑定指定标签页，返回 `target_id` |
| `get_bound_chatgpt_tab` | 当前绑定标签页 |
| `ask_chatgpt(question)` | 高层一体：确认绑定→发送→等待→返回完整回答 |
| `chat_send(...)` | 底层发送并等待回答 |
| `chat_sync` | 页面快照入库 |
| `chat_read(conversation_id, after_sequence)` | 游标读取本地消息 |
| `get_latest_message` | 最近消息 + `response_state` |
| `chat_wait_event` | 游标后等待新消息 |
| `chat_cancel` | 取消排队/执行中任务 |
| `chat_search` / `chat_export` | 检索 / 导出 Markdown、JSON |

## 关键 HTTP 端点

- `GET /api/status`、`GET /api/tabs`、`POST /api/tabs/bind`、`GET /api/chat/latest`
- `POST /api/chat/send`、`POST /api/chat/sync`、`GET /api/chat/messages`、`GET /api/chat/wait`
- `POST /api/chat/cancel/{request_id}`、`POST /api/shutdown`
- 请求需 `X-Bridge-Token`；扩展 WebSocket 需 `?token=` 与 `chrome-extension://` Origin

## 状态字段

`response_state`: `idle` / `waiting` / `streaming`（来自页面 `generating` 上报）
`chatgpt_tabs[]`: `tab_id / title / url / active / window_id / bound_target_id / page_ready / generating`

## 常见错误码

`UNAUTHORIZED`、`EXTENSION_NOT_CONNECTED`、`CHATGPT_TAB_NOT_FOUND`、`CHATGPT_PAGE_NOT_READY`、
`INPUT_NOT_FOUND`、`SEND_FAILED`、`RESPONSE_TIMEOUT`、`EMPTY_RESPONSE`、`EXTENSION_BUSY`、
`REQUEST_CANCELLED`、`BIND_TIMEOUT`、`BRIDGE_OFFLINE`、`EXTENSION_DISCONNECTED`

## 故障速答

- `RESPONSE_TIMEOUT`：先用 `get_latest_message` 找回回答；再建议重载扩展（版本号要一致）。
- 版本不一致：扩展 `manifest.json` 版本必须等于 `src/gpt_web_mcp/__init__.py` 的 `__version__`，改完重载扩展并重启 Bridge。
- 标签页丢失：打开/刷新 ChatGPT 标签页，单标签自动绑定。
- Bridge 掉线：`scripts/start_bridge.ps1` 或托盘“开启桥接”。
