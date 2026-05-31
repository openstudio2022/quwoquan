"""Materialize approved compose results into post packages."""
from __future__ import annotations

from pathlib import Path
import shutil

from _common.article_package import (
    MARKDOWN_VERSION,
    build_article_asset_manifest,
    build_gallery_markdown,
    copy_asset_files,
    sha256_text,
)
from _common.paths import batch_command_root, batch_sources_dir
from _common.io import read_json, write_json


def _resolve_entity_download_dir(
    task_id: str,
    batch_id: str,
    entity_refs: list[str],
) -> Path | None:
    for ref in entity_refs:
        name = ref.strip("/").split("/")[-1]
        if not name:
            continue
        images_dir = batch_sources_dir(task_id, batch_id, name) / "images"
        if images_dir.is_dir():
            return images_dir
    return None


def materialize_posts(task_id: str, batch_id: str, content_type: str) -> list[Path]:
    """Convert approved compose+review results into final post packages."""
    produce_root = batch_command_root(task_id, batch_id, "produce")
    review_dir = produce_root / "results" / "review"
    compose_dir = produce_root / "results" / "compose"
    posts_dir = produce_root / "posts" / content_type

    materialized: list[Path] = []

    if not review_dir.exists():
        return materialized

    for review_file in sorted(review_dir.glob("*.json")):
        review = read_json(review_file)
        payload = review.get("payload", review)
        ref = review.get("ref", review_file.stem)
        post_dir = posts_dir / ref
        if payload.get("decision") != "approved":
            if post_dir.exists():
                shutil.rmtree(post_dir)
            continue

        compose_file = compose_dir / f"{ref}.json"
        if not compose_file.exists():
            continue

        compose = read_json(compose_file)
        compose_payload = compose.get("payload", compose)

        # 出处门：只有 generator=agent 的正文允许进入交付面，脚本/占位一律拒绝落地。
        if str(compose_payload.get("generator") or "") != "agent":
            if post_dir.exists():
                shutil.rmtree(post_dir)
            continue

        post_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = post_dir / "assets"

        article_md = compose_payload.get("articleMarkdown", "")
        title = compose_payload.get("title") or ref
        template = compose_payload.get("template") or "journal"
        entity_refs = compose_payload.get("entityRefs", [])
        tag_refs = compose_payload.get("tagRefs", [])
        source_urls = compose_payload.get("sourceUrls", [])
        source_paths = compose_payload.get("sourcePaths", [])

        raw_assets = compose_payload.get("assets") or []
        if not raw_assets and compose_payload.get("coverAssetRef"):
            cover_id = compose_payload["coverAssetRef"].replace("asset://", "")
            raw_assets = [
                {
                    "assetId": cover_id,
                    "fileName": f"{cover_id}.jpg",
                    "caption": "封面",
                    "kind": "image",
                    "scope": "cold_start",
                    "objectKey": compose_payload.get("coverObjectKey", ""),
                }
            ]

        download_images = _resolve_entity_download_dir(task_id, batch_id, entity_refs)
        assets = copy_asset_files(raw_assets, assets_dir, download_images)

        if assets:
            gallery_md = compose_payload.get("galleryMarkdown") or build_gallery_markdown(
                title, assets
            )
            (post_dir / "gallery.md").write_text(gallery_md, encoding="utf-8")

        if article_md and "articleMarkdownVersion" not in article_md[:200]:
            if not article_md.lstrip().startswith("---"):
                front = (
                    f"---\n"
                    f"title: {title}\n"
                    f"template: {template}\n"
                    f"articleMarkdownVersion: {MARKDOWN_VERSION}\n"
                )
                if assets:
                    front += f"coverImage: asset://{assets[0]['assetId']}\n"
                front += "---\n\n"
                article_md = front + article_md

        (post_dir / "article.md").write_text(article_md, encoding="utf-8")

        article_asset_manifest = build_article_asset_manifest(article_md, assets)
        # 最小发布契约：只保留发布/渲染/出处必需字段。
        manifest = {
            "schemaVersion": "quwoquan_data.post_manifest",
            "topicId": ref,
            "contentType": content_type,
            "entityRefs": entity_refs,
            "tagRefs": tag_refs,
            "conditionContext": compose_payload.get("conditionContext"),
            "sourceUrls": source_urls,
            "assets": [
                {
                    "assetId": a["assetId"],
                    "fileName": a.get("fileName", ""),
                    "caption": a.get("caption", ""),
                    "imageLayout": a.get("imageLayout", "fullWidth"),
                }
                for a in assets
            ],
            "template": template,
            "carrier": compose_payload.get("carrier", "article"),
            "generator": compose_payload.get("generator", "agent"),
            "generatorModel": compose_payload.get("generatorModel"),
            "citedSourceRefs": compose_payload.get("citedSourceRefs") or source_paths,
            "reviewDecision": "approved",
            "articleMarkdownVersion": MARKDOWN_VERSION,
            "articleMarkdownDigest": sha256_text(article_md),
            "articleAssetManifest": article_asset_manifest,
            "articleRenderProfile": compose_payload.get("articleRenderProfile")
            or {
                "template": template,
                "fontPreset": "clean",
                "layoutPolicy": {
                    "wrapDowngrade": "compactWidthToFullWidth",
                    "galleryDowngrade": "singleColumn",
                },
            },
            "publishLayout": compose_payload.get("publishLayout", "travel"),
            "publishAngle": compose_payload.get("publishAngle", ""),
            "publishTitle": compose_payload.get("publishTitle", title),
            "publishSeq": compose_payload.get("publishSeq", 1),
        }
        write_json(post_dir / "manifest.json", manifest)

        # 中间态（叙事骨架/来源打分/检索计划/证据包）落非发布物，便于调试与回溯，不进 publish。
        trace = {
            "ref": ref,
            "storySpine": compose_payload.get("storySpine"),
            "sourceQuality": compose_payload.get("sourceQuality"),
            "relatedSearchPlan": compose_payload.get("relatedSearchPlan"),
            "evidenceBundle": compose_payload.get("evidenceBundle"),
            "recommendation": compose_payload.get("recommendation"),
            "sourcePaths": source_paths,
        }
        write_json(post_dir / "produce_trace.json", trace)

        # human-in-loop 账本与实体 sidecar 随 post 流转，供 promote 发布门消费。
        _copy_review_sidecars(task_id, batch_id, ref, post_dir)

        materialized.append(post_dir)

    return materialized


def _copy_review_sidecars(task_id: str, batch_id: str, ref: str, post_dir: Path) -> None:
    """把 produce/review/ledger/{ref}.json 与 entities/{ref}.json 拷进 post review/。"""
    from _common.review_ledger import ledger_path, entities_path

    review_out = post_dir / "review"
    src_ledger = ledger_path(task_id, batch_id, ref)
    if src_ledger.is_file():
        review_out.mkdir(parents=True, exist_ok=True)
        write_json(review_out / "ledger.json", read_json(src_ledger))
    src_entities = entities_path(task_id, batch_id, ref)
    if src_entities.is_file():
        review_out.mkdir(parents=True, exist_ok=True)
        write_json(review_out / "entities.json", read_json(src_entities))
