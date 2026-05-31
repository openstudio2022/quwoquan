"""实体挖掘 + 关联实体主页生成。

produce review 阶段：从 draft_meta.extractedEntities 提取专有实体（如 洛绒牛场），
判断其是否已有主页（publish 主线或本 task entities 下的 page.md）。

关联实体生产（作者视角"可关联查看"）：对无主页的抽取实体，自动在本 task entities/
下生成最小实体主页 page.md + _entity.json，使其成为可导航实体；生成后 hasHomepage=True。
发布时仍无主页的实体引用会被 publish_filter 过滤。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from _common.io import read_json, write_json
from _common.paths import PUBLISH_ROOT, task_data
from _common.review_ledger import entities_path

# 抽取实体的中文类型 → (domain, etype)
TYPE_TO_DOMAIN_ETYPE: dict[str, tuple[str, str]] = {
    "景区": ("地点", "景区"),
    "景点": ("地点", "景区"),
    "博物馆": ("地点", "博物馆"),
    "古镇": ("地点", "古镇"),
    "遗址": ("地点", "遗址"),
    "打卡地": ("地点", "打卡地"),
    "餐厅": ("地点", "餐厅"),
    "民宿": ("地点", "民宿"),
    "山峰": ("地点", "自然景观"),
    "湖泊": ("地点", "自然景观"),
    "自然景观": ("地点", "自然景观"),
    "牧场": ("地点", "自然景观"),
    "学校": ("机构", "学校"),
}
DEFAULT_DOMAIN_ETYPE = ("地点", "打卡地")


def resolve_domain_etype(etype_hint: str | None) -> tuple[str, str]:
    if not etype_hint:
        return DEFAULT_DOMAIN_ETYPE
    hint = etype_hint.strip().strip("/")
    if "/" in hint:
        parts = hint.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
    return TYPE_TO_DOMAIN_ETYPE.get(hint, DEFAULT_DOMAIN_ETYPE)


def entity_ref(domain: str, etype: str, name: str) -> str:
    return f"/entity/{domain}/{etype}/{name}"


def homepage_exists(domain: str, etype: str, name: str, task_id: str) -> bool:
    if (PUBLISH_ROOT / "entities" / domain / etype / name / "page.md").is_file():
        return True
    return task_data(task_id).entity_page(domain, etype, name).is_file()


def _stub_entity_page(name: str, domain: str, etype: str, evidence: str) -> str:
    intro = evidence.strip() or f"{name} 是与本文相关的{etype}。"
    return (
        f"# {name}\n\n"
        f"> 实体类型：[/entity/{domain}/{etype}]({entity_ref(domain, etype, '')})\n\n"
        f"{intro}\n\n"
        f"## 关于 {name}\n\n"
        f"本页由内容生产流程自动挖掘并建立，作为 {name} 的可关联实体主页；"
        f"后续可补充结构化事实与配图。\n"
    )


def generate_entity_homepage(
    task_id: str,
    name: str,
    domain: str,
    etype: str,
    *,
    evidence: str = "",
    source_ref: str = "",
) -> Path:
    """在 task entities 下生成最小实体主页 + _entity.json，使实体可关联查看。"""
    data = task_data(task_id)
    ent_dir = data.entity_dir(domain, etype, name)
    ent_dir.mkdir(parents=True, exist_ok=True)
    page = data.entity_page(domain, etype, name)
    page.write_text(_stub_entity_page(name, domain, etype, evidence), encoding="utf-8")
    write_json(
        data.entity_json(domain, etype, name),
        {
            "label": name,
            "domain": domain,
            "type": etype,
            "tagRefs": [],
            "sourceRef": source_ref,
            "generatedBy": "produce.entity_extract",
        },
    )
    return page


def build_entities_sidecar(
    task_id: str,
    batch_id: str,
    ref: str,
    draft_meta: Mapping[str, Any] | None,
    *,
    auto_generate: bool = True,
) -> dict[str, Any]:
    """从 draft_meta.extractedEntities 构建实体 sidecar，并按需生成关联实体主页。"""
    extracted: Sequence[Mapping[str, Any]] = []
    if draft_meta:
        extracted = draft_meta.get("extractedEntities") or []

    out_entities: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for ent in extracted:
        name = str(ent.get("name") or "").strip()
        if not name:
            continue
        domain, etype = resolve_domain_etype(ent.get("type"))
        key = (domain, etype, name)
        if key in seen:
            continue
        seen.add(key)
        has = homepage_exists(domain, etype, name, task_id)
        generated = False
        if not has and auto_generate:
            generate_entity_homepage(
                task_id,
                name,
                domain,
                etype,
                evidence=str(ent.get("evidence") or ent.get("evidenceRef") or ""),
                source_ref=str(ent.get("evidenceRef") or ""),
            )
            has = True
            generated = True
        out_entities.append(
            {
                "name": name,
                "domain": domain,
                "type": etype,
                "ref": entity_ref(domain, etype, name),
                "hasHomepage": has,
                "generated": generated,
                "evidenceRef": ent.get("evidenceRef") or "",
            }
        )

    sidecar = {
        "schemaVersion": "quwoquan_data.review_entities",
        "ref": ref,
        "entities": out_entities,
    }
    write_json(entities_path(task_id, batch_id, ref), sidecar)
    return sidecar
