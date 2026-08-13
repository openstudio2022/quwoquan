"""Alpha/Beta/Gamma Research 身份绑定的物化与加载（逐字搬移）。

``load_local_research_identity_binding`` 是测试的 patch 锚点，包内消费
一律经 ``_pkg.`` 属性访问。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets

import quwoquan_ops.cli.lib.local_environment_auth as _pkg

from pathlib import Path

from .constants import (
    _CROCKFORD_LOWER,
    _RESEARCH_IDENTITY_BINDING_NAME,
    _RESEARCH_IDENTITY_BINDING_SCHEMA,
)
from .guards import _require_mode, _require_nonprod_target


def materialize_local_research_identity_binding(
    *,
    environment: str,
    target_name: str,
    deployment_work_root: str | Path | None = None,
) -> dict[str, str]:
    """Freeze the pre-runtime Research subject/account identity outside source.

    The phone is a target-scoped protected Provider input.  Its canonical
    account identity is deterministic, so User startup can fail closed before
    the first OTP login and the later live login can prove the same subject.
    """

    _require_nonprod_target(environment, target_name)
    secret_root = (
        _pkg._local_environment_secret_path(
            target_name,
            deployment_work_root=deployment_work_root,
        ).parent
    )
    secret_root.mkdir(parents=True, exist_ok=True)
    os.chmod(secret_root, 0o700)
    target_slot = {"alpha-local": "1", "beta-local": "2", "gamma-local": "3"}[
        target_name
    ]
    identity_set_slot = int(
        hashlib.sha256(
            f"{target_name}\0research-identity".encode("utf-8")
        ).hexdigest()[:16],
        16,
    )
    phone = f"+86199{target_slot}{identity_set_slot % 10_000:04d}000"
    subject_hash = "sha256:" + hashlib.sha256(phone.encode("utf-8")).hexdigest()
    account_id = _deterministic_phone_owner_id(target_name, phone)
    payload = {
        "schema": _RESEARCH_IDENTITY_BINDING_SCHEMA,
        "environment": environment,
        "target": target_name,
        "phone": phone,
        "subjectHash": subject_hash,
        "accountId": account_id,
    }
    path = secret_root / _RESEARCH_IDENTITY_BINDING_NAME
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if path.exists():
        existing = _pkg.load_local_research_identity_binding(
            environment=environment,
            target_name=target_name,
            deployment_work_root=deployment_work_root,
        )
        if existing != payload:
            raise RuntimeError("GATE_BLOCK: research identity binding drift")
        return existing
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_CLOEXEC)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError:
        existing = _pkg.load_local_research_identity_binding(
            environment=environment,
            target_name=target_name,
            deployment_work_root=deployment_work_root,
        )
        if existing != payload:
            raise RuntimeError("GATE_BLOCK: research identity binding drift")
        return existing
    finally:
        os.close(fd)
        temporary.unlink(missing_ok=True)
    return payload


def load_local_research_identity_binding(
    *,
    environment: str,
    target_name: str,
    deployment_work_root: str | Path | None = None,
) -> dict[str, str]:
    _require_nonprod_target(environment, target_name)
    secret_root = (
        _pkg._local_environment_secret_path(
            target_name,
            deployment_work_root=deployment_work_root,
        ).parent
    )
    path = secret_root / _RESEARCH_IDENTITY_BINDING_NAME
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("GATE_BLOCK: research identity binding is unavailable")
    _require_mode(path, 0o600)
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected_keys = {
        "schema",
        "environment",
        "target",
        "phone",
        "subjectHash",
        "accountId",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != expected_keys
        or payload.get("schema") != _RESEARCH_IDENTITY_BINDING_SCHEMA
        or payload.get("environment") != environment
        or payload.get("target") != target_name
    ):
        raise RuntimeError("GATE_BLOCK: research identity binding identity mismatch")
    phone = str(payload.get("phone") or "").strip()
    if (
        re.fullmatch(r"\+[1-9][0-9]{7,14}", phone) is None
        or payload.get("subjectHash")
        != "sha256:" + hashlib.sha256(phone.encode("utf-8")).hexdigest()
        or payload.get("accountId") != _deterministic_phone_owner_id(target_name, phone)
    ):
        raise RuntimeError("GATE_BLOCK: research identity binding is invalid")
    return {key: str(payload[key]) for key in expected_keys}


def _deterministic_phone_owner_id(target_name: str, phone: str) -> str:
    digest = hashlib.sha256(
        f"{target_name}\0research-acceptance\0{phone}".encode("utf-8")
    ).digest()
    value = int.from_bytes(digest, "big") >> (256 - 130)
    entropy = "".join(
        _CROCKFORD_LOWER[(value >> shift) & 31]
        for shift in range(125, -1, -5)
    )
    shard = _xxh64(("01|ph|" + entropy).encode("ascii")) % 16384
    return f"uo_01_ph_{shard:04x}_{entropy}"


def _xxh64(value: bytes) -> int:
    """Small canonical XXH64 implementation matching User identity routing."""

    mask = (1 << 64) - 1
    p1, p2, p3, p4, p5 = (
        11400714785074694791,
        14029467366897019727,
        1609587929392839161,
        9650029242287828579,
        2870177450012600261,
    )

    def rotl(number: int, bits: int) -> int:
        return ((number << bits) | (number >> (64 - bits))) & mask

    def round64(accumulator: int, lane: int) -> int:
        accumulator = (accumulator + lane * p2) & mask
        accumulator = rotl(accumulator, 31)
        return (accumulator * p1) & mask

    length = len(value)
    offset = 0
    if length >= 32:
        accumulators = [p1 + p2, p2, 0, (-p1) & mask]
        while offset <= length - 32:
            for index in range(4):
                lane = int.from_bytes(value[offset : offset + 8], "little")
                accumulators[index] = round64(accumulators[index], lane)
                offset += 8
        result = sum(
            rotl(accumulators[index], bits)
            for index, bits in enumerate((1, 7, 12, 18))
        ) & mask
        for accumulator in accumulators:
            mixed = round64(0, accumulator)
            result ^= mixed
            result = (result * p1 + p4) & mask
    else:
        result = p5
    result = (result + length) & mask
    while offset <= length - 8:
        lane = int.from_bytes(value[offset : offset + 8], "little")
        result ^= round64(0, lane)
        result = (rotl(result, 27) * p1 + p4) & mask
        offset += 8
    if offset <= length - 4:
        result ^= int.from_bytes(value[offset : offset + 4], "little") * p1
        result = (rotl(result, 23) * p2 + p3) & mask
        offset += 4
    while offset < length:
        result ^= value[offset] * p5
        result = (rotl(result, 11) * p1) & mask
        offset += 1
    result ^= result >> 33
    result = (result * p2) & mask
    result ^= result >> 29
    result = (result * p3) & mask
    return (result ^ (result >> 32)) & mask
