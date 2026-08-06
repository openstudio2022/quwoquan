"""Shared frozen-input contracts for canonical campaign scale evidence."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.execution.identity import parse_execution_id
from content.release.canonical.object_transaction_contract import _read_json
from core.schema import assert_valid

CARRIERS = ("homepage", "article", "image", "video")
MIN_SOAK_SECONDS = 60 * 60
MIN_SOAK_SAMPLES = 61
MAX_SAMPLE_GAP_SECONDS = 90
MIN_SEMANTIC_JOBS_PER_LANE = 10
MIN_RECOVERY_CASES = 20
MIN_RECOVERY_CASES_PER_LANE = 5
MIN_AUTOMATIC_RECOVERED = 19
MIN_AUTOMATIC_RECOVERY_RATE = 0.95

# Canonical scale budgets are code-owned until a governed policy field exists.
# They cannot be inflated by the raw sample producer.
MAX_CONTROLLER_P95_RSS_BYTES = 512 * 1024**2
MAX_NON_VIDEO_WORKER_P95_RSS_BYTES = 1024**3
MAX_VIDEO_WORKER_P95_RSS_BYTES = 2 * 1024**3
MAX_TOTAL_P95_RSS_BYTES = 8 * 1024**3
MAX_TOTAL_RSS_BYTES = 10 * 1024**3
TEMPORARY_WORKSPACE_FIXED_ALLOWANCE_BYTES = 2 * 1024**3
MAX_TERMINAL_RESIDUAL_BYTES = 100 * 1024**2
MAX_OPEN_FD_COUNT = 2048
MAX_QUEUE_DEPTH = 4096
MAX_OLDEST_READY_AGE_SECONDS = 10 * 60
MAX_PROGRESS_AGE_SECONDS = 15 * 60
MAX_HEARTBEAT_AGE_SECONDS = 30 * 60

_FAULT_EVENTS = {
    "worker_termination": {"reclaimed"},
    "lease_expiry": {"reclaimed"},
    "redis_restart": {"failed", "reclaimed"},
    "mongo_reconnect": {"failed"},
    "provider_timeout": {"failed"},
    "provider_rate_limit": {"failed"},
}
_TERMINAL_TIMING_EVENTS = {"blocked", "failed", "reclaimed", "succeeded"}


class CampaignScaleEvidenceError(RuntimeError):
    """A frozen evidence input is missing, malformed, or identity-drifted."""


def _canonical_digest(value: Mapping[str, Any], *, excluded: str | None = None) -> str:
    payload = dict(value)
    if excluded is not None:
        payload.pop(excluded, None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _timestamp(value: object, *, label: str) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CampaignScaleEvidenceError(f"{label} must be RFC3339 date-time") from exc
    if parsed.tzinfo is None:
        raise CampaignScaleEvidenceError(f"{label} must include timezone")
    return parsed.astimezone(timezone.utc)


def _safe_ref(path: Path, *, output_root: Path, label: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise CampaignScaleEvidenceError(f"{label} must be one regular audited file: {path}")
    try:
        return path.resolve().relative_to(output_root.resolve()).as_posix()
    except ValueError as exc:
        raise CampaignScaleEvidenceError(
            f"{label} must be below QWQ_OUTPUT_ROOT: {path}"
        ) from exc


def _resolve_ref(ref: str, *, output_root: Path, label: str) -> Path:
    raw = Path(str(ref or "").strip())
    if raw.is_absolute() or not raw.parts or ".." in raw.parts:
        raise CampaignScaleEvidenceError(f"{label} is unsafe: {ref}")
    path = output_root / raw
    _safe_ref(path, output_root=output_root, label=label)
    return path


def _validated(path: Path, *schema: str, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CampaignScaleEvidenceError(f"{label} is missing: {path}")
    payload = _read_json(path)
    try:
        assert_valid(payload, *schema, label=label)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise CampaignScaleEvidenceError(str(exc)) from exc
    return payload


def _verify_evidence_digest(payload: Mapping[str, Any], *, label: str) -> str:
    actual = _canonical_digest(payload, excluded="evidenceDigest")
    if payload.get("evidenceDigest") != actual:
        raise CampaignScaleEvidenceError(f"{label} evidenceDigest drift")
    return actual


def _write_create_once(
    *,
    path: Path,
    stable: Mapping[str, Any],
    schema_name: str,
) -> tuple[dict[str, Any], Path]:
    def load_existing() -> dict[str, Any]:
        existing = _validated(
            path,
            "release",
            schema_name,
            label=f"create-once {schema_name}",
        )
        _verify_evidence_digest(existing, label=schema_name)
        if any(existing.get(key) != value for key, value in stable.items()):
            raise CampaignScaleEvidenceError(f"create-once {schema_name} collision: {path}")
        return existing

    if path.exists() or path.is_symlink():
        return load_existing(), path
    document = {
        **dict(stable),
        "recordedAt": datetime.now(timezone.utc).isoformat(),
    }
    document["evidenceDigest"] = _canonical_digest(
        document,
        excluded="evidenceDigest",
    )
    try:
        assert_valid(
            document,
            "release",
            schema_name,
            label=f"canonical {schema_name}",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise CampaignScaleEvidenceError(str(exc)) from exc
    encoded = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return load_existing(), path
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return document, path
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def _load_plan(path: Path) -> dict[str, Any]:
    plan = _validated(
        path,
        "execution",
        "content_campaign_plan",
        label="campaign scale plan",
    )
    digest = _canonical_digest(plan, excluded="planDigest")
    if plan.get("planDigest") != digest:
        raise CampaignScaleEvidenceError("campaign planDigest drift")
    execution_ids = plan.get("executionIds")
    if not isinstance(execution_ids, Mapping) or set(execution_ids) != set(CARRIERS):
        raise CampaignScaleEvidenceError("campaign plan must own exactly four lanes")
    lane_inputs = plan.get("laneExternalInputs")
    if not isinstance(lane_inputs, Mapping) or set(lane_inputs) != set(CARRIERS):
        raise CampaignScaleEvidenceError("campaign external input lanes are incomplete")
    for carrier in CARRIERS:
        row = lane_inputs[carrier]
        if not isinstance(row, Mapping):
            raise CampaignScaleEvidenceError(f"{carrier} external input row is invalid")
        refs = row.get("externalInputRefs")
        if not isinstance(refs, list):
            raise CampaignScaleEvidenceError(f"{carrier} external input refs are invalid")
        expected_digest = _canonical_digest(
            {
                "schema": "quwoquan_data.campaign_external_input_set",
                "refs": refs,
            }
        )
        if (
            row.get("executionId") != execution_ids[carrier]
            or row.get("externalInputsDigest") != expected_digest
            or any(
                not isinstance(ref, Mapping)
                or ref.get("carrier") != carrier
                or ref.get("sourceRevision") != plan.get("sourceRevision")
                or ref.get("sourceDigest") != plan.get("sourceDigest")
                or ref.get("entityCatalogDigest") != plan.get("entityCatalogDigest")
                for ref in refs
            )
        ):
            raise CampaignScaleEvidenceError(f"{carrier} external input binding drift")
    aggregate_digest = _canonical_digest(
        {
            "schema": "quwoquan_data.campaign_external_input_lanes",
            "lanes": lane_inputs,
        }
    )
    if plan.get("externalInputsDigest") != aggregate_digest:
        raise CampaignScaleEvidenceError("campaign externalInputsDigest drift")
    return plan


def campaign_source_revision(plan: Mapping[str, Any]) -> str:
    """Read the content-addressed revision frozen by all campaign submissions."""

    source_revision = str(plan.get("sourceRevision") or "")
    expected = _canonical_digest(
        {
            "schema": "quwoquan_data.campaign_content_source_revision",
            "sourceDigest": plan.get("sourceDigest"),
            "entityCatalogDigest": plan.get("entityCatalogDigest"),
        }
    )
    if source_revision != expected:
        raise CampaignScaleEvidenceError("campaign plan sourceRevision drift")
    return source_revision


def _assert_input_identity(
    payload: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    source_revision: str,
    label: str,
) -> None:
    expected = {
        "rootExecutionId": plan["rootExecutionId"],
        "sourceRevision": source_revision,
        "sourceDigest": plan["sourceDigest"],
        "entityCatalogDigest": plan["entityCatalogDigest"],
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise CampaignScaleEvidenceError(f"{label} campaign source identity drift")


def _target_set_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _execution_chain(
    *,
    execution_id: str,
    carrier: str,
    plan: Mapping[str, Any],
    tasks_root: Path,
) -> list[str]:
    chain: list[str] = []
    current = execution_id
    while current:
        if current in chain:
            raise CampaignScaleEvidenceError(f"{carrier} retryOf cycle: {current}")
        identity = parse_execution_id(current)
        if identity.content_type.value != carrier:
            raise CampaignScaleEvidenceError(f"{carrier} retry chain carrier drift: {current}")
        root = tasks_root / current
        manifest = _validated(
            root / "execution_manifest.json",
            "execution",
            "content_execution_manifest",
            label=f"execution manifest:{current}",
        )
        target_set = _validated(
            root / "0.plan/target_set.json",
            "execution",
            "target_set",
            label=f"target set:{current}",
        )
        source = manifest.get("sourceDigest")
        if (
            manifest.get("executionId") != current
            or not isinstance(source, Mapping)
            or source.get("digest") != plan.get("sourceDigest")
            or target_set.get("executionId") != current
            or target_set.get("entityCatalogDigest") != plan.get("entityCatalogDigest")
            or manifest.get("targetSetDigest") != _target_set_digest(target_set)
        ):
            raise CampaignScaleEvidenceError(f"{carrier} retry chain frozen input drift: {current}")
        chain.append(current)
        current = str(manifest.get("retryOf") or "").strip()
    return chain


def _job_timings(job: Mapping[str, Any], *, label: str) -> list[tuple[str, datetime]]:
    raw_rows = job.get("timings")
    if not isinstance(raw_rows, list):
        raise CampaignScaleEvidenceError(f"{label} timings must be an array")
    rows: list[tuple[str, datetime]] = []
    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, Mapping):
            raise CampaignScaleEvidenceError(f"{label} timing[{index}] is invalid")
        rows.append(
            (
                str(raw.get("event") or ""),
                _timestamp(raw.get("at"), label=f"{label}.timings[{index}].at"),
            )
        )
    if any(rows[index][1] < rows[index - 1][1] for index in range(1, len(rows))):
        raise CampaignScaleEvidenceError(f"{label} timings are not monotonic")
    return rows


def _semantic_jobs(
    *,
    plan: Mapping[str, Any],
    tasks_root: Path,
) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {carrier: {} for carrier in CARRIERS}
    for carrier in CARRIERS:
        execution_id = str(plan["executionIds"][carrier])
        queue_root = tasks_root / execution_id / "_shared/object_queue"
        if not queue_root.is_dir():
            raise CampaignScaleEvidenceError(f"{carrier} ReliableTask queue is missing")
        for path in sorted(queue_root.glob("*.json")):
            if path.name.startswith("_"):
                continue
            job = _validated(path, "content", "object_job", label=f"semantic job:{path.name}")
            reliable = job.get("reliableTaskRef")
            payload = reliable.get("payload") if isinstance(reliable, Mapping) else None
            if (
                job.get("executionId") != execution_id
                or job.get("stage") != "author"
                or job.get("queueBackend") != "reliabletask"
                or not isinstance(payload, Mapping)
                or payload.get("jobId") != job.get("jobId")
                or payload.get("executionId") != execution_id
                or payload.get("carrier") != carrier
                or payload.get("stage") != "author"
            ):
                continue
            source_revision = str(payload.get("sourceRevision") or "")
            if not source_revision.startswith("sha256:") or len(source_revision) != 71:
                raise CampaignScaleEvidenceError(f"semantic job sourceRevision invalid: {path}")
            job_id = str(job["jobId"])
            if job_id in result[carrier]:
                raise CampaignScaleEvidenceError(f"duplicate semantic jobId: {job_id}")
            result[carrier][job_id] = {
                "job": job,
                "timings": _job_timings(job, label=f"semantic job:{job_id}"),
            }
    return result


def _active_at(timings: list[tuple[str, datetime]], instant: datetime) -> bool:
    leased_at: datetime | None = None
    for event, captured_at in timings:
        if event == "leased":
            leased_at = captured_at
            continue
        if event in _TERMINAL_TIMING_EVENTS and leased_at is not None:
            if leased_at <= instant <= captured_at:
                return True
            leased_at = None
    return leased_at is not None and leased_at <= instant
