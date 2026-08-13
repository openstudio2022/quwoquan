"""immutable release attestation 绑定与 ContractGraph 摘要（逐字迁自原单文件）。

``canonical_contract_graph_digest`` 通过包属性读取 ``CONTRACT_GRAPH_PATH``，
以保持测试对包属性 monkeypatch 的既有语义。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import quwoquan_ops.cli.lib.deployment_candidate_manifest as _pkg

from .constants import (
    _DIGEST,
    _RELEASE_BINDING_FIELDS,
    _RELEASE_LIFECYCLE_CLASSES,
)


def _release_binding(path_value: str, *, label: str) -> dict[str, str]:
    path = Path(str(path_value or "").strip()).expanduser()
    if not str(path_value or "").strip():
        raise ValueError(f"{label} release attestation is required")
    path = path.resolve()
    try:
        encoded = path.read_bytes()
        value = json.loads(encoded.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} release attestation is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{label} release attestation must be an object")
    release_id = str(value.get("releaseId") or "").strip()
    release_digest = str(value.get("payloadSha256") or "").strip()
    release_class = str(value.get("releaseClass") or "").strip()
    lifecycle = str(value.get("productLifecycleState") or "").strip()
    if value.get("schema") != "quwoquan_data.release_attestation":
        raise ValueError(f"{label} release attestation schema mismatch")
    if not release_id or _DIGEST.fullmatch(release_digest) is None:
        raise ValueError(f"{label} release identity is invalid")
    if release_class not in _RELEASE_LIFECYCLE_CLASSES:
        raise ValueError(f"{label} releaseClass is invalid")
    if lifecycle not in _RELEASE_LIFECYCLE_CLASSES:
        raise ValueError(f"{label} productLifecycleState is invalid")
    if release_class != lifecycle:
        raise ValueError(
            f"{label} release lifecycle identity must keep "
            "releaseClass equal to productLifecycleState"
        )
    return {
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "attestationRef": str(path),
        "attestationDigest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
        "releaseClass": release_class,
        "productLifecycleState": lifecycle,
    }


def release_input_classification(release: object) -> str:
    """Classify both immutable release inputs without claiming release readiness."""

    if not isinstance(release, Mapping) or set(release) != {"candidate", "rollback"}:
        raise ValueError("release input bindings must contain candidate and rollback")
    classes: list[str] = []
    for label in ("candidate", "rollback"):
        binding = release.get(label)
        if not isinstance(binding, Mapping) or set(binding) != _RELEASE_BINDING_FIELDS:
            raise ValueError(f"{label} release input binding fields mismatch")
        release_class = str(binding.get("releaseClass") or "").strip()
        lifecycle = str(binding.get("productLifecycleState") or "").strip()
        if release_class not in _RELEASE_LIFECYCLE_CLASSES:
            raise ValueError(f"{label} releaseClass is invalid")
        if lifecycle != release_class:
            raise ValueError(
                f"{label} release lifecycle identity must keep "
                "releaseClass equal to productLifecycleState"
            )
        classes.append(release_class)
    if classes == ["research", "research"]:
        return "research_inputs"
    if classes == ["commercial", "commercial"]:
        return "commercial_inputs"
    return "mixed_inputs"


def canonical_contract_graph_digest() -> str:
    """Digest the exact canonical ContractGraph bytes used by this package."""

    path = _pkg.CONTRACT_GRAPH_PATH
    if path.is_symlink() or not path.is_file():
        raise ValueError("canonical ContractGraph is missing or unsafe")
    try:
        encoded = path.read_bytes()
        payload = json.loads(encoded.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"canonical ContractGraph is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("canonical ContractGraph must be a JSON object")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_release_attestations(
    release_attestation: str,
    rollback_release_attestation: str,
) -> dict[str, dict[str, str]]:
    """Fail before package/build work when immutable release inputs are absent."""

    candidate = _release_binding(release_attestation, label="candidate")
    rollback = _release_binding(
        rollback_release_attestation,
        label="rollback",
    )
    if (
        candidate["releaseId"] == rollback["releaseId"]
        or candidate["releaseDigest"] == rollback["releaseDigest"]
    ):
        raise ValueError(
            "candidate and rollback release attestations must have distinct "
            "releaseId and releaseDigest"
        )
    return {
        "candidate": candidate,
        "rollback": rollback,
    }
