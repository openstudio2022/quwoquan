"""三份 seal receipt 链的 exact-byte 校验与封存。

链固定为 001-1.download → 002-4.draft → 003-5.review，每份 receipt 的 predecessor 绑定前一份的
exact bytes，resultRefs 绑定产物 exact bytes。校验一次读取，既服务 publish（需要 3 份且 review
approved），也服务 release handoff（内嵌封存字节后离线重放）。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import stat
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from core.control_types import AUTHOR_ARTIFACT_BY_CARRIER, RECEIPT_STAGE_SEQUENCE, carrier_of_target_ref
from core.schema import assert_valid

_STAGES = tuple(stage.value for stage in RECEIPT_STAGE_SEQUENCE)
_RECEIPT_DIRECTORY = "_shared/receipts"
FULL_CHAIN_LENGTH = len(_STAGES)


class ReceiptChainError(ValueError):
    """receipt 链不是精确的 canonical 字节链。"""


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _safe_ref(value: object, *, label: str) -> str:
    text = str(value or "")
    ref = PurePosixPath(text)
    if not text or "\x00" in text or ref.is_absolute() or text != ref.as_posix() or any(part in {"", ".", ".."} for part in ref.parts):
        raise ReceiptChainError(f"{label} 不是安全相对引用：{text!r}")
    return text


def _assert_no_symlink(path: Path, *, label: str, regular: bool) -> Path:
    absolute = Path(os.path.abspath(path.expanduser()))
    current = Path(absolute.anchor)
    try:
        for part in absolute.parts[1:]:
            current = current / part
            if stat.S_ISLNK(os.lstat(current).st_mode):
                raise ReceiptChainError(f"{label} 不得包含 symlink：{path}")
    except FileNotFoundError as exc:
        raise ReceiptChainError(f"{label} 不存在：{path}") from exc
    if regular and not absolute.is_file():
        raise ReceiptChainError(f"{label} 必须是 regular file：{path}")
    if not regular and not absolute.is_dir():
        raise ReceiptChainError(f"{label} 必须是目录：{path}")
    return absolute


def _read_regular(path: Path, *, label: str) -> bytes:
    return _assert_no_symlink(path, label=label, regular=True).read_bytes()


def _parse_receipt(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptChainError(f"{label} 不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise ReceiptChainError(f"{label} 必须是 JSON 对象")
    try:
        assert_valid(value, "execution", "stage_receipt", label=label)
    except (TypeError, ValueError) as exc:
        raise ReceiptChainError(str(exc)) from exc
    if raw != canonical_bytes(value):
        raise ReceiptChainError(f"{label} 不是 canonical JSON")
    return value


def _binding_key(binding: Mapping[str, Any], *, label: str) -> tuple[str, str, str]:
    scope = str(binding.get("scope") or "")
    if scope != "execution":
        raise ReceiptChainError(f"{label} scope 非法：{scope!r}")
    ref = _safe_ref(binding.get("ref"), label=label)
    digest = str(binding.get("digest") or "")
    if not digest.startswith("sha256:") or len(digest) != 71:
        raise ReceiptChainError(f"{label} digest 非法")
    return scope, ref, digest


@dataclass(frozen=True, slots=True)
class ValidatedReceiptChain:
    execution_id: str
    receipts: tuple[dict[str, Any], ...]
    receipt_raws: tuple[bytes, ...]
    frozen_references: tuple[dict[str, str], ...]

    @property
    def terminal_receipt(self) -> dict[str, Any]:
        return self.receipts[-1]

    @property
    def terminal_raw(self) -> bytes:
        return self.receipt_raws[-1]

    def sealed_document(
        self,
        *,
        include_reference: Callable[[Mapping[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        frozen = self.frozen_references if include_reference is None else tuple(
            row for row in self.frozen_references if include_reference(row)
        )
        return {
            "executionId": self.execution_id,
            "receipts": list(self.receipts),
            "frozenReferences": list(frozen),
        }


def _validate_documents(
    *,
    execution_id: str,
    receipts: Sequence[tuple[dict[str, Any], bytes]],
    resolve: Callable[[Mapping[str, Any], str], bytes],
    expected_count: int | None,
    terminal_verdict: str | None,
    snapshot_omissions: set[tuple[str, str, str]],
) -> ValidatedReceiptChain:
    if not receipts:
        raise ReceiptChainError("receipt 链必须非空")
    if expected_count is not None and len(receipts) != expected_count:
        raise ReceiptChainError(f"receipt 链长度必须为 {expected_count}")
    if len(receipts) > len(_STAGES):
        raise ReceiptChainError("receipt 链超出 canonical stage 数量")

    captured: dict[tuple[str, str, str], dict[str, str]] = {}
    used: set[tuple[str, str, str]] = set()

    def verify_ref(binding: Mapping[str, Any], *, label: str) -> None:
        key = _binding_key(binding, label=label)
        raw = resolve(binding, label)
        if digest_bytes(raw) != key[2]:
            raise ReceiptChainError(f"{label} exact bytes digest 漂移")
        used.add(key)
        if key not in snapshot_omissions:
            captured.setdefault(key, {
                "scope": key[0], "ref": key[1], "digest": key[2],
                "contentBase64": base64.b64encode(raw).decode("ascii"),
            })

    predecessor: dict[str, str] | None = None
    for index, (receipt, raw) in enumerate(receipts, start=1):
        stage = _STAGES[index - 1]
        name = f"{index:03d}-{stage}.json"
        if raw != canonical_bytes(receipt):
            raise ReceiptChainError(f"{name} embedded canonical bytes 漂移")
        if (
            receipt.get("executionId") != execution_id
            or receipt.get("stage") != stage
            or receipt.get("sequence") != index
            or receipt.get("predecessor") != predecessor
        ):
            raise ReceiptChainError(f"receipt identity/sequence/predecessor 漂移：{name}")
        if index < len(receipts) and receipt.get("verdict") != "pass":
            raise ReceiptChainError(f"非 terminal receipt 必须为 pass：{name}")
        for binding in receipt.get("resultRefs") or []:
            verify_ref(binding, label=f"{execution_id} {name} resultRefs")
        predecessor = {"scope": "execution", "ref": f"{_RECEIPT_DIRECTORY}/{name}", "digest": digest_bytes(raw)}

    if terminal_verdict is not None and receipts[-1][0].get("verdict") != terminal_verdict:
        raise ReceiptChainError(f"terminal receipt 必须为 {terminal_verdict}")
    if used != set(captured) | snapshot_omissions:
        raise ReceiptChainError("sealed ref omission 与实际使用引用不一致")
    ordered = tuple(captured[key] for key in sorted(captured))
    return ValidatedReceiptChain(
        execution_id=execution_id,
        receipts=tuple(value for value, _raw in receipts),
        receipt_raws=tuple(raw for _value, raw in receipts),
        frozen_references=ordered,
    )


def validate_live_receipt_chain(
    *,
    execution_id: str,
    execution_root: Path,
    repo_root: Path | None = None,
    output_root: Path | None = None,
    expected_count: int | None = None,
    terminal_verdict: str | None = None,
    snapshot_omissions: set[tuple[str, str, str]] | None = None,
) -> ValidatedReceiptChain:
    """一次读取并校验 live receipt 链与全部冻结引用。"""

    del repo_root, output_root
    root = _assert_no_symlink(execution_root, label=f"execution:{execution_id}", regular=False)
    directory = _assert_no_symlink(root / _RECEIPT_DIRECTORY, label="receipts", regular=False)
    entries = [path for path in directory.iterdir() if not path.name.startswith(".")]
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise ReceiptChainError("receipts 目录只能包含 regular files")
    names = {path.name for path in entries}
    if not names:
        raise ReceiptChainError("receipt 链必须非空")
    count = len(names)
    expected_names = {f"{index:03d}-{stage}.json" for index, stage in enumerate(_STAGES[:count], 1)}
    if names != expected_names:
        raise ReceiptChainError("receipt 必须是 canonical 连续前缀")
    receipts: list[tuple[dict[str, Any], bytes]] = []
    for index, stage in enumerate(_STAGES[:count], 1):
        name = f"{index:03d}-{stage}.json"
        raw = _read_regular(directory / name, label=f"receipt:{name}")
        receipts.append((_parse_receipt(raw, label=f"receipt:{name}"), raw))

    def resolve(binding: Mapping[str, Any], label: str) -> bytes:
        _scope, ref, _digest = _binding_key(binding, label=label)
        return _read_regular(root / ref, label=label)

    return _validate_documents(
        execution_id=execution_id,
        receipts=receipts,
        resolve=resolve,
        expected_count=expected_count,
        terminal_verdict=terminal_verdict,
        snapshot_omissions=snapshot_omissions or set(),
    )


def validate_embedded_receipt_chain(
    document: Mapping[str, Any],
    *,
    external_bytes: Mapping[tuple[str, str, str], bytes],
    expected_count: int | None = None,
    terminal_verdict: str | None = None,
) -> ValidatedReceiptChain:
    """只用内嵌封存字节离线重放一条链。"""

    execution_id = str(document.get("executionId") or "")
    receipt_values = document.get("receipts")
    frozen_values = document.get("frozenReferences")
    if not isinstance(receipt_values, list) or not isinstance(frozen_values, list):
        raise ReceiptChainError("embedded receipt chain shape 非法")
    snapshots: dict[tuple[str, str, str], bytes] = {}
    for row in frozen_values:
        if not isinstance(row, Mapping) or set(row) != {"scope", "ref", "digest", "contentBase64"}:
            raise ReceiptChainError("embedded frozenReferences shape 非法")
        key = _binding_key(row, label="embedded frozenReference")
        try:
            raw = base64.b64decode(str(row.get("contentBase64") or ""), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ReceiptChainError("embedded frozenReference base64 非法") from exc
        if digest_bytes(raw) != key[2] or key in snapshots:
            raise ReceiptChainError("embedded frozenReference digest/唯一性漂移")
        snapshots[key] = raw

    def resolve(binding: Mapping[str, Any], label: str) -> bytes:
        key = _binding_key(binding, label=label)
        if key in external_bytes:
            return external_bytes[key]
        try:
            return snapshots[key]
        except KeyError as exc:
            raise ReceiptChainError(f"{label} 缺少 sealed exact bytes") from exc

    receipts = [(dict(value), canonical_bytes(value)) for value in receipt_values if isinstance(value, Mapping)]
    if len(receipts) != len(receipt_values):
        raise ReceiptChainError("embedded receipt document 非法")
    validated = _validate_documents(
        execution_id=execution_id,
        receipts=receipts,
        resolve=resolve,
        expected_count=expected_count,
        terminal_verdict=terminal_verdict,
        snapshot_omissions=set(external_bytes),
    )
    if {(row["scope"], row["ref"], row["digest"]) for row in validated.frozen_references} != set(snapshots):
        raise ReceiptChainError("embedded frozenReferences 包含未使用或缺失字节")
    return validated


def _independent_actors(author: Mapping[str, Any], reviewer: Mapping[str, Any]) -> None:
    if (author.get("host"), author.get("sessionId")) == (reviewer.get("host"), reviewer.get("sessionId")):
        raise ReceiptChainError("author 与 reviewer 使用同一 host/sessionId")
    author_run = str((author.get("invocation") or {}).get("runId") or "").strip()
    reviewer_run = str((reviewer.get("invocation") or {}).get("runId") or "").strip()
    if not author_run or not reviewer_run or author_run == reviewer_run:
        raise ReceiptChainError("author 与 reviewer 使用同一 invocation.runId")


def validate_publish_review_chain(
    *,
    execution_id: str,
    execution_root: Path,
    target_ref: str,
    repo_root: Path | None = None,
    output_root: Path | None = None,
) -> tuple[ValidatedReceiptChain, dict[str, Any]]:
    """publish 前置：三份 receipt 全部 pass，且该对象 content_review approved 并被 exact 绑定。"""

    del repo_root, output_root
    chain = validate_live_receipt_chain(
        execution_id=execution_id,
        execution_root=execution_root,
        expected_count=FULL_CHAIN_LENGTH,
        terminal_verdict="pass",
    )
    author_receipt = chain.receipts[_STAGES.index("4.draft")]
    review_receipt = chain.receipts[_STAGES.index("5.review")]
    _independent_actors(author_receipt.get("actor") or {}, review_receipt.get("actor") or {})

    normalized_ref = str(target_ref or "").strip().strip("/")
    carrier = carrier_of_target_ref(normalized_ref)
    draft_ref = f"{normalized_ref}/4.draft/{AUTHOR_ARTIFACT_BY_CARRIER[carrier]}"
    review_ref = f"{normalized_ref}/5.review/content_review.json"
    if not any(row.get("ref") == draft_ref for row in author_receipt.get("resultRefs") or []):
        raise ReceiptChainError("author receipt 未绑定该对象的产物")
    review_raw = _read_regular(execution_root / review_ref, label=review_ref)
    try:
        review = json.loads(review_raw)
        assert_valid(review, "content", "content_review", label=review_ref)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ReceiptChainError(f"{review_ref}: {exc}") from exc
    if review.get("executionId") != execution_id or review.get("objectRef") != normalized_ref:
        raise ReceiptChainError("content_review target identity drift")
    expected = {"scope": "execution", "ref": review_ref, "digest": digest_bytes(review_raw)}
    if sum(1 for row in review_receipt.get("resultRefs") or [] if row == expected) != 1:
        raise ReceiptChainError("review receipt 未 exact 绑定 content_review")
    if review.get("decision") != "approved":
        raise ReceiptChainError("content_review is not approved")
    return chain, review


__all__ = [
    "FULL_CHAIN_LENGTH",
    "ReceiptChainError",
    "ValidatedReceiptChain",
    "canonical_bytes",
    "digest_bytes",
    "validate_embedded_receipt_chain",
    "validate_live_receipt_chain",
    "validate_publish_review_chain",
]
