"""Validate the external Android runtime trust authority for dependency sync."""

from __future__ import annotations

import json
import stat
from pathlib import Path

from quwoquan_ops.cli.lib.app_dependency_sync_diagnostics import (
    dependency_failure_cause,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_fs import (
    assert_real_directory,
    read_regular_nofollow,
)


def validated_runtime_trust_root(
    raw: Path, *, repo_root: Path
) -> tuple[Path, tuple[str, ...]]:
    expanded = Path(raw).expanduser()
    if not expanded.is_absolute():
        raise ValueError(
            "APP.DEPENDENCY.android_runtime_trust_root_invalid: "
            "explicit trust root must be absolute"
        )
    try:
        root = expanded.resolve(strict=True)
        assert_real_directory(root, label="Android runtime trust root")
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(
            "APP.DEPENDENCY.android_runtime_trust_root_invalid: "
            "trust root is unavailable or unsafe"
        ) from exc
    repository = repo_root.expanduser().resolve(strict=False)
    if root == repository or root.is_relative_to(repository):
        raise ValueError(
            "APP.DEPENDENCY.android_runtime_trust_root_invalid: "
            "trust root must stay outside the repository"
        )
    root_metadata = root.stat(follow_symlinks=False)
    if stat.S_IMODE(root_metadata.st_mode) != 0o700:
        raise ValueError("APP.DEPENDENCY.android_runtime_trust_permissions_invalid")
    trust_directory = root / "qwq_runtime"
    try:
        assert_real_directory(
            trust_directory,
            label="Android runtime trust directory",
        )
    except (RuntimeError, ValueError) as exc:
        raise ValueError(
            "APP.DEPENDENCY.android_runtime_trust_root_invalid: "
            "trust directory is unavailable or unsafe"
        ) from exc
    if stat.S_IMODE(trust_directory.stat(follow_symlinks=False).st_mode) != 0o700:
        raise ValueError("APP.DEPENDENCY.android_runtime_trust_permissions_invalid")
    trust_path = root / "qwq_runtime/runtime-config-trust.json"
    try:
        encoded, _mode = read_regular_nofollow(
            trust_path,
            label="Android runtime trust envelope",
        )
    except (RuntimeError, ValueError) as exc:
        raise ValueError(
            "APP.DEPENDENCY.android_runtime_trust_root_invalid: "
            "trust envelope is unavailable or unsafe"
        ) from exc
    trust_metadata = trust_path.stat(follow_symlinks=False)
    if (
        not encoded
        or not stat.S_ISREG(trust_metadata.st_mode)
        or trust_metadata.st_nlink != 1
        or stat.S_IMODE(trust_metadata.st_mode) != 0o600
    ):
        raise ValueError("APP.DEPENDENCY.android_runtime_trust_permissions_invalid")
    try:
        payload = json.loads(encoded)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "APP.DEPENDENCY.android_runtime_trust_invalid: "
            f"cause={dependency_failure_cause(exc)}"
        ) from exc
    keyring = payload.get("trustedPublicKeys") if isinstance(payload, dict) else None
    key_values = (
        tuple(str(item) for pair in keyring.items() for item in pair if str(item))
        if isinstance(keyring, dict)
        else ()
    )
    return root, (str(root), str(trust_path), *key_values)
