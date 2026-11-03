# AI-Web-MCP 项目约定

- 当前基线为 **1.1.0**；版本统一维护在 `pyproject.toml`、`src/ai_web_mcp/__init__.py`、`extension/manifest.json`、`launcher/main.cpp`。
- 普通改动完成一个交付批次后运行 `python scripts/bump_version.py minor`，次版本加一、补丁归零（如 `1.0.0 → 1.1.0`）；临时小错误修复用 `patch`（如 `1.0.0 → 1.0.1`）。一个批次统一升版一次，不按保存次数升版。
- 交付前运行 `python scripts/bump_version.py --check`；同步 README 中的版本说明，重新构建 EXE，并完成对应验收。
- 保留已有未提交改动；按当前任务明确范围修改。只有收到明确要求才创建 Git 提交或推送，不自动提交、推送或覆盖历史。
- 不把本机凭据、Bridge token、API key、浏览器配置/会话数据及含这些内容的日志加入 Git；生成的 `config/config.json`、`extension/config.js`、`runtime/`、`data/`、`logs/`、`tmp/` 保持本机管理，公开产物使用示例配置。
