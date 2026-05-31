"""data media — image safety / aesthetic checks (CLI)。

`qwq-data media check-images --task --batch [--refs] [--allow-needs-review]`

三段式中的 [CLI validate + gate]：读取 compose/materialize 产出的 asset 记录，
调用 _common.image_safety 做真实 CV（人脸/水印/OCR/去重）体检，落 media_check
stage result + gate report；unsafe 即非零退出。
"""
from __future__ import annotations

import argparse
import sys

from _common.image_safety import assess_asset_sources
from _common.io import read_json
from _common.paths import batch_command_root, batch_results_dir
from _common.stage_reports import write_gate_report, write_stage_result
from media.gate import gate_media_check


def _collect_assets_for_ref(task_id: str, batch_id: str, ref: str) -> list[dict]:
    """优先取 compose 结果里的 assets（含 sourcePath），回退到 materialized manifest。"""
    compose_file = batch_results_dir(task_id, batch_id, "produce", "compose") / f"{ref}.json"
    if compose_file.exists():
        payload = read_json(compose_file).get("payload") or {}
        assets = payload.get("assets") or []
        if assets:
            return list(assets)
    posts_root = batch_command_root(task_id, batch_id, "produce") / "posts"
    for manifest in posts_root.rglob("manifest.json"):
        if manifest.parent.name == ref:
            data = read_json(manifest)
            return list(data.get("assets") or [])
    return []


def _iter_refs(task_id: str, batch_id: str, refs: list[str]) -> list[str]:
    if refs:
        return refs
    compose_dir = batch_results_dir(task_id, batch_id, "produce", "compose")
    if compose_dir.exists():
        return sorted(f.stem for f in compose_dir.glob("*.json"))
    return []


def check_images(task_id: str, batch_id: str, refs: list[str], *, allow_needs_review: bool = False) -> list[dict]:
    statuses: list[dict] = []
    for ref in _iter_refs(task_id, batch_id, refs):
        assets = _collect_assets_for_ref(task_id, batch_id, ref)
        report = assess_asset_sources(assets)
        write_stage_result(task_id, batch_id, "produce", "media_check", ref, report)
        summary = report["summary"]
        passed = summary["unsafe"] == 0 and summary["duplicateGroups"] == 0 and (
            allow_needs_review or summary["needsReview"] == 0
        )
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="produce",
            step="media_check",
            ref=ref,
            passed=passed,
            issues=[] if passed else _issues_from_summary(ref, summary, allow_needs_review),
            evidence_summary=summary,
            next_step="review" if passed else None,
            fallback_stage=None if passed else "compose",
        )
        statuses.append({"ref": ref, "passed": passed, "summary": summary})
    return statuses


def _issues_from_summary(ref: str, summary: dict, allow_needs_review: bool) -> list[str]:
    issues: list[str] = []
    if summary["unsafe"]:
        issues.append(f"{summary['unsafe']} unsafe image(s)")
    if summary["duplicateGroups"]:
        issues.append(f"{summary['duplicateGroups']} duplicate group(s)")
    if not allow_needs_review and summary["needsReview"]:
        issues.append(f"{summary['needsReview']} image(s) need human review")
    return issues


def handle_media(args: argparse.Namespace) -> None:
    if args.media_command != "check-images":
        print(f"[media] ERROR: unknown subcommand {args.media_command}", file=sys.stderr)
        raise SystemExit(2)
    task_id = args.task
    batch_id = args.batch
    refs = [r.strip() for r in (args.refs or "").split(",") if r.strip()]
    allow_needs_review = bool(getattr(args, "allow_needs_review", False))

    statuses = check_images(task_id, batch_id, refs, allow_needs_review=allow_needs_review)
    if not statuses:
        print(f"[media] No assets found for task={task_id} batch={batch_id}")
        return
    for row in statuses:
        s = row["summary"]
        flag = "OK" if row["passed"] else "BLOCK"
        print(
            f"[media] {flag} {row['ref']}: total={s['total']} unsafe={s['unsafe']} "
            f"needsReview={s['needsReview']} textHeavy={s['textHeavy']} dupGroups={s['duplicateGroups']}"
        )
    issues = gate_media_check(task_id, batch_id, allow_needs_review=allow_needs_review)
    if issues:
        for issue in issues[:20]:
            print(f"[media] FAIL {issue}", file=sys.stderr)
        raise SystemExit(1)
    print(f"[media] image safety gate passed for {len(statuses)} ref(s).")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("media", help="Media asset safety / aesthetic checks")
    media_sub = p.add_subparsers(dest="media_command", required=True)
    p_check = media_sub.add_parser("check-images", help="Run face/watermark/OCR/dedup checks on post assets")
    p_check.add_argument("--task", required=True, help="Task ID")
    p_check.add_argument("--batch", required=True, help="Batch ID")
    p_check.add_argument("--refs", help="Optional comma-separated refs (default: all compose refs)")
    p_check.add_argument(
        "--allow-needs-review",
        action="store_true",
        help="Do not fail the gate on needs_review (faces/backend) images",
    )
    p.set_defaults(handler=handle_media)
