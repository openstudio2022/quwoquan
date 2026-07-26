"""Integrity checks over one disposable execution workspace."""
from __future__ import annotations
from collections.abc import Iterable, Mapping
from typing import Any
from core.paths import execution_root
from content.release.canonical.integrity import (
    BASE_DRAFT_LEDGER_SCHEMA, REPORT_SCHEMA, _article_asset_source_issues,
    _asset_alignment_issues, _base_draft_issues, _entity_homepage_issues,
    _asset_rights_issues, _file_sha, _is_image_post, _is_text_only_article,
    _is_video_post, _json, _norm_sha, _payload, _review_gate_issues,
    _source_unit_meta,
)

def scan_runtime_batch_integrity(
    execution_id: str,
    *,
    refs: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Run the same publish-facing integrity checks before release assembly.

    This is the bridge between review/materialize and publish: approved runtime
    objects must already have complete source/image/base-draft evidence. A
    later release gate should be a confirmation, not the first place these
    defects are discovered.
    """

    root = execution_root(execution_id)
    label = f"{execution_id}/{execution_id}"
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
            "schema": REPORT_SCHEMA,
            "executionId": execution_id,
            "passed": False,
            "issues": issues,
            "stats": stats,
        }

    ledger_path = root / "_shared" / "base_draft_ledger.json"
    ledger = _json(ledger_path)
    schema = str(ledger.get("schema") or "")
    # 账本是否存在的判定延后到统计完成后：base_draft_ledger 只对认领底稿的文章/主页成品
    # 必需；image/video 作品按设计不认领底稿，纯图片/视频 release 合法缺账本，不应阻断。
    if ledger and schema != BASE_DRAFT_LEDGER_SCHEMA:
        issues.append(
            f"{label}: base_draft_ledger schema must be "
            f"{BASE_DRAFT_LEDGER_SCHEMA}, got {schema or '<empty>'}"
        )

    issues.extend(_entity_homepage_issues(root, root))

    allowed_post_rels: set[str] = set()
    if refs is not None:
        from content.post import object_index as content_object

        for ref in refs:
            try:
                allowed_post_rels.add(content_object.content_object_rel(execution_id, str(ref)))
            except KeyError:
                continue

    post_manifests = sorted((root / "posts").rglob("manifest.json")) if (root / "posts").is_dir() else []
    for manifest_path in post_manifests:
        post_rel = manifest_path.parent.relative_to(root).as_posix()
        if allowed_post_rels and post_rel not in allowed_post_rels:
            continue
        manifest = _payload(manifest_path)
        vertical = str(manifest.get("vertical") or "").strip()
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
            if is_video:
                source_asset_refs = asset.get("sourceAssetRefs")
                rights_refs = asset.get("rightsRefs")
                if not isinstance(source_asset_refs, list) or not source_asset_refs:
                    issues.append(
                        f"{post_rel}: {asset_label} missing manifest.assets[].sourceAssetRefs"
                    )
                else:
                    for source_asset in source_asset_refs:
                        source_path = root / str(source_asset).split("#", 1)[0]
                        if not source_path.is_file():
                            issues.append(
                                f"{post_rel}: {asset_label} video source asset missing: {source_asset}"
                            )
                if not isinstance(rights_refs, list) or not rights_refs:
                    issues.append(
                        f"{post_rel}: {asset_label} missing manifest.assets[].rightsRefs"
                    )
                else:
                    for rights_ref in rights_refs:
                        rights_path = root / str(rights_ref).split("#", 1)[0]
                        if not rights_path.is_file():
                            issues.append(
                                f"{post_rel}: {asset_label} video rights evidence missing: {rights_ref}"
                            )
            else:
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
                issues.extend(
                    f"{post_rel}: {issue}"
                    for issue in _asset_rights_issues(
                        asset_label,
                        asset,
                        meta,
                        vertical=vertical,
                    )
                )
            issues.extend(_asset_alignment_issues(post_rel, manifest, asset))
            if not is_image and not is_video:
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
        "schema": REPORT_SCHEMA,
        "executionId": execution_id,
        "passed": not issues,
        "issues": issues,
        "stats": stats,
    }
