"""Explicit Human PRE/DURING/POST decision receipts and lightweight projections."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..evidence_fingerprint import canonical_json_bytes
from .contract import load_contract

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STORE = REPO_ROOT / ".qwq_output/env/repo/runs/human-decisions"
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class HumanDecisionBridgeError(ValueError):
    """Typed local receipt, projection, or poll failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class HumanDecisionWriteResult:
    path: Path
    ref: str
    digest: str
    receipt: dict[str, Any]
    created: bool


def _fail(code: str, detail: str) -> None:
    raise HumanDecisionBridgeError(code, detail)


def _bridge_contract() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = load_contract()
    return (
        contract["runtime_bridge"],
        contract["schemas"]["human_runtime_decision_receipt"],
        contract["schemas"]["human_runtime_decision_projection"],
    )


def _exact_fields(value: object, expected: Sequence[str], *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("HAD.RUNTIME_DECISION_INVALID", f"{label} must be an object")
    actual = set(value)
    required = set(expected)
    if actual != required:
        _fail(
            "HAD.RUNTIME_DECISION_INVALID",
            f"{label} fields drifted missing={sorted(required-actual)} extra={sorted(actual-required)}",
        )
    return value


def _text(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\x00" in value
    ):
        _fail("HAD.RUNTIME_DECISION_INVALID", f"{label} must be trimmed non-empty text")
    return value


def _timestamp(value: object, *, label: str) -> datetime:
    raw = _text(value, label=label)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        _fail("HAD.RUNTIME_DECISION_INVALID", f"{label} must be ISO-8601")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("HAD.RUNTIME_DECISION_INVALID", f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def validate_runtime_decision_receipt(value: object) -> dict[str, Any]:
    """Validate a local explicit receipt; hosted authority is never synthesized here."""

    bridge, schema, _projection = _bridge_contract()
    receipt = _exact_fields(value, schema["required_fields"], label="human_runtime_decision_receipt")
    if receipt["schema_version"] != schema["schema_version"]:
        _fail("HAD.RUNTIME_DECISION_INVALID", "runtime decision schema_version mismatch")
    if receipt["serialization_version"] != bridge["serialization_version"]:
        _fail("HAD.RUNTIME_DECISION_INVALID", "runtime decision serialization_version mismatch")
    _text(receipt["objective_ref"], label="objective_ref")
    criteria = receipt["criteria"]
    if (
        not isinstance(criteria, list)
        or not criteria
        or len(criteria) != len(set(criteria))
        or any(not isinstance(item, str) or not item.strip() or item != item.strip() for item in criteria)
    ):
        _fail("HAD.RUNTIME_DECISION_INVALID", "criteria must be a unique non-empty explicit list")
    authority = _exact_fields(receipt["authority"], schema["authority_fields"], label="authority")
    if authority["source"] != "explicit_local_input":
        _fail("HAD.RUNTIME_DECISION_AUTHORITY_INVALID", "local receipt authority source must be explicit_local_input")
    duration = _exact_fields(authority["duration_scope"], schema["duration_scope_fields"], label="authority.duration_scope")
    if duration["kind"] not in bridge["duration_scope_kinds"]:
        _fail("HAD.RUNTIME_DECISION_INVALID", "duration scope kind is unknown")
    _text(duration["value"], label="authority.duration_scope.value")
    decision = receipt["decision"]
    if decision not in bridge["decision_values"]:
        _fail("HAD.RUNTIME_DECISION_INVALID", "decision is outside the closed set")
    redirect_target = receipt["redirect_target"]
    if decision == "redirect":
        _text(redirect_target, label="redirect_target")
    elif redirect_target is not None:
        _fail("HAD.RUNTIME_DECISION_INVALID", "redirect_target is only legal for redirect")
    _timestamp(receipt["received_at"], label="received_at")
    provider = _exact_fields(receipt["provider"], schema["provider_fields"], label="provider")
    if provider != {
        "kind": "self_attested",
        "provider_id": "local-explicit-cli",
        "provider_receipt_ref": None,
    }:
        _fail(
            "HAD.RUNTIME_DECISION_AUTHORITY_INVALID",
            "local receipts must remain self_attested; hosted authority requires external verification",
        )
    identity = _exact_fields(receipt["human_identity"], schema["human_identity_fields"], label="human_identity")
    _text(identity["subject"], label="human_identity.subject")
    if identity["assurance"] != "self_attested":
        _fail("HAD.RUNTIME_DECISION_AUTHORITY_INVALID", "local identity assurance must be self_attested")
    if receipt["input_mode"] != "explicit_cli":
        _fail("HAD.RUNTIME_DECISION_INVALID", "natural-language or inferred decisions are not verified inputs")
    if receipt["formal_production_eligible"] is not False:
        _fail("HAD.RUNTIME_DECISION_AUTHORITY_INVALID", "self-attested receipt cannot be formal production authority")
    return json.loads(json.dumps(receipt, ensure_ascii=False))


def build_self_attested_receipt(
    *,
    objective_ref: str,
    criteria: Sequence[str],
    duration_scope_kind: str,
    duration_scope_value: str,
    decision: str,
    human_identity: str,
    redirect_target: str | None = None,
    received_at: str | None = None,
) -> dict[str, Any]:
    """Build only from explicit CLI-shaped inputs; no chat text is interpreted."""

    bridge, schema, _projection = _bridge_contract()
    payload = {
        "schema_version": schema["schema_version"],
        "serialization_version": bridge["serialization_version"],
        "objective_ref": objective_ref,
        "criteria": list(criteria),
        "authority": {
            "source": "explicit_local_input",
            "duration_scope": {"kind": duration_scope_kind, "value": duration_scope_value},
        },
        "decision": decision,
        "redirect_target": redirect_target,
        "received_at": received_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": {
            "kind": "self_attested",
            "provider_id": "local-explicit-cli",
            "provider_receipt_ref": None,
        },
        "human_identity": {"subject": human_identity, "assurance": "self_attested"},
        "input_mode": "explicit_cli",
        "formal_production_eligible": False,
    }
    return validate_runtime_decision_receipt(payload)


def _repo_relative(path: Path, *, repo_root: Path) -> str:
    try:
        return path.absolute().relative_to(repo_root.absolute()).as_posix()
    except ValueError as error:
        _fail("HAD.RUNTIME_DECISION_STORE_INVALID", "decision store must stay inside repository")
    raise AssertionError from error


def _write_create_once(path: Path, raw: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError:
        existing = _read_regular(path)
        if existing != raw:
            _fail("HAD.RUNTIME_DECISION_TAMPERED", f"create-once conflict at {path}")
        return False
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return True


def _read_regular(path: Path) -> bytes:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            _fail("HAD.RUNTIME_DECISION_REF_INVALID", f"decision ref is not a regular single-link file: {path}")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        current = path.lstat()
    except HumanDecisionBridgeError:
        raise
    except OSError as error:
        _fail("HAD.RUNTIME_DECISION_REF_INVALID", f"decision ref cannot be read: {error}")
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    if identity(opened) != identity(after) or identity(after) != identity(current) or current.st_nlink != 1:
        _fail("HAD.RUNTIME_DECISION_TAMPERED", f"decision ref changed while read: {path}")
    return b"".join(chunks)


def record_runtime_decision(
    receipt: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    store: Path = DEFAULT_STORE,
) -> HumanDecisionWriteResult:
    validated = validate_runtime_decision_receipt(dict(receipt))
    raw = canonical_json_bytes(validated)
    digest_hex = hashlib.sha256(raw).hexdigest()
    path = store / "by-digest" / f"{digest_hex}.json"
    created = _write_create_once(path, raw)
    ref = _repo_relative(path, repo_root=repo_root)
    objective_key = hashlib.sha256(validated["objective_ref"].encode("utf-8")).hexdigest()
    timestamp_key = validated["received_at"].replace(":", "-").replace("+", "_")
    index_payload = canonical_json_bytes({"decision_ref": ref})
    index_path = store / "by-objective" / objective_key / f"{timestamp_key}-{digest_hex}.json"
    _write_create_once(index_path, index_payload)
    return HumanDecisionWriteResult(
        path=path,
        ref=ref,
        digest="sha256:" + digest_hex,
        receipt=validated,
        created=created,
    )


def read_runtime_decision_ref(raw_ref: str, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    _text(raw_ref, label="human_decision_ref")
    relative = Path(raw_ref)
    bridge, _schema, _projection = _bridge_contract()
    expected_root = Path(bridge["local_store"])
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        _fail("HAD.RUNTIME_DECISION_REF_INVALID", "human_decision_ref must be canonical repository-relative")
    try:
        inside = relative.relative_to(expected_root / "by-digest")
    except ValueError:
        _fail("HAD.RUNTIME_DECISION_REF_INVALID", "human_decision_ref is outside canonical decision store")
    if len(inside.parts) != 1 or not inside.name.endswith(".json") or not _DIGEST_RE.fullmatch(inside.stem):
        _fail("HAD.RUNTIME_DECISION_REF_INVALID", "human_decision_ref is not content-addressed")
    raw = _read_regular(repo_root / relative)
    actual = hashlib.sha256(raw).hexdigest()
    if actual != inside.stem:
        _fail("HAD.RUNTIME_DECISION_TAMPERED", "human_decision_ref digest drifted")
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        _fail("HAD.RUNTIME_DECISION_INVALID", f"decision receipt JSON invalid: {error}")
    return validate_runtime_decision_receipt(value)


def latest_runtime_decision_ref(
    objective_ref: str,
    *,
    repo_root: Path = REPO_ROOT,
    store: Path = DEFAULT_STORE,
) -> str | None:
    _text(objective_ref, label="objective_ref")
    key = hashlib.sha256(objective_ref.encode("utf-8")).hexdigest()
    directory = store / "by-objective" / key
    if not directory.exists():
        return None
    if directory.is_symlink() or not directory.is_dir():
        _fail("HAD.RUNTIME_DECISION_TAMPERED", "objective decision index is not a directory")
    candidates: list[tuple[datetime, str]] = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith("."):
            continue
        try:
            index = json.loads(_read_regular(path))
        except (UnicodeError, json.JSONDecodeError) as error:
            _fail("HAD.RUNTIME_DECISION_TAMPERED", f"decision index invalid: {error}")
        if not isinstance(index, dict) or set(index) != {"decision_ref"}:
            _fail("HAD.RUNTIME_DECISION_TAMPERED", "decision index fields drifted")
        ref = _text(index["decision_ref"], label="decision index ref")
        receipt = read_runtime_decision_ref(ref, repo_root=repo_root)
        if receipt["objective_ref"] != objective_ref:
            _fail("HAD.RUNTIME_DECISION_TAMPERED", "decision index objective/ref drifted")
        candidates.append((_timestamp(receipt["received_at"], label="received_at"), ref))
    if not candidates:
        return None
    return max(candidates)[1]


def project_runtime_decision(
    *,
    target_kind: str,
    admission_class: str = "ordinary",
    human_decision_ref: str | None = None,
    objective_ref: str | None = None,
    poll_latest: bool = False,
    repo_root: Path = REPO_ROOT,
    store: Path = DEFAULT_STORE,
) -> dict[str, Any]:
    """Explicitly project one receipt; ordinary absent paths remain non-blocking."""

    bridge, _receipt_schema, projection_schema = _bridge_contract()
    if target_kind not in bridge["target_kinds"]:
        _fail("HAD.RUNTIME_DECISION_INVALID", "target_kind is unknown")
    if admission_class not in bridge["admission_classes"]:
        _fail("HAD.RUNTIME_DECISION_INVALID", "admission_class is unknown")
    if poll_latest:
        if human_decision_ref is not None or objective_ref is None:
            _fail("HAD.RUNTIME_DECISION_INVALID", "poll_latest requires only objective_ref")
        human_decision_ref = latest_runtime_decision_ref(
            objective_ref, repo_root=repo_root, store=store
        )
    receipt = (
        read_runtime_decision_ref(human_decision_ref, repo_root=repo_root)
        if human_decision_ref is not None
        else None
    )
    if receipt is None:
        if admission_class == "formal_prod":
            status, projection, terminal, blocks = (
                "blocked", "required_not_projected", "HUMAN_DECISION.FORMAL_AUTHORITY_REQUIRED", True
            )
        else:
            status, projection, terminal, blocks = (
                "declared", "not_projected", "HUMAN_DECISION.NOT_PROJECTED", False
            )
        decision = redirect_target = authority_status = None
    else:
        decision = receipt["decision"]
        redirect_target = receipt["redirect_target"]
        authority_status = "self_attested_non_formal"
        if admission_class == "formal_prod":
            status, projection, terminal, blocks = (
                "blocked", "projected_non_authoritative", "HUMAN_DECISION.FORMAL_AUTHORITY_REQUIRED", True
            )
        elif decision == "pause":
            status, projection, terminal, blocks = (
                "stopped", "projected", "HUMAN_DECISION.PAUSED", True
            )
        elif decision == "redirect":
            status, projection, terminal, blocks = (
                "stopped", "projected", "HUMAN_DECISION.REDIRECTED", True
            )
        elif decision == "approve_admission":
            status, projection, terminal, blocks = (
                "declared", "projected_non_authoritative", "HUMAN_DECISION.ADMISSION_APPROVAL_DECLARED", False
            )
        else:
            status, projection, terminal, blocks = (
                "continue", "projected", "HUMAN_DECISION.CONTINUE", False
            )
    result = {
        "schema_version": projection_schema["schema_version"],
        "target_kind": target_kind,
        "admission_class": admission_class,
        "human_decision_ref": human_decision_ref,
        "status": status,
        "projection": projection,
        "decision": decision,
        "redirect_target": redirect_target,
        "authority_status": authority_status,
        "formal_admission_satisfied": False,
        "blocks_execution": blocks,
        "terminal": terminal,
    }
    _exact_fields(result, projection_schema["required_fields"], label="human_runtime_decision_projection")
    return result


def runtime_projection_exit_code(projection: Mapping[str, Any]) -> int:
    terminal = projection.get("terminal")
    if terminal == "HUMAN_DECISION.PAUSED":
        return 3
    if terminal == "HUMAN_DECISION.REDIRECTED":
        return 4
    if projection.get("status") == "blocked":
        return 2
    return 0


__all__ = [
    "DEFAULT_STORE", "HumanDecisionBridgeError", "HumanDecisionWriteResult",
    "build_self_attested_receipt", "latest_runtime_decision_ref",
    "project_runtime_decision", "read_runtime_decision_ref",
    "record_runtime_decision", "runtime_projection_exit_code",
    "validate_runtime_decision_receipt",
]
