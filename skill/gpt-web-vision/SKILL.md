---
name: gpt-web-vision
description: 纯文本 AI Agent 的本地图片理解入口。通过已登录的网页 ChatGPT 返回图片描述、文字、布局或坐标；适用于 Milk Code、DeepSeek 等无视觉模型。已有视觉能力时无需调用。
---

兼容技能：本技能仅用于 ChatGPT。AI-Web-MCP 的 GPT/GLM 统一入口和分步图片操作见同级 `ai-web-mcp` 技能。需要 GLM 时加载该技能并使用 `provider="glm"`，不要通过 GPT 专用工具代发。

# 一次调用取得视觉结果

先使用下面的入口，不要自己编写剪贴板、浏览器上传或重试代码。

## 有 MCP 工具时

1. 调用 `browser_status`。要求 `bridge=online`、`paused=false`。
2. 查看 `targets`，选择 `tab_bound=true` 且 `page_ready=true` 的目标。仅一个就绪目标则直接使用；多个则根据当前任务指定 `target_id`。不要根据 Edge/Chrome 名字或列表第一项猜测。
3. 只调用一次 `ask_chatgpt_image`，用具名参数：

```json
{
  "image_path": "本次图片的绝对路径",
  "question": "本次需要从图片中得到的具体信息",
  "target_id": "上一步得到的实际 target_id",
  "timeout_ms": 180000,
  "request_id": "本次任务的唯一ID"
}
```

4. 成功时读取 `result`，把它用于当前任务。调用本身已经上传图片、发送问题并等待答案；不要再调用 `chat_send` 发“请描述图片”，不要继续粘图。

## 没有 MCP 工具时：用现成脚本

要在指定旧聊天中看图，MCP 先用 `open_chatgpt_conversation(url)` 获取目标并把
`target_id` 传给 `ask_chatgpt_image`。CLI 可直接在 `vision` 命令后加
`--url 'https://chatgpt.com/c/<conversation_id>'`，不与 `--target` 同时使用。

Windows PowerShell 7，从任意工作目录运行。只替换图片路径与问题；有多个就绪目标时追加 `--target 实际target_id`。

只读自检：

```powershell
& 'D:\桌面\Work\AI-Web-MCP\runtime\venv\Scripts\python.exe' 'C:\Users\20970\.codex\skills\gpt-web-vision\scripts\vision.py' doctor
```

一次看图（自动选择唯一就绪目标，自动内容去重）：

```powershell
& 'D:\桌面\Work\AI-Web-MCP\runtime\venv\Scripts\python.exe' 'C:\Users\20970\.codex\skills\gpt-web-vision\scripts\vision.py' vision --image '图片绝对路径' --question '列出图中文字、主要布局，标出目标按钮的位置'
```

需要可追踪任务时追加 `--request-id vision-本次唯一ID`；长问题写到 UTF-8 文件，使用 `--question-file '问题文件绝对路径'`。`--output '结果文件绝对路径'` 可保存 JSON。脚本退出码 0 表示成功、1 表示失败，stdout 始终输出 UTF-8 JSON。

查询已有任务，绝不重新发送：

```powershell
& 'D:\桌面\Work\AI-Web-MCP\runtime\venv\Scripts\python.exe' 'C:\Users\20970\.codex\skills\gpt-web-vision\scripts\vision.py' task --request-id '原request_id'
```

脚本会处理导入路径、参数编码、目标选择、重复请求和错误输出。省略 ID 时也会在发送前计算稳定 ID，断线错误仍返回该 ID，按原 ID 查询即可。不要把项目路径当作当前工作目录要求，不需要创建临时 Python 文件。不在本机安装时设置 `GPT_WEB_MCP_ROOT` 为实际项目目录，并使用实际 Python 与本技能脚本路径。

## 判断结果与停止条件

| 返回 | 下一步 |
|---|---|
| `success=true`，有 `result` | 直接使用答案；`deduplicated=true` 是复用了原结果，同样算成功 |
| `DELIVERY_UNCERTAIN` / `RESPONSE_TIMEOUT` | 用原 ID 查询任务；completed 读取 task.result，running 等待；不要自动换 ID 或补发文字 |
| `COMPOSER_NOT_EMPTY` | 停止本次发送，报告目标输入框已有草稿/附件；不得擅自清除或再次追加 |
| `NO_READY_TARGET` / `TARGET_NOT_READY` / `IMAGE_INPUT_NOT_FOUND` | 自检目标，确认处于正常 ChatGPT 聊天模式；Codex 模式不是图片桥目标 |
| `TARGET_REQUIRED` | 从自检返回的就绪列表选择与当前任务对应的目标 |
| `BRIDGE_OFFLINE` | 用 `Start-Process -WindowStyle Hidden` 启动项目 `build\AI Web MCP.exe`，等自检在线后再执行一次 |
| `PAUSED` / `PAGE_GENERATING` / `EXTENSION_BUSY` | 等待或按当前任务授权取消原任务；不要循环发送 |
| 上传失败、断线、重启、任务 failed/interrupted | 保留原 ID 与错误，检查网页和任务记录；需要新任务时明确建立新 ID |

每个新任务记住 `request_id`；恢复原任务复用该 ID。省略 ID 时同一目标、会话、图片内容和问题自动去重。要主动重新分析相同内容，传新的 ID。文件须为本地图片，最大 20 MiB。Bridge 0.1.30 起直接文件上传，不用系统剪贴板。

`send_image_only` 只适用于已明确存在附件的草稿，不是上传失败后的自动备用入口。

## 让问题更准确

根据任务要求提问：识字要求逐字抄录；定位要求返回像素坐标或百分比、并说明图片尺寸；界面操作要求列出按钮文字及相对位置。让网页区分“确实看见”和“不确定”。不需要额外向网页发送角色声明或规划请求，除非当前任务确实要求规划。
