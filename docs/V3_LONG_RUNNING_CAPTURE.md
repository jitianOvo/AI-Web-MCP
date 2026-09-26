# V3：长期采集与恢复工作文件

状态：`in_progress`

## 目标

将 ChatGPT 网页中的新增对话持续保存为可查询的本地消息流。

## 工作项

- [x] 页面初始快照。
- [x] MutationObserver 增量事件。
- [x] 消息内容哈希和游标。
- [x] 稳定 DOM 消息 ID，支持流式 Assistant 更新覆盖。
- [ ] 会话指纹和页面切换识别。
- [ ] 浏览器刷新恢复。
- [x] Bridge 重启状态恢复/标记。
- [x] SQLite 查询、筛选和导出。
- [x] 数据保留周期和手工清理。
- [x] Markdown、JSON 导出。

## 验收

- [ ] 页面新增用户消息可采集。
- [ ] 页面新增 Assistant 消息可采集。
- [x] 重复 DOM 渲染不会生成重复记录。
- [x] 断开连接期间的消息事件本地缓冲并在重连后回放。
- [x] 重启后可以按游标继续读取。

## 当前实现证据

- Content Script 使用 `MutationObserver` 采集用户/Assistant 消息。
- DOM 缺少页面消息 ID 时使用 `WeakMap` 绑定稳定节点 ID，不再以正文前缀作为 ID。
- SQLite 以 `conversation_id + message_id` 去重；相同正文但不同消息 ID 可以并存。
- `chat_read`、`chat_wait_event` 和 `chat_sync` 已有回环测试覆盖。
- `chat_search` 支持全文片段/会话/角色过滤，`chat_export` 支持 Markdown/JSON 内容返回。
- 旧版数据库会自动补充 V2 任务字段并迁移消息表约束，已有数据保留。
- Bridge 启动时会将未完成任务标记为 `interrupted`，并可通过 `chat_task_status` 查询。
- 自动重试仍需结合浏览器页面状态，留作后续恢复策略。
- `chat_sync` 回环验证页面快照写入本地消息表，SQLite 序列游标在进程重启后仍可读取。
- `scripts/prune_data.py` 默认只预览，必须显式传 `--apply` 才删除过期消息，并可按会话过滤。
- 扩展 Service Worker 在 Bridge 断开时将 `message_event` 缓冲到 `chrome.storage.local`，重连后回放，最多保留 500 条/目标。
