"""data verify — scoped post-package quality verification (CLI)。

`qwq-data verify [--task T --batch B] [--release R] [--scope current|all]`

收紧扫描范围：默认 current（仅当前 schema 的 posts 根），可指定 task/batch 或 release。
逻辑全部沉到 _common.post_verify，旧 verify_*.py 仅作薄壳委托本命令。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common.post_verify import legacy_posts_roots
from verify.gate import gate_verify
from ship.consistency import report_to_text, scan_release_file, write_consistency_report


def handle_verify(args: argparse.Namespace) -> None:
    if getattr(args, "data_release_file", None):
        report = scan_release_file(
            Path(args.data_release_file),
            publish_root=Path(args.publish_root) if getattr(args, "publish_root", None) else None,
            metadata_root=Path(args.metadata_root) if getattr(args, "metadata_root", None) else None,
            phase=getattr(args, "phase", "preflight"),
        )
        if getattr(args, "report", None):
            write_consistency_report(report, Path(args.report))
        print(report_to_text(report))
        if report["status"] != "passed":
            raise SystemExit(1)
        return

    explicit = bool((getattr(args, "task", None) and getattr(args, "batch", None)) or getattr(args, "release", None))
    roots, issues = gate_verify(
        task=getattr(args, "task", None),
        batch=getattr(args, "batch", None),
        release=getattr(args, "release", None),
        scope=args.scope,
    )
    if args.scope == "current" and not explicit:
        legacy = legacy_posts_roots("current")
        if legacy:
            print(f"[verify] NOTE: skipped {len(legacy)} pre-schema release root(s) (no current articleMarkdownVersion):")
            for root in legacy:
                print(f"[verify]   ~ {root}")
    if not roots:
        print(f"[verify] No in-scope post packages found (scope={args.scope}).")
        return
    print(f"[verify] scope={args.scope} roots={len(roots)}")
    for root in roots:
        print(f"[verify]   - {root}")
    if issues:
        print(f"[verify] FAILED ({len(issues)} issue(s))", file=sys.stderr)
        for issue in issues[:200]:
            print(f"  - {issue}", file=sys.stderr)
        raise SystemExit(1)
    print("[verify] PASSED")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("verify", help="Verify post packages (scoped)")
    p.add_argument("--task", help="Task ID (verify a produced batch)")
    p.add_argument("--batch", help="Batch ID")
    p.add_argument("--release", help="Release ID under release/")
    p.add_argument("--data-release-file", help="Verify publish/env_releases/<releaseId>/<env>.json consistency")
    p.add_argument("--publish-root", help="Publish root for data release consistency")
    p.add_argument("--metadata-root", help="Metadata root for fixture user consistency")
    p.add_argument("--phase", choices=["preflight", "post-write-pre-activation", "post-activation"], default="preflight")
    p.add_argument("--report", help="Optional data release consistency report output path")
    p.add_argument(
        "--scope",
        choices=["current", "all"],
        default="current",
        help="批量审计针对 release/ 交付面：current=仅当前 schema release(默认门禁); all=全部 release(含旧 schema)。runtime 中间批次用 --task/--batch 显式校验。",
    )
    p.set_defaults(handler=handle_verify)
