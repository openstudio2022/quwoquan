"""homepage 底稿来源语义判别（homepage_source_judge）契约与确定性预筛。

三段式落地（与数据工程 CLI-first 范式一致）：

1. **CLI prepare（本模块 + build prepare）**：确定性预筛只拦截「硬证据」页——
   标题精确命中实体（auto_primary）、门户首页/父级行政区替代页（auto_reject）；
   灰区写 ``source.judge.request.json``（结构化输入 + 预筛证据）等待模型判别。
2. **Agent semantic**：创作 agent 按 ``prompts/{system,task}/homepage_source_judge.*``
   对灰区来源做内容格式与语义判断，写回结构化 ``source.judge.json``。
3. **CLI validate + gate（本模块 + homepage_base_draft_readiness）**：verdict 经
   schema 校验后消费；灰区无 verdict 一律 fail-closed 阻断，禁止绕过判别直接采纳。

判别类型与结构化返回字段与实体主页创作 prompt 同一口径（entityMatch/
sourcePageType/recommendedAction），供 ``failure.json`` 失败协议复用。
"""
from __future__ import annotations

import json
import re
import urllib.parse
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.localization import fold_to_simplified

SOURCE_JUDGE_SCHEMA_VERSION = "quwoquan_data.homepage_source_judge/1"
SOURCE_JUDGE_REQUEST_FILE = "source.judge.request.json"
SOURCE_JUDGE_VERDICT_FILE = "source.judge.json"

# 页面类型闭集（内容格式 + 语义双维度）。
SOURCE_PAGE_TYPES = frozenset(
    {
        "entity_homepage",          # 目标实体本身的介绍页（可作 primary 底稿）
        "entity_detail_supporting", # 提到实体但非完整主页
        "portal_home",              # 门户/站点首页
        "listing",                  # 列表/搜索/栏目/聚合页
        "admin_notice",             # 政府公文/公告/政策/新闻列表
        "parent_region_overview",   # 上级行政区/更大范围概况页
        "other_entity",             # 同区域其它实体页
        "insufficient_content",     # 正文不足无法判断
    }
)
ENTITY_MATCH_VERDICTS = frozenset({"exact", "alias", "partial", "mismatch", "uncertain"})
RECOMMENDED_ACTIONS = frozenset({"primary", "supporting_only", "reject", "needs_human_review"})

PRESCREEN_AUTO_PRIMARY = "auto_primary"
PRESCREEN_AUTO_REJECT = "auto_reject"
PRESCREEN_NEEDS_MODEL = "needs_model_judgment"

# primary 采纳最低置信度（与 plan 冻结口径一致）。
PRIMARY_MIN_CONFIDENCE = 0.75

# 父级行政区后缀：标题以此结尾且与实体无共同前缀 → 确定性判为替代页。
# 镇/乡/街道不入列（实体本身常是镇级对象，交给模型判别）。
_ADMIN_REGION_SUFFIXES = ("自治州", "自治县", "地区", "省", "市", "县", "区", "盟", "旗")
# 政府门户站点标题特征。
_PORTAL_TITLE_MARKERS = ("人民政府", "政府门户", "门户网站", "政务服务", "政府网")
# 门户/栏目页导航密度信号（headText 命中 >=4 个视为强门户信号）。
_PORTAL_NAV_MARKERS = (
    "首页",
    "政务公开",
    "信息公开",
    "办事服务",
    "互动交流",
    "走进",
    "新闻中心",
    "通知公告",
    "政策文件",
    "专题专栏",
    "更多>",
    "更多 >",
)
_DISAMBIG_SUFFIX_RE = re.compile(r"[\(（][^)）]{1,24}[\)）]\s*$")
_ASCII_ID_RE = re.compile(r"^[a-z0-9_\-]+$")
_WIKI_HOST_RE = re.compile(r"(?:wikipedia|wikivoyage|wiki)", re.IGNORECASE)
# 站点标题后缀（`秀山岛 - 维基百科，自由的百科全书` / `xx_百度百科` / `xx 维基百科`），
# 比较前剥离；分隔符可为连字符/下划线/竖线/间隔号或纯空白。
_SITE_TITLE_SUFFIX_RE = re.compile(
    r"\s*(?:[-—–_|·]\s*)?(?:Wikipedia|Wikivoyage|维基百科.*|维基导游.*|百度百科.*|搜狗百科.*|快懂百科.*)\s*$",
    re.IGNORECASE,
)


def normalize_page_title(value: str) -> str:
    """标题归一：繁→简、全半角括号统一、去空白；供实体名/页面标题等值比较。"""
    text = fold_to_simplified(str(value or ""))
    text = text.replace("（", "(").replace("）", ")").replace("_", " ")
    return re.sub(r"\s+", "", text).strip()


def _strip_disambig_suffix(title: str) -> str:
    return _DISAMBIG_SUFFIX_RE.sub("", str(title or "")).strip()


def _title_variants(value: str) -> set[str]:
    raw = str(value or "")
    out: set[str] = set()
    for candidate in {raw, _SITE_TITLE_SUFFIX_RE.sub("", raw)}:
        normalized = normalize_page_title(candidate)
        if normalized:
            out.add(normalized)
        stripped = normalize_page_title(_strip_disambig_suffix(candidate))
        if stripped:
            out.add(stripped)
    return out


def _url_page_slug(url: str) -> str:
    """URL 末段解码标题（仅 wiki 类 host 可信；其它站点路径不代表页面标题）。"""
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
    except ValueError:
        return ""
    if not _WIKI_HOST_RE.search(parsed.hostname or ""):
        return ""
    segment = (parsed.path or "").rstrip("/").rsplit("/", 1)[-1]
    return urllib.parse.unquote(segment).strip()


def _url_is_site_root(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
    except ValueError:
        return False
    if not parsed.hostname:
        # 无 URL（离线 fixture）≠ 站点根：不能据此判门户。
        return False
    path = (parsed.path or "").strip()
    return path in ("", "/", "/index.html", "/index.htm") and not parsed.query


def collect_title_evidence(
    meta: Mapping[str, Any] | None,
    *,
    unit_dir: Path | None = None,
) -> list[str]:
    """收集可信的「页面标题」证据：URL wiki slug、layout 解析标题、meta.title。

    meta.title 常被 sourceId 污染（如 ``home_wikipedia_daishan``），纯 ASCII id
    形态一律不作标题证据。
    """
    titles: list[str] = []
    meta = meta or {}
    resolved_title = str(meta.get("resolvedTitle") or "").strip()
    if resolved_title:
        titles.append(resolved_title)
    else:
        slug = _url_page_slug(str(meta.get("url") or ""))
        if slug:
            titles.append(slug)
    if unit_dir is not None:
        try:
            from core.source_layout import read_source_layout

            layout = read_source_layout(Path(unit_dir))
        except Exception:  # noqa: BLE001
            layout = None
        layout_title = str((layout or {}).get("title") or "").strip()
        if layout_title:
            titles.append(layout_title)
    meta_title = str(meta.get("title") or "").strip()
    if meta_title and not _ASCII_ID_RE.match(meta_title):
        titles.append(meta_title)
    return [t for t in dict.fromkeys(titles) if t]


def _shares_name_prefix(entity_norm: str, title_norm: str, *, min_chars: int = 2) -> bool:
    head_e = _strip_disambig_suffix(entity_norm)[:min_chars]
    head_t = _strip_disambig_suffix(title_norm)[:min_chars]
    return bool(head_e) and head_e == head_t


def _is_encyclopedia_source(meta: Mapping[str, Any] | None) -> bool:
    meta = meta or {}
    blob = " ".join(
        str(meta.get(key) or "") for key in ("sourceKind", "category", "platform")
    ).casefold()
    return "encyclopedia" in blob or "百科" in blob or "wiki" in blob


def _title_is_parent_admin_region(entity_name: str, title: str) -> bool:
    """标题是父级行政区替代页的硬证据：行政区后缀 + 与实体名无共同前缀。"""
    entity_norm = normalize_page_title(entity_name)
    title_norm = normalize_page_title(title)
    if not title_norm or title_norm == entity_norm:
        return False
    if not title_norm.endswith(_ADMIN_REGION_SUFFIXES):
        return False
    if entity_norm.endswith(_ADMIN_REGION_SUFFIXES):
        return False
    return not _shares_name_prefix(entity_norm, title_norm)


def deterministic_prescreen(
    *,
    entity_name: str,
    aliases: Sequence[str] = (),
    meta: Mapping[str, Any] | None = None,
    head_text: str = "",
    unit_dir: Path | None = None,
) -> dict[str, Any]:
    """确定性预筛：只裁决硬证据页，灰区一律交模型判别（不写死门户规则）。

    - 标题证据精确命中实体名/registry 别名 → ``auto_primary``。
    - 站点根 URL（官网/政务门户首页）、政府门户标题、父级行政区标题、
      标题完全错配 + 强导航密度 → ``auto_reject``。
    - 其余 → ``needs_model_judgment``（fail-closed，等待 source.judge.json）。
    """
    meta = meta or {}
    entity_variants = _title_variants(entity_name)
    alias_variants: set[str] = set()
    for alias in aliases or ():
        alias_variants |= _title_variants(str(alias))
    titles = collect_title_evidence(meta, unit_dir=unit_dir)
    reasons: list[str] = []

    resolved_title = str(meta.get("resolvedTitle") or "").strip()
    if resolved_title:
        resolved_variants = _title_variants(resolved_title)
        if not (resolved_variants & (entity_variants | alias_variants)):
            redirect_chain = [
                str(item) for item in (meta.get("redirectChain") or []) if str(item).strip()
            ]
            return {
                "decision": PRESCREEN_AUTO_REJECT,
                "sourcePageType": "other_entity",
                "entityMatch": "mismatch",
                "matchedTitle": resolved_title,
                "reasons": [
                    f"MediaWiki resolved title「{resolved_title}」与目标实体「{entity_name}」不一致"
                    + (f"；redirectChain={redirect_chain}" if redirect_chain else "")
                ],
            }

    for title in titles:
        for variant in _title_variants(title):
            if variant in entity_variants:
                return {
                    "decision": PRESCREEN_AUTO_PRIMARY,
                    "matchedTitle": title,
                    "entityMatch": "exact",
                    "reasons": [f"页面标题「{title}」与目标实体精确一致"],
                }
            if variant in alias_variants:
                return {
                    "decision": PRESCREEN_AUTO_PRIMARY,
                    "matchedTitle": title,
                    "entityMatch": "alias",
                    "reasons": [f"页面标题「{title}」命中 registry 登记别名"],
                }

    url = str(meta.get("url") or "")
    if _url_is_site_root(url):
        reasons.append(f"站点根 URL {url} 是门户首页，不是实体介绍页")
        return {
            "decision": PRESCREEN_AUTO_REJECT,
            "sourcePageType": "portal_home",
            "entityMatch": "mismatch",
            "reasons": reasons,
        }
    for title in titles:
        if any(marker in title for marker in _PORTAL_TITLE_MARKERS):
            reasons.append(f"页面标题「{title}」是政府/门户站点标题")
            return {
                "decision": PRESCREEN_AUTO_REJECT,
                "sourcePageType": "portal_home",
                "entityMatch": "mismatch",
                "reasons": reasons,
            }
        if _title_is_parent_admin_region(entity_name, title):
            reasons.append(
                f"页面标题「{title}」是上级/其它行政区概况页，不能替代「{entity_name}」实体主页"
            )
            return {
                "decision": PRESCREEN_AUTO_REJECT,
                "sourcePageType": "parent_region_overview",
                "entityMatch": "mismatch",
                "reasons": reasons,
            }
    if titles and head_text:
        entity_norm = normalize_page_title(entity_name)
        title_mismatch = all(
            not _shares_name_prefix(entity_norm, normalize_page_title(t)) for t in titles
        )
        nav_hits = sum(1 for marker in _PORTAL_NAV_MARKERS if marker in head_text)
        if title_mismatch and nav_hits >= 4:
            reasons.append(
                f"页面标题 {titles} 与实体无关且首屏导航/栏目信号 {nav_hits} 处，判为门户/栏目页"
            )
            return {
                "decision": PRESCREEN_AUTO_REJECT,
                "sourcePageType": "listing",
                "entityMatch": "mismatch",
                "reasons": reasons,
            }

    return {
        "decision": PRESCREEN_NEEDS_MODEL,
        "titles": titles,
        "reasons": ["标题/结构证据不足以确定性裁决，需模型做内容格式与语义判别"],
    }


def build_judge_request(
    *,
    entity_name: str,
    entity_type: str = "",
    aliases: Sequence[str] = (),
    meta: Mapping[str, Any] | None = None,
    source_text: str = "",
    unit_ref: str = "",
    prescreen: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """构造灰区来源的模型判别请求（写 ``source.judge.request.json``）。"""
    meta = meta or {}
    body = re.sub(r"\s+", " ", str(source_text or "")).strip()
    return {
        "schemaVersion": SOURCE_JUDGE_SCHEMA_VERSION,
        "targetEntity": str(entity_name or ""),
        "entityType": str(entity_type or ""),
        "canonicalAliases": [str(a) for a in (aliases or ()) if str(a).strip()],
        "unitRef": str(unit_ref or ""),
        "source": {
            "url": str(meta.get("url") or ""),
            "platform": str(meta.get("platform") or ""),
            "sourceKind": str(meta.get("sourceKind") or ""),
            "titleEvidence": collect_title_evidence(meta),
            "headText": body[:1800],
        },
        "prescreen": dict(prescreen or {}),
        "verdictFile": SOURCE_JUDGE_VERDICT_FILE,
        "allowedPageTypes": sorted(SOURCE_PAGE_TYPES),
        "allowedEntityMatch": sorted(ENTITY_MATCH_VERDICTS),
        "allowedActions": sorted(RECOMMENDED_ACTIONS),
    }


def write_judge_request(unit_dir: Path, request: Mapping[str, Any]) -> Path:
    path = Path(unit_dir) / SOURCE_JUDGE_REQUEST_FILE
    path.write_text(
        json.dumps(dict(request), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def read_judge_verdict(unit_dir: Path) -> dict[str, Any] | None:
    path = Path(unit_dir) / SOURCE_JUDGE_VERDICT_FILE
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def judge_verdict_issues(
    verdict: Mapping[str, Any] | None,
    *,
    entity_name: str,
) -> list[str]:
    """verdict schema 校验：返回问题列表（空 = 通过）。任何漂移都拒绝消费。"""
    issues: list[str] = []
    if not isinstance(verdict, Mapping):
        return ["verdict must be a JSON object"]
    if str(verdict.get("schemaVersion") or "") != SOURCE_JUDGE_SCHEMA_VERSION:
        issues.append(
            f"schemaVersion must be {SOURCE_JUDGE_SCHEMA_VERSION}, got {verdict.get('schemaVersion')!r}"
        )
    target = normalize_page_title(str(verdict.get("targetEntity") or ""))
    if target != normalize_page_title(entity_name):
        issues.append(
            f"targetEntity mismatch: verdict={verdict.get('targetEntity')!r} expected={entity_name!r}"
        )
    page_type = str(verdict.get("sourcePageType") or "")
    if page_type not in SOURCE_PAGE_TYPES:
        issues.append(f"sourcePageType invalid: {page_type!r}")
    entity_match = str(verdict.get("entityMatch") or "")
    if entity_match not in ENTITY_MATCH_VERDICTS:
        issues.append(f"entityMatch invalid: {entity_match!r}")
    action = str(verdict.get("recommendedAction") or "")
    if action not in RECOMMENDED_ACTIONS:
        issues.append(f"recommendedAction invalid: {action!r}")
    try:
        confidence = float(verdict.get("confidence"))
    except (TypeError, ValueError):
        confidence = -1.0
    if not 0.0 <= confidence <= 1.0:
        issues.append(f"confidence must be within [0,1], got {verdict.get('confidence')!r}")
    reasons = verdict.get("reasons")
    if not isinstance(reasons, list) or not any(str(r).strip() for r in reasons):
        issues.append("reasons must be a non-empty list (reason-before-score)")
    evidence = verdict.get("evidence")
    if not isinstance(evidence, list) or not any(
        isinstance(e, Mapping) and str(e.get("quote") or "").strip() for e in evidence
    ):
        issues.append("evidence must contain at least one {field, quote} entry")
    if action == "primary":
        if not bool(verdict.get("primaryEligible")):
            issues.append("recommendedAction=primary requires primaryEligible=true")
        if page_type != "entity_homepage":
            issues.append("recommendedAction=primary requires sourcePageType=entity_homepage")
        if entity_match not in ("exact", "alias"):
            issues.append("recommendedAction=primary requires entityMatch exact/alias")
        if confidence < PRIMARY_MIN_CONFIDENCE:
            issues.append(
                f"recommendedAction=primary requires confidence>={PRIMARY_MIN_CONFIDENCE}, got {confidence}"
            )
    return issues


ADMISSION_PRIMARY = "primary"
ADMISSION_SUPPORTING_ONLY = "supporting_only"
ADMISSION_REJECT = "reject"
ADMISSION_PENDING_JUDGE = "pending_judge"

# 创作阶段失败协议：Agent 发现底稿与实体不一致时写 4.draft/failure.json，
# finalize 消费后结构化阻断（不再让模型硬写错误实体的主页）。
ENTITY_PAGE_FAILURE_FILE = "failure.json"
ENTITY_PAGE_FAILURE_SCHEMA_VERSION = "quwoquan_data.entity_page_failure/1"
class EntityPageFailureKind(StrEnum):
    SOURCE_ENTITY_MISMATCH = "source_entity_mismatch"
    SOURCE_INSUFFICIENT = "source_insufficient"
    SOURCE_PAGE_TYPE_INVALID = "source_page_type_invalid"
    OTHER = "other"


ENTITY_PAGE_FAILURE_KINDS = frozenset(kind.value for kind in EntityPageFailureKind)
SOURCE_RECOVERY_FAILURE_KINDS = frozenset(
    {
        EntityPageFailureKind.SOURCE_ENTITY_MISMATCH,
        EntityPageFailureKind.SOURCE_INSUFFICIENT,
        EntityPageFailureKind.SOURCE_PAGE_TYPE_INVALID,
    }
)


def entity_page_failure_kind(
    failure: Mapping[str, Any] | None,
) -> EntityPageFailureKind | None:
    if not isinstance(failure, Mapping):
        return None
    try:
        return EntityPageFailureKind(str(failure.get("failureKind") or ""))
    except ValueError:
        return None


def read_entity_page_failure(draft_dir: Path) -> dict[str, Any] | None:
    path = Path(draft_dir) / ENTITY_PAGE_FAILURE_FILE
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schemaVersion": "", "_unreadable": True}
    return payload if isinstance(payload, dict) else {"schemaVersion": "", "_unreadable": True}


def entity_page_failure_issues(
    failure: Mapping[str, Any] | None,
    *,
    entity_name: str,
) -> list[str]:
    """failure.json schema 校验：返回问题列表（空 = 合法失败报告）。"""
    issues: list[str] = []
    if not isinstance(failure, Mapping) or failure.get("_unreadable"):
        return ["failure.json unreadable or not a JSON object"]
    if str(failure.get("schemaVersion") or "") != ENTITY_PAGE_FAILURE_SCHEMA_VERSION:
        issues.append(
            f"schemaVersion must be {ENTITY_PAGE_FAILURE_SCHEMA_VERSION}, got {failure.get('schemaVersion')!r}"
        )
    if normalize_page_title(str(failure.get("targetEntity") or "")) != normalize_page_title(entity_name):
        issues.append(
            f"targetEntity mismatch: failure={failure.get('targetEntity')!r} expected={entity_name!r}"
        )
    kind = entity_page_failure_kind(failure)
    if kind is None:
        issues.append(f"failureKind invalid: {failure.get('failureKind')!r}")
    reasons = failure.get("reasons")
    if not isinstance(reasons, list) or not any(str(r).strip() for r in reasons):
        issues.append("reasons must be a non-empty list")
    return issues


def source_judge_admission(
    *,
    entity_name: str,
    aliases: Sequence[str] = (),
    meta: Mapping[str, Any] | None = None,
    source_text: str = "",
    unit_dir: Path | None = None,
) -> dict[str, Any]:
    """homepage 底稿准入合成裁决：有效 verdict 优先，其次确定性预筛，灰区 fail-closed。

    返回 ``{"decision", "verdictSource", "issue", "prescreen"?, "verdict"?}``；
    仅 ``decision == "primary"`` 允许进入 homepage baseDraft。
    """
    if unit_dir is not None:
        verdict = read_judge_verdict(unit_dir)
        if verdict is not None:
            problems = judge_verdict_issues(verdict, entity_name=entity_name)
            if problems:
                return {
                    "decision": ADMISSION_PENDING_JUDGE,
                    "verdictSource": "verdict_invalid",
                    "issue": "source.judge.json invalid: " + "; ".join(problems),
                }
            action = str(verdict.get("recommendedAction") or "")
            if action == "primary":
                return {
                    "decision": ADMISSION_PRIMARY,
                    "verdictSource": "verdict",
                    "issue": "",
                    "verdict": dict(verdict),
                }
            decision = (
                ADMISSION_SUPPORTING_ONLY
                if action == "supporting_only"
                else ADMISSION_REJECT
                if action == "reject"
                else ADMISSION_PENDING_JUDGE
            )
            reason = "; ".join(str(r) for r in (verdict.get("reasons") or [])[:2])
            return {
                "decision": decision,
                "verdictSource": "verdict",
                "issue": f"homepage_source_judge: {action} ({reason})",
                "verdict": dict(verdict),
            }

    prescreen = deterministic_prescreen(
        entity_name=entity_name,
        aliases=aliases,
        meta=meta,
        head_text=str(source_text or "")[:3000],
        unit_dir=unit_dir,
    )
    decision = str(prescreen.get("decision") or "")
    if decision == PRESCREEN_AUTO_PRIMARY:
        return {
            "decision": ADMISSION_PRIMARY,
            "verdictSource": "prescreen",
            "issue": "",
            "prescreen": prescreen,
        }
    if decision == PRESCREEN_AUTO_REJECT:
        return {
            "decision": ADMISSION_REJECT,
            "verdictSource": "prescreen",
            "issue": "homepage_source_judge prescreen reject: "
            + "; ".join(str(r) for r in prescreen.get("reasons") or []),
            "prescreen": prescreen,
        }
    # 百科来源且完全没有标题证据（离线快照/contract fixture 无 URL）：沿用 registry
    # 权威信任，不强制模型判别；一旦存在标题证据却未命中实体（如 URL slug 是
    # 「东沙角」而实体是「东沙古镇」），仍然 fail-closed 交模型裁决。
    if _is_encyclopedia_source(meta) and not (prescreen.get("titles") or []):
        return {
            "decision": ADMISSION_PRIMARY,
            "verdictSource": "prescreen_encyclopedia_trust",
            "issue": "",
            "prescreen": prescreen,
        }
    return {
        "decision": ADMISSION_PENDING_JUDGE,
        "verdictSource": "prescreen",
        "issue": (
            "awaiting homepage_source_judge verdict: 灰区来源需模型语义判别，"
            f"请按 {SOURCE_JUDGE_REQUEST_FILE} 写回 {SOURCE_JUDGE_VERDICT_FILE}"
        ),
        "prescreen": prescreen,
    }


def render_judge_prompt(request: Mapping[str, Any]) -> str:
    """渲染 homepage_source_judge 判别指令（模板真相源 prompts/**）。"""
    from core.prompt_render import fmt_bullets, render

    source = request.get("source") if isinstance(request.get("source"), Mapping) else {}
    prescreen = request.get("prescreen") if isinstance(request.get("prescreen"), Mapping) else {}
    meta_lines = [
        f"url: {source.get('url') or '（无）'}",
        f"platform: {source.get('platform') or '（无）'}",
        f"sourceKind: {source.get('sourceKind') or '（无）'}",
        f"titleEvidence: {', '.join(source.get('titleEvidence') or []) or '（无）'}",
    ]
    return render(
        "homepage_source_judge",
        task_vars={
            "target_entity": request.get("targetEntity"),
            "entity_type": request.get("entityType") or "（未提供）",
            "aliases_line": ", ".join(request.get("canonicalAliases") or []) or "（无登记别名）",
            "unit_ref": request.get("unitRef") or "（未提供）",
            "source_meta_block": fmt_bullets(meta_lines),
            "prescreen_block": fmt_bullets(
                [str(r) for r in (prescreen.get("reasons") or [])],
                empty="（预筛未给出确定性证据）",
            ),
            "head_text_block": str(source.get("headText") or "（无正文摘录）"),
        },
    )


__all__ = [
    "SOURCE_JUDGE_SCHEMA_VERSION",
    "SOURCE_JUDGE_REQUEST_FILE",
    "SOURCE_JUDGE_VERDICT_FILE",
    "SOURCE_PAGE_TYPES",
    "ENTITY_MATCH_VERDICTS",
    "RECOMMENDED_ACTIONS",
    "PRIMARY_MIN_CONFIDENCE",
    "PRESCREEN_AUTO_PRIMARY",
    "PRESCREEN_AUTO_REJECT",
    "PRESCREEN_NEEDS_MODEL",
    "ADMISSION_PRIMARY",
    "ADMISSION_SUPPORTING_ONLY",
    "ADMISSION_REJECT",
    "ADMISSION_PENDING_JUDGE",
    "ENTITY_PAGE_FAILURE_FILE",
    "ENTITY_PAGE_FAILURE_SCHEMA_VERSION",
    "EntityPageFailureKind",
    "ENTITY_PAGE_FAILURE_KINDS",
    "SOURCE_RECOVERY_FAILURE_KINDS",
    "read_entity_page_failure",
    "entity_page_failure_kind",
    "entity_page_failure_issues",
    "normalize_page_title",
    "collect_title_evidence",
    "deterministic_prescreen",
    "build_judge_request",
    "write_judge_request",
    "read_judge_verdict",
    "judge_verdict_issues",
    "source_judge_admission",
    "render_judge_prompt",
]
