"""startup attempt receipt 的路径、校验与加载（逐字搬移）。

``startup_attempt_path`` / ``output_root`` / ``_secure_read`` 是测试的
patch 锚点，包内消费一律经 ``_pkg.`` 属性访问。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import quwoquan_ops.cli.lib.startup_attempt_receipt as _pkg

from ..immutable_image_composition import immutable_image_digest
from ..output_paths import target_process_dir
from .constants import (
    RECEIPT_FIELDS,
    SCHEMA,
    STATUSES,
    WORKLOADS,
    _DIGEST,
    _IMAGE_COMPOSITION_FIELDS,
    _IMAGE_ROLE,
    _OCI_IMAGE_FIELD_SETS,
)
from .receipt_fs import _absolute_path


def startup_attempt_path(target: str) -> Path:
    return target_process_dir(target) / "startup_attempt.json"


def startup_attempt_path_for_workload(target: str, workload: str) -> Path:
    normalized = str(workload or "").strip()
    if normalized not in {"full", "content-release", "content-commercial"}:
        raise ValueError(f"startup attempt workload is invalid: {normalized or '<empty>'}")
    return _pkg.startup_attempt_path(target).parent / "workloads" / normalized / "startup_attempt.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any] | None:
    payload = _pkg._secure_read(path)
    if payload is None:
        return None
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"startup attempt receipt is unreadable: {exc}") from exc
    return validate_startup_attempt(value)


def validate_startup_attempt(
    value: object,
    *,
    expected_env: str = "",
    expected_target: str = "",
) -> dict[str, Any]:
    """Validate the sole startup identity consumed by every runtime reader."""

    if not isinstance(value, dict) or set(value) != RECEIPT_FIELDS:
        raise ValueError("startup attempt receipt fields mismatch")
    if value.get("schema") != SCHEMA:
        raise ValueError("startup attempt receipt schema mismatch")
    env = str(value.get("env") or "").strip()
    target = str(value.get("target") or "").strip()
    if env not in {"alpha", "beta", "gamma"} or target != f"{env}-local":
        raise ValueError("startup attempt receipt target identity mismatch")
    if expected_env and env != expected_env:
        raise ValueError("startup attempt receipt environment mismatch")
    if expected_target and target != expected_target:
        raise ValueError("startup attempt receipt target mismatch")
    run_root_text = str(value.get("runRoot") or "").strip()
    canonical_run_root = _canonical_run_root(run_root_text, env=env)
    if canonical_run_root is not None and run_root_text != str(canonical_run_root):
        raise ValueError("startup attempt receipt runRoot is not canonical")
    if value.get("status") not in STATUSES:
        raise ValueError("startup attempt receipt status is invalid")
    workload = str(value.get("workload") or "").strip()
    if workload not in WORKLOADS:
        raise ValueError("startup attempt receipt workload is invalid")
    for field in ("attemptId", "composeProject"):
        if not str(value.get(field) or "").strip():
            raise ValueError(f"startup attempt receipt {field} is required")
    for field in (
        "candidateDigest",
        "configurationDigest",
        "providerRuntimeDigest",
        "imageTransportTag",
    ):
        if _DIGEST.fullmatch(str(value.get(field) or "")) is None:
            raise ValueError(f"startup attempt receipt {field} is invalid")
    observability_digest = str(value.get("observabilityLogSinkDigest") or "")
    if workload in {"full", "content-commercial"}:
        if _DIGEST.fullmatch(observability_digest) is None:
            raise ValueError(
                "startup attempt receipt observabilityLogSinkDigest is invalid"
            )
    elif observability_digest and _DIGEST.fullmatch(observability_digest) is None:
        raise ValueError(
            "startup attempt receipt observabilityLogSinkDigest is invalid"
        )

    composition = value.get("imageComposition")
    if not isinstance(composition, dict) or set(composition) != _IMAGE_COMPOSITION_FIELDS:
        raise ValueError("startup attempt receipt imageComposition fields mismatch")
    for field in ("configurationDigest", "buildInputDigest", "imageDigest"):
        if _DIGEST.fullmatch(str(composition.get(field) or "")) is None:
            raise ValueError(
                f"startup attempt receipt imageComposition {field} is invalid"
            )
    if composition["configurationDigest"] != value["configurationDigest"]:
        raise ValueError(
            "startup attempt receipt configuration differs from OCI composition"
        )
    images = composition.get("images")
    oci_images = composition.get("ociImages")
    if (
        not isinstance(images, dict)
        or not images
        or not isinstance(oci_images, dict)
        or set(images) != set(oci_images)
    ):
        raise ValueError("startup attempt receipt imageComposition has no images")
    refs: dict[str, str] = {}
    for service, descriptor in sorted(images.items()):
        if (
            _IMAGE_ROLE.fullmatch(str(service)) is None
            or not isinstance(descriptor, dict)
            or set(descriptor) != {"ref"}
            or _DIGEST.fullmatch(str(descriptor.get("ref") or "")) is None
        ):
            raise ValueError(
                f"startup attempt receipt image descriptor is invalid: {service}"
            )
        oci_descriptor = oci_images.get(service)
        if not isinstance(oci_descriptor, dict):
            raise TypeError(
                f"startup attempt receipt OCI image descriptor is invalid: {service}"
            )
        normalized_oci_descriptor = {
            str(key): str(item) for key, item in oci_descriptor.items()
        }
        if frozenset(normalized_oci_descriptor) not in _OCI_IMAGE_FIELD_SETS:
            raise ValueError(
                f"startup attempt receipt OCI image descriptor fields mismatch: {service}"
            )
        image_digest = str(normalized_oci_descriptor.get("imageDigest") or "")
        source_ref = str(normalized_oci_descriptor.get("ref") or "")
        build_input_digest = normalized_oci_descriptor.get("buildInputDigest")
        if (
            not source_ref
            or _DIGEST.fullmatch(image_digest) is None
            or (
                build_input_digest is not None
                and _DIGEST.fullmatch(build_input_digest) is None
            )
            or descriptor["ref"] != image_digest
        ):
            raise ValueError(
                f"startup attempt receipt OCI image identity is invalid: {service}"
            )
        refs[service] = image_digest
    if _sha256_json(oci_images) != composition["imageDigest"]:
        raise ValueError("startup attempt receipt OCI imageDigest mismatch")
    expected_image_version = immutable_image_digest(refs)
    if (
        composition.get("imageVersion") != expected_image_version
        or value.get("imageTransportTag") != expected_image_version
    ):
        raise ValueError("startup attempt receipt image composition mismatch")
    for field in ("startedAt", "updatedAt"):
        timestamp = str(value.get(field) or "")
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                f"startup attempt receipt {field} is invalid"
            ) from exc
    for field in ("failure", "cleanupFailure"):
        if value.get(field) is not None and not isinstance(value.get(field), str):
            raise ValueError(f"startup attempt receipt {field} is invalid")
    return value


def read_startup_attempt(target: str) -> dict[str, Any] | None:
    """只读加载启动回执，不恢复未完成的 fan-out 事务。"""

    return _read(_pkg.startup_attempt_path(target))


def load_startup_attempt(target: str) -> dict[str, Any] | None:
    path = _pkg.startup_attempt_path(target)
    _pkg._recover_fanout_transaction(
        path,
        expected_env=_environment_for_target(target),
        expected_target=target,
    )
    return _read(path)


def load_workload_startup_attempt(
    target: str,
    workload: str,
) -> dict[str, Any] | None:
    _pkg._recover_fanout_transaction(
        _pkg.startup_attempt_path(target),
        expected_env=_environment_for_target(target),
        expected_target=target,
    )
    return _read(startup_attempt_path_for_workload(target, workload))


def _environment_for_target(target: str) -> str:
    normalized = str(target or "").strip()
    for environment in ("alpha", "beta", "gamma"):
        if normalized == f"{environment}-local":
            return environment
    raise ValueError("startup attempt target identity mismatch")


def _canonical_run_root(value: str, *, env: str) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = _absolute_path(Path(text))
    expected_parent = _absolute_path(_pkg.output_root()) / "env" / env / "runs"
    try:
        relative = candidate.relative_to(expected_parent)
    except ValueError as exc:
        raise ValueError(
            "startup attempt runRoot must be target-environment run evidence"
        ) from exc
    if (
        len(relative.parts) != 1
        or relative.name in {"", ".", ".."}
        or "/" in relative.name
        or "\\" in relative.name
    ):
        raise ValueError(
            "startup attempt runRoot must be one canonical run directory"
        )
    return candidate


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
