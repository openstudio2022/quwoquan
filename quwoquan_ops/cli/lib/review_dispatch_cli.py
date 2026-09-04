"""Argument parsing and output handling for the Review dispatch CLI."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml


def _load_json(
    path: str | None,
    *,
    label: str,
    refuse: Callable[[str, str], None],
) -> dict[str, Any] | None:
    if not path:
        return None
    source = Path(path)
    if not source.is_file():
        refuse(f"REVIEW.{label.upper()}_MISSING", f"{label} 不存在：{path}")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        refuse(f"REVIEW.{label.upper()}_INVALID", f"{label} 必须是 JSON object")
    return value


def _resolve_output_dir(
    raw_path: str,
    *,
    repo_root: Path,
    runtime_output_root: str,
    refuse: Callable[[str, str], None],
) -> Path:
    if not runtime_output_root:
        refuse(
            "REVIEW.RUNTIME_OUTPUT_CONTRACT_INVALID",
            "runtime_outputs.root 必须为非空仓库相对路径",
        )
    runtime_root = (repo_root / runtime_output_root).resolve(strict=False)
    try:
        runtime_root.relative_to(repo_root.resolve())
    except ValueError:
        refuse(
            "REVIEW.RUNTIME_OUTPUT_CONTRACT_INVALID",
            f"runtime_outputs.root 越出仓库：{runtime_output_root}",
        )
    candidate = Path(raw_path)
    resolved = (
        candidate.resolve(strict=False)
        if candidate.is_absolute()
        else (repo_root / candidate).resolve(strict=False)
    )
    try:
        resolved.relative_to(runtime_root)
    except ValueError:
        refuse(
            "REVIEW.OUTPUT_PATH_OUTSIDE_RUNTIME_ROOT",
            f"--out 必须位于 {runtime_output_root}/ 下：{raw_path}",
        )
    return resolved


def main(
    argv: list[str] | None,
    *,
    description: str,
    repo_root: Path,
    registry_path: Path,
    runtime_output_root: str,
    build_plan: Callable[..., dict[str, Any]],
    refuse: Callable[[str, str], None],
    error_type: type[Exception],
) -> int:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--segment", required=True, choices=["PRE", "POST"])
    parser.add_argument("--deliverable", default=None)
    parser.add_argument("--changed-paths", nargs="*", default=[])
    parser.add_argument("--scope", default="")
    parser.add_argument(
        "--round",
        dest="round_name",
        choices=["initial", "rereview"],
        default="initial",
    )
    parser.add_argument("--finding-owner", action="append", default=[])
    parser.add_argument("--previous-plan", default=None)
    parser.add_argument("--owner-identity", default=None)
    parser.add_argument("--candidate-evidence", default=None)
    parser.add_argument("--human-decision-ref", default=None)
    parser.add_argument("--admission-class", choices=("ordinary", "formal_prod"), default="ordinary")
    parser.add_argument("--context-manifest", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--incomplete-role", action="append", default=[])
    parser.add_argument("--evidence-failed", action="append", default=[])
    parser.add_argument("--cancelled", action="store_true")
    parser.add_argument("--out", default=None, help="评审产物目录；plan.json 写入其中")
    args = parser.parse_args(argv)

    try:
        out_dir = (
            _resolve_output_dir(
                args.out,
                repo_root=repo_root,
                runtime_output_root=runtime_output_root,
                refuse=refuse,
            )
            if args.out
            else None
        )
        if args.context_manifest:
            refuse("IDENTITY.MIGRATION_REQUIRED", "--context-manifest 已退役；使用 --owner-identity + --candidate-evidence")
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
        plan = build_plan(
            registry,
            args.workflow,
            args.segment,
            args.deliverable,
            args.changed_paths,
            round_name=args.round_name,
            finding_owners=args.finding_owner,
            previous_plan=_load_json(
                args.previous_plan, label="previous_plan", refuse=refuse
            ),
            context_manifest=_load_json(
                args.owner_identity, label="owner_identity", refuse=refuse
            ),
            context_manifest_ref=args.owner_identity,
            candidate_evidence_ref=args.candidate_evidence,
            human_decision_ref=args.human_decision_ref,
            admission_class=args.admission_class,
            scope=args.scope,
            incomplete_roles=args.incomplete_role,
            failed_evidence_ids=args.evidence_failed,
            cancelled=args.cancelled,
        )
    except (error_type, json.JSONDecodeError) as exc:
        if isinstance(exc, error_type):
            code = str(exc.code)
            message = str(exc.message)
        else:
            code, message = "REVIEW.JSON_INVALID", str(exc)
        print(f"[review_dispatch] {code}: {message}", file=__import__("sys").stderr)
        return 2

    rendered = json.dumps(plan, ensure_ascii=False, indent=2)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        plan_path = out_dir / "plan.json"
        plan_path.write_text(rendered + "\n", encoding="utf-8")
        print(f"[review_dispatch] 派发清单已落盘：{plan_path}")
    else:
        print(rendered)
    return 0


__all__ = ["main"]
