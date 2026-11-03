---
name: ai-web-mcp
description: 通过本机 AI-Web-MCP 连接已登录的 ChatGPT 或智谱清言 GLM 网页，进行文本规划、指定历史会话续聊、图片理解和先上传后提问。用于调用网页 AI；不用于操控任意应用或执行本地开发任务。
---

# AI-Web-MCP

支持四种组合：ChatGPT 文本、ChatGPT 图片、GLM 文本、GLM 图片。Skill 位于本地 Agent 的技能目录，规定调用方法；唯一 Bridge 执行任务，MCP 和 CLI 连接同一个 Bridge。

## 选择目标

1. 查看 `browser_status`、`list_ai_providers` 和 `list_ai_tabs`。Bridge 离线时启动安装目录的 `build/AI Web MCP.exe`，或调用 CLI doctor/open 的既有启动流程；不要反复拉起多份服务。
2. 按对方要求选择 `provider="chatgpt"` 或 `provider="glm"`。未指定提供方且有多个候选时明确选择，不默默换站点。
3. 使用 `open_ai_chat(provider=..., url="完整旧会话地址")` 续聊，或 `open_ai_chat(provider=..., new_chat=true)` 建新聊天。返回的 `target_id` 是后续所有操作的目标。
4. ChatGPT 历史地址含 `/c/<id>`；GLM 通常为 `https://chatglm.cn/main/alltoolsdetail?cid=<id>&lang=zh`。`t` 是临时时间参数，不是会话 ID。不要把 URL 只写在问题正文中。

## 文本与图片

- 文本：`ask_ai(question=..., target_id=...)`。
- 一次看图：`ask_ai_image(image_path="本地图片绝对路径", question="具体问题", target_id=..., request_id="本次唯一ID")`。
- 分步组合：`upload_ai_image(image_path=..., target_id=..., request_id=...)` **只上传不发送**；随后 `send_ai_message(content="具体问题", target_id=..., use_attachments=true, request_id="新的发送ID")`。
- GLM 无自定义问题时使用“这是什么”默认图片动作；文字提取、翻译或界面分析应传明确问题。附件尚未就绪不能发送。
- 上传成功不代表已得到回答。分别检查上传步骤和发送步骤结果。

图片输出可用于识字、界面布局、对象描述与定位；图片理解由选定网页模型完成。本桥不会替 Agent 截屏或点击其他软件。

## 任务恢复

每个写入步骤保留原 `request_id`。连接中断或响应超时，先 `chat_task_status` / CLI task 查询原任务并检查目标页面，禁止自动换 ID 重发同一内容。已完成读取原结果；投递状态不确定先核验。

统一 MCP/CLI 默认等待 600 秒，适合 GLM 深度思考。需要更久时显式设置 `timeout_ms` / `--timeout-ms`（桥端上限 1800000 毫秒），并相应提高客户端工具超时；不要用短超时反复重发。

目标有草稿或已有附件，尊重原内容，不清空；有意消费本次上传图片时使用 `use_attachments=true`。没有明确目标的多标签请求不猜第一个。网页登录失效、目标不就绪、调试器占用时返回实际阻碍，不换到另一个提供方代发。

## 无 MCP 的 Agent

安装目录由 `AI_WEB_MCP_ROOT` 指定；本机默认 `D:\桌面\Work\AI-Web-MCP`。使用该目录 `runtime/venv/Scripts/python.exe` 运行 `scripts/ai_web.py`，命令均输出 JSON。先查看 `--help`，覆盖 providers、doctor、tabs、open、ask、vision、upload、task、cancel 和本地历史管理。

```powershell
$root = 'D:\桌面\Work\AI-Web-MCP'
& "$root/runtime/venv/Scripts/python.exe" "$root/scripts/ai_web.py" providers
& "$root/runtime/venv/Scripts/python.exe" "$root/scripts/ai_web.py" open --provider glm --url 'https://chatglm.cn/main/alltoolsdetail?cid=CONVERSATION_ID&lang=zh'
```

后续传返回目标，参数以当前 CLI `--help` 为准。MCP 和 CLI 是两个入口，同一任务选其一；切换入口恢复原任务仍复用 ID。

## 能力边界

历史搜索与导出只覆盖本地已经采集的消息。人格是任务提示模板。网页模型选择、账户权限与额度由原网页控制。仅使用已实现的文本与图片能力，不将任意附件、音视频或生成文件下载视为自动支持。


## 读取写作框与最新回答

使用 `get_latest_message(conversation_id=真实会话ID, target_id=可选目标)`；返回 `message.content` 是最新助手正文，写作框保留 Markdown 标题和段落。`source=live` 表示页面实时读取；`source=cache` 表示缓存回退，结合 `sync_error` 判断新鲜度。`message=null` 表示当前页面尚无助手正文，不把用户问题当成回答。

历史页刚打开时会短暂等待正文加载；`sync_error=PAGE_LOADING` 表示仍在加载，可稍后重新读取，无需重新发送问题。
