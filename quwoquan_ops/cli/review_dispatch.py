#!/usr/bin/env python3
"""review 派发编排：读 registry.yaml 生成派发清单与去重 gate 计划。

board 不再手工解析注册表——本脚本是派发装配的唯一执行体，输出机器可读的
plan.json，供 board 按清单派发并把评审产物落盘到同一目录。
装配语义与 registry.yaml 头部注释一一对应：profile 派生、when 求值、gate 去重。

用法：
    python3 quwoquan_ops/cli/review_dispatch.py \
        --workflow dev --segment POST \
        --changed-paths quwoquan_app/lib/foo.dart \
        [--deliverable implementation] \
        [--out .qwq_output/env/repo/runs/review/<run-id>]

缺 --out 时输出到 stdout；给 --out 时写 <out>/plan.json 并打印落盘路径。
退出码：0 成功；2 输入不合法（workflow/segment 不在注册表）。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCES_DIR = REPO_ROOT / ".agents/skills/review/references"
REGISTRY_PATH = REFERENCES_DIR / "registry.yaml"

_GATE_LINE_RE = re.compile(r"^\s*gate:\s*(?P<command>\S.*?)\s*$")


def derive_profiles(
    profiles: dict, changed_paths: list[str], deliverable: str
) -> list[str]:
    """changed_paths 命中 paths、或 deliverable 命中 deliverables，即激活该 profile。"""
    active: list[str] = []
    for name, config in profiles.items():
        config = config or {}
        patterns = config.get("paths") or []
        path_hit = any(
            fnmatch.fnmatch(path, pattern)
            for path in changed_paths
            for pattern in patterns
        )
        deliverable_hit = deliverable in (config.get("deliverables") or [])
        if path_hit or deliverable_hit:
            active.append(name)
    return active


def assemble_bindings(bindings: list[dict], active_profiles: list[str]) -> list[dict]:
    """省略 when 表示恒装配；when 为 profile 列表时任一命中即装配。"""
    selected: list[dict] = []
    for binding in bindings:
        when = binding.get("when")
        if when is None or any(profile in active_profiles for profile in when):
            selected.append({"role": binding["role"], "checklist": binding["checklist"]})
    return selected


def collect_gates(checklists: list[str]) -> list[str]:
    """从选中 checklist 提取 gate: 命令，保序去重——相同 gate 只执行一次。"""
    seen: dict[str, None] = {}
    for checklist in checklists:
        text = (REFERENCES_DIR / checklist).read_text(encoding="utf-8")
        for line in text.splitlines():
            match = _GATE_LINE_RE.match(line)
            if match:
                seen.setdefault(match.group("command"))
    return list(seen)


def build_plan(
    registry: dict,
    workflow: str,
    segment: str,
    deliverable: str | None,
    changed_paths: list[str],
) -> dict:
    workflows = registry.get("workflows") or {}
    config = workflows.get(workflow)
    if config is None:
        _fail(
            f"workflow={workflow} 不在 registry.yaml 的 workflows 中；"
            f"可选：{', '.join(sorted(workflows))}"
        )
    if segment not in (config.get("segments") or []):
        _fail(
            f"workflow={workflow} 不以 segment={segment} 调用 review；"
            f"注册表声明：{config.get('segments')}"
        )
    resolved_deliverable = deliverable or config.get("deliverable") or ""
    active_profiles = derive_profiles(
        registry.get("profiles") or {}, changed_paths, resolved_deliverable
    )
    dispatches = assemble_bindings(config.get("bindings") or [], active_profiles)
    gates = collect_gates([item["checklist"] for item in dispatches])

    roles: dict[str, list[str]] = {}
    for item in dispatches:
        roles.setdefault(item["role"], []).append(item["checklist"])

    return {
        "workflow": workflow,
        "segment": segment,
        "deliverable": resolved_deliverable,
        "changed_paths": changed_paths,
        "profiles": active_profiles,
        "dispatches": [
            {"role": role, "checklists": checklists}
            for role, checklists in roles.items()
        ],
        "gates": gates,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "head_sha": _head_sha(),
    }


def _fail(message: str) -> None:
    print(f"[review_dispatch] {message}", file=sys.stderr)
    raise SystemExit(2)


def _head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--segment", required=True, choices=["PRE", "POST"])
    parser.add_argument("--deliverable", default=None)
    parser.add_argument("--changed-paths", nargs="*", default=[])
    parser.add_argument("--out", default=None, help="评审产物目录；plan.json 写入其中")
    args = parser.parse_args(argv)

    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    plan = build_plan(
        registry, args.workflow, args.segment, args.deliverable, args.changed_paths
    )
    rendered = json.dumps(plan, ensure_ascii=False, indent=2)

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        plan_path = out_dir / "plan.json"
        plan_path.write_text(rendered + "\n", encoding="utf-8")
        print(f"[review_dispatch] 派发清单已落盘：{plan_path}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
