# 实施日志

## 2026-09-22
- 建立 GPT Web MCP 项目根目录的长期路线文档。
- 建立版本、浏览器形态和工作模块的 Markdown 工作文件索引。
- 确定 V1 为 Edge 单标签页 MCP 闭环。
- 确定 V1-B 为 Chrome/Chromium 兼容验证。
- 确定后续顺序为 V2 多标签页/多人格、V3 长期采集/恢复、V4 桌面化/分发。
- 暂未修改 `VideoEssenceExtractor` 原项目。
- 建立 V1 Python/扩展骨架、SQLite 存储、MCP facade 和 Bridge 自动配置流程。
- 本地 Bridge 状态和未连接扩展错误路径验证通过。
- 6 项 Python 单元测试通过，扩展 JavaScript 语法检查通过。
- 将 MCP 依赖约束为 `<2.0`，保持 `FastMCP` API 兼容。
- 在项目内建立 `runtime/venv` 并完成依赖安装，验证 MCP facade 可以加载。
- MCP stdio `initialize` 握手验证通过，返回 `gpt-web-mcp` 工具服务信息。
- 当前剩余 V1 现场验收：浏览器加载扩展、绑定 ChatGPT 标签页、发送真实消息并验证增量采集。
- 回环测试扩展到 9 项，新增等待超时和扩展 Manifest/资源完整性检查。
- 增加跨版本协议基线 `docs/PROTOCOL.md`，固定 MCP、HTTP、WebSocket 和消息状态模型。
- 建立 `V1_E2E_ACCEPTANCE.md`，记录真实浏览器现场验收清单和当前浏览器自动化通道故障证据。
- 开始 V2 多目标基础：新增目标注册表、多个扩展连接、按 `target_id` 任务/同步分发和多目标回环测试。
- 当前自动化测试为 11 项通过。
- V2 增加人格持久化、提示词注入、任务组提交/状态查询和配置格式文档。
- 自动化测试扩展为 13 项通过。
- V2 Bridge 改为每个就绪目标独立队列/Worker，扩展 Service Worker 改为每个绑定标签页独立 socket/request 状态。
- 新增双目标并行回环测试，当前自动化测试为 14 项通过。
- 开始 V3 长期采集基础：修正 SQLite 去重约束，允许相同正文的不同消息并存；扩展增加稳定 DOM 消息 ID。
- 修复旧版 SQLite 迁移顺序，实际迁移项目现有 `data/gpt_web_mcp.sqlite3` 成功；新增旧 schema 迁移回归测试。
- 当前自动化测试为 16 项通过，扩展 JavaScript 语法检查通过。
- V3 增加本地 `chat_search` / `chat_export` 能力和对应回环测试，当前自动化测试为 18 项通过。
- 实际启动 Bridge、读取状态并停止验证通过；端口 8765 已恢复空闲。
- V4 基础入口增加 MCP 配置片段生成和只读安装自检脚本。
- V1-B 增加浏览器类型/版本上报和目标状态记录，真实 Edge/Chrome 对照仍待现场验收。
- 本轮按 Computer Use 恢复流程完成浏览器状态重试/重置，现场通道仍不可枚举浏览器；结果已更新到 `V1_E2E_ACCEPTANCE.md`。
- V4 增加 Bridge 优雅停止接口、停止脚本、版本状态和扩展/Bridge 版本一致性检查；首次使用文档更新为支持 V2 多目标。
- 真实启动/停止脚本回归通过，当前自动化测试为 19 项通过，端口 8765 已释放。
- V4 增加 token 轮换脚本，并记录扩展配置同步与重启要求。
- V4 增加统一本地初始化、无 token 扩展包和无敏感数据诊断包脚本。
- 实际生成扩展 zip 和诊断 zip；扩展包使用 `config.example.js`，诊断包不含 SQLite 数据库。
- 统一本地初始化、安装自检、20 项测试、扩展语法检查和端口清理复核通过。
- 环境检查发现 Edge 正在运行，但未开放常见 CDP 调试端口；浏览器现场验收继续保留为待执行项。
- V4 扩展弹窗增加可执行连接诊断提示，并加入静态回归检查。
- 当前自动化测试为 21 项通过。
- 增加目标断连失败隔离回归测试，验证单目标失败不会阻塞其他目标队列。
- 当前自动化测试为 22 项通过。
- 响应宽限时间配置化，新增空回答和超时/取消回归测试。
- 增加 `replay_extension_fixture.py`，提供可自动启停 Bridge 的本地扩展协议回放入口。
- 回放器实际通过 `bridge_ready`、任务派发和结果返回，HTTP 200；Bridge 自动停止后端口恢复空闲。
- 增加 `import_personas.py`，支持从项目内 JSON 数组批量导入人格配置。
- V3 增加 Bridge 重启时的任务中断标记、单任务状态接口和 MCP 查询工具。
- 当前自动化测试为 20 项通过，扩展 JavaScript 语法检查通过。
- 修复超时 Future 被 `wait_for` 取消导致 HTTP 断连的问题，改用 shield 保留结构化错误返回。
- 当前自动化测试为 24 项通过，新增空回答、超时和结构化错误回归覆盖。
- 新增扩展页面错误码回传回归测试，V1 错误路径覆盖完成。
- 当前自动化测试为 25 项通过。
- V2 增加可配置全局速率限流 `rate_limit_per_minute`，默认关闭以保持现有行为。
- V3 文档同步标记页面快照和重启后游标读取为已实现，真实浏览器刷新恢复仍待现场验收。
- V3 增加默认预览、显式 `--apply` 的数据保留清理脚本和存储层回归测试。
- 当前自动化测试为 26 项通过；清理脚本默认预览未删除数据。
- V3 扩展断连采集增加 `chrome.storage.local` 事件缓冲和重连回放，静态回归检查加入测试。
- 当前自动化测试为 27 项通过。
- V4 Bridge 自动启动增加线程锁/二次状态检查，新增启动竞争回归测试。
- 当前自动化测试为 29 项通过。
- V2 任务组增加确定性 Markdown 汇总和同一输入的冲突候选标记，不替 Agent 做语义裁决。
- 验收矩阵同步将 V2 结果汇总/冲突候选从 planned 更新为 verified。
- 最新扩展协议回放通过：`bridge_ready`、HTTP 200、结果返回和自动停机均正常，端口恢复空闲。
- 新增跨版本验收矩阵，区分自动化、本地回环、代码待现场和计划项。
- V2 增加 `max_active_jobs` 全局活动任务上限，避免多目标数量增长后无限并发。
- V2 增加多目标绑定持久化/重启恢复静态回归检查，并在验收矩阵标为待现场验证。
- 当前自动化测试为 30 项通过。
- 速率限流增加可配置窗口并通过短窗口回归测试。
- 当前自动化测试为 31 项通过。
- 增加 Bridge 配置与扩展生成 token 一致性回归检查。
- 当前自动化测试为 32 项通过。
- 增加 `release_check.py`，统一版本整理前的测试、自检、打包和本地协议回放闸门。
- 实际运行 `release_check.py` 通过，生成扩展/诊断包，协议回放 HTTP 200，端口恢复空闲。
- 验收矩阵已登记 V4 release check 为 verified。
- 最新 release check 通过：31 项测试、安装自检、打包、扩展语法、协议回放 HTTP 200，端口空闲。
- 新增 `REAL_BROWSER_RUNBOOK.md`，固定恢复浏览器通道后的 Edge/Chrome/V2 现场验收顺序和记录模板。
- V4 增加构建包清理预览/显式应用脚本，本轮仅预览不删除。
- release check 纳入构建清理预览步骤。
- V4 增加只读 `health_report.py`，集中输出本地运行路径和 Bridge 状态，不启动服务也不显示 token。
- 真实 Edge 现场恢复：Bridge 已启动，Edge 153.0.0.0、扩展 0.1.0、目标 `tab-1885859693` 已连接，ChatGPT 页面为 ready。
- 真实 Edge `chat_sync` 调用成功，当前页面为空会话，返回消息数组为空；尚未发送测试消息。
- 现场测试消息导致会话 URL 切换但回复采集超时；增加 `conversation-turn/article` DOM 回退选择器，待刷新页面后复测。
- 当前自动化测试为 33 项通过；扩展 DOM 回退适配已通过静态回归和 JavaScript 语法检查。
- release check 纳入只读 health report 步骤。
- 最新 release check 通过，新增 health report 步骤，协议回放 HTTP 200，端口空闲。
- 增加文档相对链接检查，并纳入 release check。
- 文档链接检查通过（15 个文档），最新 release check 继续通过，端口空闲。

## 2026-09-25

- 补充唯一标签页自动绑定：扩展启动、标签页创建/更新/关闭和重连闹钟都会触发 `autoBindSingleTab`，只有一个 ChatGPT 标签页时自动绑定。
- 扩展状态上报增加 `tabs` 快照、`generating` 和 `conversation_title`；Bridge 新增 `/api/tabs`、`/api/tabs/bind`、`/api/chat/latest` 接口和 `bound_result` 消息。
- MCP 新增 `list_chatgpt_tabs`、`bind_chatgpt_tab`、`get_bound_chatgpt_tab`、`get_latest_message`、`ask_chatgpt` 工具。
- 当前自动化测试为 37 项通过，扩展 JavaScript 语法检查通过；Bridge 运行中，待用户重载扩展后执行真实发送验收。
- 版本号统一升至 `0.1.1`（扩展 manifest、Python 包、pyproject）；测试断言改为动态跟随包版本，37 项测试继续通过。
- 真实 Edge 验收完成（扩展 0.1.2/0.1.3，Bridge 0.1.2/0.1.3，目标 `tab-1885863082`）：`chat_send` 多轮真实发送全部返回完整回答；`chat_read` 同会话单条回答；页面刷新后同目标恢复 ready。
- 采集修复：任务结果复用 DOM 消息 ID 去重；任务期间消息缓冲为“用户→回答”顺序落库；过滤 `request-placeholder` 占位节点；版本升至 `0.1.3`。
- 当前自动化测试为 37 项通过；V1_E2E_ACCEPTANCE 和验收矩阵已登记 Edge 现场证据。
- 通过 Bridge 完成一次真实多轮“大脑(网页 ChatGPT) → 执行者(Codex)”实战模拟：身份声明、规划、阶段一/二搭建、回报与裁决均走通；回答完成判定发现超时漏报，回答仍可经 `chat_read` 找回。
- 完成判定加固：`waitForAnswer` 改用过滤占位节点的 `answerNodes()`，强制收敛阈值 20s→8s；版本升至 `0.1.4`，扩展重载后生效。
- 新增 `gpt-web-mcp-workflow` skill（SKILL.md + 提示词模板 + 协议速查 + `ask_brain.py` CLI），已安装到 `~/.codex/skills` 并打包 `build/GPT-Web-MCP-工作流规范.zip`；MCP 说明同步引用。
- 新增零依赖托盘程序 `scripts/bridge_tray.ps1` + `start_bridge_tray.cmd`：状态窗口、关叉静默、托盘开启/暂停/退出、图标来自 `res/GPT_Web_MCP_iconic.png`，窗口可见时才轮询。
- build 残留清理：删除 9 个过期诊断/扩展 zip，仅保留当前版本；项目 83.7MB 全在 D 盘，WSL 实验台 ~/arm64-lab 151MB（含 arm64 rootfs，位于 WSL 虚拟盘）。

## 2026-09-26（V4）

- V4 稳定性改造：发送前等待“用户消息真正上屏”ACK，任务生命周期 stage 落库（CREATED→…→COMPLETED），`USER_MESSAGE_CONFIRMED` 后禁止重复发送。
- 等待逻辑：过滤占位节点的 `answerNodes()`，自适应稳定窗口（短答 600ms / 复杂内容 1200ms），快速进入 STREAMING。
- 超时不等于失败：`_classify_timeout` 主动查页面状态，返回 `still_generating / send_failed / completed_but_missed / confirmed_no_reply / extension_offline`，已完成但漏读时直接回收回答。
- 新增 MCP：`open_chatgpt_tab`、`new_chat`、`sync_chat_state`、`wait_for_response`、`get_chat_history`；`ask_chatgpt` 支持 `new_chat` 与无标签页自动开页。
- Bridge 新增 `/api/tabs/open`、`/api/chat/new`、`/api/chat/sync-state`、`/api/pause`、`/api/resume`；状态增加 `paused/input_ready/last_request_id/last_success_time/last_error`。
- 图标修复：由 res PNG 生成 16/32/48/128 扩展图标与 ICO，manifest `icons`/`action.default_icon` 已配置。
- 统一入口：`build/GPT Web MCP.exe`（MinGW C++，733KB），单实例、控制台日志、托盘左键显隐、右键启动/暂停/关闭、退出清理子进程；版本升至 `0.1.5`。
- 压测入口：`scripts/stress_ask.py`（连续多轮统计成功率/重复/完整率）。当前自动化测试 40 项通过。

## 2026-09-26（下一阶段裁决：UI + 官方 API 双后端）

- 裁决确认：不接入 `/backend-api/conversation`，不读取/复用网页 Cookie/session；CDP 与 Win32 SendInput 提交链路经实测不满足验收，改为 UI 兼容通道 + 官方 API 可靠通道。
- 新增 `backends/`：`BackendRouter`（auto/ui/api）、`UIBackend`（现有 bridge→扩展/CDP 页面通道）、`OpenAIAPIBackend`（Responses API 流式、重试、超时、会话历史、取消）。
- `ask_chatgpt(question, ...)` 接口保持不动，内部走路由器；统一返回 `success/text/backend/elapsed/error/error_code`。
- API Key 来源：`OPENAI_API_KEY` 环境变量或 `config/api_key.local.json`（gitignore）；日志只输出 `API backend configured`；状态页/托盘展示 `backend` 字段。
- `stress_ask.py` 改走 `ask` 并分项统计 UI 成功率 / API 成功率 / fallback 次数 / 超时 / 平均耗时；当前自动化测试 45 项通过。
- 待外部条件：配置官方 API Key 后即可实测 API 后端与 auto fallback 完整链路。

## 2026-11-03 v0.1.32 恢复
恢复 Edge 文本与图片闭环，加入指定历史URL复用与目标注册等待；重建图标和桌面快捷方式，同步 Codex/ZCode 技能。ZCode APP 由 6.1 Terra 操作，文本和图片实测通过。Python57项、Node13项通过。详见 [恢复验收记录](RELEASES.md)。

## 2026-11-04 AI-Web-MCP 1.1.0

新增GLM网页对话、图片与分步上传，保留ChatGPT兼容入口。统一MCP/CLI/provider目标规则，迁移模块与程序品牌，统一技能安装到本地Agent。详见 [版本记录](RELEASES.md) 与 [架构](ARCHITECTURE.md)。真实会话证据仅留本机data目录。
