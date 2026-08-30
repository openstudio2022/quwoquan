"""Read-only M1000 App UAT sampling authority projection."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from core.schema import assert_valid

CARRIERS = ("homepage", "article", "image", "video")


class ReleaseUatSamplingAuthorityError(ValueError):
    """The external strategy or an authenticated authority readback is invalid."""


def exact_byte_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def exact_document_bytes(value: Mapping[str, Any]) -> bytes:
    """Return the canonical bytes used by the optional create-once projector."""
    return (
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _contained(root: Path, ref: str) -> Path:
    resolved_root = Path(root).expanduser().resolve(strict=True)
    relative = PurePosixPath(str(ref))
    if relative.is_absolute() or not relative.parts or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise ReleaseUatSamplingAuthorityError("authority ref must be relative and contained")
    path = resolved_root.joinpath(*relative.parts)
    try:
        path.resolve(strict=True).relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise ReleaseUatSamplingAuthorityError("authority ref is unavailable or escapes root") from exc
    if path.is_symlink():
        raise ReleaseUatSamplingAuthorityError("authority ref must not be a symlink")
    return path


def _read_exact(root: Path, binding: Mapping[str, Any], *, label: str) -> tuple[dict[str, Any], str, str]:
    if not isinstance(binding, Mapping) or set(binding) != {"ref", "digest"}:
        raise ReleaseUatSamplingAuthorityError(f"{label} requires exact ref+digest")
    ref = str(binding.get("ref") or "")
    expected = str(binding.get("digest") or "")
    path = _contained(root, ref)
    before = path.lstat()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise ReleaseUatSamplingAuthorityError(f"{label} must be a stable regular file")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ReleaseUatSamplingAuthorityError(f"{label} changed while being read")
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    if exact_byte_digest(raw) != expected:
        raise ReleaseUatSamplingAuthorityError(f"{label} exact-byte digest drifted")
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseUatSamplingAuthorityError(f"{label} is not JSON") from exc
    if not isinstance(value, dict):
        raise ReleaseUatSamplingAuthorityError(f"{label} must be an object")
    return value, ref, expected


def _authority_binding(
    *, root: Path, binding: Mapping[str, Any], role: str,
    strategy_ref: str, strategy_digest: str, release_id: str, release_digest: str,
) -> dict[str, str]:
    value, ref, digest = _read_exact(root, binding, label=f"{role} authority readback")
    assert_valid(
        value, "release", "m1000_app_uat_sampling_authority_readback",
        label=f"M1000 {role} sampling authority readback",
    )
    expected = {
        "schema": "quwoquan_data.m1000_app_uat_sampling_authority_readback",
        "role": role,
        "decision": "approved",
        "strategyRef": strategy_ref,
        "strategyDigest": strategy_digest,
        "releaseId": release_id,
        "releaseDigest": release_digest,
    }
    if any(value.get(field) != expected_value for field, expected_value in expected.items()):
        raise ReleaseUatSamplingAuthorityError(f"{role} authority readback identity drifted")
    return {
        "role": role,
        "ref": ref,
        "digest": digest,
        "authorityId": str(value["authorityId"]),
        "authenticationContextDigest": str(value["authenticationContextDigest"]),
        "observedAt": str(value["observedAt"]),
    }


def validate_release_uat_sampling_authority(
    value: object, *, release_id: str, release_digest: str
) -> dict[str, Any]:
    """Validate a projected authority already embedded in an immutable plan."""
    try:
        assert_valid(
            value, "release", "release_uat_sampling_authority",
            label="M1000 embedded release UAT sampling authority",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ReleaseUatSamplingAuthorityError(str(exc)) from exc
    if not isinstance(value, Mapping):
        raise ReleaseUatSamplingAuthorityError("embedded sampling authority must be an object")
    authority = dict(value)
    if (
        authority.get("schema") != "quwoquan_data.release_uat_sampling_authority"
        or authority.get("milestone") != "M1000"
        or authority.get("releaseId") != release_id
        or authority.get("releaseDigest") != release_digest
    ):
        raise ReleaseUatSamplingAuthorityError("embedded sampling authority release identity drifted")
    product = authority.get("productOwner")
    quality = authority.get("qualityOwner")
    if not isinstance(product, Mapping) or not isinstance(quality, Mapping):
        raise ReleaseUatSamplingAuthorityError("embedded product/quality authority is missing")
    if product.get("authorityId") == quality.get("authorityId"):
        raise ReleaseUatSamplingAuthorityError(
            "product_owner and quality_owner require distinct authenticated authorities"
        )
    return authority


def load_release_uat_sampling_authority(
    *,
    artifact_root: Path,
    authority_binding: Mapping[str, Any] | None,
    release_id: str,
    release_digest: str,
) -> dict[str, Any]:
    """Load one exact projected authority for an immutable sample plan."""
    if authority_binding is None:
        raise ReleaseUatSamplingAuthorityError(
            "DATA.RELEASE.UAT_SAMPLE_AUTHORITY_MISSING: M1000 requires a "
            "projected authority exact ref+digest"
        )
    value, _ref, _digest = _read_exact(
        artifact_root,
        authority_binding,
        label="M1000 projected sampling authority",
    )
    return validate_release_uat_sampling_authority(
        value,
        release_id=release_id,
        release_digest=release_digest,
    )


def write_release_uat_sampling_authority_projection(
    output: Path, value: Mapping[str, Any]
) -> Path:
    """Create one canonical projection file; identical replay is idempotent."""
    body = exact_document_bytes(value)
    destination = Path(output).expanduser().resolve(strict=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        descriptor, temporary = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.is_symlink() or not destination.is_file():
                raise ReleaseUatSamplingAuthorityError(
                    "sampling authority projection create-once target is not a regular file"
                ) from None
            if destination.read_bytes() != body:
                raise ReleaseUatSamplingAuthorityError(
                    "sampling authority projection create-once conflict"
                ) from None
        else:
            directory = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        return destination
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def project_release_uat_sampling_authority(
    *, artifact_root: Path, release_id: str, release_digest: str,
    strategy_binding: Mapping[str, Any] | None,
    product_owner_readback: Mapping[str, Any] | None,
    quality_owner_readback: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Project exact authority inputs; never creates, approves, or discovers facts."""
    if strategy_binding is None or product_owner_readback is None or quality_owner_readback is None:
        raise ReleaseUatSamplingAuthorityError(
            "DATA.RELEASE.UAT_SAMPLE_AUTHORITY_MISSING: M1000 requires exact external strategy and product/quality authenticated readbacks"
        )
    strategy, strategy_ref, strategy_digest = _read_exact(
        artifact_root, strategy_binding, label="M1000 sampling strategy"
    )
    assert_valid(
        strategy, "release", "m1000_app_uat_sampling_strategy",
        label="M1000 external sampling strategy",
    )
    if (
        strategy.get("schema") != "quwoquan_data.m1000_app_uat_sampling_strategy"
        or strategy.get("milestone") != "M1000"
        or strategy.get("releaseId") != release_id
        or strategy.get("releaseDigest") != release_digest
    ):
        raise ReleaseUatSamplingAuthorityError("M1000 sampling strategy release identity drifted")
    distribution = strategy.get("sampleDistribution")
    if not isinstance(distribution, Mapping) or set(distribution) != set(CARRIERS):
        raise ReleaseUatSamplingAuthorityError("M1000 sampleDistribution carrier coverage drifted")
    product = _authority_binding(
        root=artifact_root, binding=product_owner_readback, role="product_owner",
        strategy_ref=strategy_ref, strategy_digest=strategy_digest,
        release_id=release_id, release_digest=release_digest,
    )
    quality = _authority_binding(
        root=artifact_root, binding=quality_owner_readback, role="quality_owner",
        strategy_ref=strategy_ref, strategy_digest=strategy_digest,
        release_id=release_id, release_digest=release_digest,
    )
    if product["authorityId"] == quality["authorityId"]:
        raise ReleaseUatSamplingAuthorityError(
            "product_owner and quality_owner require distinct authenticated authorities"
        )
    result = {
        "schema": "quwoquan_data.release_uat_sampling_authority",
        "milestone": "M1000",
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "strategy": {
            "ref": strategy_ref,
            "digest": strategy_digest,
            "strategyId": str(strategy["strategyId"]),
            "sampleDistribution": {carrier: int(distribution[carrier]) for carrier in CARRIERS},
        },
        "productOwner": product,
        "qualityOwner": quality,
    }
    assert_valid(
        result, "release", "release_uat_sampling_authority",
        label="M1000 release UAT sampling authority",
    )
    return result


__all__ = [
    "ReleaseUatSamplingAuthorityError",
    "exact_byte_digest",
    "exact_document_bytes",
    "load_release_uat_sampling_authority",
    "project_release_uat_sampling_authority",
    "validate_release_uat_sampling_authority",
    "write_release_uat_sampling_authority_projection",
]
