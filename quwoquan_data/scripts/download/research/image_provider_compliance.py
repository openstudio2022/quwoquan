"""图库来源合规分级 + 受限如实标注（单一真相源 = content_source_registry.yaml）。

P4 诚实约束：图虫 / Pinterest 等"专业图库 / 视觉发现平台"绝大多数受版权保护，平台 ToS /
robots / 登录墙禁止抓取他人图片后再发布。诚实做法**不是**写一个绕过 ToS / 登录墙的抓取器，
而是：

1. 以 registry 的 ``rightsPolicy`` / ``fetchMode`` / ``defaultRole`` 为唯一真相源，把每个
   图库来源分级为「开放许可可发布 / 逐资产授权后可发布 / 逐图创作者授权后可发布 /
   商业授权后可发布 / 仅参考」。
2. 对受限来源产出**如实**的受限记录（受限原因 + ``bypassAttempted=false`` + 需要的授权凭证），
   并给出**替代路径**（回到 Wikimedia Commons / Openverse 等开放许可图池）。
3. 授权完整性硬门（``source_quality._collection_gate`` / ``vertical.validate_image_rights``）
   仍是最终发布闸：缺逐图 ``license/credit/termsUrl/authorizationProof/usageScope`` 一律不进
   发布面；页/集合级授权必须传播到每一张图。

本模块只做确定性分级与如实标注，**不抓取、不绕过、不伪造授权**。优先官方 API / 合规路径的
落地形态：开放许可来源走 API 真实抓取（Commons/Openverse），受限来源如实标注受限并指向替代
路径，等待人工授权凭证后才可发布。
"""
from __future__ import annotations

from typing import Any, Mapping

from _common.content_source_registry import (
    _registry_sources,
    load_content_source_registry,
)

# rightsPolicy -> 访问模式（唯一真相源 = registry.allowedValues.rightsPolicies）。
# 禁止在判定/抓取代码里另维护第二套"哪些图库可发布"的映射。
RIGHTS_POLICY_ACCESS_MODE: dict[str, str] = {
    "open_license_required": "open_license_publishable",
    "asset_level_required": "asset_level_conditional",
    "creator_authorization_required": "restricted_creator_authorization",
    "commercial_license_required": "restricted_commercial_license",
    "reference_only": "restricted_reference_only",
    "official_terms_required": "official_terms_conditional",
    "factual_reference_only": "factual_reference_only",
}

# 受限访问模式（不可直接发布，必须先拿到对应授权凭证或回退替代路径）。
_RESTRICTED_ACCESS_MODES = frozenset(
    {
        "restricted_creator_authorization",
        "restricted_commercial_license",
        "restricted_reference_only",
    }
)

# 可发布访问模式（开放许可直接可发布；逐资产授权在通过逐图硬门后可发布）。
_PUBLISHABLE_ACCESS_MODES = frozenset(
    {
        "open_license_publishable",
        "asset_level_conditional",
    }
)

_RESTRICTION_KIND_BY_MODE: dict[str, str] = {
    "restricted_creator_authorization": "creator_authorization_required",
    "restricted_commercial_license": "commercial_license_required",
    "restricted_reference_only": "platform_reference_only",
}

_RESTRICTION_REASON_BY_MODE: dict[str, str] = {
    "restricted_reference_only": (
        "视觉发现平台（如 Pinterest）ToS 仅允许构图参考，不授予转载/再发布许可；robots 与登录墙"
        "禁止抓取他人图片用于发布。仅作发现与构图参考，不抓取、不绕过 ToS/登录墙。"
    ),
    "restricted_creator_authorization": (
        "摄影社区图片（如图虫、Flickr、500px、Behance）版权归创作者/平台，发布前必须逐图取得"
        "创作者授权并保留署名与作品落地页；无授权凭证不进发布面。不抓取受版权图片绕过授权。"
    ),
    "restricted_commercial_license": (
        "商业图库（如 Getty、Shutterstock、VCG）必须先购买或取得授权凭证；无凭证不进发布面。"
    ),
}

# 每类受限来源在进入发布面前必须补齐的授权凭证字段（逐图）。
_REQUIRED_PROOF_BY_MODE: dict[str, tuple[str, ...]] = {
    "restricted_reference_only": (
        "traced_original_licensable_source",
        "license",
        "credit",
        "termsUrl",
        "authorizationProof",
        "usageScope",
    ),
    "restricted_creator_authorization": (
        "creator_authorization",
        "license",
        "credit",
        "termsUrl",
        "authorizationProof",
        "usageScope",
    ),
    "restricted_commercial_license": (
        "purchased_commercial_license",
        "license",
        "credit",
        "termsUrl",
        "authorizationProof",
        "usageScope",
    ),
}


def _image_provider_rows(data: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    registry = data if data is not None else load_content_source_registry()
    rows: list[dict[str, Any]] = []
    for _scope, row in _registry_sources(registry):
        lanes = row.get("lanes")
        if not isinstance(lanes, list):
            continue
        if "image" in {str(item).strip() for item in lanes}:
            rows.append(dict(row))
    return rows


def access_mode_for_rights_policy(rights_policy: str) -> str:
    """rightsPolicy -> 访问模式（缺失/未知按最保守的逐图授权处理）。"""
    return RIGHTS_POLICY_ACCESS_MODE.get(
        str(rights_policy or "").strip(),
        "restricted_creator_authorization",
    )


def open_license_publishable_providers(data: Mapping[str, Any] | None = None) -> list[str]:
    """开放许可可发布图库（替代路径主体：Wikimedia Commons / Openverse）。"""
    ids: list[str] = []
    for row in _image_provider_rows(data):
        if access_mode_for_rights_policy(str(row.get("rightsPolicy") or "")) == "open_license_publishable":
            sid = str(row.get("sourceId") or "").strip()
            if sid:
                ids.append(sid)
    return ids


def _alternative_path(data: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "strategy": "open_license_pools",
        "providers": open_license_publishable_providers(data),
        "note": (
            "回到 Wikimedia Commons / Openverse 等开放许可图池经官方 API 真实抓取可发布图，"
            "逐图保留 license/credit/sourceUrl/termsUrl/authorizationProof/usageScope。"
        ),
    }


def classify_image_provider(
    *,
    source_id: str = "",
    platform: str = "",
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """把一个图库来源（按 sourceId 或 platform）解析为访问模式与可发布性。

    单一真相源 = content_source_registry.yaml: common.image / verticals.*.image 行的
    rightsPolicy / fetchMode / defaultRole。缺失行按最保守的逐图创作者授权处理。
    """
    registry = data if data is not None else load_content_source_registry()
    rows = _image_provider_rows(registry)
    sid = str(source_id or "").strip().lower()
    plat = str(platform or "").strip().lower()
    matched: dict[str, Any] | None = None
    for row in rows:
        row_sid = str(row.get("sourceId") or "").strip().lower()
        row_plat = str(row.get("platform") or "").strip().lower()
        if sid and row_sid == sid:
            matched = row
            break
        if plat and row_plat == plat:
            matched = row
            break
    if matched is None and plat:
        for row in rows:
            row_plat = str(row.get("platform") or "").strip().lower()
            if row_plat and (row_plat in plat or plat in row_plat):
                matched = row
                break
    rights_policy = str((matched or {}).get("rightsPolicy") or "").strip()
    access_mode = access_mode_for_rights_policy(rights_policy)
    return {
        "sourceId": str((matched or {}).get("sourceId") or source_id or "").strip(),
        "platform": str((matched or {}).get("platform") or platform or "").strip(),
        "sourceClass": str((matched or {}).get("sourceClass") or "").strip(),
        "rightsPolicy": rights_policy,
        "fetchMode": str((matched or {}).get("fetchMode") or "").strip(),
        "defaultRole": str((matched or {}).get("defaultRole") or "").strip(),
        "accessMode": access_mode,
        "restricted": access_mode in _RESTRICTED_ACCESS_MODES,
        "publishable": access_mode in _PUBLISHABLE_ACCESS_MODES,
        "registered": matched is not None,
    }


def image_provider_restriction(
    *,
    source_id: str = "",
    platform: str = "",
    query: str = "",
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """受限图库的**如实**受限记录；非受限来源返回 None。

    受限记录显式声明 ``bypassAttempted=false``，并给出回到开放许可图池的替代路径，绝不假装
    绕过 ToS / robots / 登录墙。
    """
    registry = data if data is not None else load_content_source_registry()
    info = classify_image_provider(source_id=source_id, platform=platform, data=registry)
    access_mode = str(info["accessMode"])
    if access_mode not in _RESTRICTED_ACCESS_MODES:
        return None
    record = {
        "sourceId": info["sourceId"],
        "platform": info["platform"],
        "sourceClass": info["sourceClass"],
        "rightsPolicy": info["rightsPolicy"],
        "fetchMode": info["fetchMode"],
        "accessMode": access_mode,
        "restricted": True,
        "restrictionKind": _RESTRICTION_KIND_BY_MODE.get(access_mode, "authorization_required"),
        "reason": _RESTRICTION_REASON_BY_MODE.get(access_mode, "需授权后才可发布"),
        "bypassAttempted": False,
        "requiresProof": list(_REQUIRED_PROOF_BY_MODE.get(access_mode, ())),
        "alternativePath": _alternative_path(registry),
    }
    if str(query or "").strip():
        record["query"] = str(query).strip()
    return record


def restricted_image_providers(
    data: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """registry 内所有受限图库的如实受限记录（图虫/Pinterest/商业图库/摄影社区）。"""
    registry = data if data is not None else load_content_source_registry()
    records: list[dict[str, Any]] = []
    for row in _image_provider_rows(registry):
        sid = str(row.get("sourceId") or "").strip()
        if not sid:
            continue
        record = image_provider_restriction(source_id=sid, data=registry)
        if record is not None:
            records.append(record)
    return records


def professional_library_compliance_summary(
    provider_ids: list[str] | tuple[str, ...] | None = None,
    *,
    query: str = "",
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """图库合规审计摘要（写入 research report，使"受限+替代路径"决策可审计）。

    无 ``provider_ids`` 时审计 registry 内全部图库来源；给定时只审计指定来源。
    """
    registry = data if data is not None else load_content_source_registry()
    if provider_ids is None:
        rows = _image_provider_rows(registry)
        target_ids = [str(row.get("sourceId") or "").strip() for row in rows]
    else:
        target_ids = [str(pid).strip() for pid in provider_ids]
    restricted: list[dict[str, Any]] = []
    publishable: list[str] = []
    for sid in target_ids:
        if not sid:
            continue
        info = classify_image_provider(source_id=sid, data=registry)
        if info["restricted"]:
            record = image_provider_restriction(source_id=sid, query=query, data=registry)
            if record is not None:
                restricted.append(record)
        elif info["publishable"]:
            publishable.append(sid)
    return {
        "policy": "registry_rights_policy_single_source",
        "bypassAttempted": False,
        "publishableProviders": publishable,
        "restrictedProviders": restricted,
        "alternativePath": _alternative_path(registry),
        "note": (
            "图库可发布性以 content_source_registry.yaml rightsPolicy 为唯一真相源；受限来源"
            "如实标注，不抓取/不绕过 ToS/登录墙，发布前必须逐图补齐授权凭证或回退开放许可图池。"
        ),
    }


__all__ = [
    "RIGHTS_POLICY_ACCESS_MODE",
    "access_mode_for_rights_policy",
    "classify_image_provider",
    "image_provider_restriction",
    "open_license_publishable_providers",
    "professional_library_compliance_summary",
    "restricted_image_providers",
]
