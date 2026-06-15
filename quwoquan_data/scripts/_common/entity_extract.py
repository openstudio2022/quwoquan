"""实体挖掘、semantic mentions 与候选治理 intake。

produce review 阶段：从 draft_meta.extractedEntities 提取专有实体（如 洛绒牛场），
判断其是否已有主页（publish 主线或本 task entities 下的 page.md）。

未知实体只能进入隔离候选库并等待人工审核；本模块不会再自动生成占位主页。
批准动作由 governance 状态机记录审计并发出 backfill event，实际主页生产由后续消费者完成。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from _common.entity_object import find_entity_object_dir, sync_entity_object_to_task_mirror, write_entity_object_index
from _common.io import read_json, write_json
from _common.paths import PUBLISH_ROOT, RUNTIME_ROOT, task_data
from _common.review_ledger import entities_path
from _common.semantic_mentions import (
    DEFAULT_MAX_CANDIDATES,
    MENTION_STATUSES,
    STATUS_PENDING_REVIEW,
    STATUS_PUBLISHED,
    build_semantic_mentions,
)
from governance.candidate_store import CandidateRepository, candidate_id_for

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


def _existing_homepage_status(
    domain: str,
    etype: str,
    name: str,
    task_id: str,
    batch_id: str,
) -> str:
    metadata_paths = [PUBLISH_ROOT / "entities" / domain / etype / name / "_entity.json"]
    obj = find_entity_object_dir(task_id, domain, etype, name, batch_id=batch_id)
    if obj is not None:
        metadata_paths.append(obj / "_entity.json")
    metadata_paths.append(task_data(task_id).entity_json(domain, etype, name))
    for path in metadata_paths:
        if not path.is_file():
            continue
        status = str((read_json(path) or {}).get("status") or "").strip()
        if status in MENTION_STATUSES:
            return status
    return STATUS_PUBLISHED


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
    approved_candidate_id: str = "",
    candidate_repository: CandidateRepository | None = None,
) -> Path:
    """Materialize an approved backfill candidate as a minimal entity page.

    condition_profile（L3 实体条件画像：真实地形 regions / 最佳季节 seasons / 海拔 altitudeMeters）
    仅在显式传入且非空时写入，plan/brief 据此精确注入 conditionContext；缺省时不写，回退地域全谱。
    """
    from _common.source_unit import resolve_entity_object_dir

    repository = candidate_repository or CandidateRepository(RUNTIME_ROOT / "governance")
    candidate = repository.get(str(approved_candidate_id).strip()) if approved_candidate_id else None
    expected_ref = entity_ref(domain, etype, name)
    if (
        candidate is None
        or candidate.get("kind") != "entity_homepage"
        or candidate.get("naturalKey") != expected_ref
        or candidate.get("status") != STATUS_PUBLISHED
    ):
        raise PermissionError(
            f"entity homepage backfill requires an approved governance candidate: {expected_ref}"
        )

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
        "governanceCandidateId": approved_candidate_id,
        "status": STATUS_PUBLISHED,
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
    auto_generate: bool = False,
    article_text: str | None = None,
    candidate_repository: CandidateRepository | None = None,
) -> dict[str, Any]:
    """Build the entity sidecar and intake unknown entities for human review.

    ``auto_generate`` is retained for caller compatibility but intentionally ignored.
    """
    _ = auto_generate
    extracted: Sequence[Mapping[str, Any]] = []
    if draft_meta:
        extracted = draft_meta.get("extractedEntities") or []
    if article_text is None:
        from _common.draft_io import read_draft_article

        article_text = read_draft_article(task_id, batch_id, ref) or ""
    repository = candidate_repository or CandidateRepository(RUNTIME_ROOT / "governance")

    out_entities: list[dict[str, Any]] = []
    mention_targets: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for ent in extracted:
        name = str(ent.get("name") or "").strip()
        if not name:
            continue
        domain, etype = resolve_domain_etype(ent.get("type"))
        key = (domain, etype, name)
        if key in seen:
            continue
        if len(seen) >= DEFAULT_MAX_CANDIDATES:
            break
        seen.add(key)
        has = homepage_exists(domain, etype, name, task_id, batch_id)
        target_ref = entity_ref(domain, etype, name)
        candidate_id = ""
        if has:
            governance_status = _existing_homepage_status(domain, etype, name, task_id, batch_id)
        else:
            candidate_id = candidate_id_for("entity_homepage", target_ref)
            provisional_mentions = build_semantic_mentions(
                article_text,
                source_ref=ref,
                targets=[
                    {
                        "targetRef": target_ref,
                        "surface": name,
                        "status": STATUS_PENDING_REVIEW,
                        "candidateId": candidate_id,
                    }
                ],
            )
            candidate = repository.intake(
                kind="entity_homepage",
                natural_key=target_ref,
                payload={
                    "name": name,
                    "domain": domain,
                    "type": etype,
                    "targetRef": target_ref,
                    "evidence": str(ent.get("evidence") or ""),
                    "evidenceRef": str(ent.get("evidenceRef") or ""),
                },
                source_refs=[
                    f"task:{task_id}:batch:{batch_id}:content:{ref}",
                    str(ent.get("evidenceRef") or ""),
                ],
                mention_ids=[row["mentionId"] for row in provisional_mentions],
                actor="produce.entity_extract",
            )
            governance_status = str(candidate.get("status") or STATUS_PENDING_REVIEW)
        mention_targets.append(
            {
                "targetRef": target_ref,
                "surface": name,
                "status": governance_status,
                "candidateId": candidate_id,
            }
        )
        out_entities.append(
            {
                "name": name,
                "domain": domain,
                "type": etype,
                "ref": target_ref,
                "hasHomepage": has,
                "generated": False,
                "governanceStatus": governance_status,
                "candidateId": candidate_id,
                "evidenceRef": ent.get("evidenceRef") or "",
            }
        )

    semantic_mentions = build_semantic_mentions(
        article_text,
        source_ref=ref,
        targets=mention_targets,
    )
    mention_ids_by_ref: dict[str, list[str]] = {}
    for mention in semantic_mentions:
        mention_ids_by_ref.setdefault(str(mention["targetRef"]), []).append(str(mention["mentionId"]))
    for entity in out_entities:
        entity["mentionIds"] = mention_ids_by_ref.get(str(entity["ref"]), [])

    sidecar = {
        "schemaVersion": "quwoquan_data.review_entities",
        "ref": ref,
        "entities": out_entities,
        "semanticMentions": semantic_mentions,
    }
    write_json(entities_path(task_id, batch_id, ref), sidecar)
    return sidecar
