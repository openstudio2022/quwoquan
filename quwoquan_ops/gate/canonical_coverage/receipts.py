"""覆盖率产物的原子落盘与 provenance receipt 写入/校验。

Receipt 把产物字节、source/test/attribution/config/toolchain/scope 摘要与
HEAD identity 绑定在一起；任何漂移都要求重新 ``--collect``。除 import 重组外
与拆分前逐字一致；被测试 monkeypatch 的符号经包命名空间 ``cc`` 在调用期解析。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import quwoquan_ops.gate.canonical_coverage as cc

from .constants import (
    ARTIFACT_RECEIPT_DIGEST_FIELDS,
    ARTIFACT_RECEIPT_FIELDS,
    ARTIFACT_RECEIPT_SCHEMA,
    GIT_OBJECT_RE,
    RULE_ID,
    SHA256_DIGEST_RE,
    CoverageError,
    _display,
)
from .provenance import artifact_path, artifact_receipt_path, _sha256_file, _canonical_json_digest


def _write_text_atomic(path: Path, text: str) -> None:
    """整份替换落盘；半截产物会被 receipt 的 artifactDigest 当成合法输入。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _write_artifact_receipt(
    target: str,
    *,
    tests_green: bool,
    identity: dict[str, str] | None = None,
) -> dict:
    path = artifact_path(target)
    if not path.is_file() or path.is_symlink():
        raise CoverageError(f"覆盖率采集没有安全产物: {_display(path)}")
    payload: dict[str, object] = {
        "schema": ARTIFACT_RECEIPT_SCHEMA,
        "ruleId": RULE_ID,
        "target": target,
        "artifactRef": _display(path),
        "artifactDigest": _sha256_file(path),
        **(identity or cc.current_collection_identity(target)),
        "testsGreen": tests_green,
    }
    _write_json_atomic(artifact_receipt_path(target), payload)
    return payload


def receipt_digest(payload: dict) -> str:
    """Receipt 的内容寻址 identity；不依赖 JSON 缩进或字段顺序。"""
    return _canonical_json_digest(payload)


def _validate_receipt_payload(
    payload: object,
    *,
    expected_target: str | None = None,
    require_green: bool,
) -> dict:
    if not isinstance(payload, dict) or set(payload) != ARTIFACT_RECEIPT_FIELDS:
        raise CoverageError("覆盖率 provenance receipt fields mismatch")
    if payload.get("schema") != ARTIFACT_RECEIPT_SCHEMA:
        raise CoverageError("覆盖率 provenance receipt schema mismatch")
    if payload.get("ruleId") != RULE_ID:
        raise CoverageError("覆盖率 provenance receipt ruleId mismatch")
    target = payload.get("target")
    if not isinstance(target, str) or not target:
        raise CoverageError("覆盖率 provenance receipt target 非法")
    if expected_target is not None and target != expected_target:
        raise CoverageError(
            f"覆盖率 provenance receipt target 漂移: {target!r} != {expected_target!r}"
        )
    try:
        expected_artifact_ref = _display(artifact_path(target))
    except (KeyError, ValueError, CoverageError) as error:
        raise CoverageError(
            f"覆盖率 provenance receipt target 不可复核: {target!r}"
        ) from error
    if payload.get("artifactRef") != expected_artifact_ref:
        raise CoverageError("覆盖率 provenance receipt artifactRef mismatch")
    malformed_digests = sorted(
        key
        for key in ARTIFACT_RECEIPT_DIGEST_FIELDS
        if SHA256_DIGEST_RE.fullmatch(str(payload.get(key) or "")) is None
    )
    if malformed_digests:
        raise CoverageError(
            "覆盖率 provenance digest 非 canonical sha256（"
            + ", ".join(malformed_digests)
            + "）"
        )
    malformed_git = sorted(
        key
        for key in ("headCommit", "headTree")
        if GIT_OBJECT_RE.fullmatch(str(payload.get(key) or "")) is None
    )
    if malformed_git:
        raise CoverageError(
            "覆盖率 provenance git identity 非 canonical object id（"
            + ", ".join(malformed_git)
            + "）"
        )
    if not isinstance(payload.get("testsGreen"), bool):
        raise CoverageError("覆盖率 provenance testsGreen 必须是 boolean")
    if require_green and payload.get("testsGreen") is not True:
        raise CoverageError("覆盖率产物来自未全绿测试，不构成准出证据")
    return payload


def validate_artifact_receipt(target: str) -> dict:
    path = artifact_path(target)
    receipt_path = artifact_receipt_path(target)
    if not path.is_file():
        raise CoverageError(f"缺少覆盖率产物 {_display(path)}；先跑一次 --collect")
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise CoverageError(
            f"覆盖率产物缺少 provenance receipt {_display(receipt_path)}；"
            "旧产物不可复用，必须重新 --collect"
        )
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CoverageError(f"覆盖率 provenance receipt 无法读取: {error}") from error
    payload = _validate_receipt_payload(
        payload, expected_target=target, require_green=False
    )
    expected = {
        "schema": ARTIFACT_RECEIPT_SCHEMA,
        "ruleId": RULE_ID,
        "target": target,
        "artifactRef": _display(path),
        "artifactDigest": _sha256_file(path),
        **cc.current_collection_identity(target),
    }
    drifted = sorted(
        key for key, value in expected.items() if payload.get(key) != value
    )
    if drifted:
        raise CoverageError(
            "覆盖率产物 provenance 已陈旧（"
            + ", ".join(drifted)
            + "）；当前源码/测试/归属/采集范围必须重新 --collect"
        )
    if payload.get("testsGreen") is not True:
        raise CoverageError("覆盖率产物来自未全绿测试，不构成准出证据")
    return payload
