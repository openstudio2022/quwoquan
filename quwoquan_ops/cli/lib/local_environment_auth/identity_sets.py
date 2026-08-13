"""受保护 test-data 身份集（电话池）的物化、读取与原子写入（逐字搬移）。

``_test_data_identity_set_path`` / ``_test_data_actor_phone`` /
``materialize_test_data_identity_set`` 是测试的 patch 锚点，包内消费一律经
``_pkg.`` 属性访问。
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Any

import quwoquan_ops.cli.lib.local_environment_auth as _pkg

from ..output_paths import deployment_target_path
from .constants import (
    _TEST_DATA_IDENTITY_SET_LOCK_NAME,
    _TEST_DATA_IDENTITY_SET_NAME,
    _TEST_DATA_IDENTITY_SET_PATH_ENV,
    _TEST_DATA_IDENTITY_SET_SCHEMA,
    _TEST_DATA_PHONE_PROFILES,
)
from .guards import _canonical_actor_role, _require_nonprod_target


def materialize_test_data_identity_set(
    *,
    environment: str,
    target_name: str,
    identity_set_id: str,
    actor_count: int,
    phone_profile: str = "nonroutable",
) -> Path:
    """Materialize protected OTP inputs for one isolated test-data identity set.

    These values are transport credentials for the local SMS capture Provider,
    not reusable business accounts. The file is target-scoped, mode 0600 and
    contains no access or refresh token.
    """

    _require_nonprod_target(environment, target_name)
    canonical_identity_set_id = _canonical_actor_role(identity_set_id)
    if phone_profile not in _TEST_DATA_PHONE_PROFILES:
        raise ValueError("unsupported test-data phone profile")
    if (
        isinstance(actor_count, bool)
        or not isinstance(actor_count, int)
        or actor_count <= 0
        or actor_count > 1000
    ):
        raise ValueError("test-data actor count must be within 1..1000")

    secret_root, path = _pkg._test_data_identity_set_path(target_name)
    secret_root.mkdir(parents=True, exist_ok=True)
    os.chmod(secret_root, 0o700)
    lock_path = secret_root / _TEST_DATA_IDENTITY_SET_LOCK_NAME
    lock_flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        lock_flags |= os.O_NOFOLLOW
    lock_fd = os.open(lock_path, lock_flags, 0o600)
    try:
        lock_stat = os.fstat(lock_fd)
        if not stat.S_ISREG(lock_stat.st_mode):
            raise RuntimeError("test-data identity set lock is not regular")
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        existing_identity: tuple[int, int] | None = None
        if path.exists() or path.is_symlink():
            payload, existing_identity = _read_test_data_identity_set(
                path,
                target_name=target_name,
            )
        else:
            payload = {
                "schema": _TEST_DATA_IDENTITY_SET_SCHEMA,
                "target": target_name,
                "identitySetPhones": {},
            }
        identity_sets = payload["identitySetPhones"]
        target_slot = {
            "alpha-local": "1",
            "beta-local": "2",
            "gamma-local": "3",
        }[target_name]
        identity_set_slot = int(
            hashlib.sha256(
                f"{target_name}\0{canonical_identity_set_id}".encode("utf-8")
            ).hexdigest()[:16],
            16,
        )
        existing_phones = identity_sets.get(canonical_identity_set_id)
        phone_count = max(
            actor_count,
            len(existing_phones) if isinstance(existing_phones, list) else 0,
        )
        if phone_profile == "mainland_ui":
            canonical_phones = [
                f"+86199{target_slot}{identity_set_slot % 10_000:04d}{index:03d}"
                for index in range(phone_count)
            ]
        else:
            canonical_phones = [
                f"+999{target_slot}{identity_set_slot % 100_000_000:08d}{index:03d}"
                for index in range(phone_count)
            ]
        if existing_phones is not None:
            phones = existing_phones
            if phones != canonical_phones[: len(phones)]:
                raise RuntimeError(
                    "test-data identity set is incomplete or does not match "
                    f"the canonical prefix for {canonical_identity_set_id}"
                )
            if len(phones) >= actor_count:
                return path
        updated = {
            "schema": _TEST_DATA_IDENTITY_SET_SCHEMA,
            "target": target_name,
            "identitySetPhones": {
                **identity_sets,
                canonical_identity_set_id: canonical_phones[:actor_count],
            },
        }
        _validate_test_data_identity_set(
            updated,
            target_name=target_name,
        )
        _atomic_write_test_data_identity_set(
            path,
            updated,
            existing_identity=existing_identity,
        )
        return path
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def materialize_local_capture_ui_acceptance_phone(
    *,
    environment: str,
    target_name: str,
    actor_index: int = 0,
) -> str:
    """Return one protected +86 identity for local-capture App UAT only.

    The phone shape matches the App's fixed +86 input, while the selected
    Provider remains the non-promotable local capture substitute.  The value
    is stored only in the target-scoped mode-0600 identity pool.
    """

    if (
        isinstance(actor_index, bool)
        or not isinstance(actor_index, int)
        or actor_index < 0
        or actor_index >= 1000
    ):
        raise ValueError("local-capture UI actor index must be within 0..999")
    identity_set_id = "provider-ui-sms"
    _pkg.materialize_test_data_identity_set(
        environment=environment,
        target_name=target_name,
        identity_set_id=identity_set_id,
        actor_count=actor_index + 1,
        phone_profile="mainland_ui",
    )
    return _pkg._test_data_actor_phone(
        target_name=target_name,
        identity_set_id=identity_set_id,
        actor_index=actor_index,
    )


def _test_data_identity_set_path(
    target_name: str,
) -> tuple[Path, Path]:
    secret_root = deployment_target_path(target_name, "secrets").resolve()
    raw_path = os.environ.get(_TEST_DATA_IDENTITY_SET_PATH_ENV, "").strip()
    if raw_path:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            raise RuntimeError("test-data identity set path must be absolute")
        path = path.parent.resolve() / path.name
    else:
        path = secret_root / _TEST_DATA_IDENTITY_SET_NAME
    try:
        path.parent.resolve().relative_to(secret_root)
    except ValueError as exc:
        raise RuntimeError(
            "test-data identity set parent must remain under the target secret root"
        ) from exc
    try:
        path.relative_to(secret_root)
    except ValueError as exc:
        raise RuntimeError(
            "test-data identity set must be target-scoped under the deploy secret root"
        ) from exc
    return secret_root, path


def _validate_test_data_identity_set(
    payload: object,
    *,
    target_name: str,
) -> dict[str, list[str]]:
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != _TEST_DATA_IDENTITY_SET_SCHEMA
        or payload.get("target") != target_name
        or set(payload) != {"schema", "target", "identitySetPhones"}
    ):
        raise RuntimeError("test-data identity set identity mismatch")
    raw_identity_sets = payload.get("identitySetPhones")
    if not isinstance(raw_identity_sets, dict):
        raise RuntimeError("test-data identity sets are invalid")
    identity_sets: dict[str, list[str]] = {}
    all_phones: list[str] = []
    for raw_identity_set_id, raw_phones in raw_identity_sets.items():
        identity_set_id = _canonical_actor_role(str(raw_identity_set_id))
        if identity_set_id != raw_identity_set_id or not isinstance(raw_phones, list):
            raise RuntimeError("test-data identity set entry is invalid")
        phones = [str(value).strip() for value in raw_phones]
        if any(
            re.fullmatch(r"\+[1-9][0-9]{7,14}", phone) is None
            for phone in phones
        ):
            raise RuntimeError(
                "test-data identity set contains invalid E.164 phone"
            )
        identity_sets[identity_set_id] = phones
        all_phones.extend(phones)
    if len(all_phones) != len(set(all_phones)):
        raise RuntimeError("test-data identity set contains duplicate phones")
    return identity_sets


def _read_test_data_identity_set(
    path: Path,
    *,
    target_name: str,
) -> tuple[dict[str, Any], tuple[int, int]]:
    if path.is_symlink():
        raise RuntimeError("test-data identity set cannot be a symlink")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError("test-data identity set cannot be opened safely") from exc
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise RuntimeError("test-data identity set must use mode 0600")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
            try:
                payload = json.load(handle)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "test-data identity set is invalid JSON"
                ) from exc
        identity_sets = _validate_test_data_identity_set(
            payload,
            target_name=target_name,
        )
        payload["identitySetPhones"] = identity_sets
        return payload, (metadata.st_dev, metadata.st_ino)
    finally:
        os.close(fd)


def _atomic_write_test_data_identity_set(
    path: Path,
    payload: dict[str, Any],
    *,
    existing_identity: tuple[int, int] | None,
) -> None:
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        encoded = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

        try:
            destination_stat = os.stat(path, follow_symlinks=False)
        except FileNotFoundError:
            destination_identity = None
        else:
            if not stat.S_ISREG(destination_stat.st_mode):
                raise RuntimeError("test-data identity set destination is unsafe")
            destination_identity = (
                destination_stat.st_dev,
                destination_stat.st_ino,
            )
        if destination_identity != existing_identity:
            raise RuntimeError("test-data identity set changed during materialization")
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_CLOEXEC)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _test_data_actor_phone(
    *,
    target_name: str,
    identity_set_id: str,
    actor_index: int,
) -> str:
    _secret_root, path = _pkg._test_data_identity_set_path(target_name)
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(
            "GATE_BLOCK: test-data identity set is missing under the target "
            f"secret root (set {_TEST_DATA_IDENTITY_SET_PATH_ENV} or materialize "
            "secrets/test-data-identity-set.json)"
        )
    payload, _identity = _read_test_data_identity_set(
        path,
        target_name=target_name,
    )
    identity_sets = payload["identitySetPhones"]
    phones = identity_sets.get(identity_set_id)
    if not isinstance(phones, list) or actor_index >= len(phones):
        raise RuntimeError(
            f"test-data identity set is incomplete for {identity_set_id}"
        )
    phone = str(phones[actor_index]).strip()
    return phone
