#!/usr/bin/env python3
"""校园冷启动标杆批次：10 校 × 3 篇 = 30 篇。

用法:
  python3 cold_start/seed_campus_batch.py
  python3 cold_start/seed_campus_batch.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_ROOT.parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.article_package import asset_id_from_object_key  # noqa: E402
from _common.io import write_ndjson  # noqa: E402
from _common.paths import (  # noqa: E402
    NOW_ISO,
    batch_command_root,
    ensure_batch_layout,
    ensure_task_layout,
    release_root,
    task_data,
    task_root,
)
from cold_start.campus_catalog import (  # noqa: E402
    CAMPUS_BATCH_ID,
    CAMPUS_POST_SPECS,
    CAMPUS_RELEASE_ID,
    CAMPUS_SCHOOLS,
    CAMPUS_TASK_ID,
    build_post_tag_refs,
)
from cold_start.seed_pilots import _ensure_release_gate_stubs, _write_stage_result  # noqa: E402
from produce.materialize import materialize_posts  # noqa: E402
from publish.assemble import assemble_release  # noqa: E402
from publish.gate import gate_publish  # noqa: E402
from sample_data._common import make_entity, make_entity_manifest, write_entity  # noqa: E402

FIXTURE_POST_MEDIA = (
    REPO_ROOT
    / "quwoquan_service/contracts/metadata/_shared/test_fixtures/media/media/image/post"
)


def _campus_fixture_set(index: int) -> list[Path]:
    patterns = ["fixture_post_lifestyle_*", "fixture_post_designwriting_*", "fixture_post_*"]
    for pat in patterns:
        dirs = sorted(d for d in FIXTURE_POST_MEDIA.glob(pat) if d.is_dir())
        if dirs:
            base = dirs[index % len(dirs)]
            imgs = sorted(base.glob("v1/cover.*")) + sorted(base.glob("v1/detail_*.*"))
            if imgs:
                return imgs[:5]
    return sorted(FIXTURE_POST_MEDIA.glob("*/v1/cover.*"))[:5]


def _seed_school_images(task_id: str, batch_id: str, school: str, index: int) -> list[Path]:
    images_dir = (
        batch_command_root(task_id, batch_id, "download") / "sources" / school / "images"
    )
    images_dir.mkdir(parents=True, exist_ok=True)
    sources = _campus_fixture_set(index)
    paths: list[Path] = []
    for i in range(1, 6):
        dest = images_dir / f"img_{i:02d}.jpg"
        if not sources:
            break
        src = sources[(i - 1) % len(sources)]
        shutil.copy2(src, dest)
        meta = {
            "url": f"https://cold-start.local/campus/{school}/img_{i:02d}",
            "platform": "contract_fixture",
            "license": "contract_fixture",
            "entity": school,
            "search_terms": f"{school} 校园风景 食堂 宿舍 新生攻略",
            "download_date": NOW_ISO[:10],
        }
        dest.with_suffix(".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        paths.append(dest)
    return paths


def _school_page(school: dict) -> str:
    name = school["name"]
    motto = school.get("motto", "")
    lines = [
        f"# {name}\n\n",
        f"> {motto} — {name}校园冷启动标杆主页。\n\n",
        f"实体：[/entity/机构/学校/{name}](/entity/机构/学校/{name})\n\n",
        "## 亮点\n\n",
    ]
    for h in school["highlights"]:
        lines.append(f"- {h}\n")
    lines.append(
        f"\n相关：[/tag/Topic/教育成长](/tag/Topic/教育成长) "
        f"[/tag/Audience/圈子/校园圈/母校圈](/tag/Audience/圈子/校园圈/母校圈)\n"
    )
    body = "".join(lines)
    while len(body) < 400:
        body += f"\n\n（补充）{name} 校园信息持续更新，引用链保持 /entity/ 与 /tag/ 完整。"
    return body


def _article_sections(school: dict, angle: str) -> list[tuple[str, str]]:
    name = school["name"]
    if angle == "索引":
        return [
            (
                "基本信息",
                f"{name}是本次校园垂类冷启动标杆高校。校训「{school.get('motto', '')}」。"
                f"本文提供结构化概览，便于快速了解办学层次、校区分布与 [/tag/Topic/教育成长](/tag/Topic/教育成长) 相关内容。",
            ),
            (
                "校区与交通",
                "建议结合行政区标签核对各校区位置；报到季提前下载校内地图与公交/地铁换乘方案。",
            ),
            (
                "延伸阅读",
                f"同校 [/tag/Format/内容角度/攻略/新生攻略](/tag/Format/内容角度/攻略/新生攻略) 与 "
                f"[/tag/Format/内容角度/测评/校园评测](/tag/Format/内容角度/测评/校园评测) 可组合阅读。",
            ),
        ]
    if angle == "新生攻略":
        return [
            (
                "入学准备",
                f"即将成为 {name} 新生的你，需要提前准备证件、生活用品与数字化工具（选课/一卡通/邮箱）。"
                "建议加入官方新生群，关注教务处与学院通知。",
            ),
            (
                "校园生活指南",
                f"{name} 的食堂、图书馆、体育场馆与社团活动是校园生活的四大支点。"
                "第一周可先完成食堂试吃、图书馆办卡与一次社团开放日。",
            ),
            (
                "学习建议",
                "大学学习更强调自主与节奏管理：通识课与专业课并重，善用 office hour 与学长学姐经验。",
            ),
        ]
    if angle == "校园评测":
        return [
            (
                "整体评价",
                f"从教学质量、校园环境、生活成本与就业资源四个维度，对 {name} 做冷启动阶段客观评测。",
            ),
            (
                "食堂评测",
                "各校区食堂风味不同，建议用「价格—口味—排队时间」三维打分，记录 3 家最常去窗口。",
            ),
            (
                "宿舍评测",
                "关注空调、独立卫浴、网络与距教学楼距离；与室友提前沟通作息与卫生分工。",
            ),
            (
                "综合推荐",
                f"若你重视 {school.get('motto', '学术')} 所代表的校风，{name} 值得作为长期投入的选择。",
            ),
        ]
    return [("核心内容", f"{name} {angle} 内容。")]


def _build_article(
    school: dict,
    angle: str,
    format_ref: str | None,
    topic_ref: str,
    asset_id: str,
) -> str:
    name = school["name"]
    entity_path = f"机构/学校/{name}"
    title = f"{name}｜学校概览" if angle == "索引" else f"{name}｜{angle}"

    lines = [
        f"# {title}\n\n",
        f"> 校园冷启动标杆 · {angle}。\n\n",
        f"实体引用：[/entity/{entity_path}](/entity/{entity_path})\n\n",
    ]
    for heading, body in _article_sections(school, angle):
        lines.append(f"## {heading}\n\n{body}\n\n")
        lines.append(f"![{name}{heading}](asset://{asset_id})\n\n")

    if format_ref:
        lines.append(f"格式标签：[/tag/{format_ref}](/tag/{format_ref})\n\n")
    lines.append(f"主题标签：[/tag/{topic_ref}](/tag/{topic_ref})\n\n")
    lines.append(f"封面：`asset://{asset_id}`。\n")

    text = "".join(lines)
    min_len = 650 if angle != "索引" else 550
    pad = (
        f"\n\n（补充）{name} {angle} 持续更新；请对照 "
        f"[/entity/{entity_path}](/entity/{entity_path}) 与同主题标签浏览。"
    )
    while len(text) < min_len:
        text += pad
    return text


def _write_catalog(task_id: str, batch_id: str) -> None:
    rows = [
        {
            "entityName": s["name"],
            "entityType": "学校",
            "domain": "机构",
            "geoTagRef": s["geo"],
            "angles": [a for a, _, _, _ in CAMPUS_POST_SPECS],
        }
        for s in CAMPUS_SCHOOLS
    ]
    cat = task_root(task_id) / "catalog.ndjson"
    write_ndjson(cat, rows)
    explore = batch_command_root(task_id, batch_id, "explore")
    explore.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cat, explore / "catalog.ndjson")


def seed_campus_batch(dry_run: bool = False) -> int:
    task_id = CAMPUS_TASK_ID
    batch_id = CAMPUS_BATCH_ID
    ensure_task_layout(task_id)
    ensure_batch_layout(task_id, batch_id, "download")
    ensure_batch_layout(task_id, batch_id, "produce")
    ensure_batch_layout(task_id, batch_id, "explore")
    td = task_data(task_id)
    _write_catalog(task_id, batch_id)

    post_count = 0
    for idx, school in enumerate(CAMPUS_SCHOOLS):
        name = school["name"]
        ent_ref = f"机构/学校/{name}"
        entity = make_entity(
            name,
            school["label_en"],
            f"{name}校园冷启动标杆实体。",
            "机构",
            "学校",
            school["geo"],
            school["tags"] + ["Topic/教育成长"],
        )
        page = _school_page(school)
        em = make_entity_manifest(name, "机构", "学校", school["tags"], [ent_ref])
        if not dry_run:
            write_entity(td.root, "机构", "学校", name, entity, page, em)

        src_dir = batch_command_root(task_id, batch_id, "download") / "sources" / name / "content"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "source_01.md").write_text(
            f"---\nurl: https://cold-start.local/campus/{name}\n"
            f"platform: zhihu\ntitle: {name}新生攻略\nquality_score: 7\n---\n\n",
            encoding="utf-8",
        )
        image_paths = _seed_school_images(task_id, batch_id, name, idx)

        for angle, format_ref, topic_ref, template in CAMPUS_POST_SPECS:
            ref = f"{name}_{angle}"
            tag_post = build_post_tag_refs(school, angle, format_ref)
            object_key = f"media/image/post/cold_start_campus_{ref}/v1/cover.jpg"
            assets = []
            for img_idx, img_path in enumerate(image_paths[:3], start=1):
                aid = (
                    asset_id_from_object_key(object_key)
                    if img_idx == 1
                    else asset_id_from_object_key(object_key) + f"_{img_idx}"
                )
                ok = (
                    object_key
                    if img_idx == 1
                    else object_key.replace("cover", f"detail_{img_idx}")
                )
                assets.append(
                    {
                        "assetId": aid,
                        "fileName": img_path.name,
                        "caption": "封面" if img_idx == 1 else f"配图{img_idx}",
                        "kind": "image",
                        "scope": "cold_start",
                        "objectKey": ok,
                        "sourcePath": str(img_path),
                    }
                )

            article = _build_article(school, angle, format_ref, topic_ref, assets[0]["assetId"])
            title = f"{name}｜学校概览" if angle == "索引" else f"{name}｜{angle}"
            compose_payload = {
                "topicId": ref,
                "title": title,
                "articleMarkdown": article,
                "entityRefs": [f"/entity/{ent_ref}"],
                "tagRefs": tag_post,
                "sourceUrls": [f"https://cold-start.local/campus/{name}"],
                "template": template,
                "assets": assets,
                "publishLayout": "campus",
                "publishAngle": angle,
                "publishTitle": name,
                "publishSeq": 1,
            }
            if not dry_run:
                _write_stage_result(task_id, batch_id, "review", ref, {"decision": "approved"})
                _write_stage_result(task_id, batch_id, "compose", ref, compose_payload)
            post_count += 1

    if dry_run:
        print(f"[campus] dry-run: {len(CAMPUS_SCHOOLS)} schools, {post_count} posts planned")
        return post_count

    materialized = materialize_posts(task_id, batch_id, "article")
    rel_root = release_root(CAMPUS_RELEASE_ID)
    if rel_root.exists():
        shutil.rmtree(rel_root)
    assemble_release(task_id, CAMPUS_RELEASE_ID)
    _ensure_release_gate_stubs(CAMPUS_RELEASE_ID, task_id)
    issues = gate_publish(CAMPUS_RELEASE_ID)
    if issues:
        raise RuntimeError(f"Campus release gate failed: {issues}")

    print(
        f"[campus] schools={len(CAMPUS_SCHOOLS)} posts={post_count} "
        f"materialized={len(materialized)} release={CAMPUS_RELEASE_ID}"
    )
    return len(materialized)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    n = seed_campus_batch(dry_run=args.dry_run)
    if n == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
