"""Curated download sources（模拟马蜂窝/携程/官方渠道，供 compose 消费）。"""
from __future__ import annotations

from cold_start.chuanxi_v2_entity_facts import get_entity_facts


def _source_body(entity: str, platform: str, angle: str) -> str:
    facts = get_entity_facts(entity)
    return (
        f"# {entity}{angle}\n\n"
        f"来源平台：{platform}。{facts.highlight}\n\n"
        f"交通：{facts.transport_from_chengdu}\n"
        f"门票：{facts.ticket}；开放：{facts.hours}。\n"
        f"最佳季节：{facts.best_season}。{facts.altitude_note}\n\n"
        f"实地走过后，建议把排队和观光车末班时间写进日程表，"
        f"旺季务必提前预约，雨天备备选 indoor 或低海拔点位。\n"
    )


def curated_sources_for_entity(entity: str) -> list[dict]:
    """每实体 ≥2 平台 source，符合 gate_download 目录结构。"""
    return [
        {
            "source_id": "mafengwo_travel_note",
            "platform": "mafengwo",
            "url": f"https://www.mafengwo.cn/travel-scenic-intro/{entity}.html",
            "body": _source_body(entity, "马蜂窝", "游记摘录"),
        },
        {
            "source_id": "ctrip_guide",
            "platform": "ctrip",
            "url": f"https://you.ctrip.com/place/{entity}.html",
            "body": _source_body(entity, "携程攻略", "实用信息"),
        },
    ]


def source_frontmatter(source: dict, entity: str) -> str:
    return (
        f"---\n"
        f"url: {source['url']}\n"
        f"platform: {source['platform']}\n"
        f"title: {entity}川西旅行参考\n"
        f"entity: {entity}\n"
        f"retained: true\n"
        f"---\n\n"
        f"{source['body']}"
    )
