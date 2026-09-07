#!/usr/bin/env python3
"""Bind Review Code Health evidence to the runner's exact plan and candidate."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "quwoquan_ops/cli"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from quwoquan_ops.ci.verify_code_health_delivery import verify_delivery  # noqa: E402
from quwoquan_ops.gate import verify_review_baseline  # noqa: E402
from quwoquan_ops.gate.code_health_delta.render import render_candidate  # noqa: E402

RESULT_PATH_ENV = "QWQ_NAMED_EVIDENCE_RESULT_PATH"
SOURCE_HEAD_ENV = "QWQ_REVIEW_EVIDENCE_HEAD_SHA"
SOURCE_MERGE_BASE_ENV = "QWQ_REVIEW_EVIDENCE_MERGE_BASE_SHA"
SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")


class ReviewCodeHealthError(ValueError):
    pass


def _git(repo: Path, *args: str, binary: bool = False) -> str | bytes:
    completed = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise ReviewCodeHealthError(
            completed.stderr.decode("utf-8", errors="replace").strip()
            or f"git {' '.join(args)} failed"
        )
    return completed.stdout if binary else completed.stdout.decode("utf-8").strip()


def _descriptor_path() -> Path:
    raw = os.environ.get(RESULT_PATH_ENV, "")
    if not raw:
        raise ReviewCodeHealthError("缺 evidence_runner 注入的 artifact descriptor path")
    path = Path(raw)
    if not path.is_absolute() or path.name != "code-health-delta.json":
        raise ReviewCodeHealthError("artifact descriptor path 非 runner canonical path")
    if path.exists() or path.is_symlink():
        raise ReviewCodeHealthError("artifact descriptor path 必须 create-once")
    parent = path.parent
    parent_stat = parent.lstat()
    if not stat.S_ISDIR(parent_stat.st_mode) or stat.S_ISLNK(parent_stat.st_mode):
        raise ReviewCodeHealthError("artifact descriptor parent 非 regular directory")
    return path


def _write_descriptor(path: Path, payload: dict[str, Any]) -> None:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o400)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def verify() -> dict[str, Any]:
    descriptor_path = _descriptor_path()
    baseline = verify_review_baseline.verify()
    plan_raw, plan_ref = verify_review_baseline._exact_plan_bytes()
    plan = verify_review_baseline._load_plan(plan_raw)
    source_head = os.environ.get(SOURCE_HEAD_ENV, "")
    merge_base = os.environ.get(SOURCE_MERGE_BASE_ENV, "")
    if not SHA_RE.fullmatch(source_head) or not SHA_RE.fullmatch(merge_base):
        raise ReviewCodeHealthError("runner exact source range 缺失或非法")
    current_head = str(_git(ROOT, "rev-parse", "HEAD"))
    if source_head != current_head or source_head != plan.get("head_sha"):
        raise ReviewCodeHealthError("plan/runner/current HEAD 漂移")
    if merge_base != plan.get("merge_base_sha"):
        raise ReviewCodeHealthError("plan/runner merge base 漂移")
    if _git(ROOT, "status", "--porcelain=v1", "-z", "--untracked-files=all", binary=True):
        raise ReviewCodeHealthError("candidate-bound Code Health 只接受 clean workspace")
    actual_merge_base = str(_git(ROOT, "merge-base", source_head, merge_base))
    if actual_merge_base != merge_base:
        raise ReviewCodeHealthError("runner merge base 不是 current HEAD ancestor")

    candidate = plan["candidate_evidence_identity"]
    report, output, report_identity = verify_delivery(
        ROOT,
        base_sha=merge_base,
        head_sha=source_head,
        expected_path_digest=str(candidate["changed_paths_digest"]),
        expected_impact_plan_digest=str(candidate["impact_plan_digest"]),
    )
    expected_paths = sorted(
        {str(path) for path in plan["changed_paths"]},
        key=lambda value: value.encode("utf-8"),
    )
    if report.get("candidateSource") != "commit":
        raise ReviewCodeHealthError("Code Health report 非 clean commit candidate")
    if report.get("changedPaths") != expected_paths or not expected_paths:
        raise ReviewCodeHealthError("Code Health report changed paths 为空或与 plan 漂移")
    if report.get("summary", {}).get("changedFiles") != len(expected_paths):
        raise ReviewCodeHealthError("Code Health report changed file summary 漂移")
    output = output.resolve(strict=True)
    if not output.is_relative_to(ROOT.resolve()):
        raise ReviewCodeHealthError("Code Health report 逃逸仓库")
    output_stat = output.lstat()
    if not stat.S_ISREG(output_stat.st_mode) or stat.S_ISLNK(output_stat.st_mode) or output_stat.st_nlink != 1:
        raise ReviewCodeHealthError("Code Health report 必须为 single-link regular file")
    report_raw = output.read_bytes()
    report_payload = json.loads(report_raw.decode("utf-8"))
    if report_payload != report:
        raise ReviewCodeHealthError("Code Health report exact bytes 与 producer result 漂移")
    fingerprint = report["evidenceFingerprint"]
    descriptor = {
        "kind": "code-health-report-v1",
        "ref": output.relative_to(ROOT).as_posix(),
        "canonical_bytes_sha256": "sha256:" + hashlib.sha256(report_raw).hexdigest(),
        "schema": report["schema"],
        "terminal": report["terminal"],
        "report_identity": report_identity,
        "evidence_fingerprint_ref": fingerprint["ref"],
        "evidence_fingerprint_digest": fingerprint["digest"],
        "base_sha": report["baseSha"],
        "head_sha": report["headSha"],
        "changed_paths_digest": report["changedPathsDigest"],
        "impact_plan_ref": candidate["impact_plan_ref"],
        "impact_plan_digest": candidate["impact_plan_digest"],
        "candidate_evidence_ref": candidate["ref"],
        "candidate_evidence_sha256": candidate["canonical_bytes_sha256"],
        "plan_ref": plan_ref,
        "plan_sha256": baseline["plan_sha256"],
        "summary": report["summary"],
        "findings": report["findings"],
    }
    _write_descriptor(descriptor_path, descriptor)
    return descriptor, report


def main() -> int:
    try:
        descriptor, report = verify()
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[review-code-health] GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    # Reviewer 只读这段 Markdown 与 typed terminal，不重跑、不打开 JSON。
    print(render_candidate(report))
    print(
        "review-code-health: "
        f"{descriptor['terminal']} identity={descriptor['report_identity']} "
        f"report={descriptor['ref']}"
    )
    return 1 if descriptor["terminal"] == "GATE_BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
