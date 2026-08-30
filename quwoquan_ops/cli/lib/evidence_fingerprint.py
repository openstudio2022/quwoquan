"""Contract-driven EvidenceFingerprint canonical serializer and path snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import subprocess
import unicodedata
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_governance_contract import contract_section


class EvidenceFingerprintError(ValueError):
    """Fail-closed contract, serialization, or repository identity error."""


class _Missing:
    __slots__ = ()


MISSING = _Missing()
_MISSING_KEY = "$evidenceFingerprintMissing"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:/")


def _definition() -> dict[str, Any]:
    return contract_section("evidence_fingerprint")


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _canonical_value(value: Any) -> Any:
    if value is MISSING:
        return {_MISSING_KEY: True}
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise EvidenceFingerprintError("EvidenceFingerprint number 只允许整数")
    if isinstance(value, str):
        return _nfc(value)
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                raise EvidenceFingerprintError("EvidenceFingerprint map key 必须为字符串")
            key = _nfc(raw_key)
            if key.startswith(_MISSING_KEY):
                raise EvidenceFingerprintError(
                    f"EvidenceFingerprint 保留 member 不可由输入声明：{key}"
                )
            if key in normalized:
                raise EvidenceFingerprintError(
                    f"EvidenceFingerprint Unicode normalization 后 map key 冲突：{key}"
                )
            normalized[key] = _canonical_value(raw_value)
        return {
            key: normalized[key]
            for key in sorted(normalized, key=lambda item: item.encode("utf-8"))
        }
    raise EvidenceFingerprintError(
        f"EvidenceFingerprint 不支持 JSON 类型：{type(value).__name__}"
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize the frozen deterministic JSON subset as exact UTF-8 bytes."""

    normalized = _canonical_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def validate_digest(value: object) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise EvidenceFingerprintError(
            "EvidenceFingerprint digest 必须为 sha256:<64-lowercase-hex>"
        )
    return value


def fingerprint_ref(digest: str) -> str:
    validate_digest(digest)
    return f"{_definition()['serialization_version']}:{digest}"


def validate_ref(value: object, *, digest: str | None = None) -> str:
    if not isinstance(value, str):
        raise EvidenceFingerprintError("EvidenceFingerprint ref 必须为字符串")
    prefix = f"{_definition()['serialization_version']}:"
    if not value.startswith(prefix):
        raise EvidenceFingerprintError("EvidenceFingerprint ref serialization version 非法")
    ref_digest = validate_digest(value[len(prefix) :])
    if digest is not None and ref_digest != validate_digest(digest):
        raise EvidenceFingerprintError("EvidenceFingerprint ref 与 digest 不一致")
    return value


def _is_exact_missing_marker(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and len(value) == 1
        and _MISSING_KEY in value
        and value[_MISSING_KEY] is True
    )


def _closed_declared_mapping(
    raw: Mapping[str, Any] | None,
    fields: list[str],
    *,
    label: str,
    trusted_missing_markers: bool = False,
) -> dict[str, Any]:
    value = {} if raw is None else raw
    if not isinstance(value, Mapping):
        raise EvidenceFingerprintError(f"{label} 必须为 mapping")
    unknown = sorted(set(value) - set(fields))
    if unknown:
        raise EvidenceFingerprintError(f"{label} 含未知字段：{unknown}")
    normalized: dict[str, Any] = {}
    for field in fields:
        if field not in value or value[field] is MISSING:
            normalized[field] = MISSING
        elif trusted_missing_markers and _is_exact_missing_marker(value[field]):
            # 只在校验既有 receipt 的 contract 声明字段时解码 wire marker。
            # 公共 builder 与全局 canonical serializer 始终拒绝 caller 自造 marker。
            normalized[field] = MISSING
        else:
            normalized[field] = _canonical_value(value[field])
    return normalized


def _build_digest_payload(
    field_groups: Mapping[str, Mapping[str, Any]] | None,
    *,
    trusted_missing_markers: bool,
) -> dict[str, Any]:
    definition = _definition()
    declarations = definition["digest_payload_fields"]
    supplied = {} if field_groups is None else field_groups
    if not isinstance(supplied, Mapping):
        raise EvidenceFingerprintError("EvidenceFingerprint field_groups 必须为 mapping")
    unknown_groups = sorted(set(supplied) - set(declarations))
    if unknown_groups:
        raise EvidenceFingerprintError(
            f"EvidenceFingerprint 含未知 field group：{unknown_groups}"
        )
    payload: dict[str, Any] = {
        "schema_version": definition["schema_version"],
        "serialization_version": definition["serialization_version"],
    }
    for group, fields in declarations.items():
        payload[group] = _closed_declared_mapping(
            supplied.get(group),
            fields,
            label=f"evidence_fingerprint.{group}",
            trusted_missing_markers=trusted_missing_markers,
        )
    expected = definition["digest_payload_top_level_fields"]
    if set(payload) != set(expected):
        raise EvidenceFingerprintError("EvidenceFingerprint digest payload 顶层字段漂移")
    return {field: payload[field] for field in expected}


def build_digest_payload(
    field_groups: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Build the exact versioned digest payload from contract-declared groups."""

    return _build_digest_payload(field_groups, trusted_missing_markers=False)


def validate_evidence_fingerprint(receipt: object) -> dict[str, Any]:
    """Validate a complete canonical receipt and return it in declared order."""

    if not isinstance(receipt, Mapping):
        raise EvidenceFingerprintError("EvidenceFingerprint receipt 必须为 mapping")
    definition = _definition()
    expected = definition["receipt_fields"]
    missing = [field for field in expected if field not in receipt]
    extra = sorted(set(receipt) - set(expected))
    if missing or extra:
        raise EvidenceFingerprintError(
            f"EvidenceFingerprint receipt 字段漂移：missing={missing}, extra={extra}"
        )
    if receipt["schema_version"] != definition["schema_version"]:
        raise EvidenceFingerprintError("EvidenceFingerprint receipt schema_version 非法")
    if receipt["serialization_version"] != definition["serialization_version"]:
        raise EvidenceFingerprintError("EvidenceFingerprint receipt serialization_version 非法")
    payload = receipt["digest_payload"]
    if not isinstance(payload, Mapping):
        raise EvidenceFingerprintError("EvidenceFingerprint digest_payload 必须为 mapping")
    payload_expected = definition["digest_payload_top_level_fields"]
    payload_missing = [field for field in payload_expected if field not in payload]
    payload_extra = sorted(set(payload) - set(payload_expected))
    if payload_missing or payload_extra:
        raise EvidenceFingerprintError(
            "EvidenceFingerprint digest_payload 字段漂移："
            f"missing={payload_missing}, extra={payload_extra}"
        )
    if payload["schema_version"] != definition["schema_version"]:
        raise EvidenceFingerprintError("EvidenceFingerprint digest_payload schema_version 非法")
    if payload["serialization_version"] != definition["serialization_version"]:
        raise EvidenceFingerprintError(
            "EvidenceFingerprint digest_payload serialization_version 非法"
        )
    for group, fields in definition["digest_payload_fields"].items():
        group_payload = payload[group]
        if not isinstance(group_payload, Mapping):
            raise EvidenceFingerprintError(
                f"EvidenceFingerprint digest_payload.{group} 必须为 mapping"
            )
        group_missing = [field for field in fields if field not in group_payload]
        group_extra = sorted(set(group_payload) - set(fields))
        if group_missing or group_extra:
            raise EvidenceFingerprintError(
                f"EvidenceFingerprint digest_payload.{group} 字段漂移："
                f"missing={group_missing}, extra={group_extra}"
            )
    rebuilt = _build_digest_payload(
        {
            group: payload[group]
            for group in definition["digest_payload_fields"]
        },
        trusted_missing_markers=True,
    )
    digest = validate_digest(receipt["digest"])
    if canonical_digest(rebuilt) != digest:
        raise EvidenceFingerprintError("EvidenceFingerprint digest_payload 与 digest 不一致")
    ref = validate_ref(receipt["ref"], digest=digest)
    if not isinstance(receipt["captured_at"], str) or not receipt["captured_at"]:
        raise EvidenceFingerprintError("EvidenceFingerprint captured_at 必须为非空字符串")
    if not isinstance(receipt["captured_by"], str) or not receipt["captured_by"]:
        raise EvidenceFingerprintError("EvidenceFingerprint captured_by 必须为非空字符串")
    if not isinstance(receipt["captured_metadata"], Mapping):
        raise EvidenceFingerprintError("EvidenceFingerprint captured_metadata 必须为 mapping")
    canonical = {
        "schema_version": definition["schema_version"],
        "serialization_version": definition["serialization_version"],
        "ref": ref,
        "digest": digest,
        # 保留内部 MISSING sentinel，使校验结果仍可由 canonical serializer 编码。
        "digest_payload": rebuilt,
        "captured_at": _nfc(receipt["captured_at"]),
        "captured_by": _nfc(receipt["captured_by"]),
        "captured_metadata": _canonical_value(dict(receipt["captured_metadata"])),
    }
    return {field: canonical[field] for field in expected}


def build_evidence_fingerprint(
    field_groups: Mapping[str, Mapping[str, Any]] | None,
    *,
    captured_at: str | None = None,
    captured_by: str,
    captured_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return digest payload, canonical digest/ref, and non-digest receipt metadata."""

    if not isinstance(captured_by, str) or not captured_by:
        raise EvidenceFingerprintError("EvidenceFingerprint captured_by 必须为非空字符串")
    timestamp = captured_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not isinstance(timestamp, str) or not timestamp:
        raise EvidenceFingerprintError("EvidenceFingerprint captured_at 必须为非空字符串")
    metadata = _canonical_value(dict(captured_metadata or {}))
    payload = build_digest_payload(field_groups)
    digest = canonical_digest(payload)
    definition = _definition()
    receipt = {
        "schema_version": definition["schema_version"],
        "serialization_version": definition["serialization_version"],
        "ref": fingerprint_ref(digest),
        "digest": digest,
        "digest_payload": payload,
        "captured_at": timestamp,
        "captured_by": _nfc(captured_by),
        "captured_metadata": metadata,
    }
    expected = definition["receipt_fields"]
    if set(receipt) != set(expected):
        raise EvidenceFingerprintError("EvidenceFingerprint receipt 字段漂移")
    return {field: receipt[field] for field in expected}


def normalize_repo_relative_path(raw_path: str | os.PathLike[str], repo_root: Path) -> str:
    """Normalize slash style, NFC, and dot segments without resolving symlinks."""

    raw = _nfc(os.fspath(raw_path).replace("\\", "/"))
    root = _nfc(repo_root.absolute().as_posix()).rstrip("/")
    if _WINDOWS_DRIVE_RE.match(raw):
        raise EvidenceFingerprintError(f"路径不在仓库内：{raw_path}")
    if raw.startswith("/"):
        if raw == root:
            raw = "."
        elif raw.startswith(root + "/"):
            raw = raw[len(root) + 1 :]
        else:
            raise EvidenceFingerprintError(f"路径不在仓库内：{raw_path}")
    if raw == "" or any(part == "" for part in raw.split("/")):
        raise EvidenceFingerprintError(f"路径含空 segment：{raw_path}")
    normalized = _nfc(posixpath.normpath(raw))
    if normalized == ".." or normalized.startswith("../") or normalized.startswith("/"):
        raise EvidenceFingerprintError(f"路径不在仓库内：{raw_path}")
    return normalized


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, check=False
    )


def _head_blob_digest(relative: str, repo_root: Path) -> str | None:
    result = _git(repo_root, "show", f"HEAD:{relative}")
    return (
        "sha256:" + hashlib.sha256(result.stdout).hexdigest()
        if result.returncode == 0
        else None
    )


def _parse_status_records(
    output: bytes,
    repo_root: Path,
) -> list[tuple[str, str, str | None]]:
    entries: list[tuple[str, str, str | None]] = []
    records = output.split(b"\0")
    index = 0
    while index < len(records):
        raw = records[index]
        if not raw:
            break
        decoded = raw.decode("utf-8")
        code = decoded[:2]
        current = normalize_repo_relative_path(decoded[3:], repo_root)
        renamed_from = None
        if "R" in code or "C" in code:
            if index + 1 >= len(records) or not records[index + 1]:
                raise EvidenceFingerprintError(
                    f"git status rename 缺 source path：{current}"
                )
            renamed_from = normalize_repo_relative_path(
                records[index + 1].decode("utf-8"), repo_root
            )
            index += 1
        entries.append((current, code, renamed_from))
        index += 1
    return entries


def _lexical_target(link: Path, raw_target: str, repo_root: Path) -> tuple[str, Path]:
    target_text = _nfc(raw_target.replace("\\", "/"))
    if target_text.startswith("/") or _WINDOWS_DRIVE_RE.match(target_text):
        absolute = Path(posixpath.normpath(target_text))
    else:
        absolute = Path(posixpath.normpath((link.parent / target_text).as_posix()))
    relative = normalize_repo_relative_path(absolute.as_posix(), repo_root)
    return relative, repo_root / relative


def _node_content_digest(
    path: Path,
    repo_root: Path,
    visited: frozenset[str],
) -> str:
    relative = normalize_repo_relative_path(path.as_posix(), repo_root)
    try:
        path.lstat()
    except OSError:
        return canonical_digest({"state": "missing", "path": relative})
    if path.is_symlink():
        link = _symlink_identity(path, repo_root, visited)
        return canonical_digest(link)
    if path.is_file():
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    if path.is_dir():
        entries: list[dict[str, Any]] = []
        for child in sorted(
            path.iterdir(),
            key=lambda item: normalize_repo_relative_path(
                item.as_posix(), repo_root
            ).encode("utf-8"),
        ):
            child_relative = normalize_repo_relative_path(child.as_posix(), repo_root)
            entries.append(
                {
                    "path": child_relative,
                    "content_digest": _node_content_digest(
                        child, repo_root, visited
                    ),
                    "symlink": child.is_symlink(),
                }
            )
        return canonical_digest(entries)
    return canonical_digest({"state": "other", "path": relative})


def _symlink_identity(
    path: Path,
    repo_root: Path,
    visited: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    relative = normalize_repo_relative_path(path.as_posix(), repo_root)
    raw_target = os.readlink(path)
    target_relative, target_path = _lexical_target(path, raw_target, repo_root)
    target_digest = canonical_digest(target_relative)
    if relative in visited:
        return {
            "path": relative,
            "target": target_relative,
            "target_digest": target_digest,
            "target_content_digest": canonical_digest(
                {"state": "cycle", "path": relative}
            ),
            "broken": False,
        }
    broken = not target_path.exists() and not target_path.is_symlink()
    target_content_digest = (
        None
        if broken
        else _node_content_digest(
            target_path, repo_root, visited | frozenset({relative})
        )
    )
    return {
        "path": relative,
        "target": target_relative,
        "target_digest": target_digest,
        "target_content_digest": target_content_digest,
        "broken": broken,
    }


def snapshot_paths(
    raw_paths: list[str | os.PathLike[str]],
    *,
    repo_root: Path,
) -> list[dict[str, Any]]:
    """Snapshot a path set with one Git index/status read."""

    normalized = sorted(
        {normalize_repo_relative_path(path, repo_root) for path in raw_paths},
        key=lambda item: item.encode("utf-8"),
    )
    if not normalized:
        return []
    tracked_result = _git(repo_root, "ls-files", "-z", "--", *normalized)
    tracked_paths = {
        normalize_repo_relative_path(raw.decode("utf-8"), repo_root)
        for raw in tracked_result.stdout.split(b"\0")
        if raw
    }
    head_result = _git(repo_root, "ls-tree", "-r", "-z", "--name-only", "HEAD", "--", *normalized)
    head_paths = {
        normalize_repo_relative_path(raw.decode("utf-8"), repo_root)
        for raw in head_result.stdout.split(b"\0")
        if raw
    }
    head_result = _git(
        repo_root, "ls-tree", "-z", "--name-only", "HEAD", "--", *normalized
    )
    head_paths = {
        normalize_repo_relative_path(raw.decode("utf-8"), repo_root)
        for raw in head_result.stdout.split(b"\0")
        if raw
    }
    status_result = _git(
        repo_root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--",
        *normalized,
    )
    statuses: dict[str, tuple[str, str | None]] = {}
    if status_result.returncode == 0:
        for current, code, renamed_from in _parse_status_records(
            status_result.stdout, repo_root
        ):
            statuses[current] = (code, renamed_from)
    fallback_paths = {
        relative
        for relative in normalized
        if relative in tracked_paths
        and relative not in head_paths
        and "A" in statuses.get(relative, ("", None))[0]
    }
    # Pathspec status 会把 rename source 折叠成 destination 的 scoped A。候选集合
    # 非空时只做一次 whole-tree 查询，并仅用它修复这些 destination 的 rename identity。
    if fallback_paths:
        global_status = _git(
            repo_root,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        )
        if global_status.returncode == 0:
            for current, code, renamed_from in _parse_status_records(
                global_status.stdout, repo_root
            ):
                if current in fallback_paths:
                    statuses[current] = (code, renamed_from)
    results: list[dict[str, Any]] = []
    for relative in normalized:
        path = repo_root / relative
        tracked = relative in tracked_paths
        status, renamed_from = statuses.get(relative, ("", None))
        exists = path.exists() or path.is_symlink()
        exists_at_head = relative in head_paths
        symlink = path.is_symlink()
        symlink_identity = _symlink_identity(path, repo_root) if symlink else None
        if symlink:
            state = "symlink"
            content_digest = canonical_digest(symlink_identity)
        elif "R" in status or "C" in status:
            state = "renamed"
            content_digest = _node_content_digest(path, repo_root, frozenset())
        elif exists:
            state = "directory" if path.is_dir() else "file"
            content_digest = _node_content_digest(path, repo_root, frozenset())
        else:
            state = "deleted" if exists_at_head else "missing"
            content_digest = _head_blob_digest(relative, repo_root)
        result = {
            "path": relative,
            "exists": exists,
            "state": state,
            "tracked": tracked,
            "git_status": status,
            "content_digest": content_digest,
            "renamed_from": renamed_from,
            "symlink_target": symlink_identity["target"] if symlink_identity else None,
            "symlink_target_digest": (
                symlink_identity["target_digest"] if symlink_identity else None
            ),
            "symlink_target_content_digest": (
                symlink_identity["target_content_digest"] if symlink_identity else None
            ),
            "broken": symlink_identity["broken"] if symlink_identity else False,
        }
        expected = _definition()["path_snapshot_fields"]
        if set(result) != set(expected):
            raise EvidenceFingerprintError("EvidenceFingerprint path snapshot 字段漂移")
        results.append({field: result[field] for field in expected})
    return results


def snapshot_path(
    raw_path: str | os.PathLike[str],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    """Snapshot one path; multi-path consumers should use snapshot_paths."""

    return snapshot_paths([raw_path], repo_root=repo_root)[0]


def workspace_digests(
    paths: list[str],
    *,
    repo_root: Path,
) -> dict[str, str]:
    """Classify normalized path snapshots into the five declared workspace digests."""

    normalized = sorted(
        {normalize_repo_relative_path(path, repo_root) for path in paths},
        key=lambda item: item.encode("utf-8"),
    )
    buckets: dict[str, list[dict[str, Any]]] = {
        category: [] for category in _definition()["workspace_category_order"]
    }
    for snapshot in snapshot_paths(normalized, repo_root=repo_root):
        if snapshot["state"] == "symlink":
            category = "symlink"
        elif snapshot["state"] == "renamed":
            category = "renamed"
        elif snapshot["state"] == "deleted":
            category = "deleted"
        elif snapshot["tracked"]:
            category = "tracked"
        else:
            category = "untracked"
        buckets[category].append(snapshot)
    return {
        f"{category}_digest": canonical_digest(buckets[category])
        for category in _definition()["workspace_category_order"]
    }
