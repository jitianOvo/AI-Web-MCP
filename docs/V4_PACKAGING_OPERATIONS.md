# V4：桌面化与分发工作文件

状态：`in_progress`

## 目标

将开发模式整理为日常可使用、可诊断、可升级的本地工具。

## 工作项

- [x] 一键启动和停止。
- [ ] 托盘状态显示。
- [x] 自动生成 Bridge 配置和扩展配置。
- [x] token 自动轮换。
- [x] MCP 配置生成或检查。
- [x] 版本兼容检查。
- [x] 诊断包。
- [x] 面向使用者的安装说明。

## 运维验收

- [ ] 用户只需一次安装和一次 MCP 配置。
- [x] Bridge 未启动时能自动拉起。
- [x] 扩展未连接时有明确提示。
- [x] 日志、数据库和临时文件位置明确。
- [ ] 升级失败时可以回滚。

## 当前实现证据

- `scripts/generate_codex_config.py` 生成项目内 Codex MCP 配置片段。
- `scripts/validate_installation.py` 执行只读安装检查。
- `scripts/start_bridge.ps1` / `scripts/stop_bridge.ps1` 提供 Bridge 启停入口。
- Bridge 状态返回自身版本，安装检查验证扩展与 Bridge 版本一致。
- `scripts/rotate_token.py` 轮换本地 token 并同步生成 `extension/config.js`。
- 测试会验证生成的扩展 token 与本地 Bridge 配置一致。
- `scripts/setup_local.py` 一次生成扩展配置、Codex MCP 配置并执行安装自检。
- `scripts/package_extension.py` 生成不携带本机 token 的扩展 zip。
- `scripts/package_diagnostic.py` 生成不包含数据库和真实 token 的诊断 zip。
- `scripts/import_personas.py` 提供人格配置批量导入入口。
- `scripts/release_check.py` 统一执行测试、编译、自检、打包、扩展语法和本地协议回放。
- `scripts/clean_build.py` 默认预览重复 zip，显式 `--apply` 才清理旧构建包。
- `release_check.py` 会自动执行构建清理预览，但不会自动删除产物。
- `scripts/health_report.py` 只读输出 Bridge、扩展、数据库、日志和构建产物位置。
- release check 会执行 health report，但不会因为 Bridge 离线而自动启动它。
- `scripts/check_docs.py` 检查 README、路线和验收文档的相对链接。
- 最近一次 release check 已通过，生成物和端口清理均已验证。
- `BridgeClient.ensure_running()` 使用启动锁和二次状态检查，避免并发 MCP 调用重复拉起 Bridge。
- 扩展弹窗区分 Bridge 未连接、未绑定标签页和页面脚本未就绪三种状态。
- 当前仍需要手工加载浏览器扩展和将配置片段合并到 Codex 配置，完整安装器留待后续。
