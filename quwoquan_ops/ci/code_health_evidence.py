#!/usr/bin/env python3
"""Publish and read back immutable code-health facts as generic OCI artifacts.

独立于 promotion 证据链：hosted code-health 复算与 weekly 观测只发布 report-only fact，
workflow 文本因此不出现任何 promotion 语义。发布复用 promotion_evidence 的 canonical
bytes 与 ORAS 调用；历史读取只接受 exact @sha256 ref。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.promotion_evidence import (  # noqa: E402
    PromotionEvidenceError, canonical_bytes, materialize_oci_fact, publish_oci_fact,
)

WEEKLY_TAG = re.compile(r"^week-(\d{4})-W(\d{2})$")
INTEGRATION_TAG = re.compile(r"^base-[0-9a-f]{40}-head-[0-9a-f]{40}$")


class CodeHealthEvidenceError(ValueError):
    """Raised when a code-health fact cannot be published or read back exactly."""


def write_fact(report: dict[str, Any], output: Path) -> Path:
    """Write canonical fact bytes; the report dict itself is the fact."""
    if not isinstance(report, dict) or "schema" not in report or "terminal" not in report:
        raise CodeHealthEvidenceError("code-health fact 必须是带 schema/terminal 的报告对象")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_bytes(report) + b"\n")
    return output


def publish(report_path: Path, *, repository: str, transport_tag: str) -> str:
    if not (WEEKLY_TAG.fullmatch(transport_tag) or INTEGRATION_TAG.fullmatch(transport_tag)):
        raise CodeHealthEvidenceError("transport tag 必须为 week-YYYY-Www 或 base-<sha>-head-<sha>")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CodeHealthEvidenceError(f"report 无法读取: {exc}") from exc
    with tempfile.TemporaryDirectory(prefix="qwq-code-health-fact-") as directory:
        fact = write_fact(report, Path(directory) / "fact.json")
        try:
            return publish_oci_fact(fact_file=fact, repository=repository, transport_tag=transport_tag)
        except PromotionEvidenceError as exc:
            raise CodeHealthEvidenceError(str(exc)) from exc


def _oras(*args: str) -> str:
    completed = subprocess.run(["oras", *args], text=True, capture_output=True, check=False)
    if completed.returncode:
        raise CodeHealthEvidenceError(" ".join((completed.stderr or completed.stdout).split()) or "oras failed")
    return completed.stdout


def weekly_history_tags(repository: str) -> list[str]:
    tags = [line.strip() for line in _oras("repo", "tags", repository).splitlines() if line.strip()]
    return sorted((tag for tag in tags if WEEKLY_TAG.fullmatch(tag)), reverse=True)


def pull_weekly_history(repository: str, *, limit: int, output_dir: Path) -> dict[str, Any]:
    """Materialize up to ``limit`` most recent weekly facts; unavailability is typed, not fatal."""
    if limit <= 0:
        raise CodeHealthEvidenceError("limit 必须为正整数")
    try:
        tags = weekly_history_tags(repository)[:limit]
        materialized = []
        for tag in tags:
            digest = _oras("resolve", f"{repository}:{tag}").strip()
            exact_ref = f"{repository}@{digest}"
            output = output_dir / f"{tag}.json"
            materialize_oci_fact(exact_ref=exact_ref, output_file=output)
            materialized.append({"tag": tag, "exactRef": exact_ref, "path": str(output)})
        return {"status": "available", "repository": repository, "reports": materialized}
    except (CodeHealthEvidenceError, PromotionEvidenceError) as exc:
        return {"status": "unavailable", "repository": repository, "reason": str(exc), "reports": []}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    publish_parser = commands.add_parser("publish", help="Publish one report as an immutable OCI fact")
    publish_parser.add_argument("--report", type=Path, required=True)
    publish_parser.add_argument("--repository", required=True)
    publish_parser.add_argument("--transport-tag", required=True)
    history = commands.add_parser("pull-weekly-history", help="Materialize recent weekly facts for trend rendering")
    history.add_argument("--repository", required=True)
    history.add_argument("--limit", type=int, default=8)
    history.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "publish":
            exact_ref = publish(args.report, repository=args.repository, transport_tag=args.transport_tag)
            print(json.dumps({"exactRef": exact_ref}, sort_keys=True))
            return 0
        result = pull_weekly_history(args.repository, limit=args.limit, output_dir=args.output_dir)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except CodeHealthEvidenceError as exc:
        print(f"code-health-evidence: GATE_BLOCK: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
