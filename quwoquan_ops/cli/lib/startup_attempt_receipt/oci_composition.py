"""candidate OCI 镜像 manifest 到 startup 身份的投影与加载（逐字搬移）。

``active_candidate_manifest_path`` / ``deployment_candidate_dir`` /
``load_candidate_manifest`` / ``_secure_read`` 是测试的 patch 锚点，
一律经 ``_pkg.`` 属性访问。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import quwoquan_ops.cli.lib.startup_attempt_receipt as _pkg

from ..immutable_image_composition import immutable_image_digest
from ..output_paths import ACTIVE_CANDIDATE_SCHEMA
from .constants import (
    _ACTIVE_CANDIDATE_FIELDS,
    _DIGEST,
    _IMAGE_ROLE,
    _OCI_FIELDS,
    _OCI_IMAGE_FIELD_SETS,
    _OCI_SCHEMA,
)
from .receipt_contract import _sha256_json
from .receipt_fs import _absolute_path


def image_composition_from_candidate_oci(
    value: object,
    *,
    expected_environment: str = "",
    expected_target: str = "",
) -> dict[str, Any]:
    """Project the complete package OCI role closure into startup identity."""

    if not isinstance(value, dict) or set(value) != _OCI_FIELDS:
        raise ValueError("startup OCI image manifest fields mismatch")
    if value.get("schema") != _OCI_SCHEMA:
        raise ValueError("startup OCI image manifest schema mismatch")
    if expected_environment and value.get("environment") != expected_environment:
        raise ValueError("startup OCI image manifest environment mismatch")
    if expected_target and value.get("target") != expected_target:
        raise ValueError("startup OCI image manifest target mismatch")
    for field in ("configurationDigest", "buildInputDigest", "imageDigest"):
        if _DIGEST.fullmatch(str(value.get(field) or "")) is None:
            raise ValueError(f"startup OCI image manifest {field} is invalid")

    images = value.get("images")
    if not isinstance(images, dict) or not images:
        raise ValueError("startup OCI image manifest has no images")
    normalized_images: dict[str, dict[str, str]] = {}
    runtime_refs: dict[str, str] = {}
    for raw_role, raw_descriptor in sorted(images.items()):
        role = str(raw_role)
        if _IMAGE_ROLE.fullmatch(role) is None or not isinstance(
            raw_descriptor, dict
        ):
            raise ValueError(f"startup OCI image descriptor is invalid: {role}")
        descriptor = {str(key): str(item) for key, item in raw_descriptor.items()}
        if frozenset(descriptor) not in _OCI_IMAGE_FIELD_SETS:
            raise ValueError(f"startup OCI image descriptor fields mismatch: {role}")
        if not descriptor["ref"] or _DIGEST.fullmatch(
            descriptor["imageDigest"]
        ) is None:
            raise ValueError(f"startup OCI image identity is invalid: {role}")
        build_input_digest = descriptor.get("buildInputDigest")
        if build_input_digest is not None and _DIGEST.fullmatch(
            build_input_digest
        ) is None:
            raise ValueError(
                f"startup OCI Provider build input identity is invalid: {role}"
            )
        normalized_images[role] = descriptor
        runtime_refs[role] = descriptor["imageDigest"]
    if _sha256_json(normalized_images) != value["imageDigest"]:
        raise ValueError("startup OCI image manifest imageDigest mismatch")

    return {
        "configurationDigest": str(value["configurationDigest"]),
        "buildInputDigest": str(value["buildInputDigest"]),
        "imageDigest": str(value["imageDigest"]),
        "imageVersion": immutable_image_digest(runtime_refs),
        "images": {
            role: {"ref": image_digest}
            for role, image_digest in sorted(runtime_refs.items())
        },
        "ociImages": normalized_images,
    }


def load_candidate_oci_image_composition(
    path: Path,
    *,
    expected_environment: str,
    expected_target: str,
    expected_candidate_digest: str = "",
) -> dict[str, Any]:
    if not expected_target:
        raise ValueError("startup OCI image manifest requires expected target")
    if (
        expected_environment not in {"alpha", "beta", "gamma"}
        or expected_target != f"{expected_environment}-local"
    ):
        raise ValueError("startup OCI expected target identity mismatch")
    pointer_path = _pkg.active_candidate_manifest_path(expected_target)
    pointer_bytes = _pkg._secure_read(
        pointer_path,
        label="active deployment candidate",
    )
    if pointer_bytes is None:
        raise ValueError("startup OCI image manifest has no active candidate")
    try:
        active = json.loads(pointer_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"active deployment candidate is unreadable: {exc}") from exc
    if not isinstance(active, dict) or set(active) != _ACTIVE_CANDIDATE_FIELDS:
        raise ValueError("active deployment candidate fields mismatch")
    baseline_id = str(active.get("baselineId") or "").strip()
    candidate_root = _pkg.deployment_candidate_dir(expected_target, baseline_id)
    if (
        active.get("schema") != ACTIVE_CANDIDATE_SCHEMA
        or active.get("candidateType") != "runtime-full"
        or active.get("target") != expected_target
        or active.get("candidateDir") != str(candidate_root)
    ):
        raise ValueError("active deployment candidate identity mismatch")
    normalized_expected_candidate = str(expected_candidate_digest or "").strip()
    if (
        normalized_expected_candidate
        and normalized_expected_candidate != baseline_id
    ):
        raise ValueError("startup OCI candidate digest mismatch")
    candidate = _pkg.load_candidate_manifest(
        expected_environment,
        expected_target,
        baseline_id,
        require_full=True,
    )
    expected_path = (
        candidate_root / "packages" / "runtime-shared" / "oci-images.json"
    )
    if _absolute_path(path) != _absolute_path(expected_path):
        raise ValueError(
            "startup OCI image manifest must be the active candidate fixed artifact"
        )
    payload = _pkg._secure_read(expected_path, label="startup OCI image manifest")
    if payload is None:
        raise ValueError("startup OCI image manifest is missing or unsafe")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"startup OCI image manifest is unreadable: {exc}") from exc
    composition = image_composition_from_candidate_oci(
        value,
        expected_environment=expected_environment,
        expected_target=expected_target,
    )
    if (
        candidate.get("baselineId") != baseline_id
        or candidate.get("configurationDigest")
        != composition["configurationDigest"]
        or candidate.get("buildInputDigest") != composition["buildInputDigest"]
        or candidate.get("imageDigest") != composition["imageDigest"]
    ):
        raise ValueError("startup OCI image manifest differs from active candidate")
    pointer_after = _pkg._secure_read(
        pointer_path,
        label="active deployment candidate",
    )
    if pointer_after != pointer_bytes:
        raise ValueError("active deployment candidate changed during OCI validation")
    return composition
