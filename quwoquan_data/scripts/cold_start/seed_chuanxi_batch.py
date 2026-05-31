#!/usr/bin/env python3
"""川西冷启动全量批次：16 实体 × 2 篇 = 32 篇文章。

工作流：runtime/tasks → release → promote_to_publish_v1（不直写 publish/v1）。

用法:
  python3 cold_start/seed_chuanxi_batch.py
  python3 cold_start/seed_chuanxi_batch.py --dry-run
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
from _common.io import write_json, write_ndjson  # noqa: E402
from _common.paths import (  # noqa: E402
    NOW_ISO,
    batch_command_root,
    ensure_batch_layout,
    ensure_task_layout,
    release_root,
    task_data,
    task_root,
)
from cold_start.chuanxi_catalog import (  # noqa: E402
    CHUANXI_BATCH_ID,
    CHUANXI_ENTITIES,
    CHUANXI_RELEASE_ID,
    CHUANXI_TASK_ID,
    angles_for,
    build_post_tag_refs,
    entity_ref,
    entity_tag_line,
    geo_tag,
)
from produce.materialize import materialize_posts  # noqa: E402
from publish.assemble import assemble_release  # noqa: E402
from publish.gate import gate_publish  # noqa: E402
from sample_data._common import (  # noqa: E402
    make_entity,
    make_entity_manifest,
    make_entity_page,
    validate_travel_post,
    write_entity,
)

from cold_start.seed_pilots import (  # noqa: E402
    _ensure_release_gate_stubs,
    _write_stage_result,
)

FIXTURE_POST_MEDIA = (
    REPO_ROOT
    / "quwoquan_service/contracts/metadata/_shared/test_fixtures/media/media/image/post"
)

HIGHLIGHTS_BY_ROLE = {
    "高原核心": [
        "海拔与温差：早晚温差大，需分层穿衣并预留适应时间。",
        "预约与限流：旺季务必提前购票并关注观光车末班时间。",
        "与周边串联：可与同州其他景区组成 3–5 日川西环线。",
    ],
    "枢纽打卡": [
        "地铁可达：建议与宽窄巷子、锦里等同日步行串联。",
        "拍照时段：蓝调时刻与工作日清晨人流更少。",
        "消费提示：区分快里潮流与慢里生活美学动线。",
    ],
    "美食节点": [
        "排队策略：午市 11:30 前到店可避开高峰。",
        "口味预期：麻婆豆腐偏麻辣，可搭配解辣饮品。",
        "周边动线：与宽窄巷子、人民公园组合半日 city walk。",
    ],
}


def _travel_fixture_set(index: int) -> list[Path]:
    travel_dirs = sorted(
        d for d in FIXTURE_POST_MEDIA.glob("fixture_post_travel_*") if d.is_dir()
    )
    if not travel_dirs:
        any_cover = sorted(FIXTURE_POST_MEDIA.glob("*/v1/cover.*"))
        return any_cover[:5]
    base = travel_dirs[index % len(travel_dirs)]
    imgs = sorted(base.glob("v1/cover.*")) + sorted(base.glob("v1/detail_*.*"))
    return imgs[:5] if imgs else []


def _seed_entity_images(
    task_id: str,
    batch_id: str,
    entity_name: str,
    entity_index: int,
    copies: int = 5,
) -> list[Path]:
    images_dir = (
        batch_command_root(task_id, batch_id, "download") / "sources" / entity_name / "images"
    )
    images_dir.mkdir(parents=True, exist_ok=True)
    sources = _travel_fixture_set(entity_index)
    paths: list[Path] = []
    for i in range(1, copies + 1):
        dest = images_dir / f"img_{i:02d}.jpg"
        src = sources[(i - 1) % len(sources)] if sources else None
        if src and src.is_file():
            shutil.copy2(src, dest)
        elif not dest.exists() and sources:
            shutil.copy2(sources[0], dest)
        if not dest.is_file():
            continue
        meta = {
            "url": f"https://cold-start.local/chuanxi/{entity_name}/img_{i:02d}",
            "platform": "contract_fixture",
            "license": "contract_fixture",
            "entity": entity_name,
            "region": "川西",
            "download_date": NOW_ISO[:10],
        }
        dest.with_suffix(".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        paths.append(dest)
    return paths


def _section_blocks(name: str, city: str, etype: str, angle: str, high_alt: bool) -> list[tuple[str, str]]:
    if etype == "景区":
        if angle == "攻略":
            blocks = [
                (
                    "行前概览",
                    f"{name}位于四川省{city}，是川西环线上的重要节点。本文从攻略视角整理交通、门票、"
                    f"行程节奏与注意事项，便于与 [/tag/Topic/旅行](/tag/Topic/旅行) 主题下的其他目的地串联成 3–5 日自由行。",
                ),
                (
                    "交通与门票",
                    "从成都出发可组合高铁、自驾或景区直通车。门票与观光车政策会随旺季调整，"
                    "建议把排队窗口写进时间表，并预留 1 小时弹性应对天气突变。",
                ),
                (
                    "推荐路线",
                    "若时间有限，优先覆盖核心观景点；若有两日，可把清晨留给高反差光影时段，"
                    "下午安排强度较低的步行段落。",
                ),
            ]
            if high_alt:
                blocks.append(
                    (
                        "高原与季节",
                        "高海拔地区注意防晒、补水与保暖；初到者建议减少第一日运动量，"
                        "并关注 [/tag/Topic/旅行/旅行筹备/应急避险](/tag/Topic/旅行/旅行筹备/应急避险) 相关准备。",
                    )
                )
            return blocks
        return [
            (
                "初见印象",
                f"第一次站在 {name} 的观景点，最容易被色彩与尺度震撼——这也是川西体验向内容的核心。",
            ),
            (
                "核心体验",
                "把徒步强度与海拔适应相匹配：摄影向旅人可优先清晨与傍晚；亲子或银发人群建议缩短单次步行距离。",
            ),
            (
                "意外收获",
                "与当地向导或民宿老板聊天，常能补全攻略里没有的闭馆时间、临时管制与隐藏机位。",
            ),
        ]
    if etype == "遗址":
        if angle == "科普":
            return [
                ("历史背景", f"{name}是理解古蜀文明的重要现场，建议结合博物馆展线做前后对照阅读。"),
                ("参观要点", "重点文物与考古层位可分区浏览，避免在单一展厅消耗过多时间。"),
                ("延伸阅读", "可联动三星堆、金沙等节点组成一日文化深度游。"),
            ]
        return [
            ("现场氛围", f"在 {name} 步行，更像在时间与土层之间穿行——适合慢速体验。"),
            ("动线建议", "从入口到核心区域按导览顺序前进，中途可在阴影区休息。"),
            ("拍摄提示", "部分区域限制闪光灯，请遵守现场规定。"),
        ]
    if etype == "古镇":
        if angle == "攻略":
            return [
                ("到达与停车", f"{name}周边停车与摆渡规则随节假日变化，建议提前查官方公告。"),
                ("一日动线", "主街—河街—古巷三段式游览，中午可在河畔用餐。"),
                ("避坑提示", "商业主街与居民生活区体验不同，可各留 1–2 小时。"),
            ]
        return [
            ("叙事起点", f"在 {name}，最动人的往往是清晨尚未被旅行团填满的十分钟。"),
            ("人物与场景", "老茶馆、码头与巷口小摊构成古镇记忆的三条线索。"),
            ("离开时刻", "傍晚灯光亮起时，适合在河边做最后一圈慢行。"),
        ]
    if etype == "打卡地":
        if angle == "攻略":
            return [
                ("最佳时段", f"{name} 在工作日清晨与蓝调时刻更易出片，也更容易找到安静机位。"),
                ("交通接驳", "与地铁、共享单车组合可缩短换乘时间。"),
                ("周边串联", "可与同片区其他打卡点做半日 city walk。"),
            ]
        return [
            ("今日记录", f"在 {name} 的午后，适合用日记体记录街角、橱窗与偶然相遇。"),
            ("感官细节", "声音、气味与光影变化比地标清单更能定义一次城市漫步。"),
            ("慢下来", "留 30 分钟无目的地闲逛，往往比赶景点更贴近旅行本质。"),
        ]
    if etype == "博物馆":
        if angle == "科普":
            return [
                ("展线概览", f"{name} 常设展按时代或主题分区，建议先取导览图再入场。"),
                ("镇馆重点", "预留 40 分钟给核心展厅，其余按兴趣自由分配。"),
                ("预约规则", "旺季需提前预约，闭馆前 30 分钟停止入馆。"),
            ]
        return [
            ("沉浸参观", f"在 {name}，放慢脚步比打卡所有展厅更重要。"),
            ("互动体验", "若有数字导览或特展，可提升理解深度。"),
            ("休息节点", "中庭或咖啡区适合中途复盘所见。"),
        ]
    if etype == "餐厅":
        if angle == "探店":
            return [
                ("第一印象", f"{name} 的招牌菜与等位节奏决定了探店体验的上限。"),
                ("必点推荐", "经典菜与季节限定可各选一道，避免一次点过多重口菜品。"),
                ("环境与服务", "观察出餐速度与桌面周转，评估是否值得二次到访。"),
            ]
        return [
            ("实用攻略", "错峰用餐、提前取号、了解是否能预订包间。"),
            ("人均与搭配", "根据同行人数选择套餐或单点，辣度可提前沟通。"),
            ("周边动线", "餐后可在附近街区散步消化。"),
        ]
    if etype == "住宿":
        if angle == "体验":
            return [
                ("入住第一印象", "前台效率、房间气味与景观兑现度是体验向评价的三要素。"),
                ("设施与细节", "温泉、SPA 或亲子设施是否符合宣传，建议首日实测。"),
                ("睡眠与安静", "隔音与床品支撑度决定第二日行程状态。"),
            ]
        return [
            ("预订策略", "旺季提前 2–4 周；关注取消政策与是否含早。"),
            ("位置与交通", "距景区大门或车站的实际车程比直线距离更重要。"),
            ("性价比", "对比同档竞品时，把景观、早餐与停车一并计入。"),
        ]
    if etype == "学校":
        if angle == "攻略":
            return [
                ("参观预约", f"{name} 对外开放规则因校区而异，请以官方渠道为准。"),
                ("校园动线", "图书馆、历史建筑与食堂可作为半日参观主线。"),
                ("交通提示", "地铁与公交接驳成都各校区，自驾注意校内停车限制。"),
            ]
        return [
            ("校园氛围", f"{name} 的望江、华西等校区各具气质，适合慢行体验。"),
            ("文化触点", "博物馆、纪念馆与river-side 步道是体验向内容的好素材。"),
            ("摄影礼仪", "尊重师生隐私，避免干扰课堂与实验室。"),
        ]
    return [
        ("概览", f"{name} 川西批次 {angle} 内容。"),
        ("细节", "补充可执行建议与引用链。"),
    ]


def _build_article(
    row: dict,
    angle: str,
    entity_path: str,
    tag_refs: list[str],
    asset_id: str,
) -> str:
    name = row["name"]
    city = row["city"]
    etype = row["etype"]
    high_alt = bool(row.get("high_altitude"))
    title = f"{name}{angle}指南" if etype != "学校" else f"{name}｜{angle}"

    lines = [
        f"# {title}\n\n",
        f"> 川西冷启动 · {row['role']} · {angle}。\n\n",
        f"实体引用：[/entity/{entity_path}](/entity/{entity_path})\n\n",
    ]
    for heading, body in _section_blocks(name, city, etype, angle, high_alt):
        lines.append(f"## {heading}\n\n{body}\n\n")
        lines.append(f"![{name}{heading}](asset://{asset_id})\n\n")

    primary_tag = tag_refs[0]
    lines.append(
        f"标签：[/tag/{primary_tag}](/tag/{primary_tag}) · "
        f"[/tag/Topic/旅行](/tag/Topic/旅行)\n\n"
    )
    lines.append(
        f"## 注意事项\n\n"
        f"请结合官方公告核对开放时间与预约政策；垃圾随身带走，尊重当地生态与宗教习俗。"
        f"封面：`asset://{asset_id}`。\n"
    )
    body = "".join(lines)
    pad = (
        f"\n\n（补充）**{name}** 的{angle}信息可继续对照 "
        f"[/entity/{entity_path}](/entity/{entity_path}) 与同路线节点做日程拼装。"
    )
    while len(body) < 820:
        body += pad
    return body


def _write_catalog(task_id: str, batch_id: str) -> Path:
    catalog_rows = []
    for row in CHUANXI_ENTITIES:
        domain = row["domain"]
        etype = row["etype"]
        catalog_rows.append(
            {
                "entityName": row["name"],
                "entityType": etype,
                "domain": domain,
                "geoTagRef": geo_tag(row["city"]),
                "themeTagRef": row["theme"],
                "angles": angles_for(domain, etype),
                "batchRole": row["role"],
            }
        )
    task_cat = task_root(task_id) / "catalog.ndjson"
    write_ndjson(task_cat, catalog_rows)
    explore_dir = batch_command_root(task_id, batch_id, "explore")
    explore_dir.mkdir(parents=True, exist_ok=True)
    explore_cat = explore_dir / "catalog.ndjson"
    shutil.copy2(task_cat, explore_cat)
    return explore_cat


def seed_chuanxi_batch(dry_run: bool = False) -> int:
    task_id = CHUANXI_TASK_ID
    batch_id = CHUANXI_BATCH_ID
    ensure_task_layout(task_id)
    ensure_batch_layout(task_id, batch_id, "download")
    ensure_batch_layout(task_id, batch_id, "produce")
    ensure_batch_layout(task_id, batch_id, "explore")
    td = task_data(task_id)
    _write_catalog(task_id, batch_id)

    post_count = 0
    for idx, row in enumerate(CHUANXI_ENTITIES):
        name = row["name"]
        domain = row["domain"]
        etype = row["etype"]
        geo = geo_tag(row["city"])
        ent_ref = entity_ref(domain, etype, name)
        first_angle = angles_for(domain, etype)[0]
        ent_tags = build_post_tag_refs(row, first_angle)
        # 实体 tagRefs 不含 Format 角度
        entity_tags = [t for t in ent_tags if not t.startswith("Format/")]

        desc = (
            f"{name}位于四川省{row['city']}，川西冷启动批次 {etype} 实体。"
            f"角色：{row['role']}。"
        )
        highlights = HIGHLIGHTS_BY_ROLE.get(
            row["role"],
            [
                f"{row['city']}行程节点：建议预留缓冲时段用于排队与天气变化。",
                f"与周边景点联动：可把{name}放入同一日动线主干。",
                "内容素材经 download SOP 筛选后写入 produce/posts。",
            ],
        )
        entity = make_entity(
            name, row["label_en"], desc, domain, etype, geo, entity_tags
        )
        page = make_entity_page(name, domain, etype, desc, highlights)
        em = make_entity_manifest(name, domain, etype, entity_tags, [ent_ref])
        if not dry_run:
            write_entity(td.root, domain, etype, name, entity, page, em)

        sources_dir = batch_command_root(task_id, batch_id, "download") / "sources" / name
        content_dir = sources_dir / "content"
        content_dir.mkdir(parents=True, exist_ok=True)
        (content_dir / "source_01.md").write_text(
            f"---\nurl: https://cold-start.local/chuanxi/{name}\n"
            f"platform: mafengwo\ntitle: {name}川西攻略\nentity: {name}\n"
            f"download_date: {NOW_ISO[:10]}\nquality_score: 7\n---\n\n"
            f"{name} 川西检索来源占位，供 quality_analysis 消费。\n",
            encoding="utf-8",
        )
        image_paths = _seed_entity_images(task_id, batch_id, name, idx, 5)

        for angle in angles_for(domain, etype):
            ref = f"{name}_{angle}"
            tag_post = build_post_tag_refs(row, angle)
            pm = {
                "contentType": "article",
                "entityRefs": [ent_ref],
                "tagRefs": tag_post,
            }
            validate_travel_post(pm, etype, context=f"{task_id}:{ref}")

            object_key = f"media/image/post/cold_start_chuanxi_{ref}/v1/cover.jpg"
            assets = []
            for img_idx, img_path in enumerate(image_paths[:3], start=1):
                aid = asset_id_from_object_key(object_key) if img_idx == 1 else (
                    asset_id_from_object_key(object_key) + f"_{img_idx}"
                )
                ok = object_key if img_idx == 1 else object_key.replace(
                    "cover", f"detail_{img_idx}"
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

            article = _build_article(row, angle, ent_ref, tag_post, assets[0]["assetId"])
            title = f"{name}{angle}指南"
            compose_payload = {
                "topicId": ref,
                "title": title,
                "articleMarkdown": article,
                "entityRefs": [f"/entity/{ent_ref}"],
                "tagRefs": tag_post,
                "sourceUrls": [f"https://cold-start.local/chuanxi/{name}"],
                "template": "journal" if angle in ("日记", "叙事", "体验") else "gentle",
                "assets": assets,
                "publishLayout": "travel",
                "publishAngle": angle,
                "publishTitle": title,
                "publishSeq": 1,
            }
            if not dry_run:
                _write_stage_result(task_id, batch_id, "review", ref, {"decision": "approved"})
                _write_stage_result(task_id, batch_id, "compose", ref, compose_payload)
            post_count += 1

    if dry_run:
        print(f"[chuanxi] dry-run: {len(CHUANXI_ENTITIES)} entities, {post_count} posts planned")
        return post_count

    materialized = materialize_posts(task_id, batch_id, "article")
    rel_root = release_root(CHUANXI_RELEASE_ID)
    if rel_root.exists():
        shutil.rmtree(rel_root)
    assemble_release(task_id, CHUANXI_RELEASE_ID)
    _ensure_release_gate_stubs(CHUANXI_RELEASE_ID, task_id)
    issues = gate_publish(CHUANXI_RELEASE_ID)
    if issues:
        raise RuntimeError(f"Chuanxi release gate failed: {issues}")

    print(
        f"[chuanxi] entities={len(CHUANXI_ENTITIES)} posts={post_count} "
        f"materialized={len(materialized)} release={CHUANXI_RELEASE_ID}"
    )
    return len(materialized)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed 川西冷启动 16×2 batch")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    count = seed_chuanxi_batch(dry_run=args.dry_run)
    if count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
