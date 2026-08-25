#!/usr/bin/env python3
"""轮次交接单校验门禁。

HANDOFF 是宪法要求的工作流间交接契约，但聊天文本无法校验、无法跨会话消费。
交接单 `.qwq_output/env/repo/runs/handoff/<轮次>/manifest.md` 是它的物理形态；
本门禁校验其结构可裁定：

1. 头部字段：`intent 终版`、`新轮触发判定`。
2. 宪法四项段落齐全：`## 产出物`、`## 未决项去向`、`## 唯一合法下游`、`## 证据链`。
3. 未决项三向裁决零悬空：每条落到「转 OPEN-###」「Out of Scope」「下一工作流承接」之一。
4. 证据链每条带「命令 + 退出码 + 时间戳 + 工作树 SHA」，下游消费时过期即复跑。

用法：
    python3 quwoquan_ops/gate/verify_handoff_manifest.py <manifest.md>
    python3 quwoquan_ops/gate/verify_handoff_manifest.py   # 校验最新轮次

退出码：0 通过；1 校验失败；2 用法错误或找不到交接单。
交接单是运行产物（可删可重建）：长期事实必须同时转出到 OPEN/spec，本门禁不校验业务内容。
接入面：on-demand gate，经 `make verify-handoff-manifest` 在轮次收口时调用；
不接入 gate_repo.sh，不进 L0 commit gate。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HANDOFF_ROOT = ROOT / ".qwq_output/env/repo/runs/handoff"

sys.path.insert(0, str(ROOT / "quwoquan_ops/cli/lib"))
from gate_output import emit_gate_result, finding  # noqa: E402

REQUIRED_HEAD_FIELDS = ("intent 终版", "新轮触发判定")
REQUIRED_SECTIONS = ("## 产出物", "## 未决项去向", "## 唯一合法下游", "## 证据链")

# 三向裁决：转 OPEN / Out of Scope / 下一工作流承接。「无未决项」显式声明也合法。
RESOLUTION_RE = re.compile(r"OPEN-\d{3,}|Out of Scope|承接|无未决项")
EVIDENCE_RE = re.compile(
    r"exit=\d+.*\d{4}-\d{2}-\d{2}.*\b[0-9a-f]{7,40}\b|\d{4}-\d{2}-\d{2}.*exit=\d+.*\b[0-9a-f]{7,40}\b"
)
BULLET_RE = re.compile(r"^-\s+(.+)$", re.M)


def _section(text: str, heading: str) -> str | None:
    match = re.search(rf"^{re.escape(heading)}\s*$", text, re.M)
    if match is None:
        return None
    tail = text[match.end():]
    nxt = re.search(r"^##\s+", tail, re.M)
    return tail[: nxt.start()] if nxt else tail


def validate(text: str, rel: str) -> list[str]:
    issues: list[str] = []
    for field in REQUIRED_HEAD_FIELDS:
        if field not in text:
            issues.append(f"{rel}: 缺头部字段「{field}」")

    for heading in REQUIRED_SECTIONS:
        if _section(text, heading) is None:
            issues.append(f"{rel}: 缺宪法四项段落「{heading}」")

    pending = _section(text, "## 未决项去向")
    if pending is not None:
        for bullet in BULLET_RE.findall(pending):
            if not RESOLUTION_RE.search(bullet):
                issues.append(
                    f"{rel}: 未决项悬空「{bullet[:40]}」——必须落到"
                    "「转 OPEN-###」「Out of Scope」「下一工作流承接」之一"
                )

    downstream = _section(text, "## 唯一合法下游")
    if downstream is not None and not BULLET_RE.search(downstream):
        issues.append(f"{rel}: 「唯一合法下游」段为空，下一轮 RESOLVE 无从消费")

    evidence = _section(text, "## 证据链")
    if evidence is not None:
        bullets = BULLET_RE.findall(evidence)
        if not bullets:
            issues.append(f"{rel}: 证据链为空——完成宣称没有任何可复跑证据")
        for bullet in bullets:
            if not EVIDENCE_RE.search(bullet):
                issues.append(
                    f"{rel}: 证据条目缺字段「{bullet[:40]}」——必须带"
                    "命令 + exit=退出码 + 时间戳 + 工作树 SHA"
                )
    return issues


def _latest_manifest() -> Path | None:
    if not HANDOFF_ROOT.is_dir():
        return None
    manifests = sorted(HANDOFF_ROOT.glob("*/manifest.md"), key=lambda p: p.stat().st_mtime)
    return manifests[-1] if manifests else None


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        target = Path(argv[1])
        if not target.is_absolute():
            target = ROOT / target
    else:
        found = _latest_manifest()
        if found is None:
            print(
                f"[verify_handoff_manifest] 用法错误：{HANDOFF_ROOT.relative_to(ROOT)} "
                "下没有任何轮次交接单，且未指定路径",
                file=sys.stderr,
            )
            return 2
        target = found

    if not target.is_file():
        print(f"[verify_handoff_manifest] 找不到交接单 {target}", file=sys.stderr)
        return 2

    rel = target.relative_to(ROOT).as_posix() if target.is_relative_to(ROOT) else str(target)
    issues = validate(target.read_text(encoding="utf-8"), rel)
    emit_gate_result(
        "verify-handoff-manifest",
        [finding(issue, path=rel) for issue in issues],
        ROOT,
    )
    if issues:
        print("[verify_handoff_manifest] FAIL", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print(f"[verify_handoff_manifest] OK: {rel} 四项齐全、裁决零悬空、证据字段完整")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
