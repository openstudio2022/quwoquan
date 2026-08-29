#!/usr/bin/env python3
"""分级验收冻结门：验收窗口内禁止改引擎，失败必须先归类。

两个月「跑一次 → 改引擎 → fail-closed 身份冻结把改动变成下一批阻断」的循环，
唯一的打断机制是把「引擎不可变」变成可执行判据而不是口头承诺。本门禁提供：

- ``record``：把 ``scripts/`` 与 ``schema/`` 的 tree digest、文件数与行数冻结为该级基线。
- ``check``：与基线比对。G0 是唯一允许改引擎的窗口（只报告），G1 起任何差异即
  ``GATE_BLOCK``，该级验收作废重跑。行数增长单独阻断：验收期靠加代码解决问题
  与「跑产能」目标相反。
- ``classify``：把运行失败归类，判定是否允许动引擎。只有 ``engine_defect``
  允许，且必须先有可复现失败测试并从 G0 重新开始。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path



sys.dont_write_bytecode = True

DATA_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import OUTPUT_ROOT  # noqa: E402

ENGINE_TREES = (
    ("scripts", "*.py"),
    ("schema", "*.json"),
)
STAGES = ("g0", "g1", "g2", "g3")
# G0 的目的就是产出仓库第一个 release，必然暴露真实缺陷，此时改引擎是合法的。
ENGINE_CHANGE_ALLOWED_STAGES = frozenset({"g0"})
INPUT_FAILURE_CLASSES = (
    "source_exhausted",
    "credential_missing",
    "catalog_unavailable",
    "provider_5xx",
    "object_quality_discard",
)
ENGINE_FAILURE_CLASSES = ("engine_defect",)
FAILURE_CLASSES = INPUT_FAILURE_CLASSES + ENGINE_FAILURE_CLASSES


@dataclass(frozen=True, slots=True)
class TreeSnapshot:
    name: str
    digest: str
    file_count: int
    line_count: int
    files: dict[str, str]

    def summary(self) -> dict[str, object]:
        return {
            "name": self.name,
            "digest": self.digest,
            "fileCount": self.file_count,
            "lineCount": self.line_count,
        }

    def document(self) -> dict[str, object]:
        return {**self.summary(), "files": dict(self.files)}


def _baseline_path(stage: str) -> Path:
    return OUTPUT_ROOT / "acceptance" / "freeze" / f"{stage}.json"


def _snapshot_tree(name: str, pattern: str) -> TreeSnapshot:
    root = DATA_ROOT / name
    files: dict[str, str] = {}
    line_count = 0
    for path in sorted(root.rglob(pattern)):
        if any(part in {"__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        try:
            body = path.read_bytes()
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        files[rel] = hashlib.sha256(body).hexdigest()
        line_count += body.count(b"\n")
    digest = hashlib.sha256(
        json.dumps(files, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return TreeSnapshot(
        name=name,
        digest=f"sha256:{digest}",
        file_count=len(files),
        line_count=line_count,
        files=files,
    )


def _snapshot() -> tuple[TreeSnapshot, ...]:
    return tuple(_snapshot_tree(name, pattern) for name, pattern in ENGINE_TREES)


def _tree_drift(baseline: dict[str, object], current: TreeSnapshot) -> list[str]:
    old = baseline.get("files")
    old = old if isinstance(old, dict) else {}
    new = current.files
    drift: list[str] = []
    for rel in sorted(set(new) - set(old)):
        drift.append(f"added {current.name}/{rel}")
    for rel in sorted(set(old) - set(new)):
        drift.append(f"removed {current.name}/{rel}")
    for rel in sorted(set(old) & set(new)):
        if old[rel] != new[rel]:
            drift.append(f"modified {current.name}/{rel}")
    return drift


def _handle_record(stage: str) -> int:
    snapshots = _snapshot()
    path = _baseline_path(stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": "quwoquan_data.acceptance_freeze_baseline",
        "stage": stage,
        "engineChangeAllowed": stage in ENGINE_CHANGE_ALLOWED_STAGES,
        "trees": [snapshot.document() for snapshot in snapshots],
    }
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[acceptance-freeze] RECORDED stage={stage} baseline={path}")
    for snapshot in snapshots:
        print(
            f"  - {snapshot.name}: files={snapshot.file_count} "
            f"lines={snapshot.line_count} digest={snapshot.digest}"
        )
    return 0


def _handle_check(stage: str) -> int:
    path = _baseline_path(stage)
    if not path.is_file():
        print(
            f"[acceptance-freeze] GATE_BLOCK stage={stage}: baseline is missing; "
            f"run record before the acceptance window ({path})",
            file=sys.stderr,
        )
        return 1
    baseline = json.loads(path.read_text(encoding="utf-8"))
    by_name = {
        str(row.get("name")): row
        for row in baseline.get("trees") or []
        if isinstance(row, dict)
    }
    drift: list[str] = []
    growth: list[str] = []
    for snapshot in _snapshot():
        recorded = by_name.get(snapshot.name)
        if recorded is None:
            drift.append(f"missing baseline tree {snapshot.name}")
            continue
        if recorded.get("digest") != snapshot.digest:
            drift.extend(_tree_drift(recorded, snapshot))
        baseline_lines = int(recorded.get("lineCount") or 0)
        if snapshot.line_count > baseline_lines:
            growth.append(
                f"{snapshot.name} grew {baseline_lines} -> {snapshot.line_count} lines"
            )
        print(
            f"  - {snapshot.name}: files={snapshot.file_count} "
            f"lines={snapshot.line_count} digest={snapshot.digest}"
        )
    engine_change_allowed = stage in ENGINE_CHANGE_ALLOWED_STAGES
    if not drift and not growth:
        print(f"[acceptance-freeze] PASSED stage={stage}: engine is frozen")
        return 0
    stream = sys.stdout if engine_change_allowed else sys.stderr
    verdict = "ADVISORY" if engine_change_allowed else "GATE_BLOCK"
    print(f"[acceptance-freeze] {verdict} stage={stage}: engine changed", file=stream)
    for item in drift[:40]:
        print(f"  - {item}", file=stream)
    if len(drift) > 40:
        print(f"  - ... and {len(drift) - 40} more", file=stream)
    for item in growth:
        print(f"  - {item}", file=stream)
    if engine_change_allowed:
        print(
            "  G0 is the only window where engine changes are legitimate; "
            "re-record the baseline before G1.",
            file=stream,
        )
        return 0
    print(
        "  This acceptance run is void: re-record only after restarting from G0.",
        file=stream,
    )
    return 1


def _handle_classify(stage: str, failure_class: str, has_failing_test: bool) -> int:
    if failure_class in INPUT_FAILURE_CLASSES:
        print(
            f"[acceptance-freeze] CLASSIFIED stage={stage} class={failure_class} "
            "engineChangeAllowed=false"
        )
        print("  Fix inputs, credentials or discard the object; do not touch the engine.")
        return 0
    if not has_failing_test:
        print(
            f"[acceptance-freeze] GATE_BLOCK stage={stage} class={failure_class}: "
            "an engine defect needs a reproducible failing test first "
            "(pass --failing-test once it exists)",
            file=sys.stderr,
        )
        return 1
    print(
        f"[acceptance-freeze] CLASSIFIED stage={stage} class={failure_class} "
        "engineChangeAllowed=true"
    )
    print("  Restart acceptance from G0 after the fix; do not resume this stage.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_acceptance_freeze",
        description="分级验收冻结门：引擎不可变判据与失败归类",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("record", "check"):
        sub = subparsers.add_parser(action)
        sub.add_argument("--stage", choices=STAGES, required=True)
    classify = subparsers.add_parser("classify")
    classify.add_argument("--stage", choices=STAGES, required=True)
    classify.add_argument("--failure-class", choices=FAILURE_CLASSES, required=True)
    classify.add_argument(
        "--failing-test",
        action="store_true",
        help="已存在可复现失败测试（engine_defect 必需）",
    )
    args = parser.parse_args(argv)
    if args.action == "record":
        return _handle_record(args.stage)
    if args.action == "check":
        return _handle_check(args.stage)
    return _handle_classify(
        args.stage, args.failure_class, bool(args.failing_test)
    )


if __name__ == "__main__":
    raise SystemExit(main())
