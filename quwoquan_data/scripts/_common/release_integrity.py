"""Release integrity gate for source, base draft and asset reuse.

This module is imported by CLI gates; it is not a standalone business script.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import re
from pathlib import Path
from collections.abc import Iterable
from typing import Any, Mapping

from _common.io import read_json
from _common.image_rules import image_caption_quality_issue, image_known_reject_issue
from _common.paths import batch_root, release_root
from _common.base_draft import ARTICLE_MIN_BASE_DRAFT_CHARS, base_draft_readiness
from _common.content_source_registry import homepage_source_can_seed_base_draft


REPORT_SCHEMA = "quwoquan_data.release_integrity"
BASE_DRAFT_LEDGER_SCHEMA = "quwoquan_data.base_draft_ledger"
# RC6：长文字数门唯一真相源是 base_draft.ARTICLE_MIN_BASE_DRAFT_CHARS，此处仅做兼容别名，
# 不再另立独立字面量第二真相源。
MIN_ARTICLE_BASE_DRAFT_CHARS = ARTICLE_MIN_BASE_DRAFT_CHARS

# 文章硬门分两类：
# 1) COMMON——entity 文章与 route 文章两种 review builder 都会产出的检查，逐一必须 present+passed。
# 2) 载体可变对——entity 用 entityCoverage/sectionShape，route 用 routeCoverage/narrativeContinuity；
#    每对至少有一个 present+passed（修复历史错配：旧集合只列 entity 名，route 文章在 release 误报缺失）。
ARTICLE_HARD_CHECKS = {
    "provenanceRewrite",
    "evidenceQuality",
    "carrierConsistency",
    "proseStyle",
    "imageGate",
    "crossArticleSimilarity",
    "generatorProvenance",
    "factTraceability",
    "baseDraftFidelity",
    "sectionBalance",
    "timelineOrder",
    "registerMismatch",
    "contactInfo",
    "mechanicalHeading",
}
ARTICLE_COVERAGE_HARD_CHECKS = ("entityCoverage", "routeCoverage")
ARTICLE_STRUCTURE_HARD_CHECKS = ("sectionShape", "narrativeContinuity")
AUTHOR_EXPERIENCE_SOURCE_KINDS = ("攻略", "游记", "评论", "点评", "小红书", "图虫", "摄影")


def _payload(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except Exception:  # noqa: BLE001
        return {}
    if isinstance(data, dict) and isinstance(data.get("payload"), dict):
        return data["payload"]
    return data if isinstance(data, dict) else {}


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def _norm_sha(value: str) -> str:
    raw = str(value or "").strip()
    if raw.startswith("sha256:"):
        return raw.split(":", 1)[1]
    return raw


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _is_image_post(manifest: Mapping[str, Any]) -> bool:
    carrier = str(manifest.get("carrier") or manifest.get("contentType") or "")
    return carrier in {"image", "gallery"}


def _is_video_post(manifest: Mapping[str, Any]) -> bool:
    carrier = str(manifest.get("carrier") or manifest.get("contentType") or "")
    return carrier == "video"


def _is_text_only_article(manifest: Mapping[str, Any], runtime_post: Path | None = None) -> bool:
    if _is_image_post(manifest) or _is_video_post(manifest):
        return False
    if str(manifest.get("publishMediaMode") or "").strip() == "text_only":
        return True
    if runtime_post is not None:
        pack = _json(runtime_post / "3.compose" / "writing_pack.json")
        if str(pack.get("publishMediaMode") or "").strip() == "text_only":
            return True
    return False


def _post_entity_name(manifest: Mapping[str, Any]) -> str:
    refs = [str(ref) for ref in (manifest.get("entityRefs") or [])]
    for ref in refs:
        if "/" in ref:
            return ref.rstrip("/").rsplit("/", 1)[-1]
    normalized = [str(ref) for ref in (manifest.get("normalizedEntityRefs") or [])]
    for ref in normalized:
        if ":" in ref:
            return ref.rsplit(":", 1)[-1]
    title = str(manifest.get("title") or manifest.get("publishTitle") or "").strip()
    if "·" in title:
        prefix = title.split("·", 1)[0].strip()
        if prefix:
            return prefix
    return ""


def _source_unit_meta(runtime_batch: Path, source_ref: str) -> dict[str, Any]:
    if not source_ref:
        return {}
    source_path = runtime_batch / source_ref
    unit = source_path.parent
    meta_path = unit / "meta.json"
    if meta_path.is_file():
        return _json(meta_path)
    return {}


def _same_source_unit(source_ref: str, source_asset_ref: str) -> bool:
    if not source_ref or not source_asset_ref:
        return False
    source_unit = str(source_ref).rsplit("/", 1)[0]
    return str(source_asset_ref).startswith(source_unit + "/assets/")


def _has_rights_proof(*payloads: Mapping[str, Any]) -> bool:
    keys = ("authorizationProof", "licenseSnapshot", "termsUrl", "licenseProof")
    for payload in payloads:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return True
            if isinstance(value, Mapping) and value:
                return True
    return False


def _effective_review(path: Path) -> dict[str, Any]:
    return _payload(path)


def _review_gate_issues(post_rel: str, runtime_post: Path) -> list[str]:
    issues: list[str] = []
    review = _effective_review(runtime_post / "5.review" / "review.json")
    gate = _effective_review(runtime_post / "5.review" / "review_gate.json")
    if not review:
        return [f"{post_rel}: missing runtime 5.review/review.json"]
    if gate and (gate.get("passed") is False or gate.get("issues")):
        issues.append(f"{post_rel}: review_gate is not clean")
    decision = str(review.get("decision") or "")
    if decision != "approved":
        issues.append(f"{post_rel}: review decision is not approved: {decision or '<empty>'}")
    checks = review.get("checks") or {}
    if not isinstance(checks, Mapping):
        issues.append(f"{post_rel}: review.checks must be an object")
        return issues
    for name in sorted(ARTICLE_HARD_CHECKS):
        check = checks.get(name)
        if not isinstance(check, Mapping):
            issues.append(f"{post_rel}: hard review check missing: {name}")
        elif check.get("passed") is not True:
            detail = check.get("issues") or check.get("reason") or ""
            issues.append(f"{post_rel}: hard review check failed: {name} {detail}")
    for pair in (ARTICLE_COVERAGE_HARD_CHECKS, ARTICLE_STRUCTURE_HARD_CHECKS):
        present = [name for name in pair if isinstance(checks.get(name), Mapping)]
        if not present:
            issues.append(f"{post_rel}: hard review check missing: one of {'/'.join(pair)}")
            continue
        if not any(checks[name].get("passed") is True for name in present):
            detail = checks[present[0]].get("issues") or checks[present[0]].get("reason") or ""
            issues.append(
                f"{post_rel}: hard review check failed: {'/'.join(present)} {detail}"
            )
    return issues


def _base_draft_issues(
    *,
    release_id: str,
    post_rel: str,
    manifest: Mapping[str, Any],
    runtime_post: Path,
    ledger: Mapping[str, Any],
) -> list[str]:
    issues: list[str] = []
    source_refs = _json(runtime_post / "1.download" / "source_refs.json")
    writing_pack = _json(runtime_post / "3.compose" / "writing_pack.json")
    if not source_refs:
        return [f"{post_rel}: missing runtime 1.download/source_refs.json"]
    if not writing_pack:
        return [f"{post_rel}: missing runtime 3.compose/writing_pack.json"]
    base_source = str(source_refs.get("baseSourceRef") or "").strip()
    pack_base = str(writing_pack.get("baseSourceRef") or "").strip()
    topic_id = str(manifest.get("topicId") or "").strip()
    if not base_source:
        issues.append(f"{post_rel}: baseSourceRef is empty")
    if base_source != pack_base:
        issues.append(f"{post_rel}: source_refs.baseSourceRef != writing_pack.baseSourceRef")
    assignments = ledger.get("assignments") if isinstance(ledger, Mapping) else {}
    if not isinstance(assignments, Mapping) or not assignments:
        issues.append(f"{release_id}: base_draft_ledger.assignments missing")
    else:
        assigned = assignments.get(base_source) if base_source else None
        assigned_refs = (
            [str(item) for item in assigned if str(item).strip()]
            if isinstance(assigned, list)
            else ([str(assigned)] if str(assigned or "").strip() else [])
        )
        if base_source and topic_id not in assigned_refs:
            issues.append(
                f"{post_rel}: base draft ledger does not map {base_source} to topicId {topic_id}"
            )
    base_text = str(writing_pack.get("baseDraftText") or "")
    readiness = base_draft_readiness(
        base_text,
        publish_media_mode=str(writing_pack.get("publishMediaMode") or manifest.get("publishMediaMode") or ""),
    )
    if not readiness["ready"]:
        issues.append(
            f"{post_rel}: baseDraftText too short for article "
            f"({readiness['effectiveChars']} < {MIN_ARTICLE_BASE_DRAFT_CHARS}; "
            f"figures={readiness['inlineFigureCount']} captions={readiness['captionChars']})"
        )
    return issues


def _article_asset_source_issues(
    *,
    post_rel: str,
    asset_label: str,
    asset: Mapping[str, Any],
    runtime_post: Path | None,
) -> list[str]:
    if runtime_post is None:
        return []
    source_refs = _json(runtime_post / "1.download" / "source_refs.json")
    base_source = str(source_refs.get("baseSourceRef") or "").strip()
    source_ref = str(asset.get("sourceRef") or "").strip()
    source_asset_ref = str(asset.get("sourceAssetRef") or "").strip()
    issues: list[str] = []
    if source_ref and source_asset_ref and not _same_source_unit(source_ref, source_asset_ref):
        issues.append(
            f"{post_rel}: {asset_label} sourceAssetRef must belong to its declared sourceRef unit"
        )
    return issues


def _asset_alignment_issues(post_rel: str, manifest: Mapping[str, Any], asset: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    caption = str(asset.get("caption") or "").strip()
    entity_name = _post_entity_name(manifest)
    asset_label = str(asset.get("assetId") or asset.get("fileName") or "?")
    caption_quality_issue = image_caption_quality_issue(
        caption,
        entity_id=entity_name,
        asset_id=asset_label,
    )
    if caption_quality_issue:
        issues.append(f"{post_rel}: {caption_quality_issue}")
    known_reject_issue = image_known_reject_issue(
        " ".join(
            str(value or "")
            for value in (
                caption,
                manifest.get("caption"),
                manifest.get("title"),
                manifest.get("publishTitle"),
                asset.get("sourceRef"),
                asset.get("sourceAssetRef"),
                asset.get("collectionPageUrl"),
                asset.get("sourceCollectionId"),
            )
        ),
        entity_id=entity_name,
        asset_id=asset_label,
    )
    if known_reject_issue:
        issues.append(f"{post_rel}: {known_reject_issue}")
    if _is_image_post(manifest):
        return issues
    if not caption:
        issues.append(f"{post_rel}: article asset caption is empty")
    elif entity_name and caption in {entity_name, f"{entity_name}·回望"}:
        issues.append(f"{post_rel}: article asset caption is too generic for image-text alignment: {caption}")
    if not (
        asset.get("alignmentEvidence")
        or asset.get("imageTextAlignment")
        or asset.get("nearbyText")
        or asset.get("semanticTags")
    ):
        issues.append(f"{post_rel}: article asset missing image-text alignment evidence")
    return issues


def _entity_homepage_issues(root: Path, runtime_batch: Path | None) -> list[str]:
    issues: list[str] = []
    entity_manifests = sorted((root / "entities").rglob("manifest.json")) if (root / "entities").is_dir() else []
    for manifest_path in entity_manifests:
        entity_rel = manifest_path.parent.relative_to(root).as_posix()
        runtime_entity = (runtime_batch / entity_rel) if runtime_batch and runtime_batch.is_dir() else None
        if runtime_entity is None:
            continue
        quality = _json(runtime_entity / "2.quality" / "quality_analysis.json")
        compose = _payload(runtime_entity / "3.compose" / "entity_page_input.json")
        base_source = str(((quality.get("baseDraft") or {}) if isinstance(quality.get("baseDraft"), Mapping) else {}).get("sourceRef") or "")
        compose_base = str(((compose.get("baseDraft") or {}) if isinstance(compose.get("baseDraft"), Mapping) else {}).get("sourceRef") or "")
        if not base_source:
            issues.append(f"{entity_rel}: entity homepage baseDraft.sourceRef is empty")
            continue
        if compose_base and compose_base != base_source:
            issues.append(f"{entity_rel}: entity homepage quality base draft differs from compose base draft")
        meta = _source_unit_meta(runtime_batch, base_source)
        source_kind = str(meta.get("sourceKind") or meta.get("platform") or "").strip()
        if not homepage_source_can_seed_base_draft(meta):
            issues.append(
                f"{entity_rel}: entity homepage base draft must be homepage primary authority source, got {source_kind or '<empty>'}"
            )
        if any(marker in source_kind for marker in AUTHOR_EXPERIENCE_SOURCE_KINDS):
            issues.append(
                f"{entity_rel}: entity homepage base draft must not be author travelogue/guide/comment source, got {source_kind}"
            )
        assets = _json(manifest_path).get("assets") or []
        if not isinstance(assets, list) or not assets:
            issues.append(f"{entity_rel}: entity homepage must include at least one sourced image asset")
        for index, asset in enumerate(assets if isinstance(assets, list) else []):
            if not isinstance(asset, Mapping):
                continue
            asset_label = str(asset.get("assetId") or asset.get("fileName") or f"asset[{index}]")
            source_ref = str(asset.get("sourceRef") or "").strip()
            source_asset_ref = str(asset.get("sourceAssetRef") or "").strip()
            if not source_ref or not source_asset_ref:
                issues.append(f"{entity_rel}: {asset_label} missing entity homepage image sourceRef/sourceAssetRef")
            if source_ref and source_asset_ref and not _same_source_unit(source_ref, source_asset_ref):
                issues.append(f"{entity_rel}: {asset_label} sourceAssetRef does not belong to sourceRef unit")
            asset_meta = _source_unit_meta(runtime_batch, source_ref)
            if not _has_rights_proof(asset, asset_meta):
                issues.append(f"{entity_rel}: {asset_label} missing entity homepage image rights proof")
    return issues


def scan_release_integrity(release_id: str) -> dict[str, Any]:
    root = release_root(release_id)
    issues: list[str] = []
    stats: dict[str, Any] = {
        "postCount": 0,
        "articleCount": 0,
        "imageCount": 0,
        "videoCount": 0,
        "assetCount": 0,
    }
    if not root.is_dir():
        issues.append(f"{release_id}: release directory not found")
        return {"schemaVersion": REPORT_SCHEMA, "releaseId": release_id, "passed": False, "issues": issues, "stats": stats}

    release_manifest = _json(root / "release_manifest.json")
    task_id = str(release_manifest.get("sourceTaskId") or "").strip()
    batch_id = str(release_manifest.get("sourceBatchId") or "").strip()
    runtime_batch = batch_root(task_id, batch_id) if task_id and batch_id else None
    if not task_id or not batch_id:
        issues.append(f"{release_id}: release_manifest must contain sourceTaskId and sourceBatchId")
    elif runtime_batch is None or not runtime_batch.is_dir():
        issues.append(f"{release_id}: source runtime batch not found: {task_id} / {batch_id}")

    ledger: Mapping[str, Any] = {}
    ledger_loaded = False
    if runtime_batch and runtime_batch.is_dir():
        ledger_path = runtime_batch / "_shared" / "base_draft_ledger.json"
        ledger = _json(ledger_path)
        ledger_loaded = True
        schema = str(ledger.get("schemaVersion") or "")
        # 账本存在性判定延后到统计 articleCount 之后：image/video 作品不认领底稿，
        # 纯图片/视频 release 合法缺账本，不应阻断（schema 异常仍立即报）。
        if ledger and schema != BASE_DRAFT_LEDGER_SCHEMA:
            issues.append(
                f"{release_id}: base_draft_ledger schemaVersion must be "
                f"{BASE_DRAFT_LEDGER_SCHEMA}, got {schema or '<empty>'}"
            )
    if runtime_batch and runtime_batch.is_dir():
        issues.extend(_entity_homepage_issues(root, runtime_batch))

    post_manifests = sorted((root / "posts").rglob("manifest.json")) if (root / "posts").is_dir() else []
    for manifest_path in post_manifests:
        post_rel = manifest_path.parent.relative_to(root).as_posix()
        manifest = _payload(manifest_path)
        stats["postCount"] += 1
        is_image = _is_image_post(manifest)
        is_video = _is_video_post(manifest)
        if is_image:
            stats["imageCount"] += 1
        elif is_video:
            stats["videoCount"] += 1
        else:
            stats["articleCount"] += 1
        runtime_post = (runtime_batch / post_rel) if runtime_batch and runtime_batch.is_dir() else None
        if not is_image and not is_video and runtime_post is not None:
            issues.extend(
                _base_draft_issues(
                    release_id=release_id,
                    post_rel=post_rel,
                    manifest=manifest,
                    runtime_post=runtime_post,
                    ledger=ledger,
                )
            )
            issues.extend(_review_gate_issues(post_rel, runtime_post))

        assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
        if is_video and not assets:
            issues.append(f"{post_rel}: video must include at least one sourced video asset")
        if not is_image and not is_video and not assets and not _is_text_only_article(manifest, runtime_post):
            issues.append(f"{post_rel}: article must include at least one sourced image asset from its base draft")
        for index, asset in enumerate(assets):
            if not isinstance(asset, Mapping):
                issues.append(f"{post_rel}: manifest.assets[{index}] must be an object")
                continue
            stats["assetCount"] += 1
            asset_label = str(asset.get("assetId") or asset.get("fileName") or f"asset[{index}]")
            source_ref = str(asset.get("sourceRef") or "").strip()
            source_asset_ref = str(asset.get("sourceAssetRef") or "").strip()
            if not source_ref:
                issues.append(f"{post_rel}: {asset_label} missing manifest.assets[].sourceRef")
            if not source_asset_ref:
                issues.append(f"{post_rel}: {asset_label} missing manifest.assets[].sourceAssetRef")
            collection_id = str(asset.get("sourceCollectionId") or "").strip()
            manifest_sha = _norm_sha(str(asset.get("sha256") or ""))
            file_name = str(asset.get("fileName") or asset.get("path") or "").strip()
            actual_sha = _file_sha(manifest_path.parent / "assets" / file_name) if file_name else ""
            effective_sha = actual_sha or manifest_sha
            if not manifest_sha:
                issues.append(f"{post_rel}: {asset_label} missing sha256")
            elif actual_sha and manifest_sha != actual_sha:
                issues.append(f"{post_rel}: {asset_label} sha256 mismatch with asset file")
            if runtime_batch and runtime_batch.is_dir() and source_ref:
                meta = _source_unit_meta(runtime_batch, source_ref)
                if not _has_rights_proof(asset, meta):
                    issues.append(f"{post_rel}: {asset_label} missing image authorization proof or license snapshot")
            issues.extend(_asset_alignment_issues(post_rel, manifest, asset))
            if not is_image:
                issues.extend(
                    _article_asset_source_issues(
                        post_rel=post_rel,
                        asset_label=asset_label,
                        asset=asset,
                        runtime_post=runtime_post,
                    )
                )

    # 仅当 release 含认领底稿的文章/主页成品时才要求账本存在；纯图片/视频 release 合法缺账本。
    if ledger_loaded and stats["articleCount"] > 0 and not ledger:
        issues.append(f"{release_id}: missing _shared/base_draft_ledger.json")

    return {
        "schemaVersion": REPORT_SCHEMA,
        "releaseId": release_id,
        "sourceTaskId": task_id,
        "sourceBatchId": batch_id,
        "passed": not issues,
        "issues": issues,
        "stats": stats,
    }


def scan_runtime_batch_integrity(
    task_id: str,
    batch_id: str,
    *,
    refs: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Run the same publish-facing integrity checks before release assembly.

    This is the bridge between review/materialize and publish: approved runtime
    objects must already have complete source/image/base-draft evidence. A
    later release gate should be a confirmation, not the first place these
    defects are discovered.
    """

    root = batch_root(task_id, batch_id)
    label = f"{task_id}/{batch_id}"
    issues: list[str] = []
    stats: dict[str, Any] = {
        "postCount": 0,
        "articleCount": 0,
        "imageCount": 0,
        "videoCount": 0,
        "assetCount": 0,
    }
    if not root.is_dir():
        issues.append(f"{label}: runtime batch directory not found")
        return {
            "schemaVersion": REPORT_SCHEMA,
            "taskId": task_id,
            "batchId": batch_id,
            "passed": False,
            "issues": issues,
            "stats": stats,
        }

    ledger_path = root / "_shared" / "base_draft_ledger.json"
    ledger = _json(ledger_path)
    schema = str(ledger.get("schemaVersion") or "")
    # 账本是否存在的判定延后到统计完成后：base_draft_ledger 只对认领底稿的文章/主页成品
    # 必需；image/video 作品按设计不认领底稿，纯图片/视频 release 合法缺账本，不应阻断。
    if ledger and schema != BASE_DRAFT_LEDGER_SCHEMA:
        issues.append(
            f"{label}: base_draft_ledger schemaVersion must be "
            f"{BASE_DRAFT_LEDGER_SCHEMA}, got {schema or '<empty>'}"
        )

    issues.extend(_entity_homepage_issues(root, root))

    allowed_post_rels: set[str] = set()
    if refs is not None:
        from _common import content_object

        for ref in refs:
            try:
                allowed_post_rels.add(content_object.content_object_rel(task_id, batch_id, str(ref)))
            except KeyError:
                continue

    post_manifests = sorted((root / "posts").rglob("manifest.json")) if (root / "posts").is_dir() else []
    for manifest_path in post_manifests:
        post_rel = manifest_path.parent.relative_to(root).as_posix()
        if allowed_post_rels and post_rel not in allowed_post_rels:
            continue
        manifest = _payload(manifest_path)
        stats["postCount"] += 1
        is_image = _is_image_post(manifest)
        is_video = _is_video_post(manifest)
        if is_image:
            stats["imageCount"] += 1
        elif is_video:
            stats["videoCount"] += 1
        else:
            stats["articleCount"] += 1
            runtime_post = root / post_rel
            issues.extend(
                _base_draft_issues(
                    release_id=label,
                    post_rel=post_rel,
                    manifest=manifest,
                    runtime_post=runtime_post,
                    ledger=ledger,
                )
            )
            issues.extend(_review_gate_issues(post_rel, runtime_post))

        assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
        if is_video and not assets:
            issues.append(f"{post_rel}: video must include at least one sourced video asset")
        if not is_image and not is_video and not assets and not _is_text_only_article(manifest, root / post_rel):
            issues.append(f"{post_rel}: article must include at least one sourced image asset from its base draft")
        for index, asset in enumerate(assets):
            if not isinstance(asset, Mapping):
                issues.append(f"{post_rel}: manifest.assets[{index}] must be an object")
                continue
            stats["assetCount"] += 1
            asset_label = str(asset.get("assetId") or asset.get("fileName") or f"asset[{index}]")
            source_ref = str(asset.get("sourceRef") or "").strip()
            source_asset_ref = str(asset.get("sourceAssetRef") or "").strip()
            if not source_ref:
                issues.append(f"{post_rel}: {asset_label} missing manifest.assets[].sourceRef")
            if not source_asset_ref:
                issues.append(f"{post_rel}: {asset_label} missing manifest.assets[].sourceAssetRef")
            collection_id = str(asset.get("sourceCollectionId") or "").strip()
            manifest_sha = _norm_sha(str(asset.get("sha256") or ""))
            file_name = str(asset.get("fileName") or asset.get("path") or "").strip()
            actual_sha = _file_sha(manifest_path.parent / "assets" / file_name) if file_name else ""
            effective_sha = actual_sha or manifest_sha
            if not manifest_sha:
                issues.append(f"{post_rel}: {asset_label} missing sha256")
            elif actual_sha and manifest_sha != actual_sha:
                issues.append(f"{post_rel}: {asset_label} sha256 mismatch with asset file")
            if source_ref:
                meta = _source_unit_meta(root, source_ref)
                if not _has_rights_proof(asset, meta):
                    issues.append(f"{post_rel}: {asset_label} missing image authorization proof or license snapshot")
            issues.extend(_asset_alignment_issues(post_rel, manifest, asset))
            if not is_image:
                issues.extend(
                    _article_asset_source_issues(
                        post_rel=post_rel,
                        asset_label=asset_label,
                        asset=asset,
                        runtime_post=root / post_rel,
                    )
                )

    # 仅当存在认领底稿的文章/主页成品时才要求账本存在；纯图片/视频 release 合法缺账本，
    # 对齐"诚实弃稿/允许配额不足"的优雅降级：实体只产出图片作品时不得因缺账本硬失败。
    if stats["articleCount"] > 0 and not ledger:
        issues.append(f"{label}: missing _shared/base_draft_ledger.json")

    return {
        "schemaVersion": REPORT_SCHEMA,
        "taskId": task_id,
        "batchId": batch_id,
        "passed": not issues,
        "issues": issues,
        "stats": stats,
    }


def release_integrity_issues(release_id: str) -> list[str]:
    report = scan_release_integrity(release_id)
    return [str(issue) for issue in report.get("issues") or []]
