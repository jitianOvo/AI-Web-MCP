# 版本与工作文件汇总

本文件是长期实现入口。每次只推进一个工作文件，完成后更新状态，再进入下一个文件。

状态定义：

- `planned`：已规划，尚未开始。
- `in_progress`：正在实现或验证。
- `blocked`：存在需要外部状态变化的阻塞点。
- `done`：实现、测试、验收和清理均完成。

## 工作文件索引

| 顺序 | 文件 | 版本/形态 | 状态 | 产出 |
|---:|---|---|---|---|
| 1 | [V1_SINGLE_TAB.md](V1_SINGLE_TAB.md) | V1 Edge 单标签页 | `in_progress` | MCP、Bridge、扩展、SQLite 最小闭环 |
| 1.1 | [V1_E2E_ACCEPTANCE.md](V1_E2E_ACCEPTANCE.md) | V1 真实浏览器现场验收 | `in_progress` | Edge/Chrome 页面闭环证据 |
| 1.2 | [REAL_BROWSER_RUNBOOK.md](REAL_BROWSER_RUNBOOK.md) | 真实浏览器现场流程 | `ready` | Edge/Chrome/V2 现场执行顺序 |
| — | [PROTOCOL.md](PROTOCOL.md) | 跨版本协议基线 | `in_progress` | MCP、HTTP、WebSocket 消息契约 |
| — | [PERSONA_FORMAT.md](PERSONA_FORMAT.md) | V2 人格/任务组格式 | `in_progress` | 多维度思考的持久化字段约定 |
| — | [ACCEPTANCE_MATRIX.md](ACCEPTANCE_MATRIX.md) | 跨版本验收矩阵 | `in_progress` | 版本、浏览器形态、模块和证据对照 |
| 2 | [V1B_CHROMIUM_COMPAT.md](V1B_CHROMIUM_COMPAT.md) | Chrome/Chromium | `in_progress` | 浏览器兼容和安装记录 |
| 3 | [V2_MULTI_TARGET_PERSONA.md](V2_MULTI_TARGET_PERSONA.md) | 多标签页/多人格 | `in_progress` | 角色、目标、任务组和多队列 |
| 4 | [V3_LONG_RUNNING_CAPTURE.md](V3_LONG_RUNNING_CAPTURE.md) | 长期采集/恢复 | `in_progress` | 增量采集、搜索、断点恢复 |
| 5 | [V4_PACKAGING_OPERATIONS.md](V4_PACKAGING_OPERATIONS.md) | 桌面化/分发 | `in_progress` | 一键启动、升级、诊断 |

## 形态矩阵

| 形态 | V1 | V2 | V3 | V4 |
|---|---|---|---|---|
| Edge 单页 | 主验收 | 支持 | 支持 | 支持 |
| Chrome 单页 | 兼容验证 | 支持 | 支持 | 支持 |
| Edge 多页 | 暂不纳入 | 主验收 | 支持 | 支持 |
| Chrome 多页 | 暂不纳入 | 兼容验证 | 支持 | 支持 |
| Codex MCP | 主验收 | 主验收 | 主验收 | 主验收 |
| 独立本地 HTTP | 诊断/调试 | 支持 | 支持 | 支持 |

## 共同验收规则

每个工作文件至少要记录：

1. 目标和不包含范围。
2. 文件和模块清单。
3. 协议或数据结构变更。
4. 正常流程验收。
5. 断连、刷新、超时、取消等异常验收。
6. 浏览器版本和扩展版本。
7. 测试结果、遗留问题和下一步。
