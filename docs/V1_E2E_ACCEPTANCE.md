# V1 真实浏览器现场验收

状态：`in_progress`

## 验收范围

- [x] Edge 加载 `extension` 未解压扩展。
- [x] ChatGPT 页面已登录并绑定当前标签页。
- [x] `browser_status` 返回扩展和页面就绪。
- [x] `chat_send` 能发送一条测试消息并返回完整回答。
- [x] `chat_sync` 能同步页面当前消息。
- [x] `chat_read` 能按游标读取消息。
- [x] 页面刷新后扩展重新连接。
- [ ] `chat_wait_event` 现场验证（本地回环已覆盖）。
- [ ] Chrome/Chromium 对照验收。

## 当前证据

- 本地假扩展回环已覆盖发送、结果、同步、游标、等待和取消。
- `scripts/replay_extension_fixture.py` 提供单命令 Bridge/扩展协议回放，但不替代真实 ChatGPT 页面验收。
- MCP stdio `initialize` 和 `tools/list` 已通过。
- Manifest、扩展资源和 JavaScript 语法检查已通过。
- 当前 Bridge 端口 `8765` 已确认空闲，没有遗留运行进程。
- 2026-09-22 现场复核：Bridge `0.1.0` 在线；Edge `153.0.0.0`；扩展 `0.1.0`；目标 `tab-1885859693`；ChatGPT 标签页已绑定且 `page=ready`。
- 现场 `chat_sync` 已实际调用成功，返回 `success=true`；当前页面是空会话，因此消息数组为空。
- 当前已确认扩展连接、标签页绑定和页面就绪；发送真实测试消息及采集链路仍待明确测试内容后执行。
- 2026-09-25 现场验收通过（Edge 153.0.0.0，扩展 0.1.3，Bridge 0.1.3，目标 `tab-1885863082`，页面 `chatgpt.com/` 已登录就绪）：
  - `browser_status`：extension=connected、page=ready、tab_bound=true、`chatgpt_tabs` 含绑定标签页。
  - `chat_sync`：返回 `success=true`；空会话返回空数组，后续会话可同步出用户消息。
  - `chat_send`（真实发送）：`请只回复 TEST123` 返回完整回答 `TEST123`（约 6.5s）；后续 `TEST456/789/321/654` 多轮均成功。
  - `chat_read`：按游标读取本地消息；同一回答仅一条 assistant 记录，用户消息与回答同会话且顺序为用户在前。
  - 页面刷新恢复：刷新后同一 `target_id` 重新连接并保持 ready。
  - `get_latest_message`：返回最近消息与 `response_state=idle`。
  - 待执行：`chat_wait_event` 现场验证与 Chrome/Chromium 对照。

## 现场验收阻塞记录

2026-09-22：浏览器自动化通道连续状态检查失败；按恢复流程重试、重置并再次检查，仍返回空浏览器列表和 `nodeRepl.fetch request failed`。因此本文件保留为待现场验收，不将真实页面结果标记为通过。

补充环境检查：本机存在 Edge 主进程和多个渲染进程，但常见 CDP 调试端口 `9222/9223/9229/9515` 均未监听；当前没有可复用的浏览器调试连接。

## 手工验收入口

1. 按 [REAL_BROWSER_RUNBOOK.md](REAL_BROWSER_RUNBOOK.md) 执行完整现场流程。
2. 按 [GETTING_STARTED.md](GETTING_STARTED.md) 生成扩展配置并加载扩展。
3. 启动 Bridge，打开 ChatGPT 标签页并点击扩展中的绑定按钮。
4. 在 Codex 中依次调用 `browser_status`、`chat_sync`、`chat_send`、`chat_read`。
5. 将浏览器版本、扩展版本、页面 URL 形态、结果和异常写回本文件。
