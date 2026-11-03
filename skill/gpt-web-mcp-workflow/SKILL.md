---
name: gpt-web-mcp-workflow
description: 通过本地 GPT Web MCP 桥把网页端 ChatGPT 当作“规划大脑”、把本地 Agent 当作“执行者”的双角色自动工作流。当任务需要外部 AI 规划、多轮拍板、复杂方案拆解，或用户提供“需求+工作流规范 zip”要求全自动开工时使用；也用于复用网页端 ChatGPT 的日常咨询与验收。
---

兼容技能：本技能仅用于 ChatGPT。AI-Web-MCP 的 GPT/GLM 统一入口和分步图片操作见同级 `ai-web-mcp` 技能。需要 GLM 时加载该技能并使用 `provider="glm"`，不要通过 GPT 专用工具代发。

# GPT Web MCP 双角色工作流

## 适用场景

- 用户给出手写需求，要求“大脑规划、执行者动手、多轮回报、直到可用”。
- 需要网页端 ChatGPT 作为外部 AI 节点参与规划/裁决/方案评审。
- 本地工作涉及环境搭建、脚本编写、验证与验收，需要记录证据。

## 先选正确入口

- 仅图片理解、识字、定位：使用 `gpt-web-vision` 技能，调用一次 `ask_chatgpt_image`，不要套用本文多轮规划流程。
- 网页规划/评审：使用本文。普通文本咨询用一次 `ask_chatgpt(question=..., target_id=...)` 即可。
- MCP 不可用时：本技能 `scripts/ask_brain.py` 是文本入口；视觉使用视觉技能的 `scripts/vision.py`。不要自行改剪贴板或重发图片。

## 前置条件与目标选择

### 接着指定的旧聊天工作

对方提供 `https://chatgpt.com/c/<conversation_id>` 时，先调用
`open_chatgpt_conversation(url="完整旧会话地址")`，读取返回的 `target_id`，后续
`ask_chatgpt`、`ask_chatgpt_image`、`sync_chat_state` 都使用该目标。工具优先复用已打开的
同地址标签页；未打开则进入指定地址。页面重定向或未就绪会明确报错，不创建新聊天替代。

没有 MCP 时，使用本技能的脚本：

```powershell
& 'D:\桌面\Work\AI-Web-MCP\runtime\venv\Scripts\python.exe' 'D:\桌面\Work\AI-Web-MCP\skill\gpt-web-mcp-workflow\scripts\ask_brain.py' --url 'https://chatgpt.com/c/<conversation_id>' '接着之前的内容继续规划'
```

先只读历史可追加 `--last` 并省略提示词。不要把会话地址只写进问题正文，必须通过 URL 参数选择目标。

1. 调用 `browser_status`，要求 Bridge 在线、未暂停。
2. 在 `targets` 中选 `tab_bound=true` 且 `page_ready=true` 的目标，并在本任务每次调用保留同一个 `target_id`。仅一个就绪目标可直接用；多个按当前任务指定，不猜第一项。
3. Bridge 离线时，`Start-Process -FilePath 'D:\桌面\Work\AI-Web-MCP\build\AI Web MCP.exe' -WindowStyle Hidden`；等状态在线后继续，避免独立启动第二份 python 桥。
4. 未绑定：唯一 ChatGPT 标签自动绑定；多标签使用 `list_chatgpt_tabs` + `bind_chatgpt_tab(tab_id=...)`。页面必须是正常 ChatGPT 聊天模式，Codex 模式不作为此桥的聊天目标。

发送工具自身等待完整回答。调用成功就读取 `result`；超时先查询原任务和会话，不再发送相同问题作为“确认”。图片任务恢复必须复用原 `request_id`。

## 角色分工

- **规划大脑** = 网页端 ChatGPT：给目标、分阶段规划、验收标准、拍板。
- **本地执行者** = 当前 Agent：查环境、补环境、写脚本、建目录、跑验证、回报证据。
- 执行者只负责听大脑的规划并落地；对不明确处用追问代替猜测；发现与现实冲突时回报偏差和替代方案，由大脑裁决。

## 标准工作循环

```text
1. 身份声明：执行者向大脑说明双方身份与本轮目标（首轮必做）。
2. 规划：大脑给分阶段计划与每阶段验收标准。
3. 执行：执行者按计划动手，缺什么补什么，每次补装记录版本。
4. 回报：执行者回报完成情况、证据（命令输出/报告/文件清单）与偏差。
5. 裁决：大脑放行或要求修正；未通过则回到 3。
6. 循环直到用户认可，输出交付说明与后续路线。
```

## MCP 工具调用表

| 场景 | 工具 |
|---|---|
| 确认链路 | `browser_status` |
| 列出/绑定标签页 | `list_chatgpt_tabs`、`bind_chatgpt_tab`、`get_bound_chatgpt_tab` |
| 一键问大脑并等完整回答 | `ask_chatgpt(question)` |
| 底层发送/等待/读取 | `chat_send`、`chat_wait_event`、`chat_read`、`get_latest_message`、`chat_sync`、`chat_cancel` |
| 调试与归档 | `chat_search`、`chat_export`、`chat_task_status`、`persona_list` |

## 提示词模板

完整可复用模板见 `references/prompts.md`：首轮身份声明、规划请求、执行回报、裁决请求、验收证据、新对话启动指令。

## 故障处理

- `RESPONSE_TIMEOUT`：用原 request_id 查询 `chat_task_status`，再按真实 conversation_id 用 `chat_read` 找回；不要直接重发或默认要求更新扩展。
- `EXTENSION_NOT_CONNECTED` / `CHATGPT_TAB_NOT_FOUND`：检查 Bridge、扩展、标签页绑定。
- `BRIDGE_OFFLINE`：启动 Bridge 后重试。
- `EXTENSION_BUSY`：上一任务未结束，等待或 `chat_cancel`。
- 回答内容为占位/空：过滤 `request-placeholder` 节点；仍为空按 `EMPTY_RESPONSE` 处理，不当作成功。

## 浏览器兼容

- 扩展是标准 MV3（`chrome.tabs/windows/debugger/storage/alarms`），不依赖任何 Edge 专属 API，Chrome 可直接加载同一 `extension/` 目录。
- 在 Chrome 中只需：开发者模式 → 加载已解压的扩展程序 → 选择 `extension/`；确认 `config.js` 的 `websocketUrl`/`bridgeToken` 与本机 Bridge 一致（运行 `scripts/configure_extension.py`）。
- 浏览器识别仅用于状态上报（`browserInfo`），不改变逻辑路径。

## 容错与自愈能力

- **窗口最小化/后台**：扩展处理目标窗口状态和页面输入；发送由真实按钮点击完成。Agent 无需额外模拟 Enter、补点发送或粘贴图片。
- **composer 定位**：长答案后页面可能出现第二个 ProseMirror（aria="开始写作"），扩展按“aria=询问/Ask ChatGPT → composer form 内 → 排除开始写作”定位真实输入框，不会写错位置。
- **新开页面/会话**：`open_chatgpt_tab` 可让扩展自主开 ChatGPT 新标签/新窗口（无窗口安装自动 `windows.create`）；`new_chat` 开新会话。
- **多窗口/多标签**：每个绑定标签是独立 target（`tab-<id>`），扩展自动绑定唯一 ChatGPT 标签；多标签用 `list_chatgpt_tabs` + `bind_chatgpt_tab` 显式指定。任务严格按 target 串行，不会串线。
- **多网页并发规范**：每个对话/任务明确 `target_id`，由桥按目标排队。图片走文件上传，不操作系统剪贴板。超时先查询原任务和真实会话，不自动换会话、换 ID 或补发。
- **扩展热重载**（0.1.29+）：Bridge `/api/reload-extension` 会向所有在线扩展连接广播重载指令，扩展立即 `chrome.runtime.reload()`。若扩展 `extension_version` 未变（服务进程被语法错误拒载），需手动在 `chrome://extensions` 点一次刷新图标，然后刷新网页重新绑定。
- **自主纠正**：发送后不确认上屏会报错而不是假装成功；`sync_chat_state` 可恢复场景、`chat_cancel` 终止卡住的任务；Bridge 重启后任务持久化可查 `chat_task_status`。

## 交付要求

- 每阶段交付可运行、可复现：脚本、版本快照、验收命令、报告产物。
- 最终汇报：做了什么、占用空间与位置、残留是否清理、下一步路线。
- 用户发送 `GPT Web MCP工作流规范.zip + 手写需求` 时，先安装/读取本 skill，再按工作循环全自动开始。
