#!/usr/bin/env python3
"""Append-only hosted authority for promotion samples and diagnostic summaries."""
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

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci import promotion_timing_ratchet as ratchet

AUTHORITY = "prod-hosted-promotion-timing"
DIAGNOSTIC_SCHEMA = "ci-timing-summary"
AUTHORITY_MARKER = ".authority"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_ID_RE = re.compile(r"^[1-9][0-9]{0,19}$")
EXACT_OCI_REF_RE = re.compile(
    r"^ghcr\.io/[a-z0-9._/-]+/(?P<artifact>ci-timing-summary|promotion-timing-sample)@(?P<digest>sha256:[0-9a-f]{64})$"
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
        "outcomePolicy",
        "timestamps",
        "durations",
        "budget",
        "criticalPath",
        "phases",
        "missingEvidence",
        "notes",
    }
)
DIAGNOSTIC_RECORD_KEYS = frozenset(
    {
        "authority",
        "recordKind",
        "recordDigest",
        "candidateDigest",
        "workflowRunId",
        "sourceGitSha",
        "evidenceRef",
        "evidenceDigest",
        "payloadDigest",
        "payload",
    }
)
SAMPLE_RECORD_KEYS = frozenset(
    {
        "authority",
        "recordKind",
        "recordDigest",
        "observationId",
        "eventId",
        "repository",
        "workflowRunId",
        "runAttempt",
        "policyEpoch",
        "evidenceRef",
        "evidenceDigest",
        "payloadDigest",
        "payload",
    }
)
STATUS_VALUES = frozenset(
    {"within_budget", "released_over_soft_budget", "failed", "historical_incomplete"}
)
MAX_PAYLOAD_BYTES = 1024 * 1024


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
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
    """Validate the generic per-run diagnostic; it is not ratchet authority."""
    if not isinstance(value, dict) or set(value) != SUMMARY_KEYS:
        raise ValueError("CiTimingSummary has a non-canonical diagnostic shape")
    _reject_forbidden_fields(value)
    if value.get("schema") != DIAGNOSTIC_SCHEMA:
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
    for field in ("outcomePolicy", "timestamps", "durations", "budget", "criticalPath"):
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


def validate_promotion_sample(value: object) -> dict[str, Any]:
    return ratchet.validate_sample(value)


def _read_json(path: Path) -> tuple[object, bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("timing evidence file is missing or unsafe")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError("timing evidence file size is invalid")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("timing evidence is not valid UTF-8 JSON") from error
    return value, raw


def _read_summary(path: Path) -> tuple[dict[str, Any], bytes]:
    value, raw = _read_json(path)
    return validate_summary(value), raw


def _read_sample(path: Path) -> tuple[dict[str, Any], bytes]:
    value, raw = _read_json(path)
    return validate_promotion_sample(value), raw


def _validate_exact_oci(ref: str, digest: str, *, artifact: str | None = None) -> None:
    match = EXACT_OCI_REF_RE.fullmatch(ref)
    if match is None:
        raise ValueError("timing evidence ref must be an exact GHCR OCI digest ref")
    if artifact is not None and match.group("artifact") != artifact:
        raise ValueError("timing evidence OCI artifact kind is invalid")
    if SHA256_RE.fullmatch(digest) is None or match.group("digest") != digest:
        raise ValueError("timing evidence ref and digest do not match")


def _build_record(
    *,
    record_kind: str,
    payload: Mapping[str, Any],
    raw_payload: bytes,
    evidence_ref: str,
    evidence_digest: str,
) -> dict[str, Any]:
    if not raw_payload or len(raw_payload) > MAX_PAYLOAD_BYTES:
        raise ValueError("timing evidence source bytes are invalid")
    try:
        decoded = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("timing evidence source bytes are not valid JSON") from error
    if decoded != dict(payload):
        raise ValueError("timing evidence source bytes do not match the bound payload")
    artifact = "promotion-timing-sample" if record_kind == "promotion_sample" else "ci-timing-summary"
    _validate_exact_oci(evidence_ref, evidence_digest, artifact=artifact)
    common: dict[str, Any] = {
        "authority": AUTHORITY,
        "recordKind": record_kind,
        "evidenceRef": evidence_ref,
        "evidenceDigest": evidence_digest,
        "payloadDigest": _sha256(raw_payload),
        "payload": dict(payload),
    }
    if record_kind == "promotion_sample":
        common.update(
            {
                "observationId": payload["observationId"],
                "eventId": payload["eventId"],
                "repository": payload["repository"],
                "workflowRunId": payload["workflowRunId"],
                "runAttempt": payload["runAttempt"],
                "policyEpoch": payload["policyEpoch"],
            }
        )
    else:
        common.update(
            {
                "candidateDigest": payload["candidateDigest"],
                "workflowRunId": payload["workflowRunId"],
                "sourceGitSha": payload["sourceGitSha"],
            }
        )
    common["recordDigest"] = _sha256(_canonical_bytes(common))
    return common


def build_record(
    summary: Mapping[str, Any], raw_summary: bytes, evidence_ref: str, evidence_digest: str
) -> dict[str, Any]:
    """Compatibility name for the diagnostic-only CiTimingSummary record builder."""
    canonical = validate_summary(dict(summary))
    return _build_record(
        record_kind="diagnostic_summary",
        payload=canonical,
        raw_payload=raw_summary,
        evidence_ref=evidence_ref,
        evidence_digest=evidence_digest,
    )


def build_sample_record(
    sample: Mapping[str, Any], raw_sample: bytes, evidence_ref: str, evidence_digest: str
) -> dict[str, Any]:
    canonical = validate_promotion_sample(dict(sample))
    return _build_record(
        record_kind="promotion_sample",
        payload=canonical,
        raw_payload=raw_sample,
        evidence_ref=evidence_ref,
        evidence_digest=evidence_digest,
    )


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


def _safe_identity(value: str, field: str) -> str:
    if not value or len(value) > 512 or "/" in value or "\\" in value or value in {".", ".."}:
        raise ValueError(f"{field} is invalid")
    return value


def _diagnostic_index_path(root: Path, candidate_digest: str, workflow_run_id: str) -> Path:
    if SHA256_RE.fullmatch(candidate_digest) is None:
        raise ValueError("candidate digest is invalid")
    if RUN_ID_RE.fullmatch(workflow_run_id) is None:
        raise ValueError("workflow run id is invalid")
    return root / "diagnostics" / "by-run" / workflow_run_id / f"{candidate_digest.removeprefix('sha256:')}.ref"


def _sample_index_path(root: Path, observation_id: str) -> Path:
    encoded = hashlib.sha256(observation_id.encode("utf-8")).hexdigest()
    return root / "samples" / "by-observation" / f"{encoded}.ref"


def _event_index_path(root: Path, event_id: str, observation_id: str) -> Path:
    event = hashlib.sha256(event_id.encode("utf-8")).hexdigest()
    observation = hashlib.sha256(observation_id.encode("utf-8")).hexdigest()
    return root / "samples" / "by-event" / event / f"{observation}.ref"


def _validate_record_fields(value: Mapping[str, Any], expected_keys: frozenset[str]) -> None:
    if set(value) != expected_keys:
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
    if SHA256_RE.fullmatch(str(value.get("payloadDigest") or "")) is None:
        raise RuntimeError("hosted timing payload digest is invalid")


def validate_record(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError("hosted timing record shape is invalid")
    kind = value.get("recordKind")
    if kind == "promotion_sample":
        _validate_record_fields(value, SAMPLE_RECORD_KEYS)
        payload = validate_promotion_sample(value.get("payload"))
        _validate_exact_oci(
            str(value.get("evidenceRef") or ""),
            str(value.get("evidenceDigest") or ""),
            artifact="promotion-timing-sample",
        )
        for field in (
            "observationId",
            "eventId",
            "repository",
            "workflowRunId",
            "runAttempt",
            "policyEpoch",
        ):
            if value.get(field) != payload.get(field):
                raise RuntimeError(f"hosted timing record {field} binding is invalid")
    elif kind == "diagnostic_summary":
        _validate_record_fields(value, DIAGNOSTIC_RECORD_KEYS)
        payload = validate_summary(value.get("payload"))
        _validate_exact_oci(
            str(value.get("evidenceRef") or ""),
            str(value.get("evidenceDigest") or ""),
            artifact="ci-timing-summary",
        )
        for field in ("candidateDigest", "workflowRunId", "sourceGitSha"):
            if value.get(field) != payload.get(field):
                raise RuntimeError(f"hosted timing record {field} binding is invalid")
    else:
        raise RuntimeError("hosted timing record kind is invalid")
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


def _bind_paths(root: Path, supplied: Mapping[str, Any]) -> list[Path]:
    if supplied["recordKind"] == "promotion_sample":
        return [
            _sample_index_path(root, str(supplied["observationId"])),
            _event_index_path(
                root, str(supplied["eventId"]), str(supplied["observationId"])
            ),
        ]
    return [
        _diagnostic_index_path(
            root, str(supplied["candidateDigest"]), str(supplied["workflowRunId"])
        )
    ]


def bind(root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    supplied = validate_record(dict(record))
    record_digest = str(supplied["recordDigest"])
    record_bytes = json.dumps(
        supplied, ensure_ascii=False, indent=2, sort_keys=True
    ).encode("utf-8") + b"\n"
    with _authority_lock(root):
        indexes = _bind_paths(root, supplied)
        for index_path in indexes:
            if index_path.exists():
                if index_path.is_symlink() or not index_path.is_file():
                    raise RuntimeError("hosted timing index is unsafe")
                existing = _load_record(root, index_path.read_text(encoding="utf-8").strip())
                if existing != supplied:
                    raise RuntimeError("hosted timing append-only binding conflicts")
        record_path = root / "records" / f"{record_digest.removeprefix('sha256:')}.json"
        if record_path.exists():
            if record_path.is_symlink() or record_path.read_bytes() != record_bytes:
                raise RuntimeError("hosted timing record collision")
        else:
            _write_exclusive(record_path, record_bytes)
        for index_path in indexes:
            if not index_path.exists():
                _write_exclusive(index_path, (record_digest + "\n").encode("utf-8"))
        return _load_record(root, record_digest)


def query(root: Path, candidate_digest: str, workflow_run_id: str) -> dict[str, Any]:
    """Query a diagnostic summary; diagnostic records never drive the ratchet."""
    with _authority_lock(root):
        index_path = _diagnostic_index_path(root, candidate_digest, workflow_run_id)
        if index_path.is_symlink() or not index_path.is_file():
            raise RuntimeError("hosted timing diagnostic index entry is missing")
        record = _load_record(root, index_path.read_text(encoding="utf-8").strip())
        if record.get("recordKind") != "diagnostic_summary":
            raise RuntimeError("hosted timing diagnostic index binding is invalid")
        return record


def query_sample(root: Path, observation_id: str) -> dict[str, Any]:
    with _authority_lock(root):
        index_path = _sample_index_path(root, observation_id)
        if index_path.is_symlink() or not index_path.is_file():
            raise RuntimeError("hosted promotion timing sample is missing")
        record = _load_record(root, index_path.read_text(encoding="utf-8").strip())
        if record.get("observationId") != observation_id:
            raise RuntimeError("hosted promotion timing sample index binding is invalid")
        return record


def query_event(root: Path, event_id: str) -> dict[str, Any]:
    with _authority_lock(root):
        event_hash = hashlib.sha256(event_id.encode("utf-8")).hexdigest()
        event_root = root / "samples" / "by-event" / event_hash
        records: list[dict[str, Any]] = []
        if event_root.exists():
            if event_root.is_symlink() or not event_root.is_dir():
                raise RuntimeError("hosted promotion timing event index is unsafe")
            for child in event_root.iterdir():
                if child.is_symlink() or not child.is_file() or child.suffix != ".ref":
                    raise RuntimeError("hosted promotion timing event index is unsafe")
            for index_path in sorted(event_root.glob("*.ref")):
                if index_path.is_symlink() or not index_path.is_file():
                    raise RuntimeError("hosted promotion timing event index is unsafe")
                record = _load_record(root, index_path.read_text(encoding="utf-8").strip())
                if record.get("eventId") != event_id:
                    raise RuntimeError("hosted promotion timing event binding is invalid")
                records.append(record)
        return {"authority": AUTHORITY, "eventId": event_id, "records": records}


def query_range(root: Path, start_at: str, end_at: str) -> dict[str, Any]:
    start = ratchet.parse_time(start_at, "startAt")
    end = ratchet.parse_time(end_at, "endAt")
    if end <= start:
        raise ValueError("query range must be a non-empty [start, end) interval")
    with _authority_lock(root):
        samples: list[dict[str, Any]] = []
        records_root = root / "records"
        if records_root.exists():
            if records_root.is_symlink() or not records_root.is_dir():
                raise RuntimeError("hosted timing records root is unsafe")
            for child in records_root.iterdir():
                if child.is_symlink() or not child.is_file() or child.suffix != ".json":
                    raise RuntimeError("hosted timing records root is unsafe")
            for record_path in sorted(records_root.glob("*.json")):
                record = _load_record(root, "sha256:" + record_path.stem)
                if record["recordKind"] != "promotion_sample":
                    continue
                sample = record["payload"]
                ready = ratchet.parse_time(sample["promotionReadyAt"], "promotionReadyAt")
                if start <= ready < end:
                    samples.append(sample)
        samples.sort(key=lambda item: (item["promotionReadyAt"], item["eventId"], item["observationId"]))
        return {
            "authority": AUTHORITY,
            "startAt": ratchet.format_time(start),
            "endAt": ratchet.format_time(end),
            "samples": samples,
        }


def _request_record(encoded: str) -> dict[str, Any]:
    try:
        request = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("hosted timing bind request is invalid") from error
    if not isinstance(request, dict) or set(request) != {
        "recordKind",
        "payloadBase64",
        "evidenceRef",
        "evidenceDigest",
    }:
        raise ValueError("hosted timing bind request shape is invalid")
    try:
        raw_payload = base64.b64decode(request["payloadBase64"], validate=True)
        payload = json.loads(raw_payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("hosted timing bind payload is invalid") from error
    if request["recordKind"] == "promotion_sample":
        return build_sample_record(
            validate_promotion_sample(payload),
            raw_payload,
            str(request["evidenceRef"]),
            str(request["evidenceDigest"]),
        )
    if request["recordKind"] == "diagnostic_summary":
        return build_record(
            validate_summary(payload),
            raw_payload,
            str(request["evidenceRef"]),
            str(request["evidenceDigest"]),
        )
    raise ValueError("hosted timing bind record kind is invalid")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument(
        "--action",
        choices=(
            "initialize",
            "bind",
            "query",
            "query-sample",
            "query-event",
            "query-range",
        ),
        required=True,
    )
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--evidence-ref", default="")
    parser.add_argument("--evidence-digest", default="")
    parser.add_argument("--timing-evidence-ref", default="")
    parser.add_argument("--timing-evidence-digest", default="")
    parser.add_argument("--request-base64", default="")
    parser.add_argument("--candidate-digest", default="")
    parser.add_argument("--workflow-run-id", default="")
    parser.add_argument("--observation-id", default="")
    parser.add_argument("--event-id", default="")
    parser.add_argument("--start-at", default="")
    parser.add_argument("--end-at", default="")
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
        elif args.action == "query-sample":
            result = query_sample(root, args.observation_id)
        elif args.action == "query-event":
            result = query_event(root, args.event_id)
        elif args.action == "query-range":
            result = query_range(root, args.start_at, args.end_at)
        else:
            if args.request_base64:
                record = _request_record(args.request_base64)
            elif args.sample is not None:
                sample, raw = _read_sample(args.sample)
                record = build_sample_record(
                    sample,
                    raw,
                    args.evidence_ref or args.timing_evidence_ref,
                    args.evidence_digest or args.timing_evidence_digest,
                )
            elif args.summary is not None:
                summary, raw = _read_summary(args.summary)
                record = build_record(
                    summary,
                    raw,
                    args.evidence_ref or args.timing_evidence_ref,
                    args.evidence_digest or args.timing_evidence_digest,
                )
            else:
                raise ValueError("hosted timing bind requires a promotion sample or diagnostic summary")
            result = bind(root, record)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
