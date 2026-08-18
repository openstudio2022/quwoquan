"""Immutable public Web package resolution shared by both local startup modes.

The Web package is not a member of a runtime candidate, so `compose-up` and the
mutable `test_live` session read the exact same package through this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import re

from pathlib import Path
from typing import Any, Mapping


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
            f"immutable public Web origin is invalid: {exc}"
        ) from exc

    canonical_package_root = package_root.expanduser().resolve()
    current = package_root.expanduser() / "current"
    if not current.is_symlink():
        raise ValueError(
            "immutable public Web package current symlink is missing"
        )
    raw_link = os.readlink(current)
    link_path = Path(raw_link)
    if link_path.is_absolute() or ".." in link_path.parts:
        raise ValueError(
            "immutable public Web package current symlink is unsafe"
        )
    try:
        release_root = current.resolve(strict=True)
        release_root.relative_to(canonical_package_root)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise ValueError(
            "immutable public Web package current symlink escapes its package root"
        ) from exc
    if not release_root.is_dir() or release_root.is_symlink():
        raise ValueError("immutable public Web release root is unsafe")

    manifest_path = release_root / "manifest.json"
    public_root = release_root / "public"
    if (
        not manifest_path.is_file()
        or manifest_path.is_symlink()
        or not public_root.is_dir()
        or public_root.is_symlink()
    ):
        raise ValueError("immutable public Web package is incomplete")
    for path in public_root.rglob("*"):
        if path.is_symlink():
            raise ValueError(
                "immutable public Web package contains a symlink"
            )

    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "immutable public Web package manifest is invalid UTF-8 JSON"
        ) from exc
    if not isinstance(manifest, dict):
        raise ValueError(
            "immutable public Web package manifest must be an object"
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
            "immutable public Web package identity does not match the target"
        )
    try:
        _verify_web_build(public_root)
    except WebOfficialReleaseError as exc:
        raise ValueError(
            f"immutable public Web build is invalid: {exc}"
        ) from exc
    actual_content_sha256 = _tree_sha256(public_root)
    if actual_content_sha256 != content_sha256:
        raise ValueError(
            "immutable public Web package content digest drifted"
        )

    receipt = {
        "environment": environment,
        "packageVersion": release_id,
        "manifestDigest": "sha256:" + hashlib.sha256(manifest_bytes).hexdigest(),
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
        package_root=_stackctl.web_deployment_package_dir(
            environment,
            target=target,
        ),
        public_origin=str(public_bases.get("publicWeb") or ""),
    )
