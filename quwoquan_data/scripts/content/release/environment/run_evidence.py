"""Schema-bound append-only environment release run evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.io import write_json
from core.schema import assert_valid


def write_release_evidence(
    path: Path,
    document: Mapping[str, Any],
    schema_name: str,
) -> None:
    payload = dict(document)
    assert_valid(payload, "release", schema_name, label=f"{schema_name}:{path}")
    write_json(path, payload)


def write_verification_result(path: Path, result: Mapping[str, Any]) -> None:
    document = dict(result)
    canonical = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    document["verificationChecksum"] = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
    write_release_evidence(path, document, "environment_release_result")


def create_run(
    *,
    output_root: Path,
    environment: str,
    release_id: str,
    run_id: str,
    kind: str,
    valid_environments: frozenset[str],
) -> Path:
    if environment not in valid_environments:
        raise SystemExit(f"[ship] environment 非法：{environment}")
    run = output_root / "env" / environment / "runs" / "data-release" / release_id / run_id
    # create-once 的对象是 run 记录本身，不是承载它的目录：research 校验会把 runtime
    # proof 预存进同一 run 目录再创建 run，把目录在场当成 run 已存在会让这条链无法开始。
    if (run / "run.json").exists():
        raise SystemExit(f"[ship] append-only run 已存在：{run}")
    write_release_evidence(
        run / "run.json",
        {
            "schema": "quwoquan_data.environment_release_run",
            "environment": environment,
            "releaseId": release_id,
            "runId": run_id,
            "kind": kind,
            "startedAt": datetime.now(timezone.utc).isoformat(),
        },
        "environment_release_run",
    )
    return run


def write_applied_ref(
    *,
    output_root: Path,
    run: Path,
    environment: str,
    release_id: str,
    release_ref: str,
) -> None:
    write_release_evidence(
        run / "applied_ref.json",
        {
            "schema": "quwoquan_data.applied_release_ref",
            "environment": environment,
            "releaseId": release_id,
            "releaseRef": release_ref,
            "evidenceRef": run.relative_to(output_root).as_posix(),
        },
        "applied_release_ref",
    )
