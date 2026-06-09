"""文风族与开篇策略注册表加载 ——「美」之"开篇不千篇一律"的硬约束逻辑库。

`templates/_registry/catalogs/style_profile_catalog.yaml` 是文风唯一真相源：
- 顶层 `openingStrategies`：全局开篇策略库（label / hint / markers）。
- 每个 `styleFamilies.<族>.allowedOpenings`：该体裁允许的多种开篇策略 id。

writing_pack 下发"默认 styleFamily + 其允许的开篇策略选项 + 全部候选族"，agent 按原文体裁+
证据自选 styleFamily 与 openingStrategy 写入 draft_meta；review 开篇门用 `detect_opening_strategy`
按所选族的 markers 语义化校验（命中即视为采用了真实开篇钩子，而非套路化罗列）。

committed 真相源按脚本相对路径定位，不随运行期 QWQ_DATA_ROOT 漂移。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

STYLE_CATALOG_PATH = (
    Path(__file__).resolve().parents[2]
    / "templates"
    / "_registry"
    / "catalogs"
    / "style_profile_catalog.yaml"
)

# 未声明 allowedOpenings 的族 / 未知族的宽松兜底集合，避免把开篇门卡死。
_DEFAULT_OPENINGS = ("personal_motivation", "scene_immersion", "question_hook", "conclusion_first")


@lru_cache(maxsize=1)
def load_style_catalog() -> dict[str, Any]:
    if not STYLE_CATALOG_PATH.is_file():
        return {}
    with STYLE_CATALOG_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def opening_strategies() -> dict[str, dict[str, Any]]:
    raw = load_style_catalog().get("openingStrategies") or {}
    return {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}


def known_opening_strategy_ids() -> set[str]:
    return set(opening_strategies().keys())


def _style_families() -> dict[str, dict[str, Any]]:
    raw = load_style_catalog().get("styleFamilies") or {}
    return {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}


def known_style_families() -> set[str]:
    return set(_style_families().keys())


def family_allowed_openings(family: str) -> list[str]:
    """该体裁允许的开篇策略 id 列表；过滤掉 catalog 未定义的 id；缺失/未知族使用宽松兜底集。"""
    strategies = known_opening_strategy_ids()
    fam = _style_families().get(str(family or "")) or {}
    allowed = [str(s) for s in (fam.get("allowedOpenings") or []) if str(s) in strategies]
    if allowed:
        return allowed
    return [s for s in _DEFAULT_OPENINGS if s in strategies] or list(strategies)


def opening_strategy_options(family: str) -> list[dict[str, Any]]:
    """下发给 agent 的开篇候选：{id,label,hint}（markers 不下发，避免诱导填词凑门）。"""
    strategies = opening_strategies()
    options: list[dict[str, Any]] = []
    for sid in family_allowed_openings(family):
        meta = strategies.get(sid) or {}
        options.append({"id": sid, "label": meta.get("label", sid), "hint": meta.get("hint", "")})
    return options


def style_family_candidates() -> list[dict[str, Any]]:
    """全部候选体裁简介，供 agent 在原文体裁与 blueprint 默认不符时改选并写入 draft_meta。"""
    families = _style_families()
    out: list[dict[str, Any]] = []
    for name, fam in families.items():
        profile = fam.get("styleProfile") or {}
        out.append(
            {
                "styleFamily": name,
                "writingGenre": profile.get("writingGenre", ""),
                "allowedOpenings": family_allowed_openings(name),
            }
        )
    return out


def _markers_for(strategy_id: str) -> list[str]:
    meta = opening_strategies().get(str(strategy_id)) or {}
    return [str(m) for m in (meta.get("markers") or []) if str(m)]


def detect_opening_strategy(text: str, family: str = "") -> str | None:
    """在开篇文本中检测命中的开篇策略 id。

    - 指定 family 时只在该族 allowedOpenings 内匹配（开篇必须落在体裁允许的策略集合内）。
    - 未指定 family 时在全部策略内匹配。
    命中任一策略的任一 marker 即返回该策略 id；都未命中返回 None（门据此判千篇一律/套路化开篇）。
    """
    body = text or ""
    candidates = family_allowed_openings(family) if family else list(known_opening_strategy_ids())
    for sid in candidates:
        for marker in _markers_for(sid):
            if marker and marker in body:
                return sid
    return None


def opening_guidance(family: str) -> dict[str, Any]:
    """writing_pack 下发的开篇引导块：默认族允许的策略 + 候选族 + 选择指令。"""
    return {
        "styleFamily": str(family or ""),
        "openingStrategies": opening_strategy_options(family),
        "styleFamilyCandidates": style_family_candidates(),
        "instruction": (
            "开篇必须从下列 openingStrategies 中任选一种真正落地，禁止千篇一律的"
            "'我在屏幕上看了无数遍/又怕…'式套路开头；若原文体裁与默认 styleFamily 不符，"
            "可从 styleFamilyCandidates 改选更贴合的体裁。在 draft_meta 写明最终 "
            "styleFamily 与 openingStrategy，正文开篇须体现所选策略。"
        ),
    }


__all__ = [
    "STYLE_CATALOG_PATH",
    "load_style_catalog",
    "opening_strategies",
    "known_opening_strategy_ids",
    "known_style_families",
    "family_allowed_openings",
    "opening_strategy_options",
    "style_family_candidates",
    "detect_opening_strategy",
    "opening_guidance",
]
