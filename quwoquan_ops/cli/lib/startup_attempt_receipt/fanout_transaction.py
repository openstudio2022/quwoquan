"""startup receipt 多目的地 fan-out 的事务日志、回滚与恢复（逐字搬移）。

``_secure_read`` / ``_commit_staged_receipt`` / ``_rollback_fanout_transaction`` /
``startup_attempt_path_for_workload`` 依赖是测试的 patch 锚点或跨模块符号，
一律经 ``_pkg.`` 属性访问。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

import quwoquan_ops.cli.lib.startup_attempt_receipt as _pkg

from .constants import (
    _FANOUT_DESTINATION_FIELDS,
    _FANOUT_TRANSACTION_FIELDS,
    _FANOUT_TRANSACTION_SCHEMA,
)
from .receipt_fs import (
    _StagedReceiptWrite,
    _UnsafeStartupReceiptPath,
    _absolute_path,
    _atomic_write_bytes,
    _discard_staged_receipt,
    _encode_json,
    _secure_unlink_if_matches,
    _stage_receipt_bytes,
    _write_transaction_journal_exclusive,
)
from .receipt_contract import validate_startup_attempt


def _fanout_destinations(
    canonical_path: Path,
    payload: Mapping[str, Any],
) -> list[Path]:
    workload = str(payload.get("workload") or "").strip()
    target = str(payload.get("target") or "").strip()
    destinations = [_pkg.startup_attempt_path_for_workload(target, workload)]
    run_root = str(payload.get("runRoot") or "").strip()
    if run_root:
        destinations.append(Path(run_root) / "startup_attempt.json")
    destinations.append(canonical_path)
    normalized = [_absolute_path(item) for item in destinations]
    if len(set(normalized)) != len(normalized):
        raise ValueError("startup attempt receipt fan-out destinations overlap")
    return normalized


def _fanout_transaction_path(canonical_path: Path) -> Path:
    absolute = _absolute_path(canonical_path)
    return absolute.with_name(f".{absolute.name}.fanout-transaction.json")


def _validate_old_receipt_text(
    value: object,
    *,
    expected_env: str,
    expected_target: str,
) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("startup fan-out transaction oldPayload is invalid")
    encoded = value.encode("utf-8")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"startup fan-out transaction oldPayload is unreadable: {exc}"
        ) from exc
    validate_startup_attempt(
        parsed,
        expected_env=expected_env,
        expected_target=expected_target,
    )
    if _encode_json(parsed) != encoded:
        raise ValueError("startup fan-out transaction oldPayload is not canonical")
    return encoded


def _validate_fanout_transaction(
    value: object,
    *,
    canonical_path: Path,
    expected_env: str,
    expected_target: str,
) -> tuple[dict[str, Any], list[tuple[Path, bytes | None]]]:
    if not isinstance(value, dict) or set(value) != _FANOUT_TRANSACTION_FIELDS:
        raise ValueError("startup fan-out transaction fields mismatch")
    if value.get("schema") != _FANOUT_TRANSACTION_SCHEMA:
        raise ValueError("startup fan-out transaction schema mismatch")
    if not str(value.get("transactionId") or "").strip():
        raise ValueError("startup fan-out transaction id is missing")
    new_payload = validate_startup_attempt(
        value.get("newPayload"),
        expected_env=expected_env,
        expected_target=expected_target,
    )
    expected_paths = _fanout_destinations(canonical_path, new_payload)
    raw_destinations = value.get("destinations")
    if not isinstance(raw_destinations, list) or len(raw_destinations) != len(
        expected_paths
    ):
        raise ValueError("startup fan-out transaction destinations mismatch")
    destinations: list[tuple[Path, bytes | None]] = []
    for expected_path, raw_destination in zip(
        expected_paths,
        raw_destinations,
        strict=True,
    ):
        if (
            not isinstance(raw_destination, dict)
            or set(raw_destination) != _FANOUT_DESTINATION_FIELDS
            or raw_destination.get("path") != str(expected_path)
        ):
            raise ValueError("startup fan-out transaction destination is invalid")
        old_payload = _validate_old_receipt_text(
            raw_destination.get("oldPayload"),
            expected_env=expected_env,
            expected_target=expected_target,
        )
        destinations.append((expected_path, old_payload))
    return new_payload, destinations


def _rollback_fanout_transaction(
    value: object,
    *,
    canonical_path: Path,
    expected_env: str,
    expected_target: str,
) -> None:
    new_payload, destinations = _validate_fanout_transaction(
        value,
        canonical_path=canonical_path,
        expected_env=expected_env,
        expected_target=expected_target,
    )
    new_encoded = _encode_json(new_payload)
    errors: list[str] = []
    for destination, old_encoded in reversed(destinations):
        try:
            current = _pkg._secure_read(
                destination,
                label="startup fan-out transaction destination",
            )
            if current == old_encoded:
                continue
            if current != new_encoded:
                raise _UnsafeStartupReceiptPath(
                    f"startup fan-out destination drifted: {destination}"
                )
            if old_encoded is None:
                _secure_unlink_if_matches(destination, new_encoded)
            else:
                _atomic_write_bytes(destination, old_encoded)
        except Exception as exc:  # keep restoring the other replicas
            errors.append(f"{destination}: {exc}")
    if errors:
        raise RuntimeError(
            "startup fan-out rollback could not restore every destination: "
            + "; ".join(errors)
        )


def _recover_fanout_transaction(
    canonical_path: Path,
    *,
    expected_env: str,
    expected_target: str,
) -> None:
    journal_path = _fanout_transaction_path(canonical_path)
    journal_bytes = _pkg._secure_read(
        journal_path,
        label="startup fan-out transaction journal",
    )
    if journal_bytes is None:
        return
    try:
        value = json.loads(journal_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"startup fan-out transaction journal is unreadable: {exc}"
        ) from exc
    _pkg._rollback_fanout_transaction(
        value,
        canonical_path=canonical_path,
        expected_env=expected_env,
        expected_target=expected_target,
    )
    _secure_unlink_if_matches(journal_path, journal_bytes)


def _transactional_fanout_write(
    canonical_path: Path,
    destinations: list[Path],
    payload: Mapping[str, Any],
) -> None:
    expected_env = str(payload["env"])
    expected_target = str(payload["target"])
    encoded = _encode_json(payload)
    old_payloads = [
        _pkg._secure_read(path, label="startup fan-out destination")
        for path in destinations
    ]
    old_payload_texts: list[str | None] = []
    for old in old_payloads:
        if old is None:
            old_payload_texts.append(None)
            continue
        validated_old = _validate_old_receipt_text(
            old.decode("utf-8"),
            expected_env=expected_env,
            expected_target=expected_target,
        )
        assert validated_old is not None
        old_payload_texts.append(validated_old.decode("utf-8"))
    stages: list[_StagedReceiptWrite] = []
    for destination in destinations:
        try:
            stages.append(_stage_receipt_bytes(destination, encoded))
        except Exception:
            for staged in stages:
                _discard_staged_receipt(staged)
            raise

    journal = {
        "schema": _FANOUT_TRANSACTION_SCHEMA,
        "transactionId": uuid4().hex,
        "newPayload": dict(payload),
        "destinations": [
            {
                "path": str(destination),
                "oldPayload": old_text,
            }
            for destination, old_text in zip(
                destinations,
                old_payload_texts,
                strict=True,
            )
        ],
    }
    journal_path = _fanout_transaction_path(canonical_path)
    journal_bytes = _encode_json(journal)
    journal_written = False
    try:
        _write_transaction_journal_exclusive(journal_path, journal_bytes)
        journal_written = True
        for staged in stages:
            _pkg._commit_staged_receipt(staged)
        _secure_unlink_if_matches(journal_path, journal_bytes)
        journal_written = False
    except Exception as original:
        if journal_written:
            try:
                _pkg._rollback_fanout_transaction(
                    journal,
                    canonical_path=canonical_path,
                    expected_env=expected_env,
                    expected_target=expected_target,
                )
                current_journal = _pkg._secure_read(
                    journal_path,
                    label="startup fan-out transaction journal",
                )
                if current_journal is not None:
                    _secure_unlink_if_matches(journal_path, journal_bytes)
            except Exception as rollback_error:
                raise RuntimeError(
                    "startup fan-out commit failed and rollback was incomplete"
                ) from rollback_error
        raise original
    finally:
        for staged in stages:
            _discard_staged_receipt(staged)
