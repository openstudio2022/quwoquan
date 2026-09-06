"""Canonical OPEN/CLOSE receipt-chain byte validation and sealing helpers."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from core.control_types import RECEIPT_STAGE_SEQUENCE
from core.schema import assert_valid

_STAGES = tuple(stage.value for stage in RECEIPT_STAGE_SEQUENCE)
_OPEN_DIRECTORY = "_shared/stage-open"
_RECEIPT_DIRECTORY = "_shared/receipts"


class ReceiptChainError(ValueError):
    """The receipt chain is not an exact canonical byte chain."""


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def digest_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _safe_ref(value: object, *, label: str) -> str:
    text = str(value or "")
    ref = PurePosixPath(text)
    if (
        not text
        or "\x00" in text
        or ref.is_absolute()
        or text != ref.as_posix()
        or any(part in {"", ".", ".."} for part in ref.parts)
    ):
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


def _parse_canonical_document(
    raw: bytes, *, schema_name: str, label: str
) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptChainError(f"{label} 不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise ReceiptChainError(f"{label} 必须是 JSON 对象")
    try:
        assert_valid(value, "execution", schema_name, label=label)
    except (TypeError, ValueError) as exc:
        raise ReceiptChainError(str(exc)) from exc
    if raw != canonical_bytes(value):
        raise ReceiptChainError(f"{label} 不是 canonical JSON")
    return value


def _binding_key(binding: Mapping[str, Any], *, label: str) -> tuple[str, str, str]:
    scope = str(binding.get("scope") or "")
    if scope not in {"execution", "output", "repo"}:
        raise ReceiptChainError(f"{label} scope 非法：{scope!r}")
    ref = _safe_ref(binding.get("ref"), label=label)
    digest = str(binding.get("digest") or "")
    if not digest.startswith("sha256:") or len(digest) != 71:
        raise ReceiptChainError(f"{label} digest 非法")
    return scope, ref, digest


def _actor(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReceiptChainError(f"{label} actor 非法")
    return dict(value)


def _input_refs(
    value: object, *, label: str, allow_actor: bool = False
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ReceiptChainError(f"{label} 必须是数组")
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in value:
        if not isinstance(row, Mapping):
            raise ReceiptChainError(f"{label} 元素必须是对象")
        allowed_shapes = ({"scope", "ref"}, {"scope", "ref", "actor"})
        if set(row) not in (allowed_shapes if allow_actor else allowed_shapes[:1]):
            raise ReceiptChainError(f"{label} 元素字段非法")
        scope = str(row.get("scope") or "")
        ref = _safe_ref(row.get("ref"), label=label)
        key = (scope, ref)
        if scope not in {"execution", "output", "repo"} or key in seen:
            raise ReceiptChainError(f"{label} scope 或唯一性非法")
        seen.add(key)
        item: dict[str, Any] = {"scope": scope, "ref": ref}
        if "actor" in row:
            item["actor"] = _actor(row.get("actor"), label=label)
        result.append(item)
    return result


def _frozen_refs(
    value: object, *, label: str, allow_actor: bool = False
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ReceiptChainError(f"{label} 必须是数组")
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in value:
        if not isinstance(row, Mapping):
            raise ReceiptChainError(f"{label} 元素必须是对象")
        allowed_shapes = (
            {"scope", "ref", "digest"},
            {"scope", "ref", "digest", "actor"},
        )
        if set(row) not in (allowed_shapes if allow_actor else allowed_shapes[:1]):
            raise ReceiptChainError(f"{label} 元素字段非法")
        scope, ref, digest = _binding_key(row, label=label)
        key = (scope, ref)
        if key in seen:
            raise ReceiptChainError(f"{label} 含重复引用：{scope}:{ref}")
        seen.add(key)
        item: dict[str, Any] = {"scope": scope, "ref": ref, "digest": digest}
        if "actor" in row:
            item["actor"] = _actor(row.get("actor"), label=label)
        result.append(item)
    return result


@dataclass(frozen=True, slots=True)
class ValidatedReceiptChain:
    execution_id: str
    open_requests: tuple[dict[str, Any], ...]
    receipts: tuple[dict[str, Any], ...]
    open_raws: tuple[bytes, ...]
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
        frozen_references = (
            self.frozen_references
            if include_reference is None
            else tuple(
                row for row in self.frozen_references if include_reference(row)
            )
        )
        return {
            "executionId": self.execution_id,
            "openRequests": list(self.open_requests),
            "receipts": list(self.receipts),
            "frozenReferences": list(frozen_references),
        }


def _validate_documents(
    *,
    execution_id: str,
    opens: Sequence[tuple[dict[str, Any], bytes]],
    receipts: Sequence[tuple[dict[str, Any], bytes]],
    resolve: Any,
    expected_count: int | None,
    terminal_verdict: str | None,
    snapshot_omissions: set[tuple[str, str, str]],
) -> ValidatedReceiptChain:
    if not opens or len(opens) != len(receipts):
        raise ReceiptChainError("OPEN/receipt 必须是同长度非空连续链")
    if expected_count is not None and len(opens) != expected_count:
        raise ReceiptChainError(f"OPEN/receipt 链长度必须为 {expected_count}")
    if len(opens) > len(_STAGES):
        raise ReceiptChainError("OPEN/receipt 链超出 canonical stage 数量")

    captured: dict[tuple[str, str, str], dict[str, str]] = {}
    used_keys: set[tuple[str, str, str]] = set()

    def verify_ref(binding: Mapping[str, Any], *, label: str) -> None:
        key = _binding_key(binding, label=label)
        raw = resolve(binding, label)
        if digest_bytes(raw) != key[2]:
            raise ReceiptChainError(f"{label} exact bytes digest 漂移")
        used_keys.add(key)
        if key not in snapshot_omissions:
            captured.setdefault(
                key,
                {
                    "scope": key[0],
                    "ref": key[1],
                    "digest": key[2],
                    "contentBase64": base64.b64encode(raw).decode("ascii"),
                },
            )

    predecessor: dict[str, str] | None = None
    for index, ((open_doc, open_raw), (receipt, receipt_raw)) in enumerate(
        zip(opens, receipts, strict=True), start=1
    ):
        stage = _STAGES[index - 1]
        name = f"{index:03d}-{stage}.json"
        if open_raw != canonical_bytes(open_doc) or receipt_raw != canonical_bytes(receipt):
            raise ReceiptChainError(f"{name} embedded canonical bytes 漂移")
        if (
            open_doc.get("executionId") != execution_id
            or open_doc.get("stage") != stage
            or open_doc.get("sequence") != index
            or open_doc.get("predecessor") != predecessor
        ):
            raise ReceiptChainError(f"OPEN identity/sequence/predecessor 漂移：{name}")
        submitted_input = open_doc.get("submittedInput")
        if not isinstance(submitted_input, Mapping):
            raise ReceiptChainError(f"OPEN submittedInput 非法：{name}")
        frozen_inputs = _frozen_refs(open_doc.get("inputRefs"), label=f"OPEN inputRefs:{name}")
        if (
            open_doc.get("input") != {"digest": digest_bytes(canonical_bytes(submitted_input))}
            or _input_refs(submitted_input.get("inputRefs"), label=f"submittedInput:{name}")
            != [{"scope": row["scope"], "ref": row["ref"]} for row in frozen_inputs]
        ):
            raise ReceiptChainError(f"OPEN input digest/submittedInput 镜像漂移：{name}")

        expected_open = {
            "scope": "execution",
            "ref": f"{_OPEN_DIRECTORY}/{name}",
            "digest": digest_bytes(open_raw),
        }
        if (
            receipt.get("executionId") != execution_id
            or receipt.get("stage") != stage
            or receipt.get("sequence") != index
            or receipt.get("predecessor") != predecessor
            or receipt.get("openRequest") != expected_open
            or receipt.get("inputRefs") != frozen_inputs
        ):
            raise ReceiptChainError(f"receipt identity/open/inputRefs 漂移：{name}")
        submitted_close = receipt.get("submittedClose")
        if not isinstance(submitted_close, Mapping):
            raise ReceiptChainError(f"receipt submittedClose 非法：{name}")
        frozen_results = _frozen_refs(
            receipt.get("resultRefs"),
            label=f"receipt resultRefs:{name}",
            allow_actor=stage in {"4.draft", "5.review"},
        )
        if receipt.get("closeInput") != {
            "digest": digest_bytes(canonical_bytes(submitted_close))
        }:
            raise ReceiptChainError(f"receipt closeInput digest 漂移：{name}")
        for field in ("actor", "verdict", "typedIssues", "verifierFacts"):
            if receipt.get(field) != submitted_close.get(field):
                raise ReceiptChainError(f"receipt submittedClose.{field} 镜像漂移：{name}")
        if _input_refs(
            submitted_close.get("resultRefs"),
            label=f"submittedClose resultRefs:{name}",
            allow_actor=stage in {"4.draft", "5.review"},
        ) != [
            {key: row[key] for key in ("scope", "ref", "actor") if key in row}
            for row in frozen_results
        ]:
            raise ReceiptChainError(f"receipt submittedClose.resultRefs 镜像漂移：{name}")
        if index < len(opens) and receipt.get("verdict") != "pass":
            raise ReceiptChainError(f"非 terminal receipt 必须为 pass：{name}")

        for field, bindings in (
            ("OPEN inputRefs", frozen_inputs),
            ("receipt inputRefs", _frozen_refs(receipt.get("inputRefs"), label=f"receipt inputRefs:{name}")),
            ("receipt resultRefs", frozen_results),
        ):
            for binding in bindings:
                verify_ref(
                    {key: binding[key] for key in ("scope", "ref", "digest")},
                    label=f"{execution_id} {name} {field}",
                )
        facts = receipt.get("verifierFacts")
        if not isinstance(facts, list):
            raise ReceiptChainError(f"receipt verifierFacts 非法：{name}")
        for fact in facts:
            evidence = fact.get("evidenceRef") if isinstance(fact, Mapping) else None
            if evidence is None:
                continue
            evidence_digest = fact.get("evidenceDigest")
            if not isinstance(evidence_digest, str):
                raise ReceiptChainError(f"verifier evidenceDigest 缺失：{name}")
            verify_ref(
                {**dict(evidence), "digest": evidence_digest},
                label=f"{execution_id} {name} verifier evidence",
            )
        predecessor = {
            "scope": "execution",
            "ref": f"{_RECEIPT_DIRECTORY}/{name}",
            "digest": digest_bytes(receipt_raw),
        }

    if terminal_verdict is not None and receipts[-1][0].get("verdict") != terminal_verdict:
        raise ReceiptChainError(f"terminal receipt 必须为 {terminal_verdict}")
    ordered_references = tuple(
        captured[key] for key in sorted(captured, key=lambda row: (row[0], row[1], row[2]))
    )
    if used_keys != set(captured) | snapshot_omissions:
        raise ReceiptChainError("sealed ref omission 与实际使用引用不一致")
    return ValidatedReceiptChain(
        execution_id=execution_id,
        open_requests=tuple(value for value, _raw in opens),
        receipts=tuple(value for value, _raw in receipts),
        open_raws=tuple(raw for _value, raw in opens),
        receipt_raws=tuple(raw for _value, raw in receipts),
        frozen_references=ordered_references,
    )


def validate_live_receipt_chain(
    *,
    execution_id: str,
    execution_root: Path,
    repo_root: Path,
    output_root: Path,
    expected_count: int | None = None,
    terminal_verdict: str | None = None,
    snapshot_omissions: set[tuple[str, str, str]] | None = None,
) -> ValidatedReceiptChain:
    """Read once and validate a live canonical receipt chain and all frozen refs."""

    root = _assert_no_symlink(execution_root, label=f"execution:{execution_id}", regular=False)
    directories = {
        "open": _assert_no_symlink(root / _OPEN_DIRECTORY, label="stage-open", regular=False),
        "receipt": _assert_no_symlink(root / _RECEIPT_DIRECTORY, label="receipts", regular=False),
    }
    names_by_kind: dict[str, set[str]] = {}
    for kind, directory in directories.items():
        entries = list(directory.iterdir())
        if any(path.is_symlink() or not path.is_file() for path in entries):
            raise ReceiptChainError(f"{kind} 目录只能包含 regular files")
        names_by_kind[kind] = {path.name for path in entries}
    if names_by_kind["open"] != names_by_kind["receipt"] or not names_by_kind["open"]:
        raise ReceiptChainError("OPEN/receipt 文件集合必须相同且非空")
    count = len(names_by_kind["open"])
    expected_names = {f"{index:03d}-{stage}.json" for index, stage in enumerate(_STAGES[:count], 1)}
    if names_by_kind["open"] != expected_names:
        raise ReceiptChainError("OPEN/receipt 必须是 canonical 连续前缀")

    opens: list[tuple[dict[str, Any], bytes]] = []
    receipts: list[tuple[dict[str, Any], bytes]] = []
    for index, stage in enumerate(_STAGES[:count], 1):
        name = f"{index:03d}-{stage}.json"
        open_raw = _read_regular(directories["open"] / name, label=f"OPEN:{name}")
        receipt_raw = _read_regular(directories["receipt"] / name, label=f"receipt:{name}")
        opens.append((_parse_canonical_document(open_raw, schema_name="stage_open_request", label=f"OPEN:{name}"), open_raw))
        receipts.append((_parse_canonical_document(receipt_raw, schema_name="stage_receipt", label=f"receipt:{name}"), receipt_raw))

    roots = {"execution": root, "output": output_root, "repo": repo_root}

    def resolve(binding: Mapping[str, Any], label: str) -> bytes:
        scope = str(binding.get("scope") or "")
        if scope not in roots:
            raise ReceiptChainError(f"{label} scope 非法")
        ref = _safe_ref(binding.get("ref"), label=label)
        return _read_regular(roots[scope] / ref, label=label)

    return _validate_documents(
        execution_id=execution_id,
        opens=opens,
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
    """Validate one sealed chain without consulting any live task/ref roots."""

    execution_id = str(document.get("executionId") or "")
    open_values = document.get("openRequests")
    receipt_values = document.get("receipts")
    frozen_values = document.get("frozenReferences")
    if not isinstance(open_values, list) or not isinstance(receipt_values, list) or not isinstance(frozen_values, list):
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

    opens = [
        (dict(value), canonical_bytes(value))
        for value in open_values
        if isinstance(value, Mapping)
    ]
    receipts = [
        (dict(value), canonical_bytes(value))
        for value in receipt_values
        if isinstance(value, Mapping)
    ]
    if len(opens) != len(open_values) or len(receipts) != len(receipt_values):
        raise ReceiptChainError("embedded OPEN/receipt document 非法")
    validated = _validate_documents(
        execution_id=execution_id,
        opens=opens,
        receipts=receipts,
        resolve=resolve,
        expected_count=expected_count,
        terminal_verdict=terminal_verdict,
        snapshot_omissions=set(external_bytes),
    )
    validated_keys = {
        (row["scope"], row["ref"], row["digest"])
        for row in validated.frozen_references
    }
    if validated_keys != set(snapshots):
        raise ReceiptChainError("embedded frozenReferences 包含未使用或缺失字节")
    return validated


def _receipt_result_actor(
    receipt: Mapping[str, Any], *, ref: str, label: str
) -> Mapping[str, Any]:
    matches = [
        row
        for row in receipt.get("resultRefs") or []
        if isinstance(row, Mapping) and row.get("ref") == ref
    ]
    if len(matches) != 1:
        raise ReceiptChainError(f"{label} result ref 必须唯一")
    actor = matches[0].get("actor", receipt.get("actor"))
    if not isinstance(actor, Mapping):
        raise ReceiptChainError(f"{label} actor 非法")
    invocation = actor.get("invocation")
    if (
        not str(actor.get("host") or "").strip()
        or not str(actor.get("sessionId") or "").strip()
        or not isinstance(invocation, Mapping)
        or not str(invocation.get("runId") or "").strip()
    ):
        raise ReceiptChainError(f"{label} actor 必须记录真实 host/sessionId/invocation.runId")
    return actor


def _independent_actors(
    author: Mapping[str, Any], reviewer: Mapping[str, Any]
) -> None:
    if (author.get("host"), author.get("sessionId")) == (
        reviewer.get("host"), reviewer.get("sessionId")
    ):
        raise ReceiptChainError("sequence-006/007 object actors share host/sessionId")
    author_invocation = author.get("invocation") if isinstance(author.get("invocation"), Mapping) else {}
    reviewer_invocation = reviewer.get("invocation") if isinstance(reviewer.get("invocation"), Mapping) else {}
    author_run_id = str(author_invocation.get("runId") or "").strip()
    reviewer_run_id = str(reviewer_invocation.get("runId") or "").strip()
    if not author_run_id or not reviewer_run_id or author_run_id == reviewer_run_id:
        raise ReceiptChainError("sequence-006/007 object actors share invocation.runId")


def validate_publish_review_chain(
    *,
    execution_id: str,
    execution_root: Path,
    repo_root: Path,
    output_root: Path,
    target_ref: str,
) -> tuple[ValidatedReceiptChain, dict[str, Any]]:
    """Validate the live sequence-007 approval for exactly one object."""

    chain = validate_live_receipt_chain(
        execution_id=execution_id,
        execution_root=execution_root,
        repo_root=repo_root,
        output_root=output_root,
        expected_count=7,
        terminal_verdict="pass",
    )
    draft_receipt = chain.receipts[5]
    review_receipt = chain.receipts[6]
    normalized_ref = str(target_ref or "").strip().strip("/")
    draft_names = {
        "homepage": "page.md",
        "article": "draft.article.md",
        "image": "image_work.json",
        "video": "video_script.json",
    }
    carrier = "homepage" if normalized_ref.startswith("entities/") else normalized_ref.split("/", 2)[1]
    draft_ref = f"{normalized_ref}/4.draft/{draft_names[carrier]}"
    review_ref = f"{normalized_ref}/5.review/content_review.json"
    author = _receipt_result_actor(
        draft_receipt, ref=draft_ref, label="sequence-006"
    )
    reviewer = _receipt_result_actor(
        review_receipt, ref=review_ref, label="sequence-007"
    )
    _independent_actors(author, reviewer)

    review_path = execution_root / review_ref
    review_raw = _read_regular(review_path, label=review_ref)
    review = _parse_content_review(review_raw, label=review_ref)
    if review.get("executionId") != execution_id or review.get("objectRef") != normalized_ref:
        raise ReceiptChainError("content_review target identity drift")
    expected = {
        "scope": "execution",
        "ref": review_ref,
        "digest": digest_bytes(review_raw),
    }
    matches = [
        row
        for row in review_receipt.get("resultRefs") or []
        if isinstance(row, Mapping)
        and {key: row.get(key) for key in expected} == expected
    ]
    if len(matches) != 1:
        raise ReceiptChainError("sequence-007 resultRefs do not exact-bind content_review")
    if review.get("decision") != "approved":
        raise ReceiptChainError("content_review is not approved")
    return chain, review


def _parse_content_review(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptChainError(f"{label} 不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise ReceiptChainError(f"{label} 必须是 JSON 对象")
    try:
        assert_valid(value, "content", "content_review", label=label)
    except (TypeError, ValueError) as exc:
        raise ReceiptChainError(str(exc)) from exc
    if raw != canonical_bytes(value):
        raise ReceiptChainError(f"{label} 不是 canonical JSON")
    return value


__all__ = [
    "ReceiptChainError",
    "ValidatedReceiptChain",
    "canonical_bytes",
    "digest_bytes",
    "validate_embedded_receipt_chain",
    "validate_live_receipt_chain",
    "validate_publish_review_chain",
]
