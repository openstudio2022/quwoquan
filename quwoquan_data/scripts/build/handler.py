"""data build — 实体主页构建（prepare 下发产出契约 + validate 采纳门）。

与三层目录实体模型一致；不再依赖旧 entities.ndjson 模型。
- prepare：按 coverageTargets 下发 SOP 产出契约给 Agent
- validate：校验产出（三件套/≥800字/必填字段/conditionProfile），作为 promote 前采纳门
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.paths import ensure_batch_layout  # noqa: E402
from task.store import load_spec  # noqa: E402
from build.homepage import (  # noqa: E402
    MIN_PAGE_CHARS,
    materialize_entity_pages,
    prepare_entity_pages,
    validate_entity_pages,
)


def handle_build(args: argparse.Namespace) -> None:
    task_id = args.task
    batch_id = args.batch
    stage = args.stage
    spec = load_spec(task_id)

    print(f"[build] Task: {task_id}, Batch: {batch_id}, Stage: {stage}")

    if stage in ("prepare", "all"):
        ensure_batch_layout(task_id, batch_id, "build")
        inputs_dir, refs = prepare_entity_pages(task_id, batch_id, spec)
        print(f"[build] prepare: 下发 {len(refs)} 个实体主页产出契约 -> {inputs_dir}")
        print(
            f"[build] Agent: 按 sopDir 模板在 outputDir 物化 "
            f"page.md(≥{MIN_PAGE_CHARS}字)+_entity.json(含 conditionProfile)+manifest.json"
        )
        if not refs:
            print("[build] WARN: coverageTargets 为空，无实体可下发")

    if stage in ("materialize", "all"):
        issues = materialize_entity_pages(task_id, batch_id, spec)
        if issues:
            print(f"[build] materialize FAILED ({len(issues)} 项):")
            for issue in issues:
                print(f"  - {issue}")
            sys.exit(1)
        print("[build] materialize PASSED: 实体主页三件套已确定性物化")

    if stage in ("validate", "all"):
        issues = validate_entity_pages(task_id, batch_id, spec)
        if issues:
            print(f"[build] validate FAILED ({len(issues)} 项):")
            for issue in issues:
                print(f"  - {issue}")
            sys.exit(1)
        print("[build] validate PASSED: 所有 coverage 实体主页达标（可进入 promote 发布门）")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("build", help="Build entity homepages (prepare/validate)")
    p.add_argument("--task", required=True, help="Task ID")
    p.add_argument("--batch", default="build_1", help="Batch ID")
    p.add_argument(
        "--stage",
        choices=["prepare", "materialize", "validate", "all"],
        default="prepare",
        help="prepare=下发产出契约; materialize=确定性物化; validate=采纳门校验; all=全链路",
    )
    p.set_defaults(handler=handle_build)
