"""Unified content source registry and prompt guidance."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

CONTENT_SOURCE_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2]
    / "templates"
    / "_registry"
    / "catalogs"
    / "content_source_registry.yaml"
)
CONTENT_SOURCE_REGISTRY_SCHEMA = "quwoquan.content_source_registry.v1"


def load_content_source_registry() -> dict[str, Any]:
    if not CONTENT_SOURCE_REGISTRY_PATH.is_file():
        raise FileNotFoundError(f"missing content source registry: {CONTENT_SOURCE_REGISTRY_PATH}")
    data = yaml.safe_load(CONTENT_SOURCE_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    if data.get("schemaVersion") != CONTENT_SOURCE_REGISTRY_SCHEMA:
        raise ValueError(f"{CONTENT_SOURCE_REGISTRY_PATH}: invalid schemaVersion")
    return data


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _registry_sources(data: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    common = data.get("common") if isinstance(data.get("common"), dict) else {}
    for bucket, items in common.items():
        for item in _as_list(items):
            if isinstance(item, dict):
                rows.append((f"common.{bucket}", item))
    verticals = data.get("verticals") if isinstance(data.get("verticals"), dict) else {}
    for vertical, lanes in verticals.items():
        if not isinstance(lanes, dict):
            continue
        for lane, items in lanes.items():
            for item in _as_list(items):
                if isinstance(item, dict):
                    rows.append((f"verticals.{vertical}.{lane}", item))
    return rows


def verify_content_source_registry() -> list[str]:
    try:
        data = load_content_source_registry()
    except Exception as exc:  # noqa: BLE001
        return [f"content source registry invalid: {exc}"]

    allowed = data.get("allowedValues") if isinstance(data.get("allowedValues"), dict) else {}
    allowed_lanes = {str(item) for item in _as_list(allowed.get("lanes"))}
    allowed_roles = {str(item) for item in _as_list(allowed.get("defaultRoles"))}
    allowed_fetch_modes = {str(item) for item in _as_list(allowed.get("fetchModes"))}
    allowed_rights = {str(item) for item in _as_list(allowed.get("rightsPolicies"))}
    required = {
        "sourceId",
        "platform",
        "sourceClass",
        "lanes",
        "defaultRole",
        "fetchMode",
        "rightsPolicy",
        "rateLimit",
        "promptFacts",
    }
    issues: list[str] = []
    seen_ids: set[str] = set()
    for scope, row in _registry_sources(data):
        source_id = str(row.get("sourceId") or "").strip()
        prefix = f"{scope}.{source_id or '<missing>'}"
        missing = sorted(field for field in required if row.get(field) in (None, "", []))
        if missing:
            issues.append(f"{prefix}: missing required fields {missing}")
        if source_id:
            if source_id in seen_ids:
                issues.append(f"{prefix}: duplicate sourceId {source_id}")
            seen_ids.add(source_id)
        lanes = {str(item).strip() for item in _as_list(row.get("lanes")) if str(item).strip()}
        unknown_lanes = sorted(lanes - allowed_lanes)
        if unknown_lanes:
            issues.append(f"{prefix}: unknown lanes {unknown_lanes}")
        role = str(row.get("defaultRole") or "").strip()
        if role and role not in allowed_roles:
            issues.append(f"{prefix}: unknown defaultRole {role}")
        fetch_mode = str(row.get("fetchMode") or "").strip()
        if fetch_mode and fetch_mode not in allowed_fetch_modes:
            issues.append(f"{prefix}: unknown fetchMode {fetch_mode}")
        rights = str(row.get("rightsPolicy") or "").strip()
        if rights and rights not in allowed_rights:
            issues.append(f"{prefix}: unknown rightsPolicy {rights}")
        prompt_facts = row.get("promptFacts")
        if not isinstance(prompt_facts, list) or not all(str(item).strip() for item in prompt_facts):
            issues.append(f"{prefix}: promptFacts must be a non-empty string list")

    lane_policies = data.get("lanePolicies") if isinstance(data.get("lanePolicies"), dict) else {}
    for lane in ("homepage", "article", "image", "video"):
        if lane not in lane_policies:
            issues.append(f"lanePolicies.{lane}: missing")
    return issues


def _lane_sources(
    data: Mapping[str, Any],
    lane: str,
    *,
    vertical: str = "",
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for scope, row in _registry_sources(data):
        lanes = [str(item).strip() for item in _as_list(row.get("lanes")) if str(item).strip()]
        if lane not in lanes:
            continue
        if scope.startswith("verticals.") and vertical and not scope.startswith(f"verticals.{vertical}."):
            continue
        sources.append({**row, "scope": scope})
    return sources


def _names(rows: Iterable[Mapping[str, Any]], *, role: str | None = None) -> list[str]:
    out: list[str] = []
    for row in rows:
        if role is not None and str(row.get("defaultRole") or "") != role:
            continue
        name = str(row.get("platform") or row.get("sourceId") or "").strip()
        if name and name not in out:
            out.append(name)
    return out


def build_content_source_guidance(vertical: str = "travel") -> dict[str, Any]:
    data = load_content_source_registry()
    guidance: dict[str, Any] = {
        "schemaVersion": data.get("schemaVersion"),
        "version": data.get("version"),
        "vertical": vertical,
        "lanePolicies": data.get("lanePolicies") or {},
        "lanes": {},
    }
    for lane in ("homepage", "article", "image", "video"):
        rows = _lane_sources(data, lane, vertical=vertical)
        guidance["lanes"][lane] = {
            "sources": [
                {
                    "sourceId": str(row.get("sourceId") or ""),
                    "platform": str(row.get("platform") or ""),
                    "sourceClass": str(row.get("sourceClass") or ""),
                    "defaultRole": str(row.get("defaultRole") or ""),
                    "fetchMode": str(row.get("fetchMode") or ""),
                    "rightsPolicy": str(row.get("rightsPolicy") or ""),
                    "rateLimit": str(row.get("rateLimit") or ""),
                    "promptFacts": [str(item) for item in _as_list(row.get("promptFacts"))],
                    "scope": str(row.get("scope") or ""),
                }
                for row in rows
            ],
        }
    return guidance


def render_lane_source_prompt(
    lane: str,
    *,
    vertical: str = "travel",
    per_target_articles: int = 1,
    per_target_image_works: int = 1,
    article_intents: list[str] | None = None,
) -> str:
    data = load_content_source_registry()
    policy = (data.get("lanePolicies") or {}).get(lane) or {}
    rows = _lane_sources(data, lane, vertical=vertical)
    policy_facts = [str(item) for item in _as_list(policy.get("promptFacts")) if str(item)]
    lines: list[str] = []
    if lane == "homepage":
        primary = [
            str(row.get("platform") or "")
            for row in rows
            if str(row.get("sourceClass") or "") in set(policy.get("primarySourceClasses") or [])
        ]
        support = [
            str(row.get("platform") or "")
            for row in rows
            if str(row.get("sourceClass") or "") in set(policy.get("supportingOnlySourceClasses") or [])
        ]
        lines.append(
            f"只做实体主页检索。核心主源从配置中的通用权威源选择：{', '.join(primary[:12])}；"
            f"最多保留 {int(policy.get('maxCoreSources') or 5)} 个核心来源，填写 primaryEvidenceRef。"
        )
        if support:
            lines.append(f"以下来源只能补事实或交叉验证，不能作为主页主源：{', '.join(support[:8])}。")
    elif lane == "article":
        article_sources = _names(rows)
        intents = article_intents or ["planning_consultation", "decision_experience"]
        signals = ", ".join(str(item) for item in _as_list(policy.get("rankingSignals")))
        lines.append(
            "只做文章检索。配置中的文章型来源同等进入候选池："
            f"{', '.join(article_sources[:24])}。"
        )
        lines.append(
            f"至少 {max(4, int(per_target_articles or 1))} 个可抓取底稿候选；"
            f"为 {int(per_target_articles or 1)} 篇文章准备互不复用的主证据，主线={intents[:int(per_target_articles or 1)]}。"
            f"排序尺度只看 {signals}，不得因 UGC/垂类专业/平台文章类别天然升降级。"
        )
    elif lane == "image":
        publishable = _names(rows, role="publish_candidate")
        licensed = _names(rows, role="licensed_candidate")
        discovery = _names(rows, role="discovery_only") + _names(rows, role="reference_only")
        lines.append(
            "只做图片作品检索。广泛检索通用视觉平台、摄影社区、图库、官方图库和垂类图库。"
        )
        lines.append(
            f"开放或可发布候选优先看：{', '.join(publishable[:12])}；"
            f"授权候选看：{', '.join(licensed[:16])}；"
            f"发现/参考源包括：{', '.join(discovery[:16])}。"
        )
        lines.append(
            f"至少形成 {int(per_target_image_works or 1)} 个图片作品容量；"
            "Pinterest、小红书、微博、抖音、B站等可做发现，但未形成逐图授权链不得进入 collections。"
        )
    elif lane == "video":
        lines.append(
            "只做视频素材/参考检索。通用视频平台、素材视频库、官方账号和垂类视频源都可进入发现。"
        )
        lines.append(
            "视频发布候选必须逐条判断账号身份、标题/描述/字幕、音乐版权、画面水印、转载痕迹和商用许可。"
        )
    for fact in policy_facts:
        lines.append(fact)
    return "".join(lines)
