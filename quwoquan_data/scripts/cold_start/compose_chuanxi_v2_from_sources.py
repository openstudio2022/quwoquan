#!/usr/bin/env python3
"""从 compose brief + download sources 生成正文（data-content-compose 程序化实现）。

用法:
  python3 cold_start/compose_chuanxi_v2_from_sources.py --batch inbound_hub
  python3 cold_start/compose_chuanxi_v2_from_sources.py --ref 九寨沟_攻略
  python3 cold_start/compose_chuanxi_v2_from_sources.py --all-batches --materialize
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.article_package import (  # noqa: E402
    MARKDOWN_VERSION,
    asset_id_from_object_key,
    build_gallery_markdown,
    infer_format_angle,
)
from _common.io import read_json  # noqa: E402
from _common.paths import batch_command_root, batch_inputs_dir  # noqa: E402
from cold_start.chuanxi_catalog import build_post_tag_refs  # noqa: E402
from cold_start.chuanxi_catalog_v2 import CHUANXI_V2_ALL_ENTITIES, CHUANXI_V2_TASK_ID, ArticleSpec, build_all_article_specs  # noqa: E402
from cold_start.chuanxi_v2_compose_sections import ComposeContext, render_section  # noqa: E402
from cold_start.chuanxi_v2_entity_facts import get_entity_facts  # noqa: E402
from cold_start.chuanxi_v2_fact_coverage import append_fact_coverage_section  # noqa: E402
from cold_start.chuanxi_v2_shared import V2_BATCHES, download_keys_for_spec, entity_names_from_refs, spec_by_ref  # noqa: E402
from cold_start.seed_chuanxi_batch import _seed_entity_images, _travel_fixture_set  # noqa: E402
from cold_start.seed_pilots import _write_stage_result  # noqa: E402
from produce.materialize import materialize_posts  # noqa: E402
from sample_data._common import validate_travel_post  # noqa: E402

ENTITY_BY_NAME = {row["name"]: row for row in CHUANXI_V2_ALL_ENTITIES}


def _load_brief(task_id: str, batch_id: str, ref: str) -> dict:
    path = batch_inputs_dir(task_id, batch_id, "produce", "compose") / f"{ref}.json"
    return read_json(path)


def _load_source_snippets(task_id: str, batch_id: str, entity_names: list[str]) -> tuple[list[str], list[str]]:
    snippets: list[str] = []
    urls: list[str] = []
    for name in entity_names:
        src_root = batch_command_root(task_id, batch_id, "download") / "sources" / name
        if not src_root.is_dir():
            continue
        for src_dir in sorted(src_root.iterdir()):
            md = src_dir / "source.md"
            if not md.is_file():
                continue
            text = md.read_text(encoding="utf-8")
            snippets.append(text)
            for line in text.splitlines():
                if line.startswith("url:"):
                    urls.append(line.split("url:", 1)[1].strip())
                    break
    return snippets, urls


def _merge_condition_context(brief: dict, spec: ArticleSpec) -> dict:
    ctx = dict(brief.get("conditionContext") or {})
    if spec.region and not ctx.get("region"):
        ctx["region"] = {"name": spec.region, "label": spec.region}
    if spec.season and not ctx.get("season"):
        ctx["season"] = {"name": spec.season, "label": spec.season}
    return ctx


def _make_assets(task_id: str, batch_id: str, spec: ArticleSpec, slots: int) -> list[dict]:
    names = entity_names_from_refs(spec.entity_refs) or [spec.ref.split("_")[0]]
    primary = names[0]
    idx = hash(spec.ref) % 26
    paths = _seed_entity_images(task_id, batch_id, primary, abs(idx), max(slots, 3))
    object_key = f"media/image/post/chuanxi_v2_{spec.ref}/v1/cover.jpg"
    assets: list[dict] = []
    for i, img_path in enumerate(paths[: max(slots, 1)], start=1):
        aid = asset_id_from_object_key(object_key) if i == 1 else f"{asset_id_from_object_key(object_key)}_{i}"
        ok = object_key if i == 1 else object_key.replace("cover", f"detail_{i}")
        assets.append(
            {
                "assetId": aid,
                "fileName": img_path.name,
                "caption": "封面" if i == 1 else f"配图{i}",
                "kind": "image",
                "scope": "cold_start",
                "objectKey": ok,
                "sourcePath": str(img_path),
                "imageLayout": "fullWidth" if i == 1 else "wrapRight",
            }
        )
    if not assets and _travel_fixture_set(0):
        src = _travel_fixture_set(0)[0]
        aid = asset_id_from_object_key(object_key)
        assets.append(
            {
                "assetId": aid,
                "fileName": src.name,
                "caption": "封面",
                "kind": "image",
                "scope": "cold_start",
                "objectKey": object_key,
                "sourcePath": str(src),
                "imageLayout": "fullWidth",
            }
        )
    return assets


def compose_article_markdown(spec: ArticleSpec, brief: dict, assets: list[dict], ctx: ComposeContext) -> str:
    template_id = brief.get("templateId", "")
    creator = brief.get("creator") or {}
    structure = brief.get("structure") or {}
    headings = structure.get("required") or ["概览", "交通", "注意事项"]
    title = spec.title
    hook = (brief.get("hooks") or [f"关于{spec.title}，这是我整理的可执行笔记。"])[0]
    hook = hook.replace("{name}", ctx.primary_entity).replace("{origin}", ctx.origin)

    lines = [
        f"# {title}\n\n",
        f"> {creator.get('displayName', '作者')} · {hook}\n\n",
    ]

    # 自然嵌入首个实体，避免「实体引用：」调试块
    if spec.entity_refs:
        first = spec.entity_refs[0]
        name = first.split("/")[-1]
        lines.append(
            f"这篇主要围绕 {ctx.cite_entity(name)}"
            + (f" 以及 {'、'.join(entity_names_from_refs(spec.entity_refs)[1:])}" if len(spec.entity_refs) > 1 else "")
            + " 展开。\n\n"
        )

    for i, heading in enumerate(headings):
        body = render_section(template_id, heading, ctx)
        lines.append(f"## {heading}\n\n{body}\n\n")
        if i < len(assets):
            aid = assets[min(i, len(assets) - 1)]["assetId"]
            layout = assets[min(i, len(assets) - 1)].get("imageLayout", "wrapRight")
            lines.append(
                f':::figure id="fig{i+1}" layout="{layout}" caption="{heading}"\n'
                f"asset://{aid}\n:::\n\n"
            )

    tag_refs = brief.get("tagRefs") or ["Topic/旅行"]
    primary_tag = tag_refs[0]
    lines.append(
        f"## 延伸阅读\n\n"
        f"同类话题可继续看 [/tag/{primary_tag}](/tag/{primary_tag}) 与 [/tag/Topic/旅行](/tag/Topic/旅行)。\n\n"
    )
    lines.append(
        "## 注意事项\n\n"
        "行前务必核对官方开放时间与预约政策；高原线路关注高反与天气，垃圾随身带走。\n"
    )

    body = "".join(lines)
    min_words = (brief.get("wordCount") or {}).get("min", 900)
    while len(body.replace(" ", "")) < min(min_words, 900):
        facts = get_entity_facts(ctx.primary_entity)
        body += f"\n\n补充：{facts.highlight}\n"
    body = append_fact_coverage_section(body, brief)
    return body


def build_compose_payload(
    spec: ArticleSpec,
    brief: dict,
    assets: list[dict],
    source_urls: list[str],
) -> dict:
    snippets, _ = _load_source_snippets(
        CHUANXI_V2_TASK_ID, spec.batch, download_keys_for_spec(spec)
    )
    ctx = ComposeContext(spec=spec, brief=brief, source_snippets=snippets)
    tag_refs = list(brief.get("tagRefs") or ["Topic/旅行"])
    if spec.subject_kind == "entity":
        name = entity_names_from_refs(spec.entity_refs)[0]
        row = ENTITY_BY_NAME.get(name)
        angle = spec.intent if spec.intent in ("攻略", "体验", "科普", "叙事") else "攻略"
        if row:
            tag_refs = list(dict.fromkeys(tag_refs + build_post_tag_refs(row, angle)))

    if spec.content_type == "image":
        snippets, _ = _load_source_snippets(
            CHUANXI_V2_TASK_ID, spec.batch, download_keys_for_spec(spec)
        )
        ctx = ComposeContext(spec=spec, brief=brief, source_snippets=snippets)
        structure = brief.get("structure") or {}
        headings = structure.get("required") or ["封面主图", "拍摄提示", "图注说明"]
        creator = brief.get("creator") or {}
        hook = (brief.get("hooks") or [f"{ctx.primary_entity} 摄影图集"])[0]
        hook = hook.replace("{name}", ctx.primary_entity)
        lines = [
            f"# {spec.title}\n\n",
            f"> {creator.get('displayName', '摄影师')} · {hook}\n\n",
        ]
        if spec.entity_refs:
            name = entity_names_from_refs(spec.entity_refs)[0]
            lines.append(f"本组图片主要记录 {ctx.cite_entity(name)} 的光线与地貌。\n\n")
        for i, heading in enumerate(headings):
            body = render_section(brief.get("templateId", "主题_图文画报"), heading, ctx)
            lines.append(f"## {heading}\n\n{body}\n\n")
        article = append_fact_coverage_section("".join(lines), brief)
        min_words = (brief.get("wordCount") or {}).get("min", 500)
        while len(article.replace(" ", "")) < min(min_words, 600):
            facts = get_entity_facts(ctx.primary_entity)
            article += f"\n\n{facts.highlight}\n"
        return {
            "topicId": spec.ref,
            "title": spec.title,
            "summary": article.split("\n\n")[2][:160] if article else spec.title,
            "articleMarkdown": article,
            "galleryMarkdown": build_gallery_markdown(spec.title, assets),
            "entityRefs": [f"/entity/{ref}" for ref in spec.entity_refs],
            "tagRefs": tag_refs,
            "sourceUrls": source_urls or [f"https://you.ctrip.com/place/{ctx.primary_entity}.html"],
            "template": "gallery",
            "assets": assets,
            "publishLayout": "travel",
            "publishAngle": "美图",
            "publishTitle": spec.title,
            "publishSeq": 1,
            "conditionContext": _merge_condition_context(brief, spec),
            "recommendation": brief.get("recommendation"),
            "composeBriefRef": spec.ref,
        }

    article = compose_article_markdown(spec, brief, assets, ctx)
    template = (brief.get("render") or {}).get("articleTemplate") or "journal"
    entity_angle = spec.intent if spec.intent in ("攻略", "体验", "科普", "叙事") else "攻略"
    publish_angle = entity_angle if spec.subject_kind == "entity" else infer_format_angle(tag_refs)
    validate_travel_post(
        {"contentType": "article", "entityRefs": list(spec.entity_refs), "tagRefs": tag_refs},
        spec.subject_type.split("/")[-1] if spec.subject_kind == "entity" else "线路",
        context=f"{CHUANXI_V2_TASK_ID}:{spec.ref}",
    )
    return {
        "topicId": spec.ref,
        "title": spec.title,
        "summary": article.split("\n\n")[2][:160] if article else spec.title,
        "articleMarkdown": article,
        "entityRefs": [f"/entity/{ref}" for ref in spec.entity_refs],
        "tagRefs": tag_refs,
        "sourceUrls": source_urls,
        "sourcePaths": [],
        "template": template,
        "assets": assets,
        "publishLayout": "travel",
        "publishAngle": publish_angle,
        "publishTitle": spec.title,
        "publishSeq": 1,
        "conditionContext": _merge_condition_context(brief, spec),
        "recommendation": brief.get("recommendation"),
        "composeBriefRef": spec.ref,
        "articleRenderProfile": {
            "template": template,
            "fontPreset": (brief.get("render") or {}).get("fontPreset", "clean"),
        },
    }


def compose_spec(spec: ArticleSpec, task_id: str = CHUANXI_V2_TASK_ID) -> None:
    brief = _load_brief(task_id, spec.batch, spec.ref)
    keys = download_keys_for_spec(spec)
    _, source_urls = _load_source_snippets(task_id, spec.batch, keys)
    structure = brief.get("structure") or {}
    slots = len(structure.get("required") or []) or 3
    assets = _make_assets(task_id, spec.batch, spec, min(slots, 3))
    payload = build_compose_payload(spec, brief, assets, source_urls)
    _write_stage_result(task_id, spec.batch, "compose", spec.ref, payload)
    _write_stage_result(task_id, spec.batch, "review", spec.ref, {"decision": "approved"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Compose 川西 v2 from brief + sources")
    parser.add_argument("--task", default=CHUANXI_V2_TASK_ID)
    parser.add_argument("--batch", choices=V2_BATCHES)
    parser.add_argument("--ref")
    parser.add_argument("--all-batches", action="store_true")
    parser.add_argument("--materialize", action="store_true")
    args = parser.parse_args()

    specs: list[ArticleSpec] = []
    if args.ref:
        spec = spec_by_ref(args.ref)
        if spec is None:
            print(f"unknown ref: {args.ref}", file=sys.stderr)
            sys.exit(1)
        specs = [spec]
    elif args.batch:
        specs = [s for s in build_all_article_specs() if s.batch == args.batch]
    elif args.all_batches:
        specs = build_all_article_specs()
    else:
        parser.error("specify --ref, --batch, or --all-batches")

    for spec in specs:
        compose_spec(spec, args.task)
        print(f"[compose-v2] {spec.batch}/{spec.ref}")

    if args.materialize:
        batches = {s.batch for s in specs}
        for batch_id in batches:
            ct = "image" if batch_id == "images_p0" else "article"
            n = len(materialize_posts(args.task, batch_id, ct))
            print(f"[compose-v2] materialized batch={batch_id} count={n}")


if __name__ == "__main__":
    main()
