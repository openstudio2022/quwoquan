"""Unified content source registry and prompt guidance."""
from __future__ import annotations

from typing import Any, Iterable, Mapping
import yaml

from core.paths import CONTROL_PLANE_CATALOGS_ROOT

CONTENT_SOURCE_REGISTRY_PATH = CONTROL_PLANE_CATALOGS_ROOT / "content_source_registry.yaml"
CONTENT_SOURCE_REGISTRY_SCHEMA = "quwoquan.content_source_registry"

VALID_SOURCE_TIERS = (
    "tier1_authoritative",
    "tier2_professional",
    "tier3_quality_ugc",
    "tier4_casual",
    "tier5_reject",
)
VALID_WORKS_AFFINITIES = ("work_strong", "work", "neutral", "moment", "reject")


def load_content_source_registry() -> dict[str, Any]:
    if not CONTENT_SOURCE_REGISTRY_PATH.is_file():
        raise FileNotFoundError(f"missing content source registry: {CONTENT_SOURCE_REGISTRY_PATH}")
    data = yaml.safe_load(CONTENT_SOURCE_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    if data.get("schema") != CONTENT_SOURCE_REGISTRY_SCHEMA:
        raise ValueError(f"{CONTENT_SOURCE_REGISTRY_PATH}: invalid schema")
    return data


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_string_set(value: Any) -> set[str]:
    return {
        str(item).strip().casefold()
        for item in _as_list(value)
        if str(item).strip()
    }


def _matches_policy_token(text: str, tokens: set[str]) -> bool:
    lowered = str(text or "").casefold()
    if not lowered:
        return False
    return any(token and token in lowered for token in tokens)


def _homepage_lane_policy(data: Mapping[str, Any]) -> Mapping[str, Any]:
    lane_policies = data.get("lanePolicies") if isinstance(data.get("lanePolicies"), dict) else {}
    policy = lane_policies.get("homepage")
    return policy if isinstance(policy, Mapping) else {}


def _homepage_primary_rows(data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        row
        for row in _as_list(_homepage_lane_policy(data).get("primarySources"))
        if isinstance(row, Mapping)
    ]


def homepage_primary_authority_rank(source_kind: str) -> int:
    from core.baike_source_contract import SOURCE_AUTHORITY_RANKS

    return SOURCE_AUTHORITY_RANKS.get(str(source_kind or "").strip(), 100)


def homepage_core_source_limit() -> int:
    value = _homepage_lane_policy(load_content_source_registry()).get("maxCoreSources")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("lanePolicies.homepage.maxCoreSources must be a positive integer")
    return value


def resolve_source_tier(source_class: str, *, data: Mapping[str, Any] | None = None) -> dict[str, str]:
    """按 sourceClass 解析来源专业度先验（baseTier + worksAffinity）；缺失走 default。

    单一真相源 = content_source_registry.yaml: sourceTierSignals。供 WorksClassifier 消费，
    禁止在判定代码里另维护第二套 sourceClass→tier 映射。
    """
    registry = data if data is not None else load_content_source_registry()
    signals = registry.get("sourceTierSignals") if isinstance(registry.get("sourceTierSignals"), dict) else {}
    by_class = signals.get("bySourceClass") if isinstance(signals.get("bySourceClass"), dict) else {}
    default = signals.get("default") if isinstance(signals.get("default"), dict) else {}
    row = by_class.get(str(source_class or "").strip())
    if not isinstance(row, dict):
        row = default if isinstance(default, dict) else {}
    base_tier = str(row.get("baseTier") or "tier4_casual")
    affinity = str(row.get("worksAffinity") or "neutral")
    return {"baseTier": base_tier, "worksAffinity": affinity}


def resolve_source_class(
    *,
    source_id: str = "",
    platform: str = "",
    data: Mapping[str, Any] | None = None,
) -> str:
    """把来源单元的 sourceId/platform 解析为 registry sourceClass（单一真相源）。

    优先 sourceId 精确匹配；回退 platform 精确匹配；再回退 platform 包含匹配
    （"携程攻略" 命中 platform="携程攻略"，"携程" 命中含"携程"的条目）。
    缺失返回 ""（由 resolve_source_tier 落 default → tier4_casual）。
    WorksClassifier 经此拿到来源专业度先验，禁止在判定代码里另维护第二套映射。
    """
    registry = data if data is not None else load_content_source_registry()
    by_id: dict[str, str] = {}
    by_platform: dict[str, str] = {}
    for _, row in _registry_sources(registry):
        cls = str(row.get("sourceClass") or "").strip()
        if not cls:
            continue
        sid = str(row.get("sourceId") or "").strip().lower()
        plat = str(row.get("platform") or "").strip().lower()
        if sid:
            by_id.setdefault(sid, cls)
        if plat:
            by_platform.setdefault(plat, cls)
    sid = str(source_id or "").strip().lower()
    if sid and sid in by_id:
        return by_id[sid]
    plat = str(platform or "").strip().lower()
    if plat and plat in by_platform:
        return by_platform[plat]
    if plat:
        for known, cls in by_platform.items():
            if known and (known in plat or plat in known):
                return cls
    return ""


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


def resolve_homepage_source_role(
    *,
    source_kind: str,
    url: str = "",
    extractor: str = "",
    policy_revision: str = "",
) -> str:
    """完整显式身份匹配三百科封闭集才是 homepage primary。"""
    from core.baike_source_contract import source_identity_matches_contract

    return "primary" if source_identity_matches_contract(
        source_kind=source_kind,
        url=url,
        extractor=extractor,
        policy_revision=policy_revision,
    ) else "other"


def homepage_source_can_seed_base_draft(
    source: Mapping[str, Any],
) -> bool:
    return (
        resolve_homepage_source_role(
            source_kind=str(source.get("sourceKind") or ""),
            url=str(source.get("finalUrl") or source.get("canonicalUrl") or source.get("url") or ""),
            extractor=str(source.get("extractor") or ""),
            policy_revision=str(source.get("policyRevision") or ""),
        )
        == "primary"
    )


def verify_content_source_registry() -> list[str]:
    try:
        data = load_content_source_registry()
    except Exception as exc:  # noqa: BLE001
        return [f"content source registry invalid: {exc}"]

    issues: list[str] = []
    if data.get("version") != 2:
        issues.append("content source registry version must be 2")
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
    seen_ids: set[str] = set()
    for scope, row in _registry_sources(data):
        source_id = str(row.get("sourceId") or "").strip()
        prefix = f"{scope}.{source_id or '<missing>'}"
        missing = sorted(
            field
            for field in required
            if row.get(field) in (None, "", [])
            and not (field == "lanes" and field in row)
        )
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
    homepage_policy = _homepage_lane_policy(data)
    if homepage_policy.get("homepageSourcePolicyRevision") != "encyclopedia-primary":
        issues.append("lanePolicies.homepage.homepageSourcePolicyRevision must be encyclopedia-primary")
    primary_rows = _homepage_primary_rows(data)
    source_kinds = [str(row.get("sourceKind") or "") for row in primary_rows]
    if source_kinds != ["wikipedia", "baidu_baike", "toutiao_baike"]:
        issues.append("lanePolicies.homepage.primarySources must be the ordered three-encyclopedia closed set")
    required_primary_fields = {
        "sourceKind",
        "sourceId",
        "platform",
        "authorityRank",
        "probeOrder",
        "hosts",
        "urlPatterns",
        "extractor",
        "sourceUseMode",
        "homepageTextAllowed",
        "sameSourceImageEvidenceAllowed",
    }
    for row in primary_rows:
        kind = str(row.get("sourceKind") or "<missing>")
        missing = sorted(field for field in required_primary_fields if row.get(field) in (None, "", []))
        if missing:
            issues.append(f"lanePolicies.homepage.primarySources.{kind}: missing {missing}")
        if row.get("extractor") == "generic_html":
            issues.append(
                f"lanePolicies.homepage.primarySources.{kind}: generic_html is forbidden"
            )
    signals = data.get("sourceTierSignals") if isinstance(data.get("sourceTierSignals"), dict) else {}
    if not signals:
        issues.append("sourceTierSignals: missing (作品判定来源专业度先验真相源)")
    else:
        default = signals.get("default") if isinstance(signals.get("default"), dict) else {}
        by_class = signals.get("bySourceClass") if isinstance(signals.get("bySourceClass"), dict) else {}
        if not default:
            issues.append("sourceTierSignals.default: missing 兜底 baseTier/worksAffinity")

        def _check_tier_row(name: str, row: Mapping[str, Any]) -> None:
            base_tier = str(row.get("baseTier") or "")
            affinity = str(row.get("worksAffinity") or "")
            if base_tier not in VALID_SOURCE_TIERS:
                issues.append(f"sourceTierSignals.{name}: invalid baseTier {base_tier!r}")
            if affinity not in VALID_WORKS_AFFINITIES:
                issues.append(f"sourceTierSignals.{name}: invalid worksAffinity {affinity!r}")

        if default:
            _check_tier_row("default", default)
        for cls, row in by_class.items():
            if isinstance(row, dict):
                _check_tier_row(f"bySourceClass.{cls}", row)
            else:
                issues.append(f"sourceTierSignals.bySourceClass.{cls}: must be a mapping")
        seen_classes = {str(row.get("sourceClass") or "").strip() for _, row in _registry_sources(data)}
        for cls in sorted(c for c in seen_classes if c):
            if cls not in by_class:
                issues.append(
                    f"sourceTierSignals.bySourceClass: missing explicit mapping for sourceClass {cls!r} (falls back to default)"
                )
    from core.video_source_admission import (
        verify_video_commercial_admission,
    )

    issues.extend(verify_video_commercial_admission(data))
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
        "schema": data.get("schema"),
        "version": data.get("version"),
        "vertical": vertical,
        "lanePolicies": data.get("lanePolicies") or {},
        "lanes": {},
    }
    for lane in ("homepage", "article", "image", "video"):
        rows = _lane_sources(data, lane, vertical=vertical)
        homepage_rows = {
            str(row.get("sourceId") or ""): row
            for row in _homepage_primary_rows(data)
        }
        guidance["lanes"][lane] = {
            "sources": [
                {
                    "sourceId": str(row.get("sourceId") or ""),
                    "sourceKind": (
                        str(homepage_rows.get(str(row.get("sourceId") or ""), {}).get("sourceKind") or "")
                        if lane == "homepage"
                        else ""
                    ),
                    "platform": str(row.get("platform") or ""),
                    "sourceClass": str(row.get("sourceClass") or ""),
                    "homepageAuthorityRole": (
                        ("primary" if str(row.get("sourceId") or "") in homepage_rows else "other")
                        if lane == "homepage"
                        else ""
                    ),
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
    image_asset_strategy: str = "open_license_publish",
) -> str:
    data = load_content_source_registry()
    policy = (data.get("lanePolicies") or {}).get(lane) or {}
    rows = _lane_sources(data, lane, vertical=vertical)
    policy_facts = [str(item) for item in _as_list(policy.get("promptFacts")) if str(item)]
    lines: list[str] = []
    if lane == "homepage":
        primary = [
            str(row.get("platform") or "").strip()
            for row in _homepage_primary_rows(data)
            if str(row.get("platform") or "").strip()
        ]
        lines.append(
            f"只做实体主页检索。正文主源闭集：{', '.join(primary)}；"
            f"最多保留 {int(policy.get('maxCoreSources') or 5)} 个核心来源，填写 primaryEvidenceRef。"
        )
        lines.append(
            "Wikidata、OSM、百科搜索仅可发现候选；维基导游、360、官网、政府、"
            "门户、媒体、OTA 不得进入主页 source plan/source unit/writing pack。"
        )
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
        strategy_text = {
            "open_license_publish": "当前 imageAssetStrategy=open_license_publish：只能把开放许可或逐资产可发布授权图片写入 collections。",
            "licensed_provider_publish": "当前 imageAssetStrategy=licensed_provider_publish：只能把授权图库/授权池中有凭证的图片写入 collections。",
            "ai_generated_original": "当前 imageAssetStrategy=ai_generated_original：可使用原创生成图，但必须写 generationModel、generationPromptHash、generatedAt、syntheticDisclosure 和完整权利字段。",
            "attribution_audited_publish": "当前 imageAssetStrategy=attribution_audited_publish：每张图片必须通过标题、图注或描述的主题匹配，写入来源地址与权利审计结果；缺少商业许可只标为 unverified，不替代或静默丢弃匹配素材。",
            "reference_only_no_image_release": "当前 imageAssetStrategy=reference_only_no_image_release：只能做发现/参考验证，不得把未授权图片写成可发布 collections。",
        }.get(
            image_asset_strategy,
            f"当前 imageAssetStrategy={image_asset_strategy}：必须遵守任务配置和逐资产权利门。",
        )
        lines.append(
            "只做图片作品检索。广泛检索通用视觉平台、摄影社区、图库、官方图库和垂类图库。"
        )
        lines.append(strategy_text)
        lines.append(
            f"开放或可发布候选优先看：{', '.join(publishable[:12])}；"
            f"授权候选看：{', '.join(licensed[:16])}；"
            f"发现/参考源包括：{', '.join(discovery[:16])}。"
        )
        if image_asset_strategy == "attribution_audited_publish":
            lines.append(
                f"至少形成 {int(per_target_image_works or 1)} 个图片作品容量；"
                "进入 collections 前必须验证标题、图注或描述与主题匹配，并保留来源页、原始地址、作者或署名、权利审计状态及审计问题。"
            )
        else:
            lines.append(
                f"至少形成 {int(per_target_image_works or 1)} 个图片作品容量；"
                "Pinterest、小红书、微博、抖音、B站等可做发现；其中 Pinterest 只有在 "
                "attribution_no_watermark 证据链完整时才可进入 collections，其他来源未形成逐图授权链不得进入 collections。"
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
