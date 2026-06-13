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

from _common.entity_object import find_entity_object_dir, sync_entity_object_to_task_mirror, write_entity_object_index
from _common.io import read_json, write_json
from _common.paths import PUBLISH_ROOT, batch_entity_object_dir, task_data
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


def resolve_domain_etype(
    etype_hint: str | None,
    *,
    allow_default_on_missing: bool = True,
    allow_default_on_unknown: bool = True,
) -> tuple[str, str]:
    if not etype_hint:
        if allow_default_on_missing:
            return DEFAULT_DOMAIN_ETYPE
        raise ValueError("entityType missing")
    hint = etype_hint.strip().strip("/")
    if not hint:
        if allow_default_on_missing:
            return DEFAULT_DOMAIN_ETYPE
        raise ValueError("entityType missing")
    if "/" in hint:
        parts = hint.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
    mapped = TYPE_TO_DOMAIN_ETYPE.get(hint)
    if mapped is not None:
        return mapped
    if allow_default_on_unknown:
        return DEFAULT_DOMAIN_ETYPE
    raise ValueError(f"unknown entityType hint: {etype_hint!r}")


def require_domain_etype(etype_hint: str | None, *, context: str = "entityType") -> tuple[str, str]:
    try:
        return resolve_domain_etype(
            etype_hint,
            allow_default_on_missing=False,
            allow_default_on_unknown=False,
        )
    except ValueError as exc:
        raise ValueError(f"{context}: {exc}") from exc


def normalize_domain_etype_path(
    etype_hint: str | None,
    *,
    context: str = "entityType",
    allow_default_on_missing: bool = True,
    allow_default_on_unknown: bool = True,
) -> str:
    domain, etype = resolve_domain_etype(
        etype_hint,
        allow_default_on_missing=allow_default_on_missing,
        allow_default_on_unknown=allow_default_on_unknown,
    )
    return f"{domain}/{etype}"


def entity_ref(domain: str, etype: str, name: str) -> str:
    return f"/entity/{domain}/{etype}/{name}"


def normalize_entity_refs(raw_refs: Sequence[Any] | None, subject_type: str | None) -> list[str]:
    """把 compose-brief 的实体引用补全为发布门可识别的全路径 /entity/{domain}/{type}/{name}。

    单一真相源：domain/type 取自 compose input 的 subject.type（如 "地点/景区"），不维护第二套
    实体类型映射；已是全路径（含 domain/type）的引用原样规范化，短名引用按 subject 补全。
    publish_filter 据此精确定位 entities/{domain}/{type}/{name}/page.md，避免主实体被误过滤。
    """
    if subject_type:
        domain, etype = require_domain_etype(subject_type, context="brief.subject.type")
    else:
        domain, etype = DEFAULT_DOMAIN_ETYPE
    out: list[str] = []
    for item in raw_refs or []:
        s = str(item).strip().strip("/")
        if not s:
            continue
        parts = s.split("/")
        if parts and parts[0] == "entity":
            parts = parts[1:]
        if len(parts) >= 3:
            out.append("/entity/" + "/".join(parts))
        else:
            out.append(entity_ref(domain, etype, parts[-1]))
    return out


def homepage_exists(domain: str, etype: str, name: str, task_id: str, batch_id: str = "") -> bool:
    if (PUBLISH_ROOT / "entities" / domain / etype / name / "page.md").is_file():
        return True
    obj = find_entity_object_dir(task_id, domain, etype, name, batch_id=batch_id)
    if obj is not None and (obj / "page.md").is_file():
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
    batch_id: str,
    name: str,
    domain: str,
    etype: str,
    *,
    evidence: str = "",
    source_ref: str = "",
    condition_profile: Mapping[str, Any] | None = None,
) -> Path:
    """在 batch 实体对象下生成最小实体主页 + _entity.json，使实体可关联查看。

    condition_profile（L3 实体条件画像：真实地形 regions / 最佳季节 seasons / 海拔 altitudeMeters）
    仅在显式传入且非空时写入，plan/brief 据此精确注入 conditionContext；缺省时不写，回退地域全谱。
    """
    from _common.source_unit import resolve_entity_object_dir

    ent_dir = resolve_entity_object_dir(
        task_id,
        batch_id,
        name,
        etype_hint=f"{domain}/{etype}",
    )
    ent_dir.mkdir(parents=True, exist_ok=True)
    page = ent_dir / "page.md"
    page.write_text(_stub_entity_page(name, domain, etype, evidence), encoding="utf-8")
    payload: dict[str, Any] = {
        "label": name,
        "domain": domain,
        "type": etype,
        "tagRefs": [],
        "sourceRef": source_ref,
        "generatedBy": "produce.entity_extract",
        "sourceTaskId": task_id,
    }
    if condition_profile:
        payload["conditionProfile"] = dict(condition_profile)
    write_json(ent_dir / "_entity.json", payload)
    write_entity_object_index(task_id, batch_id, domain, etype, name)
    sync_entity_object_to_task_mirror(task_id, batch_id, domain, etype, name)
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
        has = homepage_exists(domain, etype, name, task_id, batch_id)
        generated = False
        if not has and auto_generate:
            generate_entity_homepage(
                task_id,
                batch_id,
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
