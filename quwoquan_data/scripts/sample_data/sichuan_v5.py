"""四川旅行 v5 示例数据：16 实体 + 32 posts。"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _common.paths import NOW_ISO, PUBLISH_ROOT, RUNTIME_ROOT, ensure_task_layout  # noqa: E402

from sample_data._common import (  # noqa: E402
    make_entity,
    make_entity_manifest,
    make_entity_page,
    make_post_article,
    make_post_manifest,
    validate_travel_post,
    write_entity,
    write_post,
    write_task_manifest,
)

TASK_ID = "四川旅行_v5"

# 与 gate_e2e.py 中 TYPE_ANGLES / G4 约定一致（路径：内容角度/{angle}，标题：{name}{angle}指南）
TYPE_ANGLES: dict[tuple[str, str], list[str]] = {
    ("地点", "景区"): ["攻略", "体验"],
    ("地点", "遗址"): ["科普", "体验"],
    ("地点", "打卡地"): ["攻略", "日记"],
    ("地点", "博物馆"): ["科普", "体验"],
    ("地点", "古镇"): ["攻略", "叙事"],
    ("地点", "餐厅"): ["探店", "攻略"],
    ("地点", "住宿"): ["体验", "攻略"],
    ("机构", "学校"): ["攻略", "体验"],
}


def _geo(city: str) -> str:
    return f"Topic/地理/行政区/中国/四川省/{city}"


def _entity_tag_line(domain: str, etype: str) -> str:
    return f"Entity/{domain}/{etype}"


def build(dry_run: bool = False):
    """生成四川旅行 v5 全量数据。"""
    root = RUNTIME_ROOT / "tasks" / TASK_ID
    if not dry_run:
        ensure_task_layout(TASK_ID)

    rows: list[dict] = [
        {
            "name": "峨眉山",
            "label_en": "Mount Emei",
            "etype": "景区",
            "domain": "地点",
            "city": "乐山市",
            "theme": "Topic/旅行/旅行主题/雪山探险",
        },
        {
            "name": "九寨沟",
            "label_en": "Jiuzhaigou",
            "etype": "景区",
            "domain": "地点",
            "city": "阿坝州",
            "theme": "Topic/旅行/玩法/观光游览",
        },
        {
            "name": "稻城亚丁",
            "label_en": "Daocheng Yading",
            "etype": "景区",
            "domain": "地点",
            "city": "甘孜州",
            "theme": "Topic/旅行/出行方式/徒步穿越",
        },
        {
            "name": "黄龙",
            "label_en": "Huanglong",
            "etype": "景区",
            "domain": "地点",
            "city": "阿坝州",
            "theme": "Topic/旅行/旅行主题/海滨度假",
        },
        {
            "name": "海螺沟",
            "label_en": "Hailuogou",
            "etype": "景区",
            "domain": "地点",
            "city": "甘孜州",
            "theme": "Topic/旅行/旅行主题/雪山探险",
        },
        {
            "name": "三星堆遗址",
            "label_en": "Sanxingdui Site",
            "etype": "遗址",
            "domain": "地点",
            "city": "德阳市",
            "theme": "Topic/旅行/旅行主题/文化深度游",
        },
        {
            "name": "金沙遗址",
            "label_en": "Jinsha Site",
            "etype": "遗址",
            "domain": "地点",
            "city": "成都市",
            "theme": "Topic/旅行/旅行主题/文化深度游",
        },
        {
            "name": "阆中古城",
            "label_en": "Langzhong Ancient Town",
            "etype": "古镇",
            "domain": "地点",
            "city": "南充市",
            "theme": "Topic/旅行/玩法/古迹寻访",
        },
        {
            "name": "黄龙溪古镇",
            "label_en": "Huanglongxi Ancient Town",
            "etype": "古镇",
            "domain": "地点",
            "city": "成都市",
            "theme": "Topic/旅行/玩法/古迹寻访",
        },
        {
            "name": "成都太古里",
            "label_en": "Chengdu Taikoo Li",
            "etype": "打卡地",
            "domain": "地点",
            "city": "成都市",
            "theme": "Topic/旅行/旅行主题/城市漫步",
        },
        {
            "name": "宽窄巷子",
            "label_en": "Kuanzhai Alley",
            "etype": "打卡地",
            "domain": "地点",
            "city": "成都市",
            "theme": "Topic/旅行/旅行主题/城市漫步",
        },
        {
            "name": "三星堆博物馆",
            "label_en": "Sanxingdui Museum",
            "etype": "博物馆",
            "domain": "地点",
            "city": "德阳市",
            "theme": "Topic/旅行/玩法/博物馆展览",
        },
        {
            "name": "成都博物馆",
            "label_en": "Chengdu Museum",
            "etype": "博物馆",
            "domain": "地点",
            "city": "成都市",
            "theme": "Topic/旅行/玩法/博物馆展览",
        },
        {
            "name": "陈麻婆豆腐总店",
            "label_en": "Chen Mapo Tofu Flagship",
            "etype": "餐厅",
            "domain": "地点",
            "city": "成都市",
            "theme": "Topic/旅行/玩法/市集探店",
        },
        {
            "name": "峨眉山蓝光己庄温泉度假村",
            "label_en": "Blulight Yizhuang Emei Hot Spring Resort",
            "etype": "住宿",
            "domain": "地点",
            "city": "乐山市",
            "theme": "Topic/旅行/玩法/SPA美容",
        },
        {
            "name": "四川大学",
            "label_en": "Sichuan University",
            "etype": "学校",
            "domain": "机构",
            "city": "成都市",
            "theme": "Topic/旅行/旅行主题/城市漫步",
        },
    ]

    entity_count = 0
    post_count = 0
    for r in rows:
        name = r["name"]
        etype = r["etype"]
        domain = r["domain"]
        geo = _geo(r["city"])
        desc = (
            f"{name} 位于四川省{r['city']}，类型为 {etype}，是四川旅行 v5 示例数据中的结构化实体，"
            "用于验证实体三件套与 post 关联链路。"
        )
        highlights = [
            f"{r['city']}行程节点：建议预留缓冲时段用于排队、预约与天气变化。",
            f"与周边景点联动：可把{name}放入同一日的动线主干，减少折返。",
            "风险提示：关注高海拔、雨季路况与景区临时管控公告。",
            "内容提示：正文与图片素材需单独走版权与事实核验流程（本数据为占位）。",
        ]
        first_angle = TYPE_ANGLES[(domain, etype)][0]
        ent_tags = [
            r["theme"],
            "Topic/旅行/玩法/观光游览",
            "Topic/旅行/出行方式/自驾",
            "Topic/旅行/行程形态/自由行",
            "Topic/旅行/旅行时长/3-5日中线",
            f"Format/内容角度/{first_angle}",
            _entity_tag_line(domain, etype),
        ]
        entity = make_entity(
            name,
            r["label_en"],
            desc,
            domain,
            etype,
            geo,
            ent_tags,
        )
        page = make_entity_page(name, domain, etype, desc, highlights)
        em = make_entity_manifest(name, domain, etype, ent_tags, entity_refs=[])
        entity_ref = f"{domain}/{etype}/{name}"
        if not dry_run:
            write_entity(root, domain, etype, name, entity, page, em)
        entity_count += 1

        for angle in TYPE_ANGLES[(domain, etype)]:
            title = f"{name}{angle}指南"
            theme_bonus = (
                "Topic/旅行/旅行主题/城市漫步"
                if etype in {"打卡地", "博物馆", "餐厅", "住宿", "学校"}
                else r["theme"]
            )
            tr = [
                theme_bonus,
                "Topic/旅行/玩法/观光游览",
                "Topic/旅行/出行方式/自驾",
                "Topic/旅行/行程形态/自由行",
                f"Format/内容角度/{angle}",
                _entity_tag_line(domain, etype),
            ]
            if name == "稻城亚丁" and angle == "体验":
                tr.append("Topic/旅行/玩法/摄影旅拍")
            paras = [
                f"围绕 {name} 的「{angle}」视角：从动线、耗时与体验节奏写清可执行建议。",
                f"结合 {r['city']} 的交通与预约现实，给出可手动校准的时间表。",
                "把最容易踩坑的节点（排队、闭馆、临时管制）提前标注，避免到现场被动改线。",
            ]
            pm = make_post_manifest(title, entity_ref, tr, content_type="article")
            validate_travel_post(pm, etype, context=f"{TASK_ID}:{title}")
            art = make_post_article(title, name, domain, etype, angle, paras)
            if not dry_run:
                write_post(root, "article", angle, title, 1, art, pm)
            post_count += 1

    if not dry_run:
        write_task_manifest(root, TASK_ID, entity_count, post_count)

        # publish 同构：把当前 task 产物同步到 publish/v1，供 gate_e2e 读取
        publish_root = PUBLISH_ROOT / "v1"
        shutil.copytree(root / "entities", publish_root / "entities", dirs_exist_ok=True)
        shutil.copytree(root / "posts", publish_root / "posts", dirs_exist_ok=True)

        # gate_e2e.py（G1/G7/G8）需要的最小文件结构
        publish_tags = PUBLISH_ROOT / "v1" / "tags"
        tags_path = root / "tags"
        if publish_tags.exists():
            if tags_path.exists() and not tags_path.is_symlink():
                shutil.rmtree(tags_path)
            if not tags_path.exists():
                tags_path.symlink_to(publish_tags, target_is_directory=True)
        else:
            tags_path.mkdir(parents=True, exist_ok=True)

        taxonomy_path = tags_path / "_taxonomy.json"
        if tags_path.exists() and not taxonomy_path.exists():
            taxonomy_data = {
                "schemaVersion": "1",
                "groups": ["Topic", "Audience", "Format", "Entity"],
                "createdAt": NOW_ISO,
                "updatedAt": NOW_ISO,
            }
            taxonomy_path.write_text(
                json.dumps(taxonomy_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        cs_dir = root / "changeset"
        cs_dir.mkdir(parents=True, exist_ok=True)
        entities_lines = [f"{r['domain']}/{r['etype']}/{r['name']}" for r in rows]
        (cs_dir / "entities.txt").write_text("\n".join(entities_lines) + "\n", encoding="utf-8")
        (cs_dir / "tags.txt").write_text(
            "Topic/旅行\nTopic/地理/行政区\n",
            encoding="utf-8",
        )
        posts_lines: list[str] = []
        for r in rows:
            name_i = r["name"]
            domain_i = r["domain"]
            etype_i = r["etype"]
            for ang in TYPE_ANGLES[(domain_i, etype_i)]:
                tit = f"{name_i}{ang}指南"
                posts_lines.append(f"article/{ang}/{tit}/1")
        (cs_dir / "posts.txt").write_text("\n".join(posts_lines) + "\n", encoding="utf-8")

        batch_root = root / "batches" / "多维度冒烟"
        for cmd in ["explore", "build", "download", "produce", "reconcile"]:
            cmd_dir = batch_root / cmd
            (cmd_dir / "inputs").mkdir(parents=True, exist_ok=True)
            (cmd_dir / "results").mkdir(parents=True, exist_ok=True)
            at_dir = cmd_dir / "assistant_tasks"
            at_dir.mkdir(parents=True, exist_ok=True)
            at_file = at_dir / "step_001.json"
            if not at_file.exists():
                at_file.write_text(
                    json.dumps(
                        {
                            "stepId": "step_001",
                            "command": cmd,
                            "status": "completed",
                            "createdAt": NOW_ISO,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
    return entity_count, post_count
