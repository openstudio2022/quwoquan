from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common import ENTITY_CATALOG_ROOT, write_ndjson

SEMANTIC_CLUSTER_SCHEMA_VERSION = "quwoquan_data.semantic_cluster_candidate"
DEFAULT_CANDIDATES_NAME = "semantic_cluster_candidates.ndjson"
DEFAULT_PENDING_NAME = "semantic_cluster_pending.ndjson"

_PARENT_SUFFIXES = (
    "国家级风景名胜区",
    "风景名胜区",
    "风景旅游区",
    "旅游景区",
    "旅游区",
    "风景区",
    "景区",
    "国家公园",
    "旅游度假区",
    "文旅度假区",
    "庄园",
    "基地",
    "古镇",
    "古城",
    "旧址群",
    "遗址群",
    "遗址公园",
)
_POINT_PARENT_SUFFIXES = (
    "国家级风景名胜区",
    "风景名胜区",
    "风景旅游区",
    "旅游景区",
    "旅游区",
    "风景区",
    "景区",
    "国家公园",
    "旅游度假区",
    "文旅度假区",
    "庄园",
    "基地",
    "古镇",
    "古城",
    "公园",
)
_ESTATE_PARENT_SUFFIXES = ("庄园", "旧址群", "古镇", "古城", "遗址群")
_GENERIC_REJECT_NAMES = {"景点", "办公楼", "历史建筑", "建筑群", "园区入口"}
_DIRECT_NUMBERED_MEMBER_RE = re.compile(
    r"^(?P<base>.+?)(?P<ordinal>[0-9一二三四五六七八九十百]+)号(?P<role>观景台|别墅|公馆|院落|冰川观景台)$"
)
_PAREN_NAME_RE = re.compile(r"^(?P<lemma>.+?)[(（](?P<inner>[^()（）]+)[)）]$")
_UNIVERSITY_OLD_SITE_RE = re.compile(
    r"^(?P<org>(?:国立)?[^()（）]+?大学)(?P<unit>.+?)(?:[(（]?旧址[)）]?)$"
)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class PreparedRow:
    row: dict[str, Any]
    canonical_name: str
    clean_name: str
    topic_id: str
    entity_type: str
    province: str
    prefecture: str
    district: str
    region_key: str
    authority_status: str
    source_type: str
    source_id: str


@dataclass(frozen=True)
class MemberHint:
    role: str
    cluster_token: str
    parent_hints: tuple[str, ...]
    ordinal: str = ""
    family_token: str = ""
    force_pending_without_parent: bool = False
    reason_code: str = ""


def semantic_cluster_candidates_path(name: str = DEFAULT_CANDIDATES_NAME) -> Path:
    return ENTITY_CATALOG_ROOT / name


def semantic_cluster_pending_path(name: str = DEFAULT_PENDING_NAME) -> Path:
    return ENTITY_CATALOG_ROOT / name


def write_semantic_cluster_artifacts(
    *,
    candidates: list[dict[str, Any]],
    pending: list[dict[str, Any]],
    candidates_name: str = DEFAULT_CANDIDATES_NAME,
    pending_name: str = DEFAULT_PENDING_NAME,
) -> dict[str, str]:
    candidates_path = semantic_cluster_candidates_path(candidates_name)
    pending_path = semantic_cluster_pending_path(pending_name)
    write_ndjson(candidates_path, candidates)
    write_ndjson(pending_path, pending)
    return {"candidates": str(candidates_path), "pending": str(pending_path)}


def looks_like_catalog_candidate(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    topic_id = str(row.get("topic_id") or row.get("topicId") or "").strip()
    name = str(row.get("name") or row.get("normalized_name") or "").strip()
    entity_id = str(row.get("entityId") or row.get("entity_id") or "").strip()
    return bool(topic_id and name and not entity_id)


def resolve_catalog_semantics(catalog_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    prepared = [_prepare_row(row) for row in catalog_rows if isinstance(row, dict)]
    hints_by_topic = {row.topic_id: _member_hint(row) for row in prepared if row.topic_id}

    cluster_counts: dict[tuple[str, str, str], int] = {}
    for row in prepared:
        hint = hints_by_topic.get(row.topic_id)
        if not hint or not hint.cluster_token:
            continue
        key = (row.region_key, hint.role, hint.cluster_token)
        cluster_counts[key] = cluster_counts.get(key, 0) + 1

    decisions: dict[str, dict[str, Any]] = {}
    children_by_root: dict[str, list[tuple[PreparedRow, MemberHint]]] = {}
    aliases_by_root: dict[str, list[str]] = {}

    for row in prepared:
        hint = hints_by_topic.get(row.topic_id)
        if _should_reject(row):
            decisions[row.topic_id] = _decision_row(
                row,
                decision="reject",
                cluster_id=_cluster_id(row.region_key, row.clean_name, "reject"),
                reason_codes=["generic_reject_name"],
            )
            continue
        explicit = _explicit_semantic_decision(row)
        if explicit == "reject":
            decisions[row.topic_id] = _decision_row(
                row,
                decision="reject",
                cluster_id=_cluster_id(row.region_key, row.clean_name, "reject"),
                reason_codes=["explicit_reject_hint"],
            )
            continue
        if explicit == "alias":
            root = _pick_alias_root(row, prepared)
            if root:
                decisions[row.topic_id] = _decision_row(
                    row,
                    decision="alias",
                    cluster_id=_cluster_id(row.region_key, root.clean_name, "alias"),
                    root=root,
                    reason_codes=["explicit_alias_hint", "matched_alias_root"],
                )
                alias_value = _alias_value(row, root)
                if alias_value:
                    aliases_by_root.setdefault(root.topic_id, []).append(alias_value)
            else:
                decisions[row.topic_id] = _decision_row(
                    row,
                    decision="pending_review",
                    cluster_id=_cluster_id(row.region_key, row.clean_name, "alias_pending"),
                    reason_codes=["explicit_alias_hint", "alias_root_missing"],
                )
            continue
        if explicit == "parallel_entity":
            root = _pick_parallel_root(row, prepared)
            decisions[row.topic_id] = _decision_row(
                row,
                decision="parallel_entity",
                cluster_id=_cluster_id(row.region_key, row.clean_name, "parallel_entity"),
                root=root,
                reason_codes=["explicit_parallel_hint"],
            )
            continue
        alias_root = _pick_alias_root(row, prepared)
        if alias_root:
            decisions[row.topic_id] = _decision_row(
                row,
                decision="alias",
                cluster_id=_cluster_id(row.region_key, alias_root.clean_name, "alias"),
                root=alias_root,
                reason_codes=["normalized_alias_variant", "matched_alias_root"],
            )
            alias_value = _alias_value(row, alias_root)
            if alias_value:
                aliases_by_root.setdefault(alias_root.topic_id, []).append(alias_value)
            continue
        if not hint:
            decisions[row.topic_id] = _decision_row(
                row,
                decision="standalone",
                cluster_id=_cluster_id(row.region_key, row.clean_name, "standalone"),
                reason_codes=["no_member_signal"],
            )
            continue

        parent = _pick_parent(row, hint, prepared)
        cluster_id = _cluster_id(row.region_key, hint.cluster_token, hint.role)
        if parent:
            decisions[row.topic_id] = _decision_row(
                row,
                decision="member",
                cluster_id=cluster_id,
                member_role=hint.role,
                ordinal=hint.ordinal,
                root=parent,
                reason_codes=[hint.reason_code or "matched_member_pattern", "matched_parent_entity"],
            )
            children_by_root.setdefault(parent.topic_id, []).append((row, hint))
            continue

        cluster_size = cluster_counts.get((row.region_key, hint.role, hint.cluster_token), 0)
        if hint.force_pending_without_parent or cluster_size >= 2:
            reasons = [hint.reason_code or "matched_member_pattern", "pending_without_parent"]
            if cluster_size >= 2:
                reasons.append("cluster_requires_review")
            decisions[row.topic_id] = _decision_row(
                row,
                decision="pending_review",
                cluster_id=cluster_id,
                member_role=hint.role,
                ordinal=hint.ordinal,
                reason_codes=reasons,
            )
            continue

        decisions[row.topic_id] = _decision_row(
            row,
            decision="standalone",
            cluster_id=_cluster_id(row.region_key, row.clean_name, "standalone"),
            reason_codes=[hint.reason_code or "matched_member_pattern", "insufficient_parent_evidence"],
        )

    candidates: list[dict[str, Any]] = []
    resolutions: list[dict[str, Any]] = []
    for row in prepared:
        decision = dict(decisions[row.topic_id])
        if decision["decision"] in {"standalone", "parallel_entity"}:
            members = children_by_root.get(row.topic_id) or []
            aliases = _dedupe(aliases_by_root.get(row.topic_id) or [])
            decision["memberTopicIds"] = [child.topic_id for child, _hint in members if child.topic_id]
            if members:
                decision.setdefault("reasonCodes", []).append("root_with_members")
            if aliases:
                decision["aliasNames"] = aliases
                decision.setdefault("reasonCodes", []).append("root_with_aliases")
            resolutions.append(_build_resolution_record(row, members, aliases=aliases))
        candidates.append(decision)

    candidates.sort(key=lambda item: (str(item.get("decision") or ""), str(item.get("canonicalName") or "")))
    pending = [row for row in candidates if str(row.get("decision") or "") == "pending_review"]
    return {"candidates": candidates, "pending": pending, "resolutions": resolutions}


def _prepare_row(row: dict[str, Any]) -> PreparedRow:
    topic_id = str(row.get("topic_id") or row.get("topicId") or "").strip()
    canonical_name = str(row.get("normalized_name") or row.get("canonicalName") or row.get("name") or "").strip()
    canonical_name = _canonicalize_name(canonical_name)
    prefecture = str(row.get("prefecture") or "").strip()
    district = str(row.get("district") or "").strip()
    province = str(row.get("province") or "").strip()
    source_type = str(row.get("source_type") or row.get("sourceType") or "").strip()
    source_id = str(row.get("source_id") or row.get("sourceId") or "").strip()
    if not source_type or not source_id:
        source = row.get("_source") or {}
        if isinstance(source, dict):
            source_type = source_type or str(source.get("type") or "").strip()
            source_id = source_id or str(source.get("id") or "").strip()
    return PreparedRow(
        row=row,
        canonical_name=canonical_name,
        clean_name=_cluster_key(canonical_name),
        topic_id=topic_id,
        entity_type=str(row.get("entity_type") or row.get("entityType") or "scenic_spot").strip() or "scenic_spot",
        province=province,
        prefecture=prefecture,
        district=district,
        region_key="|".join([province, prefecture, district]),
        authority_status=str(row.get("authority_status") or row.get("authorityStatus") or "pending_check").strip()
        or "pending_check",
        source_type=source_type,
        source_id=source_id,
    )


def _member_hint(row: PreparedRow) -> MemberHint | None:
    name = row.canonical_name
    direct = _DIRECT_NUMBERED_MEMBER_RE.match(name)
    if direct:
        base = _cluster_key(direct.group("base"))
        role = direct.group("role")
        parent_hints = [base]
        if "大熊猫" in base:
            parent_hints.append("大熊猫")
        return MemberHint(
            role=role,
            cluster_token=base,
            parent_hints=tuple(_dedupe(parent_hints)),
            ordinal=direct.group("ordinal"),
            force_pending_without_parent=True,
            reason_code="direct_numbered_member",
        )

    paren = _PAREN_NAME_RE.match(name)
    if paren:
        lemma = _canonicalize_name(paren.group("lemma"))
        inner = _canonicalize_name(paren.group("inner"))
        if inner.endswith("观景台"):
            role = "观景台"
            ordinal = ""
            numbered = re.match(r"^(?P<ordinal>[0-9一二三四五六七八九十百]+)号", inner)
            if numbered:
                ordinal = numbered.group("ordinal")
            parent_hints = [_cluster_key(_theme_token(lemma))]
            if "贡嘎" in lemma:
                parent_hints.append("贡嘎")
            return MemberHint(
                role=role,
                cluster_token=_cluster_key(_theme_token(lemma) or lemma),
                parent_hints=tuple(_dedupe([item for item in parent_hints if item])),
                ordinal=ordinal,
                force_pending_without_parent=True,
                reason_code="paren_viewpoint_member",
            )
        if inner == "旧址" and "大学" in lemma:
            org = _extract_university_org_token(lemma)
            return MemberHint(
                role="旧址",
                cluster_token=_cluster_key(org),
                parent_hints=tuple([_cluster_key(org)]),
                reason_code="campus_old_site_member",
            )

    if name.endswith("关楼"):
        base = _cluster_key(name[: -len("关楼")])
        return MemberHint(
            role="关楼",
            cluster_token=base,
            parent_hints=tuple([base]),
            force_pending_without_parent=True,
            reason_code="gate_tower_member",
        )

    if name.endswith(("公馆", "祖居", "旧居")):
        family = _family_token(name)
        if family:
            return MemberHint(
                role=name[-2:],
                cluster_token=family,
                parent_hints=tuple([family]),
                family_token=family,
                reason_code="estate_member",
            )

    university_old_site = _UNIVERSITY_OLD_SITE_RE.match(name)
    if university_old_site:
        org = _normalize_org_token(university_old_site.group("org"))
        return MemberHint(
            role="旧址",
            cluster_token=_cluster_key(org),
            parent_hints=tuple([_cluster_key(org)]),
            reason_code="university_old_site_member",
        )
    return None


def _explicit_semantic_decision(row: PreparedRow) -> str:
    explicit = str(
        row.row.get("semantic_decision_hint")
        or row.row.get("semanticDecisionHint")
        or ""
    ).strip()
    if explicit in {"standalone", "member", "alias", "parallel_entity", "reject", "pending_review"}:
        return explicit
    hints = {
        str(item).strip()
        for item in (
            row.row.get("cluster_hints")
            or row.row.get("clusterHints")
            or []
        )
        if str(item).strip()
    }
    if "alias_candidate" in hints or "alias" in hints:
        return "alias"
    if "parallel_entity" in hints or "parallel_candidate" in hints:
        return "parallel_entity"
    return ""


def _pick_alias_root(row: PreparedRow, prepared: list[PreparedRow]) -> PreparedRow | None:
    topic_id_hint = str(
        row.row.get("alias_of_topic_id")
        or row.row.get("aliasOfTopicId")
        or ""
    ).strip()
    if topic_id_hint:
        for candidate in prepared:
            if candidate.topic_id == topic_id_hint:
                return candidate
    name_hints = _dedupe(
        [
            str(row.row.get("alias_of_name") or row.row.get("aliasOfName") or "").strip(),
        ]
    )
    named_root = _pick_named_root(row, prepared, name_hints)
    if named_root:
        return named_root
    raw_name = _raw_name(row)
    if raw_name and raw_name != row.canonical_name:
        for candidate in prepared:
            if candidate.topic_id == row.topic_id or candidate.region_key != row.region_key:
                continue
            if candidate.clean_name != row.clean_name:
                continue
            if _member_hint(candidate):
                continue
            if _raw_name(candidate) == candidate.canonical_name:
                return candidate
    return None


def _pick_parallel_root(row: PreparedRow, prepared: list[PreparedRow]) -> PreparedRow | None:
    topic_id_hint = str(
        row.row.get("parallel_of_topic_id")
        or row.row.get("parallelOfTopicId")
        or ""
    ).strip()
    if topic_id_hint:
        for candidate in prepared:
            if candidate.topic_id == topic_id_hint:
                return candidate
    name_hints = _dedupe(
        [
            str(row.row.get("parallel_of_name") or row.row.get("parallelOfName") or "").strip(),
            str(row.row.get("parent_name_hint") or row.row.get("parentNameHint") or "").strip(),
        ]
    )
    return _pick_named_root(row, prepared, name_hints)


def _pick_named_root(row: PreparedRow, prepared: list[PreparedRow], name_hints: list[str]) -> PreparedRow | None:
    best: tuple[int, PreparedRow] | None = None
    normalized_hints = [_cluster_key(item) for item in name_hints if item]
    for candidate in prepared:
        if candidate.topic_id == row.topic_id or candidate.region_key != row.region_key:
            continue
        if _member_hint(candidate):
            continue
        score = 0
        for hint in normalized_hints:
            if not hint:
                continue
            if candidate.clean_name == hint:
                score += 12
            elif candidate.clean_name.startswith(hint) or hint in candidate.clean_name:
                score += 8
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, candidate)
    return best[1] if best else None


def _pick_parent(row: PreparedRow, hint: MemberHint, prepared: list[PreparedRow]) -> PreparedRow | None:
    best: tuple[int, PreparedRow] | None = None
    for candidate in prepared:
        if candidate.topic_id == row.topic_id:
            continue
        if candidate.region_key != row.region_key:
            continue
        if _member_hint(candidate):
            continue
        if not _role_allows_parent(hint.role, candidate):
            continue
        score = _parent_score(row, hint, candidate)
        if score < 9:
            continue
        if best is None or score > best[0]:
            best = (score, candidate)
    return best[1] if best else None


def _role_allows_parent(role: str, candidate: PreparedRow) -> bool:
    clean_name = candidate.clean_name
    if role in {"观景台", "别墅", "冰川观景台"}:
        return _has_suffix(clean_name, _POINT_PARENT_SUFFIXES) or candidate.entity_type != "viewpoint"
    if role == "关楼":
        return _has_suffix(clean_name, _PARENT_SUFFIXES)
    if role in {"公馆", "祖居", "旧居"}:
        return _has_suffix(clean_name, _ESTATE_PARENT_SUFFIXES)
    if role == "旧址":
        return _has_suffix(clean_name, ("旧址群", "遗址群"))
    return False


def _parent_score(row: PreparedRow, hint: MemberHint, candidate: PreparedRow) -> int:
    score = 0
    if row.prefecture and row.prefecture == candidate.prefecture:
        score += 2
    if row.district and row.district == candidate.district:
        score += 2
    candidate_base = _strip_parent_suffix(candidate.clean_name)
    for parent_hint in hint.parent_hints:
        if not parent_hint:
            continue
        if candidate.clean_name == parent_hint or candidate_base == parent_hint:
            score += 10
        elif parent_hint and parent_hint in candidate.clean_name:
            score += 7
        elif parent_hint and candidate.clean_name in parent_hint:
            score += 4
    if hint.family_token and candidate.clean_name.startswith(hint.family_token):
        score += 4
    if hint.role in {"公馆", "祖居", "旧居"} and candidate.clean_name.endswith("庄园"):
        score += 4
    if hint.role in {"观景台", "别墅", "冰川观景台"} and _has_suffix(candidate.clean_name, _POINT_PARENT_SUFFIXES):
        score += 3
    if hint.role == "关楼" and _has_suffix(candidate.clean_name, _PARENT_SUFFIXES):
        score += 3
    return score


def _build_resolution_record(
    root: PreparedRow,
    members: list[tuple[PreparedRow, MemberHint]],
    *,
    aliases: list[str],
) -> dict[str, Any]:
    catalog_topic_ids = [root.topic_id]
    member_rows = []
    for child, hint in sorted(
        members,
        key=lambda item: (_sort_ordinal(item[1].ordinal), item[0].canonical_name),
    ):
        if child.topic_id:
            catalog_topic_ids.append(child.topic_id)
        member_rows.append(
            {
                "nameCanonicalZhHans": child.canonical_name,
                "memberRole": hint.role,
                "ordinal": hint.ordinal,
                "catalogTopicIds": [child.topic_id] if child.topic_id else [],
                "evidenceRefs": [],
            }
        )
    return {
        "schemaVersion": "quwoquan_data.normalization.entity_resolution_record",
        "sourceRefs": [],
        "catalogTopicIds": [item for item in catalog_topic_ids if item],
        "mainEntity": {
            "canonicalZhHans": root.canonical_name,
            "entityType": root.entity_type,
            "summary": "catalog semantic materialization",
            "authorityStatus": root.authority_status,
            "authorityRefs": [],
            "aliases": [item for item in aliases if item and item != root.canonical_name],
            "admissionTrack": _catalog_admission_track(root),
            "conflictCheckStatus": _catalog_conflict_check_status(root),
            "undevelopedOrWildAccess": _catalog_undeveloped_or_wild_access(root),
        },
        "members": member_rows,
        "rejectedMembers": [],
        "rawPoiRefs": [],
        "sourceResultRefs": [],
        "selectedContentAssets": [],
        "rejectedAssets": [],
        "normalizationStatus": "catalog_semantic_compiled",
        "manualReviewRequired": False,
        "evidenceArticleUrls": _catalog_evidence_urls(root),
        "evidenceIndependenceNotes": _catalog_evidence_notes(root),
        "conflictCheckStatus": _catalog_conflict_check_status(root),
        "undevelopedOrWildAccess": _catalog_undeveloped_or_wild_access(root),
    }


def _decision_row(
    row: PreparedRow,
    *,
    decision: str,
    cluster_id: str,
    reason_codes: list[str],
    member_role: str = "",
    ordinal: str = "",
    root: PreparedRow | None = None,
) -> dict[str, Any]:
    payload = {
        "schemaVersion": SEMANTIC_CLUSTER_SCHEMA_VERSION,
        "topicId": row.topic_id,
        "canonicalName": row.canonical_name,
        "rawName": _raw_name(row),
        "normalizedName": str(row.row.get("normalized_name") or row.row.get("normalizedName") or row.canonical_name).strip(),
        "entityType": row.entity_type,
        "province": row.province,
        "prefecture": row.prefecture,
        "district": row.district,
        "decision": decision,
        "clusterId": cluster_id,
        "memberRole": member_role,
        "ordinal": ordinal,
        "rootTopicId": root.topic_id if root else "",
        "rootCanonicalName": root.canonical_name if root else "",
        "sourceType": row.source_type,
        "sourceId": row.source_id,
        "parentNameHint": str(row.row.get("parent_name_hint") or row.row.get("parentNameHint") or "").strip(),
        "admissionTrackHint": _catalog_admission_track_hint(row),
        "conflictCheckStatus": "pending" if decision == "pending_review" else _catalog_conflict_check_status(row),
        "reasonCodes": _dedupe(reason_codes),
    }
    return payload


def _should_reject(row: PreparedRow) -> bool:
    return row.clean_name in _GENERIC_REJECT_NAMES or not _CJK_RE.search(row.canonical_name)


def _raw_name(row: PreparedRow) -> str:
    return str(row.row.get("raw_name") or row.row.get("rawName") or row.canonical_name).strip()


def _alias_value(row: PreparedRow, root: PreparedRow) -> str:
    raw_name = _raw_name(row)
    if raw_name and raw_name != root.canonical_name:
        return raw_name
    if row.canonical_name != root.canonical_name:
        return row.canonical_name
    return ""


def _catalog_admission_track_hint(row: PreparedRow) -> str:
    explicit = str(
        row.row.get("admission_track_hint")
        or row.row.get("admissionTrackHint")
        or ""
    ).strip()
    if explicit:
        return explicit
    if len(_catalog_evidence_urls(row)) >= 2:
        return "post_evidence"
    return "authority"


def _catalog_admission_track(row: PreparedRow) -> str:
    hint = _catalog_admission_track_hint(row)
    if hint == "mixed":
        return "authority_plus_post"
    if hint in {"authority", "authority_plus_post", "post_evidence"}:
        return hint
    return "authority"


def _catalog_conflict_check_status(row: PreparedRow) -> str:
    explicit = str(
        row.row.get("conflict_check_status")
        or row.row.get("conflictCheckStatus")
        or ""
    ).strip()
    if explicit:
        return explicit
    if _catalog_admission_track(row) == "post_evidence":
        return "pass" if len(_catalog_evidence_urls(row)) >= 2 else "pending"
    return "pass"


def _catalog_evidence_urls(row: PreparedRow) -> list[str]:
    values = row.row.get("evidence_article_urls") or row.row.get("evidenceArticleUrls") or []
    return _dedupe([str(item).strip() for item in values if str(item).strip()])


def _catalog_evidence_notes(row: PreparedRow) -> list[str]:
    values = row.row.get("evidence_independence_notes") or row.row.get("evidenceIndependenceNotes") or []
    return _dedupe([str(item).strip() for item in values if str(item).strip()])


def _catalog_undeveloped_or_wild_access(row: PreparedRow) -> bool:
    value = row.row.get("undeveloped_or_wild_access")
    if value is None:
        value = row.row.get("undevelopedOrWildAccess")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _family_token(text: str) -> str:
    for char in text:
        if _CJK_RE.fullmatch(char):
            return char
    return ""


def _theme_token(text: str) -> str:
    head = text.split("之", 1)[0].strip()
    return head or text


def _cluster_key(name: str) -> str:
    text = _canonicalize_name(name)
    text = _SPACE_RE.sub("", text)
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"[()（）·•\-_/]", "", text)
    return text


def _canonicalize_name(name: str) -> str:
    text = _SPACE_RE.sub(" ", str(name or "").strip())
    if not text:
        return ""
    for suffix in _PARENT_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            base = text[: -len(suffix)]
            while len(base) >= 2 and base[-1] == base[-2]:
                base = base[:-1]
            return base + suffix
    return text


def _normalize_org_token(text: str) -> str:
    normalized = _canonicalize_name(text)
    for prefix in ("国立",):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
    return normalized


def _extract_university_org_token(text: str) -> str:
    normalized = _normalize_org_token(text)
    match = re.match(r"^(?P<org>[^()（）]+?大学)", normalized)
    if match:
        return _normalize_org_token(match.group("org"))
    return normalized


def _strip_parent_suffix(text: str) -> str:
    for suffix in _PARENT_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)]
    return text


def _has_suffix(text: str, suffixes: tuple[str, ...]) -> bool:
    return any(text.endswith(suffix) for suffix in suffixes)


def _cluster_id(region_key: str, token: str, role: str) -> str:
    raw = f"{region_key}|{token}|{role}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _sort_ordinal(value: str) -> tuple[int, str]:
    text = str(value or "").strip()
    if not text:
        return (9999, "")
    digits = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if text.isdigit():
        return (int(text), text)
    if text in digits:
        return (digits[text], text)
    return (9999, text)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
