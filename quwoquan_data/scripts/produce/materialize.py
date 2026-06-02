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
from _common.draft_io import read_draft_meta, read_writing_pack
from _common.provenance import build_provenance
from _common.intersection_signal import build_intersection_hints
from _common.entity_annotation import annotate_inline, normalize_link_ref


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


def _build_title_seq_index(review_dir: Path, compose_dir: Path) -> dict[str, int]:
    """approved+agent 的 ref → 该发布标题下的稳定序号。

    seq 默认 1；同一 publishTitle 下多篇按 ref 排序依次 1,2,3…（支持标题重复）；
    同一 ref 重跑映射到同一 seq（稳定，不会无限累加）。
    """
    from collections import defaultdict

    title_refs: dict[str, list[str]] = defaultdict(list)
    for review_file in sorted(review_dir.glob("*.json")):
        review = read_json(review_file)
        payload = review.get("payload", review)
        ref = review.get("ref", review_file.stem)
        if payload.get("decision") != "approved":
            continue
        compose_file = compose_dir / f"{ref}.json"
        if not compose_file.exists():
            continue
        compose_payload = read_json(compose_file).get("payload", {})
        if str(compose_payload.get("generator") or "") != "agent":
            continue
        title = compose_payload.get("publishTitle") or compose_payload.get("title") or ref
        title_refs[title].append(ref)
    seq_index: dict[str, int] = {}
    for refs in title_refs.values():
        for index, ref in enumerate(sorted(refs), start=1):
            seq_index[ref] = index
    return seq_index


def _annotate_manifest_entities(article_md: str, entity_refs: list[str]) -> str:
    """Materialized posts must keep article links and manifest.entityRefs closed."""
    dictionary: dict[str, str] = {}
    for raw_ref in entity_refs:
        ref = normalize_link_ref(str(raw_ref))
        name = ref.strip("/").split("/")[-1] if ref else ""
        if name:
            dictionary[name] = ref
    if not dictionary:
        return article_md
    annotated_article, _ = annotate_inline(article_md, dictionary)
    return annotated_article


def materialize_posts(task_id: str, batch_id: str, content_type: str) -> list[Path]:
    """Convert approved compose+review results into final post packages."""
    produce_root = batch_command_root(task_id, batch_id, "produce")
    review_dir = produce_root / "results" / "review"
    compose_dir = produce_root / "results" / "compose"
    posts_dir = produce_root / "posts" / content_type

    materialized: list[Path] = []

    if not review_dir.exists():
        return materialized

    # 全量重建该 content_type 的 posts：只保留本轮 approved+agent 结果，并按"发布标题→序号"稳定布局。
    if posts_dir.exists():
        shutil.rmtree(posts_dir)
    # 预扫描：approved 且 generator=agent 的 ref → 序号，落地为 posts/<type>/<标题>/<seq>/
    # （seq 默认 1，同标题多篇按 ref 稳定递增，支持标题重复；与 promote 发布面 <标题>/<seq> 对齐）。
    seq_index = _build_title_seq_index(review_dir, compose_dir)

    for review_file in sorted(review_dir.glob("*.json")):
        review = read_json(review_file)
        payload = review.get("payload", review)
        ref = review.get("ref", review_file.stem)
        if payload.get("decision") != "approved":
            continue

        compose_file = compose_dir / f"{ref}.json"
        if not compose_file.exists():
            continue

        compose = read_json(compose_file)
        compose_payload = compose.get("payload", compose)

        # 出处门：只有 generator=agent 的正文允许进入交付面，脚本/占位一律拒绝落地。
        if str(compose_payload.get("generator") or "") != "agent":
            continue

        article_md = compose_payload.get("articleMarkdown", "")
        title = compose_payload.get("title") or ref
        template = compose_payload.get("template") or "journal"
        publish_title = compose_payload.get("publishTitle") or title
        seq = seq_index.get(ref, 1)
        post_dir = posts_dir / publish_title / str(seq)
        post_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = post_dir / "assets"
        entity_refs = compose_payload.get("entityRefs", [])
        tag_refs = compose_payload.get("tagRefs", [])
        source_urls = compose_payload.get("sourceUrls", [])
        source_paths = compose_payload.get("sourcePaths", [])
        if isinstance(entity_refs, list):
            article_md = _annotate_manifest_entities(article_md, entity_refs)

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
            "publishTitle": publish_title,
            "publishSeq": seq,
            # 溯源：内容来自哪个任务/批次（task trace/hydrate、推荐归因消费）
            "sourceTaskId": task_id,
            "sourceBatchId": batch_id,
        }
        # 「明」：预生成内容侧交集锚点（对齐 IntersectionReason 闭集口径），runtime 据此 + 用户补全文案。
        manifest["intersectionHints"] = build_intersection_hints(manifest)
        write_json(post_dir / "manifest.json", manifest)

        # 结构化出处：把「给 agent 的输入摘要 / 最终结果 / 原始源 / 补全证据源 / 门结果」汇成
        # 单一回查入口，明确区分最终结果（final）与中间过程（intermediate），取代分散的 produce_trace.json。
        provenance = build_provenance(
            ref,
            writing_pack=read_writing_pack(task_id, batch_id, ref),
            draft_meta=read_draft_meta(task_id, batch_id, ref),
            review_payload=payload,
            compose_payload=compose_payload,
            manifest=manifest,
        )
        write_json(post_dir / "provenance.json", provenance)

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
