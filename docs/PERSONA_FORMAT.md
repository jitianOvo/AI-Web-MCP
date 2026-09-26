# 人格配置格式

人格是本地 Bridge 保存的可复用提示词配置。人格本身不绑定浏览器标签页；任务发送时通过 `persona_id` 和 `target_id` 分别选择角色与执行目标。

## JSON 结构

```json
{
  "persona_id": "critic",
  "name": "批评者",
  "system_prompt": "主动寻找前提漏洞、反例和失败模式。",
  "config_json": {
    "output_style": "counterexample_first"
  }
}
```

字段约定：

- `persona_id`：稳定 ID，任务引用使用该值。
- `name`：用于状态页和任务组结果展示。
- `system_prompt`：发送到 ChatGPT 网页前插入的角色指令。
- `config_json`：后续扩展字段，目前作为 JSON 字符串存储。

## 任务项结构

```json
{
  "content": "分析这个方案",
  "persona_id": "critic",
  "target_id": "edge-tab-critic",
  "conversation_id": "current",
  "expected_format": "text",
  "timeout_ms": 600000
}
```

## 任务组结构

```json
{
  "task_group_id": "architecture-review-001",
  "title": "架构评审",
  "tasks": [
    {"content": "从证据角度分析", "persona_id": "researcher", "target_id": "edge-tab-researcher"},
    {"content": "从风险角度分析", "persona_id": "critic", "target_id": "edge-tab-critic"}
  ]
}
```

V2 当前保证：任务项归属可持久化、按目标路由、按人格注入提示词、按任务组查询结果；同一目标串行，不同目标可并行。自动冲突合并留在后续 V2 工作项。

批量导入使用：

```powershell
& '.\runtime\venv\Scripts\python.exe' scripts/import_personas.py config/personas.example.json
```
