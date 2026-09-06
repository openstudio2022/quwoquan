#!/usr/bin/env python3
"""Pure file-fact scheduler for detached Environment Ops executions."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import (
    ACCEPTANCE_PROFILES,
    DSSE_PAYLOAD_TYPE,
    ENVIRONMENTS,
    NO_LIVE_ENVIRONMENT_REQUIRED,
)
from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import (
    SCHEMA as ACCEPTANCE_SCHEMA,
)
from quwoquan_ops.cli.lib.environment_acceptance_fact_validator import (
    validate_environment_acceptance_fact as validate_canonical_environment_acceptance_fact,
)

RESOURCE_GROUP = "workstation-commercial-runtime"
REQUEST_SCHEMA = "quwoquan_ops.environment_execution_request.v1"
EVENT_SCHEMA = "quwoquan_ops.environment_execution_event.v1"

_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EVENT_STATES = {
    "queued",
    "mutation_started",
    "cancelled",
    "safe_teardown_required",
    "acceptance_issued",
}
_TERMINAL_STATES = {"cancelled", "acceptance_issued"}


class EnvironmentSchedulerError(ValueError):
    """Stable typed failure from the local scheduler core."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def canonical_json_bytes(value: object) -> bytes:
    """Encode one JSON value with a single deterministic byte representation."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", "value is not canonical JSON"
        ) from exc


def canonical_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def exact_file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def dsse_pae(payload_type: str, payload: bytes) -> bytes:
    """Return the DSSE v1 pre-authentication encoding for signer input."""

    payload_type_bytes = _text(payload_type, "payloadType").encode("utf-8")
    return b" ".join(
        (
            b"DSSEv1",
            str(len(payload_type_bytes)).encode("ascii"),
            payload_type_bytes,
            str(len(payload)).encode("ascii"),
            payload,
        )
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp(value: object, field: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", f"{field} must be an exact timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", f"{field} must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", f"{field} must include timezone"
        )
    return value


def _text(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(char in value for char in ("\x00", "\n", "\r"))
    ):
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", f"{field} must be non-empty canonical text"
        )
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA_RE.fullmatch(text) is None:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", f"{field} must be an exact Git object id"
        )
    return text


def _digest(value: object, field: str) -> str:
    text = _text(value, field)
    if _DIGEST_RE.fullmatch(text) is None:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID",
            f"{field} must be sha256:<64 lowercase hex>",
        )
    return text


def _relative_ref(value: object, field: str) -> str:
    text = _text(value, field)
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in text
        or text.endswith("/latest")
        or "/latest/" in text
        or PurePosixPath(text).name.startswith("latest.")
    ):
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.MUTABLE_REF",
            f"{field} must be an immutable relative ref",
        )
    return text


def _exact_ref(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"ref", "digest"}:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID",
            f"{field} must contain exactly ref and digest",
        )
    return {
        "ref": _relative_ref(value.get("ref"), f"{field}.ref"),
        "digest": _digest(value.get("digest"), f"{field}.digest"),
    }


def _safe_root(root: Path) -> Path:
    root = root.expanduser()
    if root.is_symlink():
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.UNSAFE_PATH", "store root must not be a symlink"
        )
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def _resolve_ref(root: Path, ref: str, *, field: str) -> Path:
    current = root
    for part in PurePosixPath(ref).parts:
        current = current / part
        if current.is_symlink():
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.UNSAFE_PATH", f"{field} traverses a symlink"
            )
    try:
        current.resolve().relative_to(root)
    except ValueError as exc:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.UNSAFE_PATH", f"{field} leaves the store root"
        ) from exc
    if not current.is_file():
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.MISSING", f"{field} does not identify a file"
        )
    return current


def _read_canonical_object(path: Path, *, field: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", f"{field} is not readable JSON"
        ) from exc
    if not isinstance(value, dict):
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", f"{field} must be a JSON object"
        )
    if raw != canonical_json_bytes(value) + b"\n":
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.NON_CANONICAL",
            f"{field} bytes are not canonical JSON",
        )
    return value


def _load_exact_object(
    root: Path, value: object, *, field: str
) -> tuple[dict[str, Any], dict[str, str]]:
    exact = _exact_ref(value, field)
    path = _resolve_ref(root, exact["ref"], field=field)
    if exact_file_digest(path) != exact["digest"]:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.STALE", f"{field} exact bytes drifted"
        )
    return _read_canonical_object(path, field=field), exact


def write_create_once(path: Path, payload: Mapping[str, Any]) -> Path:
    """Atomically create canonical bytes, allowing only byte-identical replay."""

    encoded = canonical_json_bytes(dict(payload)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.UNSAFE_PATH",
            f"create-once slot is a symlink: {path}",
        )
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError as exc:
        if path.is_symlink() or path.read_bytes() != encoded:
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.CREATE_CONFLICT",
                f"create-once slot differs: {path.name}",
            ) from exc
        return path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _candidate_identity(candidate: Mapping[str, Any]) -> dict[str, str]:
    if candidate.get("schema") != "quwoquan_ops.exact_integration_candidate.v1":
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.CANDIDATE_INVALID", "candidate schema is unsupported"
        )
    candidate_id = _digest(candidate.get("candidateId"), "candidate.candidateId")
    unsigned = dict(candidate)
    unsigned.pop("candidateId", None)
    if canonical_digest(unsigned) != candidate_id:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.CANDIDATE_INVALID",
            "candidateId does not bind candidate bytes",
        )
    return {
        "candidateId": candidate_id,
        "commit": _sha(candidate.get("commit"), "candidate.commit"),
        "tree": _sha(candidate.get("tree"), "candidate.tree"),
    }


def create_execution_request(
    *,
    store_root: Path,
    candidate_ref: Mapping[str, str],
    environment: str,
    impact_plan_digest: str,
    priority: int,
    created_at: str | None = None,
) -> Path:
    """Create one deduplicated hermetic/detached request per candidate and environment."""

    root = _safe_root(store_root)
    if environment not in ENVIRONMENTS:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", "environment must be alpha, beta, or gamma"
        )
    if type(priority) is not int or priority < 0:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", "priority must be a non-negative integer"
        )
    candidate, exact_candidate = _load_exact_object(
        root, candidate_ref, field="candidate"
    )
    identity = _candidate_identity(candidate)
    impact_digest = _digest(impact_plan_digest, "impactPlanDigest")
    if candidate.get("impactPlanDigest") != impact_digest:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.STALE", "candidate ImpactPlan digest drifted"
        )
    requested_at = _timestamp(created_at or _now(), "createdAt")
    body: dict[str, Any] = {
        "schema": REQUEST_SCHEMA,
        "candidate": {**identity, **exact_candidate},
        "environment": environment,
        "impactPlanDigest": impact_digest,
        "priority": priority,
        "executionMode": "hermetic_detached_exact_candidate",
        "resourceGroup": RESOURCE_GROUP,
        "createdAt": requested_at,
    }
    body["requestId"] = canonical_digest(body)
    dedupe_key = canonical_digest(
        {"candidateId": identity["candidateId"], "environment": environment}
    ).removeprefix("sha256:")
    path = root / "environment-execution" / "requests" / f"{dedupe_key}.json"
    if path.exists() and not path.is_symlink():
        existing = load_execution_request(
            root,
            {
                "ref": path.relative_to(root).as_posix(),
                "digest": exact_file_digest(path),
            },
        )
        if (
            existing["candidate"]["candidateId"] != identity["candidateId"]
            or existing["environment"] != environment
        ):
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.CREATE_CONFLICT", "dedupe slot identity differs"
            )
        # The first create owns priority and timestamps for this dedupe identity.
        return path
    return write_create_once(path, body)


def load_execution_request(
    store_root: Path, request_ref: Mapping[str, str]
) -> dict[str, Any]:
    root = _safe_root(store_root)
    request, _ = _load_exact_object(root, request_ref, field="request")
    if request.get("schema") != REQUEST_SCHEMA:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", "request schema is unsupported"
        )
    if request.get("executionMode") != "hermetic_detached_exact_candidate":
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", "request is not hermetic and detached"
        )
    if request.get("resourceGroup") != RESOURCE_GROUP:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", "request resource group drifted"
        )
    environment = request.get("environment")
    if environment not in ENVIRONMENTS:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", "request environment is unsupported"
        )
    candidate_binding = request.get("candidate")
    if not isinstance(candidate_binding, Mapping):
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", "request candidate binding is missing"
        )
    candidate, exact_candidate = _load_exact_object(
        root,
        {
            "ref": candidate_binding.get("ref"),
            "digest": candidate_binding.get("digest"),
        },
        field="request.candidate",
    )
    identity = _candidate_identity(candidate)
    for key, expected in identity.items():
        if candidate_binding.get(key) != expected:
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.STALE", f"request candidate {key} drifted"
            )
    if dict(candidate_binding) != {**identity, **exact_candidate}:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID",
            "request candidate binding has unknown fields",
        )
    impact_digest = _digest(request.get("impactPlanDigest"), "request.impactPlanDigest")
    if candidate.get("impactPlanDigest") != impact_digest:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.STALE",
            "request ImpactPlan digest drifted from candidate",
        )
    if type(request.get("priority")) is not int or request["priority"] < 0:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", "request priority is invalid"
        )
    _timestamp(request.get("createdAt"), "request.createdAt")
    expected_id = dict(request)
    request_id = expected_id.pop("requestId", None)
    if request_id != canonical_digest(expected_id):
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", "requestId does not bind request content"
        )
    return request


def request_exact_ref(store_root: Path, request_path: Path) -> dict[str, str]:
    root = _safe_root(store_root)
    path = request_path.resolve()
    try:
        ref = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.UNSAFE_PATH", "request path leaves the store root"
        ) from exc
    return {"ref": _relative_ref(ref, "request.ref"), "digest": exact_file_digest(path)}


def select_next_request(
    *, store_root: Path, request_refs: Sequence[Mapping[str, str]]
) -> dict[str, Any] | None:
    """Select the highest-priority runnable request; Gamma always wins."""

    root = _safe_root(store_root)
    requests: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for exact_ref in request_refs:
        request = load_execution_request(root, exact_ref)
        key = (request["candidate"]["candidateId"], request["environment"])
        if key in seen:
            continue
        seen.add(key)
        state = current_task_state(store_root=root, request_id=request["requestId"])
        if state not in _TERMINAL_STATES and state != "safe_teardown_required":
            requests.append(request)
    if not requests:
        return None
    return min(
        requests,
        key=lambda item: (
            0 if item["environment"] == "gamma" else 1,
            -item["priority"],
            item["createdAt"],
            item["requestId"],
        ),
    )


def _event_paths(root: Path, request_id: str) -> list[Path]:
    _digest(request_id, "requestId")
    directory = (
        root / "environment-execution" / "events" / request_id.removeprefix("sha256:")
    )
    return sorted(directory.glob("*.json")) if directory.is_dir() else []


def _events(root: Path, request_id: str) -> list[dict[str, Any]]:
    events = [
        _read_canonical_object(path, field="execution event")
        for path in _event_paths(root, request_id)
    ]
    events.sort(key=lambda item: (item.get("sequence", -1), item.get("eventId", "")))
    for sequence, event in enumerate(events):
        if event.get("schema") != EVENT_SCHEMA or event.get("requestId") != request_id:
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.INVALID", "execution event identity drifted"
            )
        if event.get("sequence") != sequence or event.get("state") not in _EVENT_STATES:
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.INVALID",
                "execution event sequence or state is invalid",
            )
        unsigned = dict(event)
        event_id = unsigned.pop("eventId", None)
        if event_id != canonical_digest(unsigned):
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.INVALID", "eventId does not bind event content"
            )
    return events


def current_task_state(*, store_root: Path, request_id: str) -> str | None:
    root = _safe_root(store_root)
    events = _events(root, request_id)
    return events[-1]["state"] if events else None


def append_task_state(
    *,
    store_root: Path,
    request_ref: Mapping[str, str],
    state: str,
    occurred_at: str | None = None,
    reason: str | None = None,
    acceptance_ref: Mapping[str, str] | None = None,
) -> Path:
    """Append a create-once state fact after validating the state transition."""

    root = _safe_root(store_root)
    request = load_execution_request(root, request_ref)
    events = _events(root, request["requestId"])
    previous = events[-1]["state"] if events else None
    transitions = {
        None: {"queued"},
        "queued": {"mutation_started", "cancelled", "acceptance_issued"},
        "mutation_started": {"safe_teardown_required", "acceptance_issued"},
        "safe_teardown_required": set(),
        "cancelled": set(),
        "acceptance_issued": set(),
    }
    if state not in transitions[previous]:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID_TRANSITION",
            f"cannot append {state!r} after {previous!r}",
        )
    if state == "acceptance_issued":
        acceptance, exact_acceptance = _load_exact_object(
            root, acceptance_ref, field="acceptance"
        )
        acceptance = validate_environment_acceptance_fact(
            acceptance, store_root=root, verify_references=True
        )
        expected_candidate = {
            key: request["candidate"][key] for key in ("candidateId", "commit", "tree")
        }
        if (
            acceptance.get("environment") != request["environment"]
            or acceptance.get("candidate") != expected_candidate
            or acceptance.get("impactPlanDigest") != request["impactPlanDigest"]
        ):
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.ACCEPTANCE_INVALID",
                "acceptance event binding differs from request",
            )
    else:
        if acceptance_ref is not None:
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.INVALID",
                "only acceptance_issued may bind acceptance",
            )
        exact_acceptance = None
    body: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "requestId": request["requestId"],
        "sequence": len(events),
        "state": state,
        "occurredAt": _timestamp(occurred_at or _now(), "occurredAt"),
    }
    if reason is not None:
        body["reason"] = _text(reason, "reason")
    if exact_acceptance is not None:
        body["acceptance"] = exact_acceptance
    body["eventId"] = canonical_digest(body)
    directory = (
        root
        / "environment-execution"
        / "events"
        / request["requestId"].removeprefix("sha256:")
    )
    return write_create_once(directory / f"{len(events):08d}.json", body)


def supersede_request(
    *,
    store_root: Path,
    request_ref: Mapping[str, str],
    reason: str,
    occurred_at: str | None = None,
) -> Path:
    """Cancel before mutation, otherwise require teardown without acceptance."""

    root = _safe_root(store_root)
    request = load_execution_request(root, request_ref)
    current = current_task_state(store_root=root, request_id=request["requestId"])
    if current is None:
        append_task_state(
            store_root=root,
            request_ref=request_ref,
            state="queued",
            occurred_at=occurred_at,
        )
        current = "queued"
    target = "cancelled" if current == "queued" else "safe_teardown_required"
    return append_task_state(
        store_root=root,
        request_ref=request_ref,
        state=target,
        occurred_at=occurred_at,
        reason=reason,
    )


def _validate_evidence_refs(
    root: Path,
    refs: Sequence[Mapping[str, str]],
    *,
    field: str,
) -> list[dict[str, str]]:
    if isinstance(refs, (str, bytes)) or not refs:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.INVALID", f"{field} must be non-empty"
        )
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, value in enumerate(refs):
        exact = _exact_ref(value, f"{field}[{index}]")
        path = _resolve_ref(root, exact["ref"], field=f"{field}[{index}]")
        if exact_file_digest(path) != exact["digest"]:
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.STALE", f"{field} exact bytes drifted"
            )
        _read_canonical_object(path, field=f"{field}[{index}]")
        key = (exact["ref"], exact["digest"])
        if key in seen:
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.INVALID", f"{field} must be duplicate-free"
            )
        seen.add(key)
        normalized.append(exact)
    return sorted(normalized, key=lambda item: (item["ref"], item["digest"]))


def _validate_evidence_binding(
    root: Path,
    value: Mapping[str, str],
    *,
    field: str,
) -> dict[str, str]:
    _, exact = _load_exact_object(root, value, field=field)
    return exact


def validate_environment_acceptance_fact(
    payload: Mapping[str, Any],
    *,
    store_root: Path | None = None,
    verify_references: bool = False,
    accepted_at: datetime | None = None,
    signature_verifier: Callable[[str, bytes, str], bool] | None = None,
    expected_signer_identity: str | None = None,
) -> dict[str, Any]:
    """Validate one canonical v2 fact, including DSSE trust when supplied.

    ``signature_verifier`` receives signer identity, DSSE PAE bytes, and the
    encoded signature.  The canonical validator works with decoded payload
    bytes, so this boundary is the single place that reconstructs DSSE PAE.
    """

    canonical_verifier: Callable[[str, bytes, str], bool] | None = None
    if signature_verifier is not None:

        def canonical_verifier(
            signer_identity: str, signed_payload: bytes, signature: str
        ) -> bool:
            return (
                signature_verifier(
                    signer_identity,
                    dsse_pae(DSSE_PAYLOAD_TYPE, signed_payload),
                    signature,
                )
                is True
            )

    try:
        fact = validate_canonical_environment_acceptance_fact(
            payload,
            store_root=store_root,
            verify_references=verify_references,
            accepted_at=accepted_at,
            error_type=EnvironmentSchedulerError,
            invalid_code="ENVIRONMENT_SCHEDULER.ACCEPTANCE_INVALID",
            evidence_code="ENVIRONMENT_SCHEDULER.ACCEPTANCE_EVIDENCE_INVALID",
            signature_verifier=canonical_verifier,
        )
        if expected_signer_identity is not None:
            expected_identity = _text(
                expected_signer_identity, "expectedSignerIdentity"
            )
            signer = fact.get("signer")
            if (
                not isinstance(signer, Mapping)
                or signer.get("identity") != expected_identity
            ):
                raise EnvironmentSchedulerError(
                    "ENVIRONMENT_SCHEDULER.ACCEPTANCE_INVALID",
                    "environment acceptance signer identity drifted",
                )
        return fact
    except EnvironmentSchedulerError as exc:
        if "acceptance fact is expired" in exc.detail:
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.ACCEPTANCE_EXPIRED", exc.detail
            ) from exc
        raise


def issue_environment_acceptance_fact(
    *,
    store_root: Path,
    request_ref: Mapping[str, str],
    profile: str,
    status: str,
    case_result_refs: Sequence[Mapping[str, str]],
    runtime_identity: Mapping[str, str],
    data_lifecycle: Mapping[str, str],
    provider_readiness: Mapping[str, str],
    observability_readiness: Mapping[str, str],
    inspect_evidence: Mapping[str, str],
    doctor_evidence: Mapping[str, str],
    cleanup_evidence: Mapping[str, str],
    lease_closure_evidence: Mapping[str, str],
    predecessor: Mapping[str, str] | None,
    signer_identity: str,
    signer: Callable[[bytes], str],
    expires_at: str,
    non_promotable: bool,
    reason_code: str | None = None,
    issued_at: str | None = None,
) -> Path:
    """Issue one exact-byte v2 acceptance fact with all named gate evidence."""

    root = _safe_root(store_root)
    request = load_execution_request(root, request_ref)
    if profile not in ACCEPTANCE_PROFILES:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.ACCEPTANCE_INVALID", "profile is unsupported"
        )
    if status not in {"passed", "not_required"}:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.ACCEPTANCE_INVALID",
            "status must be passed or not_required",
        )
    if type(non_promotable) is not bool:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.ACCEPTANCE_INVALID", "nonPromotable must be boolean"
        )
    if status == "not_required":
        if (
            request["environment"] != "beta"
            or reason_code != NO_LIVE_ENVIRONMENT_REQUIRED
        ):
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.NOT_REQUIRED_INVALID",
                "only Beta may use typed no-live not_required",
            )
    elif reason_code is not None:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.ACCEPTANCE_INVALID",
            "passed facts cannot carry reasonCode",
        )
    state = current_task_state(store_root=root, request_id=request["requestId"])
    required_state = "queued" if status == "not_required" else "mutation_started"
    if state != required_state:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.ACCEPTANCE_FORBIDDEN",
            f"{status} acceptance requires {required_state} and is forbidden after supersede",
        )
    candidate = {
        "candidateId": request["candidate"]["candidateId"],
        "commit": request["candidate"]["commit"],
        "tree": request["candidate"]["tree"],
    }
    impact_digest = request["impactPlanDigest"]
    predecessor_ref = None
    if request["environment"] == "alpha":
        if predecessor is not None:
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.PREDECESSOR_INVALID",
                "alpha predecessor must be null",
            )
    else:
        if predecessor is None:
            raise EnvironmentSchedulerError(
                "ENVIRONMENT_SCHEDULER.PREDECESSOR_INVALID",
                "predecessor is required",
            )
        predecessor_ref = _exact_ref(predecessor, "predecessor")
    case_results = _validate_evidence_refs(
        root, case_result_refs, field="caseResultRefs"
    )
    named_input = {
        "runtimeIdentity": runtime_identity,
        "dataLifecycle": data_lifecycle,
        "providerReadiness": provider_readiness,
        "observabilityReadiness": observability_readiness,
        "inspectEvidence": inspect_evidence,
        "doctorEvidence": doctor_evidence,
        "cleanupEvidence": cleanup_evidence,
        "leaseClosureEvidence": lease_closure_evidence,
    }
    named = {
        field: _validate_evidence_binding(root, value, field=field)
        for field, value in named_input.items()
    }
    issued_timestamp = _timestamp(issued_at or _now(), "issuedAt")
    expiry_timestamp = _timestamp(expires_at, "expiresAt")
    issued_time = datetime.fromisoformat(issued_timestamp.replace("Z", "+00:00"))
    expiry_time = datetime.fromisoformat(expiry_timestamp.replace("Z", "+00:00"))
    if expiry_time <= issued_time:
        raise EnvironmentSchedulerError(
            "ENVIRONMENT_SCHEDULER.ACCEPTANCE_INVALID",
            "expiresAt must be after issuedAt",
        )
    envelope: dict[str, Any] = {
        "schema": ACCEPTANCE_SCHEMA,
        "environment": request["environment"],
        "profile": profile,
        "status": status,
        "candidate": candidate,
        "impactPlanDigest": impact_digest,
        "caseResultRefs": case_results,
        **named,
        "predecessor": predecessor_ref,
        "expiresAt": expiry_timestamp,
        "nonPromotable": non_promotable,
        "issuedAt": issued_timestamp,
    }
    if reason_code is not None:
        envelope["reasonCode"] = reason_code
    payload = canonical_json_bytes(envelope)
    signature = _text(signer(dsse_pae(DSSE_PAYLOAD_TYPE, payload)), "signer.signature")
    signed = {
        **envelope,
        "signer": {
            "identity": _text(signer_identity, "signer.identity"),
            "payloadType": DSSE_PAYLOAD_TYPE,
            "payload": base64.b64encode(payload).decode("ascii"),
            "signature": signature,
        },
    }
    signed["factId"] = canonical_digest(signed)
    signed = validate_environment_acceptance_fact(
        signed, store_root=root, verify_references=True
    )
    path = (
        root
        / "environment-execution"
        / "acceptance"
        / request["candidate"]["candidateId"].removeprefix("sha256:")
        / f"{request['environment']}.json"
    )
    result = write_create_once(path, signed)
    append_task_state(
        store_root=root,
        request_ref=request_ref,
        state="acceptance_issued",
        occurred_at=issued_at,
        acceptance_ref={
            "ref": result.relative_to(root).as_posix(),
            "digest": exact_file_digest(result),
        },
    )
    return result
