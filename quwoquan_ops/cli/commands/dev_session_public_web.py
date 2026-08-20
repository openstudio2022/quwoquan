"""Immutable public Web package resolution for mutable ``test_live`` sessions."""

from __future__ import annotations

import hashlib
import json
import os
import re

from pathlib import Path
from typing import Any, Mapping


def _exact_active_release(
    *,
    package_root: Path,
    environment: str,
    public_origin: str,
) -> tuple[str, str]:
    """Return the exact ``(releaseId, manifestSHA256)`` selected by the writer.

    指针缺席（尚未迁移的包目录）返回空对，让调用方回落到 current 兼容投影；
    指针在场但不可解析则是失败，不得降级。
    """
    from quwoquan_ops.cli.lib.web_official_release import (
        ACTIVE_POINTER_NAME,
        ACTIVE_POINTER_SCHEMA,
    )

    pointer = package_root.expanduser() / ACTIVE_POINTER_NAME
    if not pointer.is_file() or pointer.is_symlink():
        return "", ""
    try:
        payload = json.loads(pointer.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "mutable test_live public Web active release pointer is invalid UTF-8 JSON"
        ) from exc
    release_id = ""
    manifest_digest = ""
    if isinstance(payload, dict):
        release_id = str(payload.get("releaseId") or "").strip()
        manifest_digest = str(payload.get("manifestSHA256") or "").strip()
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != ACTIVE_POINTER_SCHEMA
        or payload.get("environment") != environment
        or payload.get("publicOrigin") != public_origin
        or not release_id
        or "/" in release_id
        or release_id.startswith(".")
        or re.fullmatch(r"sha256:[0-9a-f]{64}", manifest_digest) is None
    ):
        raise ValueError(
            "mutable test_live public Web active release pointer does not match the target"
        )
    return release_id, manifest_digest


def _load_dev_session_public_web_package(
    *,
    environment: str,
    package_root: Path,
    public_origin: str,
) -> tuple[dict[str, str], Path]:
    """Read and verify the immutable Web package selected by ``current``."""
    from quwoquan_ops.cli.lib.web_official_release import (
        WebOfficialReleaseError,
        _tree_sha256,
        _trusted_web_origin,
        _verify_web_build,
    )

    try:
        expected_origin = _trusted_web_origin(environment, public_origin)
    except WebOfficialReleaseError as exc:
        raise ValueError(
            f"mutable test_live public Web origin is invalid: {exc}"
        ) from exc

    canonical_package_root = package_root.expanduser().resolve()
    # 身份真相源是 writer 落下的 exact 指针；current 只是兼容投影，
    # 两者同时存在时必须指向同一 release，否则按失败处理。
    expected_release_id, expected_manifest_digest = _exact_active_release(
        package_root=package_root,
        environment=environment,
        public_origin=expected_origin,
    )
    current = package_root.expanduser() / "current"
    if expected_release_id:
        release_root = canonical_package_root / expected_release_id
        if not release_root.is_dir() or release_root.is_symlink():
            raise ValueError(
                "mutable test_live public Web active release is missing"
            )
        if current.is_symlink() and os.readlink(current) != expected_release_id:
            raise ValueError(
                "mutable test_live public Web current projection contradicts the "
                "active release pointer"
            )
    else:
        if not current.is_symlink():
            raise ValueError(
                "mutable test_live public Web package current symlink is missing"
            )
        raw_link = os.readlink(current)
        link_path = Path(raw_link)
        if link_path.is_absolute() or ".." in link_path.parts:
            raise ValueError(
                "mutable test_live public Web package current symlink is unsafe"
            )
        try:
            release_root = current.resolve(strict=True)
            release_root.relative_to(canonical_package_root)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise ValueError(
                "mutable test_live public Web package current symlink escapes its package root"
            ) from exc
        if not release_root.is_dir() or release_root.is_symlink():
            raise ValueError("mutable test_live public Web release root is unsafe")

    manifest_path = release_root / "manifest.json"
    public_root = release_root / "public"
    if (
        not manifest_path.is_file()
        or manifest_path.is_symlink()
        or not public_root.is_dir()
        or public_root.is_symlink()
    ):
        raise ValueError("mutable test_live public Web package is incomplete")
    for path in public_root.rglob("*"):
        if path.is_symlink():
            raise ValueError(
                "mutable test_live public Web package contains a symlink"
            )

    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "mutable test_live public Web package manifest is invalid UTF-8 JSON"
        ) from exc
    if not isinstance(manifest, dict):
        raise ValueError(
            "mutable test_live public Web package manifest must be an object"
        )
    release_id = str(manifest.get("releaseId") or "").strip()
    content_sha256 = str(manifest.get("contentSHA256") or "").strip()
    if (
        manifest.get("schema") != "client-app.web.official-release"
        or manifest.get("environment") != environment
        or manifest.get("publicOrigin") != expected_origin
        or not release_id
        or release_root.name != release_id
        or re.fullmatch(r"[0-9a-f]{64}", content_sha256) is None
    ):
        raise ValueError(
            "mutable test_live public Web package identity does not match the target"
        )
    try:
        _verify_web_build(public_root)
    except WebOfficialReleaseError as exc:
        raise ValueError(
            f"mutable test_live public Web build is invalid: {exc}"
        ) from exc
    actual_content_sha256 = _tree_sha256(public_root)
    if actual_content_sha256 != content_sha256:
        raise ValueError(
            "mutable test_live public Web package content digest drifted"
        )

    manifest_digest = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    if expected_manifest_digest and manifest_digest != expected_manifest_digest:
        raise ValueError(
            "mutable test_live public Web package manifest digest drifted"
        )

    receipt = {
        "environment": environment,
        "packageVersion": release_id,
        "manifestDigest": manifest_digest,
        "contentDigest": "sha256:" + content_sha256,
        "publicOrigin": expected_origin,
    }
    return receipt, public_root


def _resolve_dev_session_public_web_package(
    *,
    environment: str,
    target: str,
    target_contract: Mapping[str, Any],
) -> tuple[dict[str, str], Path]:
    import quwoquan_ops.cli.stackctl as _stackctl

    public_bases = target_contract.get("publicBases") or {}
    return _load_dev_session_public_web_package(
        environment=environment,
        package_root=_stackctl.deployment_target_path(
            target,
            "standalone-packages",
            "web",
            "packages",
            "public-web",
        ),
        public_origin=str(public_bases.get("publicWeb") or ""),
    )
