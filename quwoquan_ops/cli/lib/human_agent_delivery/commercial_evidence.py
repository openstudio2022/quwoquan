"""商用证据的纯只读、非裁决聚合投影。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from ..evidence_fingerprint import EvidenceFingerprintError, canonical_digest, fingerprint_ref
from .contract import ContractError, load_contract, namespace_values, typed_blocker

_INPUT_FIELDS = frozenset({
    "scope", "evidence_root", "evidence_items", "captured_at",
    "policy_allows_limited_go", "limited_scope_reversible",
})
_SCOPE_REQUIRED_FIELDS = frozenset({"immutable_candidate", "source_sha"})
_EVIDENCE_FIELDS = frozenset({
    "evidence_id", "owner_role", "label", "status", "required", "hard_gate",
    "fresh", "ref", "digest", "detail",
})
_STATUSES = frozenset({"passed", "failed", "missing", "unknown"})
_LAYERS = (
    "immutable_artifact", "nonproduction", "commercial", "production_campaign",
    "channel", "outcome",
)
_LAYER_LABELS = {
    "immutable_artifact": "不可变产物",
    "nonproduction": "非生产验证",
    "commercial": "商用准备",
    "production_campaign": "生产 campaign",
    "channel": "渠道公开",
    "outcome": "结果接受",
}
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
_EXTERNAL_OPEN_ITEMS = (
    {
        "open_id": "human-agent-delivery/OPEN-001",
        "code": "HAD.AUTHORITY_PROVIDER_UNAVAILABLE",
        "detail": "真实身份与 authenticated Human Authority provider 尚未接入",
    },
    {
        "open_id": "human-agent-delivery/OPEN-003",
        "code": "HAD.AUTHORITY_PROVIDER_UNAVAILABLE",
        "detail": "外部商用、生产、渠道与 outcome authority 尚未闭合",
    },
)


class CommercialEvidenceError(ContractError):
    """可安全投影给 CLI 的商用证据输入错误。"""

    def __init__(self, detail: str, *, code: str = "HAD.CONTRACT_INVALID") -> None:
        super().__init__(detail)
        self.code = code


def _fail(detail: str, *, code: str = "HAD.CONTRACT_INVALID") -> CommercialEvidenceError:
    return CommercialEvidenceError(detail, code=code)


def _require_exact_fields(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise _fail(
            f"{label} 字段漂移: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _require_nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(f"{label} 必须为非空字符串")
    return value


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise _fail(f"{label} 必须为 boolean")
    return value


def _normalize_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise _fail(f"{label} 必须为 sha256:<64-lowercase-hex>")
    return value


def _validate_scope(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _fail("scope 必须为 JSON object")
    if not _SCOPE_REQUIRED_FIELDS.issubset(value):
        raise _fail("scope 必须包含 immutable_candidate 与 source_sha")
    scope = dict(value)
    _require_nonempty_string(scope["immutable_candidate"], "scope.immutable_candidate")
    source_sha = _require_nonempty_string(scope["source_sha"], "scope.source_sha")
    if _SOURCE_SHA_RE.fullmatch(source_sha) is None:
        raise _fail("scope.source_sha 必须为 40 或 64 位 lowercase hex")
    try:
        canonical_digest(scope)
    except EvidenceFingerprintError as error:
        raise _fail(f"scope 不符合 canonical JSON 约束: {error}") from error
    return scope


def _validate_root(raw_root: object) -> Path:
    root_text = _require_nonempty_string(raw_root, "evidence_root")
    root = Path(root_text)
    if not root.is_absolute():
        raise _fail("evidence_root 必须为 explicit absolute directory")
    try:
        root.lstat()
    except OSError as error:
        raise _fail("evidence_root 不存在或不可访问") from error
    if root.is_symlink() or not root.is_dir():
        raise _fail("evidence_root 必须为非 symlink directory")
    anchor = Path(root.anchor)
    current = anchor
    try:
        relative_parts = root.relative_to(anchor).parts
    except ValueError as error:
        raise _fail("evidence_root 必须为 canonical absolute path") from error
    for part in relative_parts:
        current = current / part
        try:
            current.lstat()
        except OSError as error:
            raise _fail("evidence_root ancestor 不存在或不可访问") from error
        if current.is_symlink():
            raise _fail("evidence_root ancestor 禁止 symlink")
    if root.resolve(strict=True) != root:
        raise _fail("evidence_root 必须为 canonical absolute path")
    return root


def _safe_relative_ref(raw_ref: object) -> PurePosixPath:
    ref = _require_nonempty_string(raw_ref, "evidence.ref")
    if "\\" in ref:
        raise _fail("evidence.ref 只允许 POSIX relative path")
    path = PurePosixPath(ref)
    if path.is_absolute() or path.as_posix() in {"", "."}:
        raise _fail("evidence.ref 不得为 absolute 或空路径")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise _fail("evidence.ref 禁止 path traversal 与 dot segment")
    if path.as_posix() != ref:
        raise _fail("evidence.ref 必须为 canonical POSIX relative path")
    return path


def _load_exact_json(root: Path, raw_ref: object, declared_digest: object) -> dict[str, Any]:
    relative = _safe_relative_ref(raw_ref)
    digest = _normalize_digest(declared_digest, "evidence.digest")
    current = root
    for part in relative.parts:
        candidate = current / part
        try:
            candidate.lstat()
        except OSError as error:
            raise _fail(f"evidence.ref 文件不存在: {relative.as_posix()}") from error
        if candidate.is_symlink():
            raise _fail(f"evidence.ref 禁止 symlink: {relative.as_posix()}")
        current = candidate
    if not current.is_file():
        raise _fail(f"evidence.ref 必须指向普通文件: {relative.as_posix()}")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow
    file_flags = os.O_RDONLY | nofollow
    descriptors: list[int] = []
    try:
        directory_descriptor = os.open(root, directory_flags)
        descriptors.append(directory_descriptor)
        for part in relative.parts[:-1]:
            directory_descriptor = os.open(
                part, directory_flags, dir_fd=directory_descriptor
            )
            descriptors.append(directory_descriptor)
            if not stat.S_ISDIR(os.fstat(directory_descriptor).st_mode):
                raise _fail(f"evidence.ref 中间路径必须为目录: {relative.as_posix()}")
        descriptor = os.open(
            relative.parts[-1], file_flags, dir_fd=directory_descriptor
        )
        descriptors.append(descriptor)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise _fail(f"evidence.ref 必须指向普通文件: {relative.as_posix()}")
        chunks: list[bytes] = []
        total = 0
        while total <= _MAX_EVIDENCE_BYTES:
            chunk = os.read(
                descriptor,
                min(64 * 1024, _MAX_EVIDENCE_BYTES + 1 - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        raw = b"".join(chunks)
    except CommercialEvidenceError:
        raise
    except OSError as error:
        raise _fail(f"evidence.ref 无法安全打开: {relative.as_posix()}") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    if not raw or len(raw) > _MAX_EVIDENCE_BYTES:
        raise _fail(f"evidence JSON 字节大小非法: {relative.as_posix()}")
    actual_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual_digest != digest:
        raise _fail(f"evidence digest drift: {relative.as_posix()}")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _fail(f"evidence 必须为 UTF-8 JSON: {relative.as_posix()}") from error
    if not isinstance(value, dict):
        raise _fail(f"evidence JSON 必须为 object: {relative.as_posix()}")
    if value.get("status") not in _STATUSES:
        raise _fail(f"evidence JSON.status 非法或缺失: {relative.as_posix()}")
    return value


def _normalize_item(raw: object, *, root: Path) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise _fail("evidence_items 每项必须为 JSON object")
    _require_exact_fields(raw, _EVIDENCE_FIELDS, "evidence_item")
    item = dict(raw)
    evidence_id = _require_nonempty_string(item["evidence_id"], "evidence_id")
    owner_role = _require_nonempty_string(item["owner_role"], f"{evidence_id}.owner_role")
    contract = load_contract()
    human_roles = set(namespace_values("human_authority_role"))
    review_roles = set(namespace_values("review_role"))
    if owner_role in review_roles or owner_role.startswith(str(contract["namespaces"]["review_role"]["prefix"]) + "."):
        raise _fail(f"ReviewRole 不得作为商用证据 owner: {owner_role}", code="HAD.REVIEW_ROLE_FORBIDDEN")
    if owner_role not in human_roles:
        raise _fail(f"owner_role 不属于 HumanAuthorityRole: {owner_role}")
    label = _require_nonempty_string(item["label"], f"{evidence_id}.label")
    status = item["status"]
    if status not in _STATUSES:
        raise _fail(f"{evidence_id}.status 必须属于 {sorted(_STATUSES)}")
    required = _require_bool(item["required"], f"{evidence_id}.required")
    hard_gate = _require_bool(item["hard_gate"], f"{evidence_id}.hard_gate")
    fresh = _require_bool(item["fresh"], f"{evidence_id}.fresh")
    detail = item["detail"]
    if not isinstance(detail, str):
        raise _fail(f"{evidence_id}.detail 必须为字符串")
    ref, digest = item["ref"], item["digest"]
    if (ref is None) != (digest is None):
        raise _fail(f"{evidence_id}.ref 与 digest 必须成对")
    evidence_document: dict[str, Any] | None = None
    if status == "missing":
        if ref is not None:
            evidence_document = _load_exact_json(root, ref, digest)
    else:
        if ref is None:
            raise _fail(f"{evidence_id}.{status} 必须提供 exact ref/digest")
        evidence_document = _load_exact_json(root, ref, digest)
    if evidence_document is not None and evidence_document["status"] != status:
        raise _fail(
            f"{evidence_id} 声明 status={status} 与 evidence JSON.status="
            f"{evidence_document['status']} 不一致"
        )
    return {
        "evidence_id": evidence_id,
        "owner_role": owner_role,
        "label": label,
        "status": status,
        "required": required,
        "hard_gate": hard_gate,
        "fresh": fresh,
        "ref": ref,
        "digest": digest,
        "detail": detail,
    }


def _layer_for(item: Mapping[str, Any]) -> str:
    searchable = " ".join((str(item["evidence_id"]), str(item["label"]))).lower()
    aliases = (
        ("outcome", ("outcome", "attained", "结果", "成效")),
        ("channel", ("channel", "published", "publication", "渠道", "上架", "公开")),
        ("production_campaign", ("production", "campaign", "released", "rollout", "生产", "放量")),
        ("commercial", ("commercial", "business", "商用", "商业")),
        ("nonproduction", ("nonproduction", "nonprod", "uat", "gamma", "非生产")),
        ("immutable_artifact", ("immutable", "artifact", "candidate", "产物", "候选")),
    )
    for layer, tokens in aliases:
        if any(token in searchable for token in tokens):
            return layer
    return "commercial"


def _hard_gate_blocker(item: Mapping[str, Any]) -> dict[str, Any] | None:
    if not (item["required"] and item["hard_gate"]):
        return None
    reasons: list[str] = []
    if item["status"] != "passed":
        reasons.append(str(item["status"]))
    if not item["fresh"]:
        reasons.append("stale")
    if not reasons:
        return None
    blocker = typed_blocker(
        "HAD.HARD_GATE_FAILED",
        detail=f"{item['evidence_id']}: {','.join(reasons)}; {item['detail']}",
    )
    blocker.update({
        "evidence_id": item["evidence_id"],
        "owner_role": item["owner_role"],
        "reasons": reasons,
    })
    return blocker


def _external_blockers() -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for item in _EXTERNAL_OPEN_ITEMS:
        blocker = typed_blocker(item["code"], detail=item["detail"])
        blocker["open_id"] = item["open_id"]
        blockers.append(blocker)
    return blockers


def _role_order(items: Sequence[Mapping[str, Any]]) -> list[str]:
    blockers = [item for item in items if _hard_gate_blocker(item) is not None]
    ordered: list[str] = []
    for item in [*blockers, *items]:
        role = str(item["owner_role"])
        if role not in ordered and (not item["fresh"] or item["status"] != "passed" or item in blockers):
            ordered.append(role)
    for role in (
        "release_owner", "operations_support_market_channel_owner",
        "business_sponsor",
    ):
        if role not in ordered:
            ordered.append(role)
    if "product_owner" in ordered:
        ordered.remove("product_owner")
    ordered.append("product_owner")
    return ordered


def _build_role_cards(
    items: Sequence[Mapping[str, Any]], required_roles: Sequence[str]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item["owner_role"]), []).append(item)
    cards: list[dict[str, Any]] = []
    for role in namespace_values("human_authority_role"):
        owned = grouped.get(role, [])
        if not owned and role not in required_roles:
            continue
        known = [
            f"{item['label']}: {item['status']}"
            for item in owned
            if item["status"] in {"passed", "failed"} and item["fresh"]
        ]
        unknown = [item["label"] for item in owned if item["status"] in {"missing", "unknown"} or not item["fresh"]]
        hard_constraints = [
            item["label"] for item in owned if item["hard_gate"] and _hard_gate_blocker(item) is not None
        ]
        checks = [
            {
                "evidence_id": item["evidence_id"],
                "label": item["label"],
                "status": item["status"],
                "required": item["required"],
                "hard_gate": item["hard_gate"],
                "fresh": item["fresh"],
                "detail": item["detail"],
                "action": (
                    "核对并接受本角色拥有的证据"
                    if item["status"] == "passed" and item["fresh"]
                    else "补充或刷新证据后再检查"
                ),
            }
            for item in owned
        ]
        if not owned:
            unknown = ["缺少外部 authenticated authority 与 exact-byte readback"]
            hard_constraints = ["本地 evidence 不得替代外部 Human Authority"]
            checks = [{
                "evidence_id": None,
                "label": "外部 authority",
                "status": "missing",
                "required": True,
                "hard_gate": True,
                "fresh": False,
                "detail": "保持 OPEN-001/OPEN-003 阻断并转交具名角色",
                "action": "取得外部 authority 后再检查",
            }]
        cards.append({
            "card_type": "post_check",
            "current_role": role,
            "known_facts": known,
            "unknowns": unknown,
            "hard_constraints": hard_constraints,
            "pending_checks": checks,
            "actions": ["request_evidence", "transfer_to_correct_role", "pause_or_stop"],
            "accepts_only_own_result": True,
        })
    return cards


def _layer_projection(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_layer: dict[str, list[Mapping[str, Any]]] = {layer: [] for layer in _LAYERS}
    for item in items:
        by_layer[_layer_for(item)].append(item)
    result: list[dict[str, Any]] = []
    for layer in _LAYERS:
        rows = by_layer[layer]
        status = "not_evidenced"
        if rows:
            if all(row["status"] == "passed" and row["fresh"] for row in rows):
                status = "evidenced"
            elif any(row["status"] == "failed" for row in rows):
                status = "failed"
            else:
                status = "unknown"
        result.append({
            "layer": layer,
            "label": _LAYER_LABELS[layer],
            "evidence_ids": [row["evidence_id"] for row in rows],
            "evidence_status": status,
            "decision_status": "not_decided",
            "does_not_imply_next_layer": True,
        })
    return result


def project_commercial_evidence(
    *,
    scope: Mapping[str, Any],
    evidence_root: str,
    evidence_items: Sequence[Mapping[str, Any]],
    captured_at: str,
    policy_allows_limited_go: bool = False,
    limited_scope_reversible: bool = False,
) -> dict[str, Any]:
    """聚合 exact-byte 证据并只返回非执行、非裁决投影。"""
    normalized_scope = _validate_scope(scope)
    root = _validate_root(evidence_root)
    captured = _require_nonempty_string(captured_at, "captured_at")
    policy_allows = _require_bool(policy_allows_limited_go, "policy_allows_limited_go")
    reversible = _require_bool(limited_scope_reversible, "limited_scope_reversible")
    if not isinstance(evidence_items, list):
        raise _fail("evidence_items 必须为 JSON array")
    normalized = [_normalize_item(item, root=root) for item in evidence_items]
    ids = [item["evidence_id"] for item in normalized]
    if len(ids) != len(set(ids)):
        raise _fail("evidence_id 必须唯一")
    normalized.sort(key=lambda item: item["evidence_id"].encode("utf-8"))
    blockers = [blocker for item in normalized if (blocker := _hard_gate_blocker(item)) is not None]
    external_blockers = _external_blockers()
    required_hard_gates = [
        item for item in normalized if item["required"] and item["hard_gate"]
    ]
    gates_ready = bool(required_hard_gates) and not blockers and all(
        item["status"] == "passed" and item["fresh"]
        for item in required_hard_gates
    )
    options = ["hold", "abort"]
    if gates_ready:
        options = ["go", *options]
        if policy_allows and reversible:
            options.insert(1, "limited_go")
    required_roles = _role_order(normalized)
    fingerprint_input = {
        "schema_id": "human-agent-delivery-commercial-evidence-input",
        "schema_version": 1,
        "scope": normalized_scope,
        "evidence_root": root.as_posix(),
        "captured_at": captured,
        "policy_allows_limited_go": policy_allows,
        "limited_scope_reversible": reversible,
        "external_authority_status": "unavailable",
        "evidence_items": normalized,
    }
    try:
        digest = canonical_digest(fingerprint_input)
        ref = fingerprint_ref(digest)
    except EvidenceFingerprintError as error:
        raise _fail(f"无法生成 canonical EvidenceFingerprint: {error}") from error
    return {
        "schema_id": "human-agent-delivery-commercial-evidence-projection",
        "schema_version": 1,
        "scope": normalized_scope,
        "captured_at": captured,
        "fingerprint_ref": ref,
        "digest": digest,
        "decision_status": "not_decided",
        "selected_commercial_option": None,
        "authenticated_authority": False,
        "executable": False,
        "available_commercial_options": options,
        "option_disposition": "可交产品负责人裁决" if gates_ready else "硬门阻断，保持 Hold 或 Abort",
        "hard_gate_blockers": blockers,
        "external_authority_blockers": external_blockers,
        "next_required_roles": required_roles,
        "role_cards": _build_role_cards(normalized, required_roles),
        "delivery_layers": _layer_projection(normalized),
        "non_derivation_guarantees": {
            "commercial_does_not_authorize_production_campaign": True,
            "production_release_does_not_publish_channel": True,
            "released_or_published_does_not_attain_outcome": True,
            "production_campaign_approval_emitted": False,
            "channel_publication_emitted": False,
            "outcome_acceptance_emitted": False,
        },
    }


def project_commercial_evidence_payload(payload: object) -> dict[str, Any]:
    """验证 CLI 顶层 closed fields 后投影。"""
    if not isinstance(payload, Mapping):
        raise _fail("input JSON 必须为 object")
    unknown = set(payload) - _INPUT_FIELDS
    required = {"scope", "evidence_root", "evidence_items", "captured_at"}
    missing = required - set(payload)
    if missing or unknown:
        raise _fail(f"input 字段漂移: missing={sorted(missing)}, extra={sorted(unknown)}")
    return project_commercial_evidence(
        scope=payload["scope"],
        evidence_root=payload["evidence_root"],
        evidence_items=payload["evidence_items"],
        captured_at=payload["captured_at"],
        policy_allows_limited_go=payload.get("policy_allows_limited_go", False),
        limited_scope_reversible=payload.get("limited_scope_reversible", False),
    )


def commercial_evidence_blocker(error: Exception) -> dict[str, Any]:
    """把聚合错误稳定投影为 typed blocker。"""
    code = getattr(error, "code", "HAD.CONTRACT_INVALID")
    return typed_blocker(code, detail=str(error))
