"""Materialize one receipt-protocol approved post into publishable form (DEC-027).

物化只消费冻结产物：坐标来自 0.plan target_set，creator/tag 来自
3.compose writing_pack，正文/脚本来自 4.draft，评审事实来自 5.review attestation。
本模块是确定性 IO，不驱动 agent、不推进状态机。

载体分发：article 物化 article.md+manifest.json；video 复用
render_sourced_video_package（转码/poster/字幕/基础 manifest）后按 frozen target
坐标补 receipt 协议发布字段；image 从 image_evidence_pack 物化 assets+manifest。
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from core.article_package import (
    MARKDOWN_DIALECT,
    build_markdown_frontmatter,
)
from core.io import read_json, write_json
from core.paths import now_iso

_REQUIRED_PACK_FIELDS = ("vertical", "title", "creatorProfileRef", "tagRefs", "baseSourceRef")
_VIDEO_REQUIRED_PACK_FIELDS = ("vertical", "title", "creatorProfileRef", "tagRefs", "sourceVideo")
_IMAGE_REQUIRED_PACK_FIELDS = ("vertical", "title", "creatorProfileRef", "tagRefs", "assets")


class ReceiptMaterializeError(ValueError):
    """One object's materialization inputs are incomplete or drifted."""


def _load_pack_and_attestation(object_dir: Path) -> tuple[dict, dict]:
    pack_path = object_dir / "3.compose/writing_pack.json"
    attestation_path = object_dir / "5.review/attestation.json"
    for path in (pack_path, attestation_path):
        if not path.is_file():
            raise ReceiptMaterializeError(f"missing frozen input: {path.name}")
    pack = read_json(pack_path)
    attestation = read_json(attestation_path)
    if attestation.get("decision") != "approved":
        raise ReceiptMaterializeError("attestation decision is not approved")
    return pack, attestation


def _assert_pack_fields(pack: dict, required: tuple[str, ...]) -> None:
    missing = [field for field in required if not pack.get(field)]
    if missing:
        raise ReceiptMaterializeError(
            "writing_pack lacks frozen publish inputs: " + ",".join(missing)
        )


def _load_frozen_inputs(object_dir: Path) -> tuple[dict, str | None, dict]:
    """plan 模式与 article apply 共用的冻结输入校验（按 carrier 分支）。"""
    pack, attestation = _load_pack_and_attestation(object_dir)
    carrier = str(pack.get("carrier") or "")
    if carrier == "article":
        draft_path = object_dir / "4.draft/draft.article.md"
        if not draft_path.is_file():
            raise ReceiptMaterializeError(f"missing frozen input: {draft_path.name}")
        _assert_pack_fields(pack, _REQUIRED_PACK_FIELDS)
        return pack, draft_path.read_text(encoding="utf-8"), attestation
    if carrier == "video":
        script_path = object_dir / "4.draft/video_script.json"
        meta_path = object_dir / "4.draft/draft_meta.json"
        for path in (script_path, meta_path):
            if not path.is_file():
                raise ReceiptMaterializeError(f"missing frozen input: {path.name}")
        _assert_pack_fields(pack, _VIDEO_REQUIRED_PACK_FIELDS)
        from content.post.video.codec import VideoWritingPack

        VideoWritingPack.from_mapping(pack)
        return pack, None, attestation
    if carrier == "image":
        _assert_pack_fields(pack, _IMAGE_REQUIRED_PACK_FIELDS)
        return pack, None, attestation
    raise ReceiptMaterializeError(
        f"receipt materialization does not support carrier: {carrier!r}"
    )


def _creator_fields(creator_profile_ref: str) -> dict[str, Any]:
    from governance.creators.assignment import creator_from_payload

    projection = creator_from_payload({"creatorProfileId": creator_profile_ref})
    if not projection.get("authorId"):
        raise ReceiptMaterializeError(
            f"creatorProfileRef is not registry-backed: {creator_profile_ref}"
        )
    version = str(
        projection.get("creatorProfileVersion")
        or projection.get("creatorProfileDigest")
        or ""
    )
    return {**projection, "creatorProfileVersion": version}


def _entity_bindings(target: dict[str, Any]) -> tuple[list[str], list[str]]:
    entity_type = str(target.get("entityType") or "").strip("/")
    name = str(target.get("name") or "").strip()
    if len(entity_type.split("/")) != 2 or not name:
        raise ReceiptMaterializeError(f"invalid frozen target: {target}")
    return (
        [f"/entity/{entity_type}/{name}"],
        [f"entity:{entity_type.split('/')[-1]}:{name}"],
    )


def _frozen_coordinates(target: dict[str, Any]) -> tuple[str, str, int]:
    angle = str(target.get("publishAngle") or "").strip()
    publish_title = str(target.get("publishTitle") or "").strip()
    seq = int(target.get("publishSeq") or 1)
    if not angle or not publish_title:
        raise ReceiptMaterializeError(
            "target lacks frozen publishAngle/publishTitle coordinates"
        )
    return angle, publish_title, seq


def _finalize_receipt_manifest(
    manifest: dict[str, Any],
    *,
    execution_id: str,
    ref: str,
    object_dir: Path,
) -> dict[str, Any]:
    """幂等时间戳沿用 + rewrite identity + intersectionHints + schema 校验。"""
    from content.execution.planning.rewrite import apply_execution_rewrite_identity
    from core.intersection_signal import build_intersection_hints
    from core.schema import assert_valid

    existing_manifest_path = object_dir / "manifest.json"
    if existing_manifest_path.is_file():
        existing = read_json(existing_manifest_path)
        manifest["createdAt"] = existing.get("createdAt") or manifest["createdAt"]
        manifest["updatedAt"] = existing.get("updatedAt") or manifest["updatedAt"]
    manifest = apply_execution_rewrite_identity(
        manifest, execution_id=execution_id, ref=ref
    )
    manifest["intersectionHints"] = build_intersection_hints(manifest)
    assert_valid(
        manifest, "content", "post_manifest", label=f"receipt materialize:{ref}"
    )
    write_json(existing_manifest_path, manifest)
    return manifest


def _materialize_receipt_article(
    execution_id: str,
    *,
    object_dir: Path,
    target: dict[str, Any],
    pack: dict[str, Any],
    draft_md: str,
) -> dict[str, Any]:
    from content.post.materialize_contract import _publication_story_spine
    from content.post.source_attribution import source_unit_attribution
    from verify.verify_content_quality import asset_closure_issues

    angle, publish_title, seq = _frozen_coordinates(target)
    entity_refs, normalized_entity_refs = _entity_bindings(target)
    creator = _creator_fields(str(pack["creatorProfileRef"]))
    ref = str(pack["ref"])
    attribution = source_unit_attribution(
        execution_id,
        "article",
        compose_payload={
            "baseSourceRef": pack["baseSourceRef"],
            "sourceUrls": pack.get("selectedSourceUrls") or [],
        },
        assets=[],
    )
    if attribution is None:
        raise ReceiptMaterializeError(
            "base source unit meta lacks sourceAttribution"
        )
    title = str(pack["title"])
    template = str(pack.get("templateId") or "journal").split(".")[-1] or "journal"
    if not draft_md.lstrip().startswith("---"):
        draft_md = (
            build_markdown_frontmatter(
                {
                    "title": title,
                    "template": template,
                    "markdownDialect": MARKDOWN_DIALECT,
                }
            )
            + draft_md
        )
    manifest: dict[str, Any] = {
        "schema": "quwoquan_data.post_manifest",
        "topicId": ref,
        "contentId": "qwq_data_"
        + hashlib.sha256(f"{execution_id}|{ref}".encode()).hexdigest()[:24],
        "version": 1,
        "contentType": "article",
        "contentIdentity": "work",
        "vertical": pack["vertical"],
        "entityRefs": entity_refs,
        "normalizedEntityRefs": normalized_entity_refs,
        "tagRefs": sorted({str(item) for item in pack["tagRefs"]}),
        "publishMediaMode": "text_only",
        **creator,
        "sourceUrls": list(pack.get("selectedSourceUrls") or []),
        "assets": [],
        "template": template,
        "carrier": "article",
        "generator": "agent",
        "citedSourceRefs": [str(pack["baseSourceRef"])],
        "reviewDecision": "approved",
        "publishLayout": str(pack.get("publishLayout") or "entity"),
        "publishAngle": angle,
        "publishTitle": publish_title,
        "publishSeq": seq,
        "storySpine": _publication_story_spine(pack),
        "sourceAttribution": attribution,
        "markdownDialect": MARKDOWN_DIALECT,
        "articleRenderProfile": {
            "template": template,
            "fontPreset": "clean",
            "layoutPolicy": {
                "wrapDowngrade": "compactWidthToFullWidth",
                "galleryDowngrade": "singleColumn",
            },
        },
        "allowedContactNumbers": list(pack.get("allowedContactNumbers") or []),
        "executionId": execution_id,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    if pack.get("writingIntent"):
        manifest["writingIntent"] = pack["writingIntent"]
    (object_dir / "article.md").write_text(draft_md, encoding="utf-8")
    manifest = _finalize_receipt_manifest(
        manifest, execution_id=execution_id, ref=ref, object_dir=object_dir
    )
    closure_issues = asset_closure_issues(object_dir, manifest)
    if closure_issues:
        raise ReceiptMaterializeError(
            "post asset closure failed: " + "; ".join(closure_issues)
        )
    return manifest


def _materialize_receipt_video(
    execution_id: str,
    *,
    object_dir: Path,
    target: dict[str, Any],
    pack: dict[str, Any],
) -> dict[str, Any]:
    from content.execution.identity import parse_execution_id
    from content.post.materialize_contract import _publication_story_spine
    from content.post.video.codec import (
        VideoDraftMeta,
        VideoScriptDraft,
        VideoWritingPack,
    )
    from content.post.video.source_video import SourcedVideoAsset
    from content.post.video.sourced_package import (
        SourcedVideoPackageRequest,
        render_sourced_video_package,
    )
    from core.paths import execution_root
    from governance.content_supply_policy import load_content_supply_policy

    video_pack = VideoWritingPack.from_mapping(pack)
    if video_pack.source_video is None:
        raise ReceiptMaterializeError("video writing_pack lacks admitted sourceVideo")
    script = VideoScriptDraft.load(object_dir / "4.draft/video_script.json")
    meta = VideoDraftMeta.from_mapping(
        read_json(object_dir / "4.draft/draft_meta.json") or {}
    )
    angle, publish_title, seq = _frozen_coordinates(target)
    entity_refs, normalized_entity_refs = _entity_bindings(target)
    creator = _creator_fields(str(pack["creatorProfileRef"]))
    ref = str(pack["ref"])
    identity = parse_execution_id(execution_id)
    created_at = meta.created_at or now_iso()
    # 成品全量重建（幂等）：仅清成品，过程阶段证据保留。
    for stale in (
        object_dir / "assets",
        object_dir / "manifest.json",
        object_dir / "provenance.json",
        object_dir / "subtitles.vtt",
    ):
        if stale.is_dir():
            shutil.rmtree(stale)
        elif stale.is_file():
            stale.unlink()
    try:
        render_sourced_video_package(
            SourcedVideoPackageRequest(
                output_dir=object_dir,
                execution_id=execution_id,
                execution_sequence=identity.sequence,
                topic_id=ref,
                entity_ref=entity_refs[0],
                tag_refs=tuple(str(item) for item in pack["tagRefs"]),
                title=script.title,
                caption=script.caption,
                script_lines=script.script_lines,
                source=SourcedVideoAsset(
                    path=execution_root(execution_id)
                    / video_pack.source_video.asset_ref,
                    evidence=video_pack.source_video,
                ),
                author_id=str(creator["authorId"]),
                creator_profile_id=str(creator["creatorProfileId"]),
                agent_run_id=meta.agent_run_id or f"receipt-{execution_id}",
                agent_model=meta.model or "receipt_protocol_host",
                created_at=created_at,
            ),
            policy=load_content_supply_policy(identity.vertical).video_delivery,
        )
    except (RuntimeError, ValueError) as exc:
        raise ReceiptMaterializeError(str(exc)) from exc
    manifest = read_json(object_dir / "manifest.json")
    manifest.update(
        {
            "contentId": "qwq_data_"
            + hashlib.sha256(f"{execution_id}|{ref}".encode()).hexdigest()[:24],
            "version": 1,
            "normalizedEntityRefs": normalized_entity_refs,
            "reviewDecision": "approved",
            "publishLayout": str(pack.get("publishLayout") or "video"),
            "publishAngle": angle,
            "publishTitle": publish_title,
            "publishSeq": seq,
            "storySpine": _publication_story_spine(pack),
            "updatedAt": created_at,
        }
    )
    for field in (
        "creatorArchetype",
        "creatorProfileDigest",
        "creatorProfileVersion",
        "creatorDisclosure",
        "experienceClaimMode",
        "authorQualitySignals",
    ):
        value = creator.get(field)
        if value not in (None, "", {}):
            manifest[field] = value
    return _finalize_receipt_manifest(
        manifest, execution_id=execution_id, ref=ref, object_dir=object_dir
    )


def _materialize_receipt_image(
    execution_id: str,
    *,
    object_dir: Path,
    target: dict[str, Any],
    pack: dict[str, Any],
) -> dict[str, Any]:
    from content.post.materialize_contract import (
        _image_source_contract,
        _publication_story_spine,
    )
    from content.post.source_attribution import source_unit_attribution
    from core.article_package import copy_asset_files
    from core.paths import execution_root

    angle, publish_title, seq = _frozen_coordinates(target)
    entity_refs, normalized_entity_refs = _entity_bindings(target)
    creator = _creator_fields(str(pack["creatorProfileRef"]))
    ref = str(pack["ref"])
    title = str(pack["title"])
    caption = str(pack.get("caption") or "")
    if not caption:
        raise ReceiptMaterializeError("image writing_pack lacks caption")
    if len(title) > 80:
        raise ReceiptMaterializeError(f"{ref}: image title exceeds 80 characters")
    if len(caption) > 300:
        raise ReceiptMaterializeError(f"{ref}: image caption exceeds 300 characters")
    raw_assets = list(pack.get("assets") or [])
    if not 1 <= len(raw_assets) <= 20:
        raise ReceiptMaterializeError(
            f"{ref}: image work requires 1..20 assets, got {len(raw_assets)}"
        )
    image_source = _image_source_contract(
        pack,
        raw_assets,
        ref=ref,
        vertical=str(pack.get("vertical") or ""),
    )
    assets_dir = object_dir / "assets"
    if assets_dir.exists():
        shutil.rmtree(assets_dir)
    assets = copy_asset_files(raw_assets, assets_dir, execution_root(execution_id))
    attribution = source_unit_attribution(
        execution_id,
        "image",
        compose_payload=pack,
        assets=assets,
    )
    manifest: dict[str, Any] = {
        "schema": "quwoquan_data.post_manifest",
        "topicId": ref,
        "contentId": "qwq_data_"
        + hashlib.sha256(f"{execution_id}|{ref}".encode()).hexdigest()[:24],
        "version": 1,
        "contentType": "image",
        "contentIdentity": "work",
        "carrier": "image",
        "vertical": pack["vertical"],
        "title": title,
        "caption": caption,
        "entityRefs": entity_refs,
        "normalizedEntityRefs": normalized_entity_refs,
        "tagRefs": sorted({str(item) for item in pack["tagRefs"]}),
        **creator,
        "sourceUrls": list(pack.get("selectedSourceUrls") or []),
        "assets": [
            {
                "assetId": a["assetId"],
                "fileName": a.get("fileName", ""),
                "caption": a.get("caption", ""),
                "imageLayout": a.get("imageLayout", "fullWidth"),
                "role": "cover" if str(a.get("role") or "") == "cover" else "detail",
                "sha256": a.get("sha256", ""),
                "sourceRef": a.get("sourceRef", ""),
                "sourceAssetRef": a.get("sourceAssetRef", ""),
                "alignmentEvidence": a.get("alignmentEvidence", ""),
                "sourceCollectionId": a.get("sourceCollectionId", ""),
                "creator": a.get("creator", ""),
                "collectionPageUrl": a.get("collectionPageUrl", ""),
                "license": a.get("license", ""),
                "termsUrl": a.get("termsUrl", ""),
                "authorizationProof": a.get("authorizationProof", ""),
                "rightsAuditStatus": a.get("rightsAuditStatus", ""),
                "rightsAuditIssues": list(a.get("rightsAuditIssues") or []),
                "originalAssetUrl": a.get("originalAssetUrl", ""),
                "collectedAt": a.get("collectedAt", ""),
                "usageScope": a.get("usageScope", ""),
                "acquisitionReceiptRef": a.get("acquisitionReceiptRef", ""),
                "professionalAssetId": a.get("professionalAssetId", ""),
                "professionalContentSha256": a.get(
                    "professionalContentSha256", ""
                ),
            }
            for a in assets
        ],
        "template": str(pack.get("templateId") or "journal").split(".")[-1]
        or "journal",
        "generator": "agent",
        "citedSourceRefs": [
            str(item) for item in (pack.get("sourcePaths") or []) if str(item)
        ],
        "reviewDecision": "approved",
        "publishLayout": str(pack.get("publishLayout") or "image"),
        "publishAngle": angle,
        "publishTitle": publish_title,
        "publishSeq": seq,
        "storySpine": _publication_story_spine(pack),
        "executionId": execution_id,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        **image_source,
    }
    if attribution is not None:
        manifest["sourceAttribution"] = attribution
    return _finalize_receipt_manifest(
        manifest, execution_id=execution_id, ref=ref, object_dir=object_dir
    )


def materialize_receipt_post(
    execution_id: str,
    *,
    object_dir: Path,
    target: dict[str, Any],
) -> dict[str, Any]:
    """按 writing_pack.carrier 分发物化 approved 对象，幂等重写一致内容。"""
    pack, draft_md, _attestation = _load_frozen_inputs(object_dir)
    carrier = str(pack.get("carrier") or "")
    if carrier == "article":
        assert draft_md is not None
        return _materialize_receipt_article(
            execution_id,
            object_dir=object_dir,
            target=target,
            pack=pack,
            draft_md=draft_md,
        )
    if carrier == "video":
        return _materialize_receipt_video(
            execution_id, object_dir=object_dir, target=target, pack=pack
        )
    if carrier == "image":
        return _materialize_receipt_image(
            execution_id, object_dir=object_dir, target=target, pack=pack
        )
    raise ReceiptMaterializeError(
        f"receipt materialization does not support carrier: {carrier!r}"
    )


__all__ = ["ReceiptMaterializeError", "materialize_receipt_post"]
