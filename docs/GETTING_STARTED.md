最新多提供方安装和使用以 [README](../README.md) 为准；本文保留早期 GPT 流程，GLM 使用通用工具。

# V1 首次使用

## 1. 初始化本地环境

项目已经将 Python 依赖安装在：

```text
D:\桌面\Work\AI-Web-MCP\runtime\venv
```

如果需要重新安装：

```powershell
Set-Location -LiteralPath 'D:\桌面\Work\AI-Web-MCP'
& '.\runtime\venv\Scripts\python.exe' -m pip install -r requirements.txt
```

首次启动 Bridge 会自动生成 `config/config.json` 和安装级 token。

也可以执行统一本地初始化：

```powershell
Set-Location -LiteralPath 'D:\桌面\Work\AI-Web-MCP'
& '.\runtime\venv\Scripts\python.exe' scripts/setup_local.py
```

## 2. 配置扩展

```powershell
Set-Location -LiteralPath 'D:\桌面\Work\AI-Web-MCP'
& '.\runtime\venv\Scripts\python.exe' scripts/configure_extension.py
```

在 Edge 或 Chrome 打开扩展管理页，开启开发者模式，选择“加载已解压的扩展”，目录选择：

```text
D:\桌面\Work\AI-Web-MCP\extension
```

打开 ChatGPT 网页，在扩展弹窗中点击“绑定当前 ChatGPT 标签页”。

只有一个 ChatGPT 标签页时，扩展会自动绑定它，无需点击弹窗；多个标签页时先用 `list_chatgpt_tabs` 查看，再用 `bind_chatgpt_tab` 指定。

批量导入示例人格：

```powershell
& '.\runtime\venv\Scripts\python.exe' scripts/import_personas.py
```

## 3. 启动 Bridge

```powershell
Set-Location -LiteralPath 'D:\桌面\Work\AI-Web-MCP'
& powershell -ExecutionPolicy Bypass -File '.\scripts\start_bridge.ps1'
```

也可以直接运行：

```powershell
$env:PYTHONPATH = 'D:\桌面\Work\AI-Web-MCP\src'
& '.\runtime\venv\Scripts\python.exe' -m ai_web_mcp.bridge
```

MCP 工具在调用时也会尝试自动启动 Bridge。

停止 Bridge：

```powershell
Set-Location -LiteralPath 'D:\桌面\Work\AI-Web-MCP'
& powershell -ExecutionPolicy Bypass -File '.\scripts\stop_bridge.ps1'
```

### 托盘程序（推荐日常入口）

双击 `scripts\start_bridge_tray.cmd` 打开简易状态窗口；点右上角 X 或最小化会静默到右下角托盘图标。
托盘菜单可“显示状态 / 开启桥接 / 暂停桥接 / 退出程序”；状态窗口可见时才轮询，平时不占用 CPU。

### 统一 EXE 入口（V4 推荐）

双击 `build\AI-Web-MCP.exe` 即可：自动启动 Bridge、显示控制台日志、创建右下角托盘图标；
点控制台右上角 X 只隐藏窗口不退出；左键托盘显示/隐藏控制台，右键可“启动/暂停、关闭”；关闭时自动停止子进程。

## 4. 配置 Codex MCP

可以先生成项目内的配置片段：

```powershell
Set-Location -LiteralPath 'D:\桌面\Work\AI-Web-MCP'
& '.\runtime\venv\Scripts\python.exe' scripts/generate_codex_config.py
```

生成文件为 `config/ai_web_mcp.codex.toml`，将其内容合并到 Codex 的 `config.toml`。

在 Codex 的 `config.toml` 中加入本地 stdio MCP 服务：

```toml
[mcp_servers.ai_web_mcp]
command = "D:/桌面/Work/AI-Web-MCP/runtime/venv/Scripts/python.exe"
args = ["D:/桌面/Work/AI-Web-MCP/scripts/run_mcp.py"]
cwd = "D:/桌面/Work/AI-Web-MCP"
startup_timeout_sec = 15
tool_timeout_sec = 660
```

配置完成后，在 Codex 中查看 MCP 工具，先调用 `browser_status`，确认扩展和页面均为就绪状态，再调用 `chat_send`。

常用工具入口：

- `list_chatgpt_tabs`：查看全部 ChatGPT 标签页。
- `open_chatgpt_conversation(url)`：传入旧聊天完整地址，复用已有标签或打开指定会话，返回 `target_id`，后续问题和图片传入该目标。
- `bind_chatgpt_tab(tab_id)`：绑定指定标签页。
- `get_bound_chatgpt_tab`：查看当前绑定。
- `ask_chatgpt(question)`：一键发送并等待完整回答。
- `get_latest_message`：读取最近回答和生成状态。
- 底层调试：`chat_send`、`chat_read`、`chat_sync`、`chat_wait_event`、`chat_cancel`。

安装自检：

```powershell
& '.\runtime\venv\Scripts\python.exe' scripts/validate_installation.py
```

只读查看本地健康状态：

```powershell
& '.\runtime\venv\Scripts\python.exe' scripts/health_report.py
```

需要轮换本地 Bridge token 时：

```powershell
& '.\runtime\venv\Scripts\python.exe' scripts/rotate_token.py
```

轮换后重启 Bridge，并在浏览器扩展管理页重新加载扩展。

生成扩展分发包和诊断包：

```powershell
& '.\runtime\venv\Scripts\python.exe' scripts/package_extension.py
& '.\runtime\venv\Scripts\python.exe' scripts/package_diagnostic.py
```

产物位于项目内的 `build/`，扩展分发包使用示例配置，不包含当前机器 token。

清理重复构建包时先预览：

```powershell
& '.\runtime\venv\Scripts\python.exe' scripts/clean_build.py
```

确认输出后追加 `--apply` 才会删除旧 zip。

版本整理前运行统一检查：

```powershell
& '.\runtime\venv\Scripts\python.exe' scripts/release_check.py
```

运行本地扩展协议回放回归（不打开浏览器）：

```powershell
& '.\runtime\venv\Scripts\python.exe' scripts/replay_extension_fixture.py
```

数据保留清理默认只预览：

```powershell
& '.\runtime\venv\Scripts\python.exe' scripts/prune_data.py --days 30
```

确认范围后，追加 `--apply` 才会执行删除。

## 5. 当前限制

- V1 单目标流程支持一个绑定标签页；V2 扩展可为多个绑定标签页维护独立目标。
- 同一个标签页严格串行处理任务，不同目标可以并行处理。
- 页面选择器随 ChatGPT 网页变化时，需要更新 `extension/selectors.js`。
- `extension/config.js` 和 `config/config.json` 含本机 token，属于生成文件，不应复制到其他机器。
