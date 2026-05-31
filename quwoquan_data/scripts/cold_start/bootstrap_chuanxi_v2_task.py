#!/usr/bin/env python3
"""川西 v2 任务 bootstrap：实体 + catalog + manifest + compose brief（不写正文）。

正文必须通过 compose_chuanxi_v2_from_sources.py（消费 download sources）生成。

用法:
  python3 cold_start/bootstrap_chuanxi_v2_task.py
  python3 cold_start/bootstrap_chuanxi_v2_task.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.io import write_ndjson  # noqa: E402
from _common.paths import batch_inputs_dir, ensure_batch_layout, ensure_task_layout, task_data, task_root  # noqa: E402
from cold_start.chuanxi_catalog import angles_for, build_post_tag_refs, entity_ref, geo_tag  # noqa: E402
from cold_start.chuanxi_catalog_v2 import (  # noqa: E402
    CHUANXI_V2_ALL_ENTITIES,
    CHUANXI_V2_SCENIC,
    CHUANXI_V2_TASK_ID,
    build_all_article_specs,
    build_batch_manifest_rows,
)
from cold_start.chuanxi_v2_shared import V2_BATCHES  # noqa: E402
from cold_start.generate_chuanxi_v2_manifest import spec_to_route_request  # noqa: E402
from cold_start.seed_chuanxi_batch import HIGHLIGHTS_BY_ROLE  # noqa: E402
from plan.brief import resolve_compose_brief, write_brief  # noqa: E402
from sample_data._common import make_entity, make_entity_manifest, make_entity_page, write_entity  # noqa: E402
from template.registry import TemplateRegistry  # noqa: E402

HIGHLIGHTS_V2 = {
    **HIGHLIGHTS_BY_ROLE,
    "户外核心": ["双桥沟/长坪沟强度不同，按同行体力选线。", "高海拔区注意防晒与补水。"],
    "藏寨人文": ["藏寨观景台早晚光线更适合摄影。", "尊重当地习俗，拍摄人物前先征得同意。"],
    "高原奇观": ["墨石公园建议预留 2–3 小时。", "风大时注意保暖与镜头防护。"],
    "人文高地": ["色达地区宗教氛围浓厚，请保持安静与尊重。"],
    "摄影走廊": ["新都桥清晨傍晚是黄金时段。", "318 沿线注意行车安全。"],
    "彩林沟谷": ["秋季彩林是毕棚沟高光。", "沟内海拔变化大，分层穿衣。"],
    "草原湿地": ["花湖观赏期随年份变化，行前查官方公告。"],
    "康定门户": ["木格措注意末班观光车。", "冬季部分路段可能结冰。"],
    "高城驿站": ["理塘初到者建议慢走慢吃。", "长青春科尔寺是人文亮点。"],
    "藏乡秘境": ["甲根坝适合摄影与慢行。", "可与新都桥方向组合。"],
}


def _write_catalog(task_id: str) -> None:
    rows = []
    for row in CHUANXI_V2_ALL_ENTITIES:
        rows.append(
            {
                "entityName": row["name"],
                "entityType": row["etype"],
                "domain": row["domain"],
                "geoTagRef": geo_tag(row["city"]),
                "themeTagRef": row["theme"],
                "angles": angles_for(row["domain"], row["etype"]),
                "batchRole": row["role"],
                "p0Scenic": row in CHUANXI_V2_SCENIC,
            }
        )
    write_ndjson(task_root(task_id) / "catalog.ndjson", rows)


def _seed_entities(task_id: str, dry_run: bool) -> None:
    td = task_data(task_id)
    for row in CHUANXI_V2_ALL_ENTITIES:
        name = row["name"]
        domain = row["domain"]
        etype = row["etype"]
        geo = geo_tag(row["city"])
        ent_ref = entity_ref(domain, etype, name)
        first_angle = angles_for(domain, etype)[0]
        ent_tags = build_post_tag_refs(row, first_angle)
        entity_tags = [t for t in ent_tags if not t.startswith("Format/")]
        desc = f"{name}位于四川省{row['city']}，川西旅行标杆 {etype}。定位：{row['role']}。"
        highlights = HIGHLIGHTS_V2.get(row["role"], [f"{row['city']}行程节点建议预留缓冲。"])
        entity = make_entity(name, row["label_en"], desc, domain, etype, geo, entity_tags)
        page = make_entity_page(name, domain, etype, desc, highlights)
        em = make_entity_manifest(name, domain, etype, entity_tags, [ent_ref])
        if not dry_run:
            write_entity(td.root, domain, etype, name, entity, page, em)


def bootstrap_chuanxi_v2(dry_run: bool = False) -> int:
    task_id = CHUANXI_V2_TASK_ID
    ensure_task_layout(task_id)
    for batch_id in V2_BATCHES:
        ensure_batch_layout(task_id, batch_id, "download")
        ensure_batch_layout(task_id, batch_id, "produce")

    if not dry_run:
        write_ndjson(task_root(task_id) / "batch_manifest.ndjson", build_batch_manifest_rows())
    _write_catalog(task_id)
    _seed_entities(task_id, dry_run)

    registry = TemplateRegistry.load()
    specs_by_batch: dict[str, list] = defaultdict(list)
    for spec in build_all_article_specs():
        specs_by_batch[spec.batch].append(spec)

    brief_count = 0
    for batch_id in V2_BATCHES:
        for spec in specs_by_batch[batch_id]:
            brief = resolve_compose_brief(
                registry,
                spec_to_route_request(spec),
                title=spec.title,
                entity_refs=list(spec.entity_refs),
            )
            if not dry_run:
                write_brief(
                    batch_inputs_dir(task_id, batch_id, "produce", "compose") / f"{spec.ref}.json",
                    brief,
                )
            brief_count += 1

    print(
        f"[bootstrap-v2] task={task_id} entities={len(CHUANXI_V2_ALL_ENTITIES)} "
        f"briefs={brief_count} (no compose results written)"
    )
    return brief_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap 川西冷启动 v2 task layout")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if bootstrap_chuanxi_v2(dry_run=args.dry_run) == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
