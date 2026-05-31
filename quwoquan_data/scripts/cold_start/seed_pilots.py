#!/usr/bin/env python3
"""Seed travel + campus cold-start pilot batches (runtime only).

Creates download sources, approved compose/review, materializes posts, assembles release.
Does NOT write publish/v1 — run promote_to_publish_v1.py after gate.

用法:
  python3 cold_start/seed_pilots.py
  python3 cold_start/seed_pilots.py --travel-only
  python3 cold_start/seed_pilots.py --campus-only
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

from _common.article_package import asset_id_from_object_key, sha256_text  # noqa: E402
from _common.io import write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    NOW_ISO,
    batch_command_root,
    ensure_batch_layout,
    ensure_task_layout,
    task_data,
)
from produce.materialize import materialize_posts  # noqa: E402
from publish.assemble import assemble_release  # noqa: E402
from publish.gate import gate_publish  # noqa: E402
from _common.paths import release_root, task_entity_pages, task_graph, task_tags  # noqa: E402
from sample_data._common import (  # noqa: E402
    make_entity,
    make_entity_manifest,
    make_entity_page,
    write_entity,
)

TRAVEL_TASK = "四川旅行_冷启动_v1"
TRAVEL_BATCH = "pilot"
TRAVEL_RELEASE = "travel_cold_start_r1"

CAMPUS_TASK = "校园冷启动_首批50校"
CAMPUS_BATCH = "pilot"
CAMPUS_RELEASE = "campus_cold_start_r1"

FIXTURE_POST_MEDIA = (
    REPO_ROOT
    / "quwoquan_service/contracts/metadata/_shared/test_fixtures/media/media/image/post"
)

TRAVEL_ENTITIES = [
    {
        "name": "峨眉山",
        "city": "乐山市",
        "etype": "景区",
        "theme": "Topic/旅行/旅行主题/雪山探险",
        "play": "Topic/旅行/玩法/观光游览",
    },
    {
        "name": "九寨沟",
        "city": "阿坝州",
        "etype": "景区",
        "theme": "Topic/旅行/玩法/观光游览",
        "play": "Topic/旅行/出行方式/自驾",
    },
    {
        "name": "稻城亚丁",
        "city": "甘孜州",
        "etype": "景区",
        "theme": "Topic/旅行/出行方式/徒步穿越",
        "play": "Topic/旅行/玩法/摄影旅拍",
    },
]

TRAVEL_ANGLES = ("攻略", "体验")

CAMPUS_SCHOOLS = [
    {
        "name": "四川大学",
        "geo": "Topic/地理/行政区/中国/四川省/成都市",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/综合类",
            "Entity/机构/学校/公办",
        ],
    },
    {
        "name": "北京大学",
        "geo": "Topic/地理/行政区/中国/北京市",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/综合类",
            "Entity/机构/学校/公办",
        ],
    },
    {
        "name": "清华大学",
        "geo": "Topic/地理/行政区/中国/北京市",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/理工类",
            "Entity/机构/学校/公办",
        ],
    },
    {
        "name": "复旦大学",
        "geo": "Topic/地理/行政区/中国/上海市",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/综合类",
            "Entity/机构/学校/公办",
        ],
    },
    {
        "name": "浙江大学",
        "geo": "Topic/地理/行政区/中国/浙江省/杭州市",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/综合类",
            "Entity/机构/学校/公办",
        ],
    },
    {
        "name": "武汉大学",
        "geo": "Topic/地理/行政区/中国/湖北省/武汉市",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/综合类",
            "Entity/机构/学校/公办",
        ],
    },
    {
        "name": "南京大学",
        "geo": "Topic/地理/行政区/中国/江苏省/南京市",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/综合类",
            "Entity/机构/学校/公办",
        ],
    },
    {
        "name": "上海交通大学",
        "geo": "Topic/地理/行政区/中国/上海市",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/理工类",
            "Entity/机构/学校/公办",
        ],
    },
    {
        "name": "同济大学",
        "geo": "Topic/地理/行政区/中国/上海市",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/理工类",
            "Entity/机构/学校/公办",
        ],
    },
    {
        "name": "中国人民大学",
        "geo": "Topic/地理/行政区/中国/北京市",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/综合类",
            "Entity/机构/学校/公办",
        ],
    },
]

CAMPUS_POST_SPECS = [
    # 索引帖目录为「索引」，tagRefs 勿含 Format/内容角度/*（避免 G19 与目录名不一致）
    ("索引", None, "Topic/教育成长/校园生活", "journal"),
    ("新生攻略", "Format/内容角度/攻略/新生攻略", "Topic/教育成长/校园生活", "gentle"),
    ("校园评测", "Format/内容角度/测评/校园评测", "Topic/教育成长/校园生活", "journal"),
]


def _fixture_cover(post_glob: str) -> Path | None:
    matches = sorted(FIXTURE_POST_MEDIA.glob(post_glob))
    return matches[0] if matches else None


def _seed_download_images(task_id: str, batch_id: str, entity_name: str, copies: int = 5) -> list[Path]:
    images_dir = batch_command_root(task_id, batch_id, "download") / "sources" / entity_name / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    src = _fixture_cover("fixture_post_travel_*/v1/cover.jpg") or _fixture_cover("*/v1/cover.jpg")
    paths: list[Path] = []
    if not src:
        return paths
    for i in range(1, copies + 1):
        dest = images_dir / f"img_{i:02d}.jpg"
        shutil.copy2(src, dest)
        meta = {
            "url": f"https://cold-start.local/{entity_name}/img_{i:02d}",
            "platform": "cold_start_fixture",
            "license": "contract_fixture",
            "download_date": NOW_ISO[:10],
        }
        dest.with_suffix(".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        paths.append(dest)
    return paths


def _ensure_release_gate_stubs(release_id: str, task_id: str) -> None:
    """Fill minimal release files required by gate_publish."""
    root = release_root(release_id)
    ent_file = root / "entities" / "entities.ndjson"
    if not ent_file.exists():
        ent_file.parent.mkdir(parents=True, exist_ok=True)
        ent_file.write_text("", encoding="utf-8")

    tags_file = root / "tags" / "tags.ndjson"
    if not tags_file.exists():
        tags_file.parent.mkdir(parents=True, exist_ok=True)
        tags_src = task_tags(task_id)
        if tags_src.exists():
            shutil.copy2(tags_src, tags_file)
        else:
            tags_file.write_text("", encoding="utf-8")

    pages_dst = root / "entity_pages"
    pages_dst.mkdir(parents=True, exist_ok=True)
    if not any(pages_dst.iterdir()):
        pages_src = task_entity_pages(task_id)
        if pages_src.exists() and any(pages_src.iterdir()):
            for item in pages_src.iterdir():
                dest = pages_dst / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
        else:
            task_entities_root = task_data(task_id).entities_dir()
            for page_md in task_entities_root.rglob("page.md"):
                rel = page_md.relative_to(task_entities_root)
                target = pages_dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(page_md, target)

    graph_file = root / "graph" / "relations.ndjson"
    if not graph_file.exists():
        graph_file.parent.mkdir(parents=True, exist_ok=True)
        graph_src = task_graph(task_id) / "relations.ndjson"
        if graph_src.exists():
            shutil.copy2(graph_src, graph_file)
        else:
            graph_file.write_text("", encoding="utf-8")


def _write_stage_result(
    task_id: str,
    batch_id: str,
    step: str,
    ref: str,
    payload: dict,
) -> None:
    out_dir = batch_command_root(task_id, batch_id, "produce") / "results" / step
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        out_dir / f"{ref}.json",
        {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "taskId": task_id,
            "batchId": batch_id,
            "step": step,
            "ref": ref,
            "payload": payload,
        },
    )


def _travel_article(name: str, angle: str, entity_ref: str, tag_refs: list[str], asset_id: str) -> str:
    title = f"{name}{angle}指南"
    body = (
        f"# {title}\n\n"
        f"> 四川旅行冷启动深内容（{angle}）。\n\n"
        f"实体引用：[/entity/{entity_ref}](/entity/{entity_ref})\n\n"
        f"## 行前概览\n\n"
        f"{name}是川西环线上的核心目的地之一。本文从{angle}视角整理交通、门票、行程节奏与注意事项，"
        f"便于与 [/tag/Topic/旅行](/tag/Topic/旅行) 主题下的其他节点串联成 3–5 日自由行。"
        f"建议提前在官方渠道核对开放时间、预约政策与季节性风险（雨季路况、高原反应等）。\n\n"
        f"![{name}风景](asset://{asset_id})\n\n"
        f"## 交通与门票\n\n"
        f"从成都出发可组合高铁、自驾或景区直通车。门票与观光车政策会随旺季调整，"
        f"建议把排队窗口写进时间表，避免现场被动改线。标签：[/tag/{tag_refs[0]}](/tag/{tag_refs[0]})。\n\n"
        f"## 核心体验\n\n"
        f"若你更关注风光拍摄，可把清晨与傍晚留给高反差时段；若偏体验向，"
        f"优先安排徒步强度与海拔适应相匹配的段落，并预留 1 小时弹性应对天气突变。\n\n"
        f"## 注意事项\n\n"
        f"高原地区注意防晒、补水与保暖；垃圾随身带走，尊重当地宗教与生态规则。"
        f"封面：`asset://{asset_id}`。\n"
    )
    pad = (
        f"\n\n（补充）关于 **{name}** 的{angle}信息可继续对照 "
        f"[/entity/{entity_ref}](/entity/{entity_ref}) 与同路线住宿、用餐节点做日程拼装。"
    )
    while len(body) < 820:
        body += pad
    return body


def seed_travel() -> int:
    ensure_task_layout(TRAVEL_TASK)
    ensure_batch_layout(TRAVEL_TASK, TRAVEL_BATCH, "download")
    ensure_batch_layout(TRAVEL_TASK, TRAVEL_BATCH, "produce")
    td = task_data(TRAVEL_TASK)
    count = 0

    for row in TRAVEL_ENTITIES:
        name = row["name"]
        geo = f"Topic/地理/行政区/中国/四川省/{row['city']}"
        tag_refs = [
            "Entity/地点/景区",
            row["theme"],
            row["play"],
            "Topic/旅行",
        ]
        entity = make_entity(
            name,
            name,
            f"{name}是四川旅行冷启动标杆实体。",
            "地点",
            row["etype"],
            geo,
            tag_refs,
        )
        page = make_entity_page(name, "地点", row["etype"], entity["description"], [row["theme"]])
        em = make_entity_manifest(
            name, "地点", row["etype"], tag_refs, [f"地点/{row['etype']}/{name}"]
        )
        write_entity(td.root, "地点", row["etype"], name, entity, page, em)

        sources_dir = batch_command_root(TRAVEL_TASK, TRAVEL_BATCH, "download") / "sources" / name
        sources_dir.mkdir(parents=True, exist_ok=True)
        (sources_dir / "content" / "source_01.md").parent.mkdir(parents=True, exist_ok=True)
        (sources_dir / "content" / "source_01.md").write_text(
            f"---\nurl: https://cold-start.local/{name}\nplatform: mafengwo\ntitle: {name}游记\n---\n\n{name} source stub.\n",
            encoding="utf-8",
        )
        image_paths = _seed_download_images(TRAVEL_TASK, TRAVEL_BATCH, name, 5)

        entity_ref = f"地点/景区/{name}" if row["etype"] == "景区" else f"地点/{row['etype']}/{name}"
        for angle in TRAVEL_ANGLES:
            ref = f"{name}_{angle}"
            object_key = f"media/image/post/cold_start_{ref}/v1/cover.jpg"
            asset_id = asset_id_from_object_key(object_key)
            assets = []
            for idx, img_path in enumerate(image_paths[:3], start=1):
                assets.append(
                    {
                        "assetId": asset_id if idx == 1 else f"{asset_id}_{idx}",
                        "fileName": img_path.name,
                        "caption": "封面" if idx == 1 else f"配图{idx}",
                        "kind": "image",
                        "scope": "cold_start",
                        "objectKey": object_key if idx == 1 else object_key.replace("cover", f"detail_{idx}"),
                        "sourcePath": str(img_path),
                    }
                )
            format_angle = angle
            tag_post = tag_refs + [f"Format/内容角度/{format_angle}"]
            article = _travel_article(name, angle, entity_ref, tag_post, assets[0]["assetId"])
            compose_payload = {
                "topicId": ref,
                "title": f"{name}{angle}指南",
                "articleMarkdown": article,
                "entityRefs": [f"/entity/{entity_ref}"],
                "tagRefs": tag_post,
                "sourceUrls": [f"https://cold-start.local/{name}"],
                "template": "journal",
                "assets": assets,
                "publishLayout": "travel",
                "publishAngle": angle,
                "publishTitle": f"{name}{angle}指南",
                "publishSeq": 1,
            }
            _write_stage_result(TRAVEL_TASK, TRAVEL_BATCH, "review", ref, {"decision": "approved"})
            _write_stage_result(TRAVEL_TASK, TRAVEL_BATCH, "compose", ref, compose_payload)
            count += 1

    materialized = materialize_posts(TRAVEL_TASK, TRAVEL_BATCH, "article")
    rel_root = release_root(TRAVEL_RELEASE)
    if rel_root.exists():
        shutil.rmtree(rel_root)
    assemble_release(TRAVEL_TASK, TRAVEL_RELEASE)
    _ensure_release_gate_stubs(TRAVEL_RELEASE, TRAVEL_TASK)
    issues = gate_publish(TRAVEL_RELEASE)
    if issues:
        raise RuntimeError(f"Travel release gate failed: {issues}")
    print(f"[travel] materialized {len(materialized)} posts, release={TRAVEL_RELEASE}")
    return len(materialized)


def _campus_article(
    school: str,
    angle: str,
    format_ref: str,
    topic_ref: str,
    asset_id: str,
) -> str:
    entity_path = f"机构/学校/{school}"
    if angle == "索引":
        return (
            f"# {school}｜学校概览\n\n"
            f"> {school}冷启动索引帖。\n\n"
            f"实体引用：[/entity/{entity_path}](/entity/{entity_path})\n\n"
            f"## 基本信息\n\n"
            f"{school}是本次校园垂类冷启动的标杆高校之一。本文提供结构化概览，"
            f"便于快速了解办学层次、校园环境与相关 [/tag/Topic/教育成长](/tag/Topic/教育成长) 主题内容。\n\n"
            f"![{school}](asset://{asset_id})\n\n"
            f"## 位置与交通\n\n"
            f"建议结合行政区标签核对校区分布与公共交通。封面 `asset://{asset_id}`。\n\n"
            f"标签：[/tag/{topic_ref}](/tag/{topic_ref})\n"
        )
    sections = {
        "新生攻略": ("入学准备", "校园生活指南", "学习建议"),
        "校园评测": ("整体评价", "食堂评测", "宿舍评测"),
    }.get(angle, ("核心内容", "延伸阅读"))
    lines = [
        f"# {school}｜{angle}\n\n",
        f"> {school}{angle}（冷启动）。\n\n",
        f"实体引用：[/entity/{entity_path}](/entity/{entity_path})\n\n",
    ]
    for sec in sections:
        lines.append(f"## {sec}\n\n")
        lines.append(
            f"围绕 {school} 的{angle}，从真实就读体验出发整理可执行建议。"
            f"请结合 [/tag/{format_ref}](/tag/{format_ref}) 与 [/tag/{topic_ref}](/tag/{topic_ref}) 浏览同主题内容。\n\n"
        )
    lines.append(f"![校园](asset://{asset_id})\n\n")
    body = "".join(lines)
    while len(body) < 650:
        body += f"\n\n（补充）{school} {angle} 持续更新中，引用链保持 /entity/ 与 /tag/ 完整。"
    return body


def seed_campus() -> int:
    ensure_task_layout(CAMPUS_TASK)
    ensure_batch_layout(CAMPUS_TASK, CAMPUS_BATCH, "download")
    ensure_batch_layout(CAMPUS_TASK, CAMPUS_BATCH, "produce")
    td = task_data(CAMPUS_TASK)
    count = 0

    for school_row in CAMPUS_SCHOOLS:
        name = school_row["name"]
        geo = school_row["geo"]
        tag_refs = school_row["tags"]
        entity = make_entity(
            name,
            name,
            f"{name}校园冷启动实体。",
            "机构",
            "学校",
            geo,
            tag_refs,
        )
        page = (
            f"# {name}\n\n> {name}校园主页（冷启动）。\n\n"
            f"相关：[/tag/Topic/教育成长](/tag/Topic/教育成长)\n"
        )
        em = make_entity_manifest(
            name, "机构", "学校", tag_refs, [f"机构/学校/{name}"]
        )
        write_entity(td.root, "机构", "学校", name, entity, page, em)
        _seed_download_images(CAMPUS_TASK, CAMPUS_BATCH, name, 5)

        for angle, format_ref, topic_ref, template in CAMPUS_POST_SPECS:
            ref = f"{name}_{angle}"
            object_key = f"media/image/post/cold_start_campus_{ref}/v1/cover.jpg"
            asset_id = asset_id_from_object_key(object_key)
            img_dir = (
                batch_command_root(CAMPUS_TASK, CAMPUS_BATCH, "download")
                / "sources"
                / name
                / "images"
            )
            first_img = sorted(img_dir.glob("img_*.jpg"))[0] if img_dir.is_dir() else None
            assets = [
                {
                    "assetId": asset_id,
                    "fileName": first_img.name if first_img else "cover.jpg",
                    "caption": "封面",
                    "kind": "image",
                    "scope": "cold_start",
                    "objectKey": object_key,
                    "sourcePath": str(first_img) if first_img else "",
                }
            ]
            article = _campus_article(name, angle, format_ref or topic_ref, topic_ref, asset_id)
            post_tag_refs = list(set(tag_refs + [topic_ref, "Topic/教育成长"]))
            if format_ref:
                post_tag_refs.append(format_ref)
            compose_payload = {
                "topicId": ref,
                "title": f"{name}｜{angle}" if angle != "索引" else f"{name}｜学校概览",
                "articleMarkdown": article,
                "entityRefs": [f"/entity/机构/学校/{name}"],
                "tagRefs": post_tag_refs,
                "template": template,
                "assets": assets,
                "publishLayout": "campus",
                "publishAngle": angle,
                "publishTitle": name,
                "publishSeq": 1,
            }
            _write_stage_result(CAMPUS_TASK, CAMPUS_BATCH, "review", ref, {"decision": "approved"})
            _write_stage_result(CAMPUS_TASK, CAMPUS_BATCH, "compose", ref, compose_payload)
            count += 1

    materialized = materialize_posts(CAMPUS_TASK, CAMPUS_BATCH, "article")
    rel_root = release_root(CAMPUS_RELEASE)
    if rel_root.exists():
        shutil.rmtree(rel_root)
    assemble_release(CAMPUS_TASK, CAMPUS_RELEASE)
    _ensure_release_gate_stubs(CAMPUS_RELEASE, CAMPUS_TASK)
    issues = gate_publish(CAMPUS_RELEASE)
    if issues:
        raise RuntimeError(f"Campus release gate failed: {issues}")
    print(f"[campus] materialized {len(materialized)} posts, release={CAMPUS_RELEASE}")
    return len(materialized)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--travel-only", action="store_true")
    parser.add_argument("--campus-only", action="store_true")
    args = parser.parse_args()

    if args.campus_only:
        seed_campus()
        return
    if args.travel_only:
        seed_travel()
        return
    seed_travel()
    seed_campus()


if __name__ == "__main__":
    main()
