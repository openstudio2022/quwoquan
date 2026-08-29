"""对一个入池批次里的单个对象做逐项应用，并为整批回滚准备可逆现场。

本模块只负责「一项」：校验声明身份与磁盘实际是否逐字节一致、决定该项落 ready /
pending / appended，以及在 author 投影这类需要整目录替换的路径上保留可回退的备份。
批次级判否、报告与 all-or-nothing 提交留在 `pool_append`。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from content.release.canonical.content_pool_record import (
    append_pool_record,
    is_pool_record_admitted,
    pool_payload_digest,
    preflight_pool_record_append,
)
from content.release.canonical.creator_projection import project_creator_object
from content.release.canonical.object_source_identity import (
    validate_object_source_identity,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_file,
    _read_json,
    _safe_rel,
)

__all__ = [
    "apply_pool_item",
    "item_target",
    "prepare_item_rollback",
    "restore_batch",
]


def _replace_author_projection(
    *, target: Path, creator_ref: str, record: Mapping[str, Any]
) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.pool-", dir=target.parent))
    backup = target.with_name(f".{target.name}.{os.getpid()}.pool-backup")
    try:
        projection = staging / "projection"
        project_creator_object(creator_ref, projection)
        profile = _read_json(projection / "profile.json")
        if (
            str(profile.get("authorId") or "") != str(record["objectId"])
            or profile.get("version") != record["contentVersion"]
        ):
            raise ObjectTransactionError("DATA.POOL.AUTHOR_PROJECTION_IDENTITY_DRIFT")
        if target.is_dir() and (target / "_pool").is_dir():
            shutil.copytree(target / "_pool", projection / "_pool")
        append_status, _ = append_pool_record(object_root=projection, record=record)
        if target.exists():
            if backup.exists():
                raise ObjectTransactionError("DATA.POOL.AUTHOR_BACKUP_CONFLICT")
            os.replace(target, backup)
        try:
            os.replace(projection, target)
        except BaseException:
            if backup.exists() and not target.exists():
                os.replace(backup, target)
            raise
        shutil.rmtree(backup, ignore_errors=True)
        return append_status
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def apply_pool_item(
    item: Mapping[str, Any], *, publish_root: Path, creator_pool_root: Path, apply: bool
) -> dict[str, Any]:
    record = dict(item["record"])
    object_type = str(record.get("objectType") or "")
    object_ref = _safe_rel(str(record.get("objectRef") or ""), label="objectRef")
    if object_type == "author":
        source = creator_pool_root / _safe_rel(
            str(item.get("sourceRef") or ""), label="sourceRef"
        )
        target = publish_root / "creators" / object_ref
        evidence = creator_pool_root / _safe_rel(
            str(record.get("evidenceRef") or ""), label="evidenceRef"
        )
        actual_payload_digest = _digest_file(source)
        try:
            profile = yaml.safe_load(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ObjectTransactionError("DATA.POOL.AUTHOR_PROFILE_INVALID") from exc
        if (
            not isinstance(profile, Mapping)
            or profile.get("creatorProfileId") != object_ref.as_posix()
            or profile.get("authorId") != record.get("objectId")
            or profile.get("version") != record.get("contentVersion")
            or not isinstance(profile.get("admission"), Mapping)
            or profile["admission"].get("processResult")
            != record.get("processResult")
            or profile["admission"].get("qualityResult")
            != record.get("qualityResult")
            or profile["admission"].get("evidenceRef")
            != record.get("evidenceRef")
            or profile["admission"].get("evidenceDigest")
            != record.get("evidenceDigest")
        ):
            raise ObjectTransactionError("DATA.POOL.AUTHOR_IDENTITY_DRIFT")
    elif object_type in {"content", "homepage"}:
        kind = "posts" if object_type == "content" else "entities"
        target = publish_root / kind / object_ref
        declared_source = _safe_rel(str(item.get("sourceRef") or ""), label="sourceRef")
        if declared_source != Path(kind) / object_ref:
            raise ObjectTransactionError("DATA.POOL.SOURCE_REF_MISMATCH")
        source = target
        evidence = target / _safe_rel(
            str(record.get("evidenceRef") or ""), label="evidenceRef"
        )
        actual_payload_digest = pool_payload_digest(target)
        manifest = _read_json(target / "manifest.json")
        if record.get("sourceAttribution") != manifest.get("sourceAttribution"):
            raise ObjectTransactionError(
                "DATA.POOL.SOURCE_ATTRIBUTION_DRIFT"
            )
        declared_identity = record.get("sourceIdentity")
        if not isinstance(declared_identity, Mapping):
            raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_INVALID")
        expected_identity = validate_object_source_identity(manifest)
        if dict(declared_identity) != expected_identity:
            raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_DRIFT")
    else:
        raise ObjectTransactionError("DATA.POOL.RECORD_OBJECT_TYPE_INVALID")
    if not source.exists() or actual_payload_digest != record.get("payloadDigest"):
        raise ObjectTransactionError("DATA.POOL.PAYLOAD_DIGEST_DRIFT")
    if not evidence.is_file() or _digest_file(evidence) != record.get("evidenceDigest"):
        raise ObjectTransactionError("DATA.POOL.EVIDENCE_DIGEST_DRIFT")
    admitted = is_pool_record_admitted(record)
    if not admitted:
        status = "pending"
    elif not apply:
        write_status, _ = preflight_pool_record_append(
            object_root=target,
            record=record,
        )
        status = "ready" if write_status == "appended" else write_status
    elif object_type == "author":
        status = _replace_author_projection(
            target=target, creator_ref=object_ref.as_posix(), record=record
        )
    else:
        status, _ = append_pool_record(object_root=target, record=record)
    return {
        "itemId": str(item["itemId"]),
        "objectType": object_type,
        "objectId": str(record.get("objectId") or ""),
        "contentVersion": int(record.get("contentVersion") or 0),
        "recordSequence": int(record.get("recordSequence") or 0),
        "status": status,
        "eligibilityResult": str(record.get("eligibilityResult") or ""),
        "usageScope": record.get("usageScope"),
    }


def item_target(item: Mapping[str, Any], publish_root: Path) -> Path:
    record = item["record"]
    object_type = str(record.get("objectType") or "")
    object_ref = _safe_rel(str(record.get("objectRef") or ""), label="objectRef")
    if object_type == "author":
        return publish_root / "creators" / object_ref
    if object_type == "content":
        return publish_root / "posts" / object_ref
    if object_type == "homepage":
        return publish_root / "entities" / object_ref
    raise ObjectTransactionError("DATA.POOL.RECORD_OBJECT_TYPE_INVALID")


def restore_batch(
    *,
    author_backups: list[tuple[Path, Path | None]],
    record_targets: list[Path],
) -> None:
    for target in reversed(record_targets):
        target.unlink(missing_ok=True)
    for target, backup in reversed(author_backups):
        if target.exists():
            shutil.rmtree(target)
        if backup is not None and backup.exists():
            os.replace(backup, target)


def prepare_item_rollback(
    item: Mapping[str, Any], *, publish_root: Path, rollback_root: Path, index: int
) -> tuple[list[tuple[Path, Path | None]], list[Path]]:
    target = item_target(item, publish_root)
    record = item["record"]
    if record["objectType"] != "author":
        return [], [
            target / "_pool" / "versions" / f"{record['recordSequence']}.json"
        ]
    backup = rollback_root / f"author-{index}"
    if target.exists():
        shutil.copytree(target, backup)
        return [(target, backup)], []
    return [(target, None)], []
