"""Hard validation for final production artifact envelopes."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from core.schema import assert_valid

AGENT_RESULT_ENVELOPE_SCHEMA = "quwoquan.agent_result_envelope"


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def validate_agent_result_envelope(
    envelope: Mapping[str, Any],
    *,
    workspace_root: str | Path | None = None,
    require_passing_gates: bool = True,
) -> list[str]:
    issues: list[str] = []
    try:
        assert_valid(dict(envelope), "content", "agent_result_envelope", label="final artifact envelope")
    except (OSError, TypeError, ValueError) as exc:
        issues.append(str(exc))
        return issues
    root = Path(workspace_root).resolve() if workspace_root is not None else None
    for index, item in enumerate(envelope.get("files", [])):
        if not isinstance(item, Mapping):
            continue
        raw = str(item.get("path") or "")
        rel = PurePosixPath(raw)
        if not raw or rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
            issues.append(f"envelope.files[{index}].path must be safe relative path: {raw}")
            continue
        if root is None:
            continue
        actual = (root / raw).resolve()
        try:
            actual.relative_to(root)
        except ValueError:
            issues.append(f"envelope.files[{index}].path escapes artifact root: {raw}")
            continue
        if not actual.is_file():
            issues.append(f"envelope.files[{index}] missing file: {raw}")
        elif sha256_file(actual) != item.get("sha256"):
            issues.append(f"envelope.files[{index}] hash mismatch: {raw}")
    if require_passing_gates:
        for gate in envelope.get("gates", []):
            if isinstance(gate, Mapping) and gate.get("decision") not in {"passed", "approved"}:
                issues.append(f"gate.decision must pass for final artifact: {gate.get('gateId') or gate.get('gate') or '<unknown>'}")
    return issues


__all__ = [
    "AGENT_RESULT_ENVELOPE_SCHEMA",
    "sha256_bytes",
    "sha256_file",
    "sha256_text",
    "validate_agent_result_envelope",
]
