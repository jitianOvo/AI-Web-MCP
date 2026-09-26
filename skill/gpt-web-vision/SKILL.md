---
name: gpt-web-vision
description: 当当前 Codex 模型没有多模态视觉能力时，把本地图片交给网页端 ChatGPT 理解。通过系统剪贴板 + 浏览器粘贴把图片送入已登录的 ChatGPT 网页，配合提示词读取图片描述/定位/文字识别，再把回复返回给 Codex。只用于无视觉模型的场景；若当前模型本身具备视觉能力则不需要本技能。
---

# GPT Web 视觉桥（无视觉模型时的图片理解）

## 适用场景

- 当前 Codex 模型是纯大语言模型（如 DeepSeek 中转站），无法直接看图。
- 任务需要：截图理解、图片定位、看窗口、看图识字、UI 走查、复杂图片语义分析。
- 已有 OCR 但不足以处理复杂图片语义时，用网页 ChatGPT 作为视觉大脑。

## 前置条件

1. Bridge 在线、扩展已连接、ChatGPT 标签页已绑定（`browser_status`）。
2. 图片是本地文件（PNG/JPG 等），路径可访问。
3. 使用 `ask_chatgpt_image(image_path, question)` 或底层 `send_image`。

## 原理与流程

```text
Codex（无视觉）
  -> ask_chatgpt_image(image_path, question)
  -> Bridge：PowerShell 把图片写入系统剪贴板
  -> Bridge：调用 gpt_sendinput.exe --paste（系统级 Ctrl+V，不依赖窗口焦点）
  -> 扩展：等待网页上传完成
  -> 扩展：把 question 追加到 composer 并发送
  -> 网页 ChatGPT 理解图片并回答
  -> Bridge 读取完整回答返回 Codex
```

两个入口：

- `ask_chatgpt_image(image_path, question)`：自动粘贴新图。
- `send_image_only(question)`：composer 里已有图片时，只追加问题并发送（`skip_paste=True`）。

## MCP 工具

| 工具 | 说明 |
|---|---|
| `ask_chatgpt_image(image_path, question)` | 传本地图片 + 问题，网页 ChatGPT 看图回答 |
| `chat_read` / `chat_wait_event` | 读取或等待视觉回答 |
| `chat_cancel` | 终止卡住的图片任务 |

## 提示词模板

```
请仔细查看这张图片，然后回答：
1) 图片里有什么（对象/文字/布局）？
2) 与问题 {问题} 相关的位置或细节是什么？
3) 若涉及文字，逐字列出看到的文字内容。
用中文回答，直接给结论。
```

定位类任务追加：

```
请用坐标或相对方位描述目标元素的位置（上/下/左/右/中心，或百分比），
不要只描述颜色和风格。
```

截图类任务（Codex 侧先截图）：

```
先用系统截图工具截取目标窗口/区域保存为 PNG，
再调用 ask_chatgpt_image 让网页 ChatGPT 描述。
```

## 故障处理

- `IMAGE_UPLOAD_TIMEOUT`：粘贴后未在 composer 确认上屏。先检查窗口是否被占用/网络是否慢；重试一次；若持续失败改用 `send_image_only` 在已粘贴图片上直接提问。
- `CLIPBOARD_FAILED`：PowerShell 写剪贴板失败，确认图片路径有效、PowerShell 未被策略拦截。
- `SENDINPUT_MISSING` / `SENDINPUT_PASTE_FAILED`：`build/gpt_sendinput.exe` 缺失或未编译 --paste 模式，运行 `scripts/build_exe.cmd`（含 gpt_sendinput 编译）或单独编译 `launcher/sendinput.cpp`。
- `EXTENSION_NOT_CONNECTED`：扩展未连接 Bridge，先检查扩展状态。

## 边界

- 本技能只作为视觉兜底：若当前 Codex 模型已具备视觉，直接用本地工具看图，不要绕道网页。
- 不上传到第三方 API；图片只进入用户已登录的 ChatGPT 网页会话。
- 不修改网页私有后端协议，全程走正常网页交互。
