#!/usr/bin/env python3
"""Append-only hosted authority for canonical CI timing evidence."""

from __future__ import annotations

import argparse
import base64
import contextlib
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping


AUTHORITY = "prod-hosted-ci-timing"
CANONICAL_SCHEMA = "ci-timing-summary"
AUTHORITY_MARKER = ".authority"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_ID_RE = re.compile(r"^[1-9][0-9]{0,19}$")
EXACT_OCI_REF_RE = re.compile(
    r"^ghcr\.io/[a-z0-9._/-]+/ci-timing-summary@(?P<digest>sha256:[0-9a-f]{64})$"
)
SUMMARY_KEYS = frozenset(
    {
        "schema",
        "generatedAt",
        "workflow",
        "workflowRunId",
        "sourceGitSha",
        "candidateDigest",
        "status",
        "timestamps",
        "durations",
        "budget",
        "criticalPath",
        "phases",
        "missingEvidence",
        "notes",
    }
)
RECORD_KEYS = frozenset(
    {
        "authority",
        "recordDigest",
        "candidateDigest",
        "workflowRunId",
        "sourceGitSha",
        "timingEvidenceRef",
        "timingEvidenceDigest",
        "timingSummaryDigest",
        "timingSummary",
    }
)
STATUS_VALUES = frozenset(
    {
        "within_budget",
        "released_over_soft_budget",
        "failed",
        "historical_incomplete",
    }
)
MAX_SUMMARY_BYTES = 1024 * 1024


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _forbidden_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z]", "", key.lower())
    return normalized in {
        "schema" + "version",
        "contract" + "version",
        "registry" + "revision",
        "version" + "s",
    }


def _reject_forbidden_fields(value: object, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str) or _forbidden_key(key):
                raise ValueError(f"forbidden timing field at {path}: {key!r}")
            _reject_forbidden_fields(nested, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_forbidden_fields(nested, path=f"{path}[{index}]")


def _require_timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return value


def validate_summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SUMMARY_KEYS:
        raise ValueError("CiTimingSummary has a non-canonical shape")
    _reject_forbidden_fields(value)
    if value.get("schema") != CANONICAL_SCHEMA:
        raise ValueError("CiTimingSummary schema is not canonical")
    _require_timestamp(value.get("generatedAt"), field="generatedAt")
    run_id = str(value.get("workflowRunId") or "")
    if RUN_ID_RE.fullmatch(run_id) is None:
        raise ValueError("workflowRunId is invalid")
    source_sha = str(value.get("sourceGitSha") or "")
    if GIT_SHA_RE.fullmatch(source_sha) is None:
        raise ValueError("sourceGitSha is invalid")
    candidate = str(value.get("candidateDigest") or "")
    if SHA256_RE.fullmatch(candidate) is None:
        raise ValueError("candidateDigest must be sha256")
    if value.get("status") not in STATUS_VALUES:
        raise ValueError("CiTimingSummary status is invalid")
    if not isinstance(value.get("workflow"), dict):
        raise ValueError("workflow must be an object")
    for field in ("timestamps", "durations", "budget", "criticalPath"):
        if not isinstance(value.get(field), dict):
            raise ValueError(f"{field} must be an object")
    if not isinstance(value.get("phases"), list):
        raise ValueError("phases must be an array")
    for field in ("missingEvidence", "notes"):
        items = value.get(field)
        if not isinstance(items, list) or not all(
            isinstance(item, str) and item.strip() for item in items
        ):
            raise ValueError(f"{field} must contain non-empty strings")
    return dict(value)


def _read_summary(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("CiTimingSummary file is missing or unsafe")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_SUMMARY_BYTES:
        raise ValueError("CiTimingSummary file size is invalid")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("CiTimingSummary is not valid UTF-8 JSON") from error
    return validate_summary(value), raw


def _validate_exact_oci(ref: str, digest: str) -> None:
    match = EXACT_OCI_REF_RE.fullmatch(ref)
    if match is None:
        raise ValueError("timing evidence ref must be an exact GHCR OCI digest ref")
    if SHA256_RE.fullmatch(digest) is None or match.group("digest") != digest:
        raise ValueError("timing evidence ref and digest do not match")


def build_record(
    summary: Mapping[str, Any], raw_summary: bytes, evidence_ref: str, evidence_digest: str
) -> dict[str, Any]:
    canonical = validate_summary(dict(summary))
    if not raw_summary or len(raw_summary) > MAX_SUMMARY_BYTES:
        raise ValueError("CiTimingSummary source bytes are invalid")
    try:
        decoded_summary = json.loads(raw_summary.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("CiTimingSummary source bytes are not valid JSON") from error
    if decoded_summary != canonical:
        raise ValueError("CiTimingSummary source bytes do not match the bound summary")
    _validate_exact_oci(evidence_ref, evidence_digest)
    record: dict[str, Any] = {
        "authority": AUTHORITY,
        "candidateDigest": canonical["candidateDigest"],
        "workflowRunId": canonical["workflowRunId"],
        "sourceGitSha": canonical["sourceGitSha"],
        "timingEvidenceRef": evidence_ref,
        "timingEvidenceDigest": evidence_digest,
        "timingSummaryDigest": _sha256(raw_summary),
        "timingSummary": canonical,
    }
    record["recordDigest"] = _sha256(_canonical_bytes(record))
    return record


def _require_authority(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("hosted timing authority is missing")
    marker = root / AUTHORITY_MARKER
    if marker.is_symlink() or not marker.is_file():
        raise RuntimeError("hosted timing authority marker is missing")
    if marker.read_text(encoding="utf-8") != AUTHORITY + "\n":
        raise RuntimeError("hosted timing authority marker is invalid")


def initialize(root: Path) -> dict[str, str]:
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise RuntimeError("hosted timing authority root is unsafe")
    root.mkdir(parents=True, exist_ok=True)
    marker = root / AUTHORITY_MARKER
    expected = (AUTHORITY + "\n").encode("utf-8")
    if marker.exists():
        if marker.is_symlink() or not marker.is_file() or marker.read_bytes() != expected:
            raise RuntimeError("hosted timing authority marker conflicts")
    else:
        with marker.open("xb") as handle:
            handle.write(expected)
            handle.flush()
            os.fsync(handle.fileno())
    return {"authority": AUTHORITY, "root": str(root)}


@contextlib.contextmanager
def _authority_lock(root: Path) -> Any:
    _require_authority(root)
    lock_path = root / ".timing.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            _require_authority(root)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_exclusive(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _index_path(root: Path, candidate_digest: str, workflow_run_id: str) -> Path:
    if SHA256_RE.fullmatch(candidate_digest) is None:
        raise ValueError("candidate digest is invalid")
    if RUN_ID_RE.fullmatch(workflow_run_id) is None:
        raise ValueError("workflow run id is invalid")
    return root / "by-run" / workflow_run_id / f"{candidate_digest.removeprefix('sha256:')}.ref"


def validate_record(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != RECORD_KEYS:
        raise RuntimeError("hosted timing record shape is invalid")
    unsigned = dict(value)
    record_digest = unsigned.pop("recordDigest", None)
    if (
        not isinstance(record_digest, str)
        or SHA256_RE.fullmatch(record_digest) is None
        or _sha256(_canonical_bytes(unsigned)) != record_digest
    ):
        raise RuntimeError("hosted timing record digest is invalid")
    if value.get("authority") != AUTHORITY:
        raise RuntimeError("hosted timing record authority is invalid")
    summary = validate_summary(value.get("timingSummary"))
    _validate_exact_oci(
        str(value.get("timingEvidenceRef") or ""),
        str(value.get("timingEvidenceDigest") or ""),
    )
    for field in ("candidateDigest", "workflowRunId", "sourceGitSha"):
        if value.get(field) != summary.get(field):
            raise RuntimeError(f"hosted timing record {field} binding is invalid")
    if SHA256_RE.fullmatch(str(value.get("timingSummaryDigest") or "")) is None:
        raise RuntimeError("hosted timing summary digest is invalid")
    return dict(value)


def _load_record(root: Path, record_digest: str) -> dict[str, Any]:
    if SHA256_RE.fullmatch(record_digest) is None:
        raise RuntimeError("hosted timing record digest is invalid")
    record_path = root / "records" / f"{record_digest.removeprefix('sha256:')}.json"
    if record_path.is_symlink() or not record_path.is_file():
        raise RuntimeError("hosted timing record is missing")
    try:
        value = json.loads(record_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError("hosted timing record is malformed") from error
    validated = validate_record(value)
    if validated["recordDigest"] != record_digest:
        raise RuntimeError("hosted timing record filename binding is invalid")
    return validated


def bind(root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    supplied = validate_record(dict(record))
    record_digest = str(supplied.get("recordDigest") or "")
    candidate = str(supplied.get("candidateDigest") or "")
    run_id = str(supplied.get("workflowRunId") or "")
    record_bytes = json.dumps(
        supplied, ensure_ascii=False, indent=2, sort_keys=True
    ).encode("utf-8") + b"\n"
    with _authority_lock(root):
        index_path = _index_path(root, candidate, run_id)
        if index_path.exists():
            if index_path.is_symlink() or not index_path.is_file():
                raise RuntimeError("hosted timing index is unsafe")
            existing_digest = index_path.read_text(encoding="utf-8").strip()
            existing = _load_record(root, existing_digest)
            if existing != supplied:
                raise RuntimeError("hosted timing append-only binding conflicts")
            return existing
        record_path = root / "records" / f"{record_digest.removeprefix('sha256:')}.json"
        if record_path.exists():
            if record_path.is_symlink() or record_path.read_bytes() != record_bytes:
                raise RuntimeError("hosted timing record collision")
        else:
            _write_exclusive(record_path, record_bytes)
        _write_exclusive(index_path, (record_digest + "\n").encode("utf-8"))
        return _load_record(root, record_digest)


def query(root: Path, candidate_digest: str, workflow_run_id: str) -> dict[str, Any]:
    with _authority_lock(root):
        index_path = _index_path(root, candidate_digest, workflow_run_id)
        if index_path.is_symlink() or not index_path.is_file():
            raise RuntimeError("hosted timing index entry is missing")
        record = _load_record(root, index_path.read_text(encoding="utf-8").strip())
        if (
            record.get("candidateDigest") != candidate_digest
            or record.get("workflowRunId") != workflow_run_id
        ):
            raise RuntimeError("hosted timing index binding is invalid")
        return record


def _request_record(encoded: str) -> dict[str, Any]:
    try:
        request = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("hosted timing bind request is invalid") from error
    if not isinstance(request, dict) or set(request) != {
        "summaryBase64",
        "timingEvidenceRef",
        "timingEvidenceDigest",
    }:
        raise ValueError("hosted timing bind request shape is invalid")
    try:
        raw_summary = base64.b64decode(request["summaryBase64"], validate=True)
        summary = json.loads(raw_summary.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("hosted timing bind summary is invalid") from error
    if not raw_summary or len(raw_summary) > MAX_SUMMARY_BYTES:
        raise ValueError("hosted timing bind summary size is invalid")
    return build_record(
        validate_summary(summary),
        raw_summary,
        str(request["timingEvidenceRef"]),
        str(request["timingEvidenceDigest"]),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--action", choices=("initialize", "bind", "query"), required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--timing-evidence-ref", default="")
    parser.add_argument("--timing-evidence-digest", default="")
    parser.add_argument("--request-base64", default="")
    parser.add_argument("--candidate-digest", default="")
    parser.add_argument("--workflow-run-id", default="")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        root = args.root.expanduser()
        if not root.is_absolute():
            raise ValueError("hosted timing authority root must be absolute")
        if args.action == "initialize":
            result: object = initialize(root)
        elif args.action == "query":
            result = query(root, args.candidate_digest, args.workflow_run_id)
        else:
            if args.request_base64:
                record = _request_record(args.request_base64)
            elif args.summary is not None:
                summary, raw = _read_summary(args.summary)
                record = build_record(
                    summary,
                    raw,
                    args.timing_evidence_ref,
                    args.timing_evidence_digest,
                )
            else:
                raise ValueError("hosted timing bind requires a canonical summary")
            result = bind(root, record)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
