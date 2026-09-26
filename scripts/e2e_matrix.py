#!/usr/bin/env python3
"""End-to-end scenario matrix for the ChatGPT web bridge.

Covers the real workflow shapes that the K1 smoke test never exercised:
short/long prompts, long structured answers, multi-turn follow-ups, fresh
conversations, and payloads with code fences, Windows paths, quotes and emoji.

Usage:
  python scripts/e2e_matrix.py                     # run all scenarios
  python scripts/e2e_matrix.py --only short,long   # run a subset
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LONG_BRIEF = """# 角色
你是本项目的规划大脑，负责把模糊需求拆成可执行步骤。

# 项目背景
我们在做一个本地桥接项目 GPT Web MCP，位置在 D:\\桌面\\Work\\GPT Web MCP。目标是把已经登录的 ChatGPT 网页变成 Agent 可以调用的节点：

```
mcp 调用 ask_chatgpt
  -> 本地 Bridge (127.0.0.1:8765)
  -> 浏览器扩展
  -> ChatGPT 网页自己发送
  -> 网页生成回答
  -> Bridge 读取完整回答
  -> 返回 MCP
```

# 当前状态
1. 网页自动发送已经打通，`请只回复 K1` 这类短消息 100% 成功；
2. 连续 5 轮压测全部成功，平均每轮 10.1 秒；
3. 还没有验证过长消息、长答案、多轮追问；
4. 后台运行还会把窗口拉到前台，体验需要优化。

# 约束
- 不使用任何 API Key，全部走网页；
- 不要重复已经完成的工作；
- 每一步都要能被单独验证。

# 本次问题
请用中文回答，严格按下面的结构输出：

1. 给出 4 到 5 个编号小节，每节标题不超过 12 个字；
2. 每节至少 3 条要点，每条不超过 40 个字；
3. 必须包含一个 ```json 代码块，给出阶段里程碑；
4. 最后一行以"下一步："开头，写明最优先的一件事。

# 参考数据
| 指标 | 数值 | 备注 |
| --- | --- | --- |
| 成功率 | 100% | 5/5 短消息 |
| 平均耗时 | 10.1s | 含网页生成 |
| 残留 API 代码 | 0 | 已全部撤销 |

需要特别关注长答案在读取阶段的稳定性，谢谢！"""

FOLLOW_UP = "针对你刚才的第 2 小节，把其中最优先的那一条再展开成 3 个可执行子步骤，每步都要写明验证方式。"

DEEP_ANSWER = """请写一份不少于 600 字的方案，主题是"把浏览器自动化桥接做成可交付产品"。要求：
- 分 5 节，每节有小标题；
- 至少包含 2 个 markdown 表格；
- 至少包含 1 个 python 代码块；
- 涉及路径时使用 Windows 风格路径，例如 D:\\桌面\\Work\\GPT Web MCP\\src；
- 结尾列出 5 条验收标准。"""

SPECIAL_CHARS = """请原样复述下面这段内容，不要改写，然后在后面加一行"已复述"：

路径：D:\\桌面\\Work\\GPT Web MCP\\extension\\manifest.json
JSON：{"target": "tab-1885864863", "ok": true, "count": 5}
符号：引号"双引号"、单引号'x'、反引号 `code`、星号 *星号*、下划线 _下划线_
表情：🚀 ✅ 🧪
制表：a\tb
多行：
第一行
第二行
第三行"""

SCENARIOS = {
    "short": {
        "prompt": "只回复 PONG，不要加别的内容。",
        "expect_contains": ["PONG"],
        "min_len": 1,
    },
    "long": {
        "prompt": LONG_BRIEF,
        "expect_contains": ["下一步："],
        "min_len": 200,
    },
    "followup": {
        "prompt": FOLLOW_UP,
        "expect_contains": [],
        "min_len": 40,
    },
    "new_chat_long": {
        "prompt": "这是新会话的第一条消息。请用编号列出 3 条关于本地 MCP 桥接的注意事项，每条不超过 30 个字。",
        "new_chat": True,
        "expect_contains": [],
        "min_len": 40,
    },
    "deep": {
        "prompt": DEEP_ANSWER,
        "expect_contains": [],
        "min_len": 400,
    },
    "special": {
        "prompt": SPECIAL_CHARS,
        "expect_contains": ["已复述"],
        "min_len": 40,
    },
    "fence": {
        "prompt": "只输出一个 python 代码块，内容只有一行 print(1)，代码块前后不要写任何其他文字。",
        "expect_contains": ["print(1)"],
        "min_len": 5,
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E scenario matrix")
    parser.add_argument("--only", default="")
    parser.add_argument("--target", default="")
    parser.add_argument("--timeout-ms", type=int, default=240000)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    from gpt_web_mcp.client import BridgeClient  # noqa: E402

    wanted = {item.strip() for item in args.only.split(",") if item.strip()}
    client = BridgeClient(timeout=args.timeout_ms / 1000 + 30)
    client.ensure_running()
    target = args.target or client.bound_tab().get("bound_target_id", "")
    if not target:
        print(json.dumps({"error": "NO_BOUND_TAB"}, ensure_ascii=False))
        return 1

    results = []
    for name, spec in SCENARIOS.items():
        if wanted and name not in wanted:
            continue
        record = {"scenario": name, "prompt_chars": len(spec["prompt"])}
        if spec.get("new_chat"):
            client.new_chat(target)
            time.sleep(1.0)
        started = time.time()
        try:
            response = client.send(spec["prompt"], "current", "text", args.timeout_ms, target)
        except Exception as error:  # noqa: BLE001
            record.update({"success": False, "error": f"{type(error).__name__}: {error}"[:200]})
            results.append(record)
            print(json.dumps(record, ensure_ascii=False))
            continue
        elapsed = time.time() - started
        answer = str(response.get("result") or response.get("text") or "")
        record.update({
            "success": bool(response.get("success")),
            "elapsed": round(elapsed, 1),
            "answer_chars": len(answer),
            "conversation_id": response.get("conversation_id", ""),
            "request_id": response.get("request_id", ""),
        })
        if record["success"]:
            missing = [needle for needle in spec["expect_contains"] if needle not in answer]
            record["missing_markers"] = missing
            record["too_short"] = len(answer) < spec["min_len"]
            record["head"] = answer[:120]
            record["tail"] = answer[-120:]
        else:
            record["error"] = str(response.get("error") or response.get("error_code"))[:200]
        results.append(record)
        print(json.dumps({k: record.get(k) for k in ("scenario", "success", "elapsed", "answer_chars", "missing_markers", "too_short", "error")}, ensure_ascii=False))

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(args.out or ROOT / "tmp" / f"e2e_matrix_{stamp}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out}")

    failed = [r for r in results if not r.get("success") or r.get("too_short") or r.get("missing_markers")]
    print(f"scenarios={len(results)} failed={len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
