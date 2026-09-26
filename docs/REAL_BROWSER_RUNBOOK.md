# 真实浏览器现场验收 Runbook

适用：Edge、Chrome/Chromium；当前 V1/V1-B/V2/V3 真实页面验收。

## 前置检查

在项目根目录执行：

```powershell
Set-Location -LiteralPath 'D:\桌面\Work\GPT Web MCP'
& '.\runtime\venv\Scripts\python.exe' scripts/setup_local.py
& '.\runtime\venv\Scripts\python.exe' scripts/validate_installation.py
```

启动 Bridge：

```powershell
& powershell -ExecutionPolicy Bypass -File '.\scripts\start_bridge.ps1'
```

## Edge/Chrome 操作顺序

1. 打开浏览器扩展管理页。
2. 开启开发者模式。
3. 加载 `D:\桌面\Work\GPT Web MCP\extension` 未解压扩展。
4. 打开已登录的 ChatGPT 页面。
5. 打开扩展弹窗，确认 Bridge 已连接。
6. 点击绑定当前 ChatGPT 标签页。
7. 记录弹窗显示的目标 ID、浏览器类型和页面状态。

## MCP 验收顺序

1. 调用 `browser_status`，记录 `bridge_version`、`targets`、浏览器版本和 `page=ready`。
2. 调用 `chat_sync`，确认当前页面消息进入本地数据库。
3. 调用 `chat_send`，使用现场专用测试文本，确认返回完整 Assistant 内容。
4. 调用 `chat_read`，使用返回的 sequence 游标增量读取。
5. 调用 `chat_wait_event`，在页面产生一条新消息后确认事件返回。
6. 调用 `chat_search` 和 `chat_export`，确认本地查询与归档。
7. 刷新页面，重新调用 `browser_status` 和 `chat_sync`，确认目标重新连接。

## V2 多目标验收

1. 在第二个 ChatGPT 标签页加载内容脚本并绑定。
2. 确认两个不同 `target_id` 出现在 `browser_status.targets`。
3. 使用 `task_group_submit` 向两个目标发送同一测试问题。
4. 检查 `results`、`merged_markdown` 和 `conflict_candidates`。
5. 关闭其中一个目标，确认另一目标仍可执行任务。

## 记录模板

```text
日期：
浏览器：Edge / Chrome / Chromium
浏览器版本：
扩展版本：
Bridge 版本：
ChatGPT 页面 URL 形态：
目标 ID：
browser_status：
chat_sync：
chat_send：
chat_read：
chat_wait_event：
刷新恢复：通过 / 失败
多目标：通过 / 失败 / 未执行
异常与截图位置：
```

验收完成后，将结果写入 [V1_E2E_ACCEPTANCE.md](V1_E2E_ACCEPTANCE.md) 和 [V1B_CHROMIUM_COMPAT.md](V1B_CHROMIUM_COMPAT.md)。
