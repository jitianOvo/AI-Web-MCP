# GPT Web MCP 验收矩阵

本矩阵区分三类证据：

- `verified`：已有自动化测试、运行命令或实际生成物证明。
- `implemented_pending_live`：代码路径已实现，但需要真实浏览器现场确认。
- `planned`：尚未实现。

## 版本 × 模块

| 版本 | 工作模块 | 当前状态 | 证据 |
|---|---|---|---|
| V1 | MCP stdio 工具发现 | `verified` | `initialize` / `tools/list` |
| V1 | Bridge HTTP/WebSocket 闭环 | `verified` | `tests/test_bridge.py`、本地回放器 |
| V1 | 发送、空回答、页面错误、超时、取消 | `verified` | Bridge 回环测试 |
| V1 | SQLite 消息、游标、去重 | `verified` | `tests/test_storage.py` |
| V1 | 真实 ChatGPT 页面 | `verified` | Edge 0.1.3 现场发送/回答/读取通过，见 [V1_E2E_ACCEPTANCE.md](V1_E2E_ACCEPTANCE.md) |
| V1 | 唯一标签页自动绑定 | `verified` | 扩展 `autoBindSingleTab`；Edge 现场自动绑定 `tab-1885863082` |
| V1 | 标签页枚举与指定绑定 | `verified` | `list_chatgpt_tabs` / `bind_chatgpt_tab` 回环测试 |
| V1 | 高层 `ask_chatgpt` 与 `get_latest_message` | `verified` | 回环测试与 MCP facade |
| V1-B | Manifest V3、Edge/Chrome 权限 | `verified` | `test_extension_manifest.py` |
| V1-B | 浏览器名称/版本上报 | `verified` | 目标状态测试 |
| V1-B | Edge/Chrome 页面现场对照 | `implemented_pending_live` | [V1B_CHROMIUM_COMPAT.md](V1B_CHROMIUM_COMPAT.md) |
| V2 | 多目标连接与 `target_id` 路由 | `verified` | 双目标回环测试 |
| V2 | 多目标独立队列/并行 | `verified` | 并行目标回环测试 |
| V2 | 人格配置与提示词注入 | `verified` | 人格回环测试 |
| V2 | 任务组提交和状态 | `verified` | 任务组回环测试 |
| V2 | 断连失败隔离 | `verified` | 目标断连测试 |
| V2 | 活动任务上限/速率限流 | `verified` | 配置与调度实现 |
| V2 | 结果 Markdown 汇总/冲突候选标记 | `verified` | 任务组回环测试；语义裁决仍由 Agent 完成 |
| V2 | 多目标绑定持久化/重启恢复代码路径 | `implemented_pending_live` | 扩展静态检查；待真实浏览器重启验收 |
| V3 | 页面快照、搜索、导出 | `verified` | `chat_sync`、`chat_search`、`chat_export` |
| V3 | 断连事件缓冲与回放 | `implemented_pending_live` | 扩展静态检查；待真实 Service Worker 验收 |
| V3 | Bridge 重启任务标记 | `verified` | SQLite 重启回归测试 |
| V3 | 数据保留预览/清理 | `verified` | `prune_data.py` 与存储测试 |
| V3 | 浏览器刷新恢复 | `verified` | Edge 现场刷新后同目标重新连接保持 ready |
| V4 | 自动启动/停止/版本检查 | `verified` | 启停脚本和安装自检 |
| V4 | token 轮换 | `verified` | `rotate_token.py` |
| V4 | 扩展包/诊断包 | `verified` | `build/*.zip` 内容检查 |
| V4 | 统一 release check | `verified` | `release_check.py` 实际通过 |
| V4 | 托盘、升级、回滚 | `planned` | [V4_PACKAGING_OPERATIONS.md](V4_PACKAGING_OPERATIONS.md) |
| V4 | UI+API 双后端路由（auto/ui/api） | `verified`（未配 Key 时 API 返回 `API_KEY_MISSING`） | `BackendRouter` 回环测试；API Key 待外部配置 |

## 浏览器形态

| 形态 | 协议代码 | 本地回环 | 真实页面 |
|---|---:|---:|---:|
| Edge 单标签页 | ✅ | ✅ | ✅ 0.1.3 |
| Chrome 单标签页 | ✅ | ✅ | 待验收 |
| Edge 多标签页 | ✅ | ✅ | 待验收 |
| Chrome 多标签页 | ✅ | ✅ | 待验收 |

## 当前现场条件

- 本机 Edge 进程存在。
- 常见 CDP 端口未监听。
- Computer Use 浏览器枚举通道报告 `nodeRepl.fetch request failed`。
- 本地协议回放器不替代真实页面验收。

## 更新规则

每次实现或现场测试后，更新本文件对应行，同时更新 [WORK_LOG.md](WORK_LOG.md)。
