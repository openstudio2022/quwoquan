"""qwq-data plan — resolve instructions into compose briefs."""
from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from content.execution.planning.brief import resolve_compose_brief, write_brief
from content.execution.planning.nl_dispatch import dispatch_instruction
from content.templates.registry import TemplateRegistry
from content.templates.router import RouteRequest


ENTITY_KIND_MAP = {
    "景区": "地点/景区",
    "博物馆": "地点/博物馆",
    "古镇": "地点/古镇",
    "遗址": "地点/遗址",
    "打卡地": "地点/打卡地",
    "餐厅": "地点/餐厅",
    "民宿": "地点/民宿",
    "学校": "机构/学校",
}

TOPIC_KIND_MAP = {
    "线路": "旅行/线路",
    "榜单": "旅行/榜单",
    "主题": "旅行/主题",
    "合辑": "教育成长/合辑",
}


def handle_plan(args: argparse.Namespace) -> None:
    registry = TemplateRegistry.load()
    if args.instruction:
        request = dispatch_instruction(args.instruction, default_vertical=args.vertical)
        title = args.instruction
    else:
        subject_type = _subject_type(args.subject, args.kind, args.vertical)
        request = RouteRequest(
            vertical=args.vertical,
            subject_kind=args.subject,
            subject_type=subject_type,
            intent=args.intent or args.angle,
            audience=args.audience,
            creator_archetype=args.creator_archetype,
            region=args.region,
            season=args.season,
        )
        title = args.title
    # 显式 --region/--season 覆盖自然语言推断结果
    overrides = {}
    if args.region:
        overrides["region"] = args.region
    if args.season:
        overrides["season"] = args.season
    if overrides:
        request = dataclasses.replace(request, **overrides)
    entity_refs = [item.strip() for item in (args.entity_refs or "").split(",") if item.strip()]
    brief = resolve_compose_brief(registry, request, title=title, entity_refs=entity_refs)
    if args.output:
        write_brief(Path(args.output), brief)
        print(f"[plan] wrote compose brief: {args.output}")
    else:
        print(json.dumps(brief, ensure_ascii=False, indent=2))


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("plan", help="Resolve a content instruction into compose_brief JSON")
    p.add_argument("--instruction", help="Natural language instruction")
    p.add_argument("--vertical", choices=["travel", "campus"], default="travel")
    p.add_argument("--subject", choices=["entity", "topic"], default="entity")
    p.add_argument("--kind", default="景区", help="Entity/topic kind, e.g. 景区, 学校, 线路")
    p.add_argument("--intent", help="Intent name, e.g. 路线推荐, 新生攻略")
    p.add_argument("--angle", help="Backward-compatible alias of --intent")
    p.add_argument("--audience", help="Audience id")
    p.add_argument("--region", help="Region condition key, e.g. 高原, 沿海海岛, 平原都市")
    p.add_argument("--season", help="Season condition key, e.g. 春, 夏, 秋, 冬, 雨季, 旺季")
    p.add_argument("--creator-archetype", help="Optional creator archetype override")
    p.add_argument("--entity-refs", help="Comma-separated entity refs for topic/entity cross refs")
    p.add_argument("--title", help="Title hint")
    p.add_argument("--output", help="Write compose_brief JSON to this path")
    p.set_defaults(handler=handle_plan)


def _subject_type(subject_kind: str, kind: str, vertical: str) -> str:
    if subject_kind == "topic":
        if kind in TOPIC_KIND_MAP:
            return TOPIC_KIND_MAP[kind]
        return "教育成长/合辑" if vertical == "campus" else "旅行/主题"
    return ENTITY_KIND_MAP.get(kind, kind)
