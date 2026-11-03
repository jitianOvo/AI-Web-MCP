# GPT Web MCP 工作流规范（skill 交付包）

这个 zip 是一个**标准 Codex skill**：内部是 `gpt-web-mcp-workflow/SKILL.md` 及配套资源。

## 安装

把 `gpt-web-mcp-workflow/` 整个目录放进 Agent 的 skills 目录（例如 `C:\Users\<用户名>\.codex\skills\`），
或在对话中直接要求 Agent 读取包内的 `SKILL.md` 与 `references/`。

## 使用方法

1. 先准备好本地运行条件：
   - Bridge：`D:\桌面\Work\AI-Web-MCP\scripts\start_bridge.ps1`（或托盘 `start_bridge_tray.cmd`）。
   - Edge 加载 `extension` 未解压扩展，并打开已登录的 ChatGPT 标签页（单标签自动绑定）。
2. 把**手写需求文件**（或直接文字需求）交给 Agent。
3. 告诉 Agent：按 `SKILL.md` 的工作循环开始（身份声明 → 大脑规划 → 执行 → 回报 → 裁决 → 直到可用）。
4. Agent 自检 `browser_status`，缺失项自动处理；无法处理的（如需要你重载扩展、打开标签页）会停下来让你操作。

## 包含内容

```text
gpt-web-mcp-workflow/
├─ SKILL.md                    # 工作流本体（角色、循环、故障、交付要求）
├─ references/
│  ├─ prompts.md               # 首轮身份声明/规划/回报/裁决/新对话启动模板
│  └─ protocol-quickref.md     # MCP 工具、HTTP 端点、错误码速查
└─ scripts/
   └─ ask_brain.py             # 不用 MCP 时直接调网页端 ChatGPT 的 CLI
```

## 交付检查

- [ ] Bridge 在线、扩展已加载、ChatGPT 标签页已绑定
- [ ] 首轮对话声明了“规划大脑 / 本地执行者”身份
- [ ] 每阶段有验收命令与产物证据
- [ ] 版本一致（扩展 manifest 版本 == Bridge `__version__`）
- [ ] 结束时有“做了什么 / 空间与位置 / 残留清理 / 下一步”汇报
