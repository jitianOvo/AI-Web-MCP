# V1-B：Chrome/Chromium 兼容工作文件

状态：`in_progress`

## 目标

验证 V1 扩展在 Edge、Chrome 及兼容 Chromium 浏览器中的行为一致性。

## 工作项

- [x] 抽离浏览器名称、扩展名称和安装说明。
- [x] 验证 Manifest V3 权限。
- [x] 验证本地 WebSocket 连接策略。
- [x] 验证 Service Worker 心跳、重连和唤醒路径。
- [x] 验证 `tabs.sendMessage`、`storage`、`alarms`。
- [x] 扩展上报浏览器名称和版本，Bridge 写入目标状态。
- [ ] 建立 Edge/Chrome 对照验收表。

## 验收

- [ ] Edge 完成发送、回答、读取和刷新恢复。
- [ ] Chrome 完成发送、回答、读取和刷新恢复。
- [ ] 两者的协议消息保持一致。
- [ ] 浏览器差异不泄漏到 MCP 工具层。

## 当前实现证据

- `extension/background.js` 从 User-Agent 推导 `edge`、`chrome` 或 `chromium` 及版本。
- Bridge 的目标状态保留浏览器标识，MCP 仍只使用 `target_id`，不依赖具体浏览器名称。
- 扩展新增唯一标签页自动绑定和标签页快照上报，Edge/Chrome 共用同一逻辑，真实对照仍待现场验收。
- Edge 0.1.3 现场已通过自动绑定、发送、读取和刷新恢复；Chrome 对照仍待执行。
- 真实 Edge/Chrome 对照仍待浏览器现场通道恢复后执行。

当前 Edge 现场已确认扩展连接、目标绑定和页面就绪；Chrome 对照及真实消息发送仍待执行。

现场测试发现当前 ChatGPT 页面可发送并切换会话 URL，但一次 `chat_sync` 未提取到消息；已增加 `conversation-turn/article` DOM 回退适配，需在页面刷新后重新验收。
