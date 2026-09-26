# V2：多标签页与多人格工作文件

状态：`in_progress`

## 目标

让 Codex 为多个角色或分析方向分配独立 ChatGPT 标签页，并统一收集结果。

## 计划模型

```text
task_group_id
  ├── persona_id / target_id A
  ├── persona_id / target_id B
  └── persona_id / target_id C
```

## 工作项

- [x] 引入 `target_id`。
- [x] Bridge 维护多个扩展连接和目标状态。
- [x] 任务可按 `target_id` 分发到指定标签页。
- [x] 扩展按绑定标签页维护独立 target/socket/request 状态。
- [x] 引入 `persona_id`、`task_group_id`。
- [x] 人格配置保存、查询和提示词注入。
- [x] 任务组批量提交、逐项结果和状态持久化。
- [x] 每个标签页独立队列和状态机。
- [x] 就绪目标可以并行处理互不相关的任务。
- [x] 全局活动任务上限。
- [x] 全局速率限流（配置项 `rate_limit_per_minute`，默认关闭；窗口可配置）。
- [x] 人格配置 Markdown/JSON 约定。
- [x] 结果合并和冲突候选标记；语义裁决仍交由 Agent。
- [x] 单个标签页失败时的隔离；自动重试仍待后续策略。
- [x] 多标签页重启后的目标恢复代码路径；真实浏览器重启仍待现场验收。

## 当前实现证据

- `src/gpt_web_mcp/targets.py` 提供目标注册表。
- `BridgeService.status()` 返回 `targets` 列表。
- `chat_send` 和 `chat_sync` 支持可选 `target_id`。
- 回环测试覆盖两个目标连接并验证任务只发送到指定目标。
- `docs/PERSONA_FORMAT.md` 和 `config/personas.example.json` 固定人格/任务组字段格式。
- `scripts/import_personas.py` 支持将 JSON 人格数组批量写入本地数据库。
- 任务组返回 `merged_markdown` 和 `conflict_candidates`，只标记差异，不替 Agent 做语义裁决。
- 回环测试覆盖人格提示词注入和双目标任务组。
- `max_active_jobs` 使用全局信号量限制跨目标活动任务数，同一目标仍由独立 Worker 串行处理。
- 扩展 `background.js` 已从单 `boundTabId/currentRequestId` 升级为多目标绑定映射和每目标 WebSocket。
- 回环测试验证两个就绪目标可同时收到任务。

## 不变原则

- 同一个标签页不并发。
- MCP 工具不直接操作 DOM。
- 多人格属于 Codex 编排层，Bridge 只负责可靠执行。
