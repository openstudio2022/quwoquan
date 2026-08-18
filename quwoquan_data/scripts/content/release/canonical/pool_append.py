"""Plan and apply object-level pool admission without rewriting canonical objects."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from content.release.canonical.content_pool_record import (
    append_pool_record,
    is_pool_record_admitted,
    iter_pool_records,
    pool_payload_digest,
    preflight_pool_record_append,
)
from content.release.canonical.creator_projection import project_creator_object
from content.release.canonical.object_source_identity import (
    validate_object_source_identity,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_bytes,
    _digest_file,
    _json_bytes,
    _read_json,
    _safe_rel,
    refresh_canonical_tag_snapshots,
)
from content.release.canonical.pool_append_report import (
    batch_reason,
    batch_report,
    excluded_outcome,
    is_hard_batch_failure,
)
from content.release.canonical.pool_backfill_canonical import (
    build_pool_record,
    canonical_plan_items,
)
from core.paths import CONTROL_PLANE_CREATOR_POOL_ROOT, PUBLISH_ROOT
from core.schema import assert_valid

BATCH_SCHEMA = "quwoquan_data.pool_append_batch"
PLAN_SCHEMA = "quwoquan_data.pool_backfill_plan"


def _result_value(*, ready: int, pending: int, failed: int) -> str:
    if ready and not pending and not failed:
        return "ready"
    if ready:
        return "partial"
    return "blocked"


def _checks(*, ready: int, pending: int, failed: int) -> dict[str, str]:
    return {
        "quality": "failed" if failed else "passed",
        "eligibility": "failed" if pending or failed else "passed",
        "delivery": "passed" if ready else "failed",
    }


def _profile_rows(creator_pool_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    rows: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted((creator_pool_root / "profiles").rglob("*.creator.yaml")):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ObjectTransactionError(f"creator profile unreadable: {path}: {exc}") from exc
        if isinstance(payload, dict):
            rows.append((path, payload))
    return rows


def _author_plan_items(
    creator_pool_root: Path,
    publish_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]]]:
    items: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    already_admitted: list[dict[str, str]] = []
    for path, profile in _profile_rows(creator_pool_root):
        admission = profile.get("admission")
        version = profile.get("version")
        creator_ref = str(profile.get("creatorProfileId") or "").strip()
        author_id = str(profile.get("authorId") or "").strip()
        exclusion = {
            "objectType": "author",
            "objectRef": creator_ref or path.relative_to(creator_pool_root).as_posix(),
        }
        if profile.get("status") != "active":
            continue
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version < 1
            or not isinstance(admission, Mapping)
            or admission.get("processResult") != "completed"
            or admission.get("qualityResult") != "passed"
            or not creator_ref
            or not author_id
        ):
            exclusions.append(
                {**exclusion, "reason": "DATA.POOL.AUTHOR_IDENTITY_INVALID"}
            )
            continue
        evidence_ref = str(admission.get("evidenceRef") or "").strip()
        evidence_path = creator_pool_root / _safe_rel(
            evidence_ref, label="author.evidenceRef"
        )
        evidence_digest = str(admission.get("evidenceDigest") or "").strip()
        if not evidence_path.is_file() or _digest_file(evidence_path) != evidence_digest:
            exclusions.append(
                {**exclusion, "reason": "DATA.POOL.EVIDENCE_DIGEST_DRIFT"}
            )
            continue
        target = publish_root / "creators" / creator_ref
        try:
            records = iter_pool_records(target, object_type="author")
        except (OSError, TypeError, ValueError, ObjectTransactionError):
            exclusions.append(
                {**exclusion, "reason": "DATA.POOL.AUTHOR_IDENTITY_INVALID"}
            )
            continue
        if any(
            row.get("objectId") != author_id or row.get("objectRef") != creator_ref
            for row in records
        ):
            exclusions.append(
                {**exclusion, "reason": "DATA.POOL.AUTHOR_IDENTITY_INVALID"}
            )
            continue
        record_sequence = int(records[-1]["recordSequence"]) + 1 if records else 1
        record = build_pool_record(
            object_type="author",
            object_id=author_id,
            object_ref=creator_ref,
            record_sequence=record_sequence,
            content_version=version,
            process_result="completed",
            quality_result="passed",
            eligibility_result="passed",
            usage_scope=None,
            evidence_ref=evidence_ref,
            evidence_digest=evidence_digest,
            payload_digest=_digest_file(path),
        )
        latest = records[-1] if records else None
        if latest is not None and is_pool_record_admitted(latest):
            replay_record = dict(record)
            replay_record["recordSequence"] = latest["recordSequence"]
            if latest == replay_record:
                already_admitted.append(exclusion)
                continue
            if latest.get("contentVersion") == version:
                exclusions.append(
                    {**exclusion, "reason": "DATA.POOL.AUTHOR_RECORD_DRIFT"}
                )
                continue
        items.append(
            {
                "itemId": f"author:{creator_ref}:{version}",
                "sourceRef": path.relative_to(creator_pool_root).as_posix(),
                "record": record,
            }
        )
    return items, exclusions, already_admitted


def plan_pool_backfill(
    *,
    publish_root: Path = PUBLISH_ROOT,
    creator_pool_root: Path = CONTROL_PLANE_CREATOR_POOL_ROOT,
) -> dict[str, Any]:
    """Derive a read-only append batch exclusively from existing evidence."""

    entity_items, entity_exclusions, entity_repairs, entity_admitted = canonical_plan_items(
        publish_root, "entities"
    )
    content_items, content_exclusions, content_repairs, content_admitted = canonical_plan_items(
        publish_root, "posts"
    )
    author_items, author_exclusions, author_admitted = _author_plan_items(
        creator_pool_root, publish_root
    )
    exclusions = [*author_exclusions, *entity_exclusions, *content_exclusions]
    already_admitted = [*author_admitted, *entity_admitted, *content_admitted]
    items = [*author_items, *entity_items, *content_items]
    items.sort(key=lambda item: str(item["itemId"]))
    counts = Counter(str(item["record"]["objectType"]) for item in items)
    counts.update(str(item["objectType"]) for item in exclusions)
    counts.update(str(item["objectType"]) for item in already_admitted)
    planned_admitted = sum(is_pool_record_admitted(item["record"]) for item in items)
    admitted = planned_admitted + len(already_admitted)
    pending = sum(
        item["record"]["eligibilityResult"] == "pending" for item in items
    )
    failed = len(items) - planned_admitted - pending + len(exclusions)
    batch = {
        "schema": BATCH_SCHEMA,
        "appendSetId": "canonical-evidence-backfill",
        "items": items,
    }
    batch["batchDigest"] = _digest_bytes(_json_bytes(batch))
    return {
        "schema": PLAN_SCHEMA,
        "result": _result_value(ready=admitted, pending=pending, failed=failed),
        "checks": _checks(ready=admitted, pending=pending, failed=failed),
        "counts": {
            "total": len(items) + len(exclusions) + len(already_admitted),
            "ready": admitted,
            "alreadyAdmitted": len(already_admitted),
            "eligibilityPending": pending,
            "failed": failed,
            "authors": counts["author"],
            "homepages": counts["homepage"],
            "contents": counts["content"],
        },
        "reasons": sorted(
            {
                str(item["reason"])
                for item in items
                if str(item.get("reason") or "").strip()
            }
            | {row["reason"] for row in exclusions}
        ),
        "detailsRef": None,
        "repairRequirements": [*entity_repairs, *content_repairs],
        "batch": batch,
    }


def _validate_batch(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    if document.get("schema") == PLAN_SCHEMA:
        document = document.get("batch") or {}
    if document.get("schema") != BATCH_SCHEMA:
        raise ObjectTransactionError("DATA.POOL.BATCH_SCHEMA_INVALID")
    try:
        assert_valid(
            dict(document),
            "release",
            "pool_append_batch",
            label="pool_append_batch",
        )
    except (FileNotFoundError, ValueError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    declared_digest = str(document.get("batchDigest") or "")
    if declared_digest:
        digest_payload = dict(document)
        digest_payload.pop("batchDigest", None)
        if _digest_bytes(_json_bytes(digest_payload)) != declared_digest:
            raise ObjectTransactionError("DATA.POOL.BATCH_DIGEST_DRIFT")
    items = document.get("items")
    if not isinstance(items, list) or not items:
        raise ObjectTransactionError("DATA.POOL.BATCH_EMPTY")
    identities: set[str] = set()
    targets: set[tuple[str, str, int]] = set()
    result: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, Mapping):
            raise ObjectTransactionError("DATA.POOL.BATCH_ITEM_INVALID")
        item = dict(raw)
        item_id = str(item.get("itemId") or "").strip()
        if not item_id or item_id in identities:
            raise ObjectTransactionError("DATA.POOL.BATCH_ITEM_ID_CONFLICT")
        identities.add(item_id)
        if not isinstance(item.get("record"), Mapping):
            raise ObjectTransactionError("DATA.POOL.BATCH_RECORD_MISSING")
        record = item["record"]
        target = (
            str(record.get("objectType") or ""),
            str(record.get("objectRef") or ""),
            int(record.get("recordSequence") or 0),
        )
        if target in targets:
            raise ObjectTransactionError("DATA.POOL.BATCH_TARGET_CONFLICT")
        targets.add(target)
        result.append(item)
    return result


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


def _apply_item(
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


def _item_target(item: Mapping[str, Any], publish_root: Path) -> Path:
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


def _restore_batch(
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


def _prepare_item_rollback(
    item: Mapping[str, Any], *, publish_root: Path, rollback_root: Path, index: int
) -> tuple[list[tuple[Path, Path | None]], list[Path]]:
    target = _item_target(item, publish_root)
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


def append_pool_batch(
    *,
    input_path: Path,
    publish_root: Path = PUBLISH_ROOT,
    creator_pool_root: Path = CONTROL_PLANE_CREATOR_POOL_ROOT,
    apply: bool = False,
) -> dict[str, Any]:
    """Append every valid object; only structural corruption aborts siblings."""

    document = _read_json(input_path)
    items = _validate_batch(document)
    preflight: dict[str, dict[str, Any]] = {}
    reasons: list[dict[str, str]] = []
    pending = 0
    failed = 0
    for item in items:
        try:
            outcome = _apply_item(
                item,
                publish_root=publish_root,
                creator_pool_root=creator_pool_root,
                apply=False,
            )
            preflight[str(item["itemId"])] = outcome
            if outcome["eligibilityResult"] != "passed":
                pending += 1
                reasons.append(
                    {
                        "category": "eligibility",
                        "itemId": str(item["itemId"]),
                        "code": str(
                            item.get("reason")
                            or "DATA.POOL.ELIGIBILITY_EVIDENCE_PENDING"
                        ),
                    }
                )
        except (OSError, TypeError, ValueError, ObjectTransactionError) as exc:
            if is_hard_batch_failure(exc):
                return batch_report(
                    apply=apply,
                    total=len(items),
                    ready=0,
                    pending=0,
                    failed=len(items),
                    reasons=[batch_reason(item, exc)],
                    outcomes=[],
                )
            failed += 1
            reasons.append(batch_reason(item, exc))
            preflight[str(item["itemId"])] = excluded_outcome(item)
    ready_items = [
        item
        for item in items
        if preflight[str(item["itemId"])]["status"] not in {"pending", "excluded"}
    ]
    if not apply:
        return batch_report(
            apply=False,
            total=len(items),
            ready=len(ready_items),
            pending=pending,
            failed=failed,
            reasons=reasons,
            outcomes=[preflight[str(item["itemId"])] for item in items],
        )

    rollback_root = Path(tempfile.mkdtemp(
        prefix=".pool-batch-rollback-", dir=publish_root.parent
    ))
    author_backups: list[tuple[Path, Path | None]] = []
    record_targets: list[Path] = []
    ready = 0
    try:
        for index, item in enumerate(ready_items):
            outcome = preflight[str(item["itemId"])]
            if outcome["status"] == "replayed":
                ready += 1
                continue
            item_authors, item_records = _prepare_item_rollback(
                item,
                publish_root=publish_root,
                rollback_root=rollback_root,
                index=index,
            )
            try:
                preflight[str(item["itemId"])] = _apply_item(
                    item,
                    publish_root=publish_root,
                    creator_pool_root=creator_pool_root,
                    apply=True,
                )
            except (OSError, TypeError, ValueError, ObjectTransactionError) as exc:
                if is_hard_batch_failure(exc):
                    _restore_batch(
                        author_backups=[*author_backups, *item_authors],
                        record_targets=[*record_targets, *item_records],
                    )
                    return batch_report(
                        apply=True,
                        total=len(items),
                        ready=0,
                        pending=0,
                        failed=len(items),
                        reasons=[batch_reason(item, exc)],
                        outcomes=[],
                    )
                _restore_batch(
                    author_backups=item_authors,
                    record_targets=item_records,
                )
                failed += 1
                reasons.append(batch_reason(item, exc))
                preflight[str(item["itemId"])] = excluded_outcome(item)
                continue
            author_backups.extend(item_authors)
            record_targets.extend(item_records)
            ready += 1
    finally:
        shutil.rmtree(rollback_root, ignore_errors=True)
    # A projected creator carries its own tag references, so the batch owns their
    # snapshot closure. Collection walks the whole canonical tree, which is why it
    # settles once per batch here instead of per admitted object; an unresolvable
    # reference leaves publish unclosed and must surface rather than be absorbed.
    refresh_canonical_tag_snapshots(publish_root)
    return batch_report(
        apply=True,
        total=len(items),
        ready=ready,
        pending=pending,
        failed=failed,
        reasons=reasons,
        outcomes=[preflight[str(item["itemId"])] for item in items],
    )


__all__ = ["append_pool_batch", "plan_pool_backfill"]
