"""作品 vs 随记判定器（WorksClassifier）。

商用主线只生产『作品』(work)：实体主页 / article / image / video(后置)。
碎片即时『随记』(moment) 与证据不足 (abandoned) 不进入 content_plan / produce。

判定融合两类信号（单一真相源，禁止散落魔数）：
- 来源专业度先验：content_source_registry.yaml: sourceTierSignals（sourceClass → baseTier + worksAffinity）。
- 内容实测信号：_common/content_evidence.score_source_markdown 文本质量分 + 结构/事实密度/叙事量/图片数。

阈值版本化于 templates/_registry/catalogs/works_classification.yaml；裁决符合
schema/produce/works_classification.schema.json，写入 thresholdsVersion 可审计、可回滚。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

from _common.content_evidence import anonymize_source_markdown, score_source_markdown
from _common.content_source_registry import load_content_source_registry, resolve_source_tier

WORKS_CLASSIFICATION_SCHEMA = "quwoquan_data.works_classification.v1"
WORKS_CLASSIFICATION_CONFIG_PATH = (
    Path(__file__).resolve().parents[2]
    / "templates"
    / "_registry"
    / "catalogs"
    / "works_classification.yaml"
)
_CONFIG_SCHEMA = "quwoquan.works_classification.v1"


@lru_cache(maxsize=1)
def load_works_classification_config() -> dict[str, Any]:
    if not WORKS_CLASSIFICATION_CONFIG_PATH.is_file():
        raise FileNotFoundError(f"missing works classification config: {WORKS_CLASSIFICATION_CONFIG_PATH}")
    data = yaml.safe_load(WORKS_CLASSIFICATION_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if data.get("schemaVersion") != _CONFIG_SCHEMA:
        raise ValueError(f"{WORKS_CLASSIFICATION_CONFIG_PATH}: invalid schemaVersion")
    return data


def _section_count(text: str, *, config: Mapping[str, Any] | None = None) -> int:
    raw = str(text or "")
    markdown_sections = len([line for line in raw.splitlines() if line.lstrip().startswith("##")])
    content_cfg = config.get("contentSignals") if isinstance(config, Mapping) else {}
    if not isinstance(content_cfg, Mapping):
        content_cfg = {}
    compact = re.sub(r"\s+", " ", raw).strip()
    plain_markers = [
        str(value).strip()
        for value in (content_cfg.get("plainTextSectionMarkers") or [])
        if str(value).strip()
    ]
    plain_patterns = [
        str(value).strip()
        for value in (content_cfg.get("plainTextSectionPatterns") or [])
        if str(value).strip()
    ]
    plain_hits = {marker for marker in plain_markers if marker in compact}
    for pattern in plain_patterns:
        try:
            plain_hits.update(re.findall(pattern, compact, flags=re.IGNORECASE))
        except re.error:
            continue
    return max(markdown_sections, min(len(plain_hits), 6))


def _paragraph_count(text: str) -> int:
    return len([p for p in str(text or "").split("\n\n") if p.strip()])


def _structure_score(text: str, *, config: Mapping[str, Any] | None = None) -> float:
    """结构完整度 0..1：综合小节数与段落数。"""
    sections = _section_count(text, config=config)
    paragraphs = _paragraph_count(text)
    section_part = min(1.0, sections / 3.0)
    paragraph_part = min(1.0, paragraphs / 4.0)
    return round(0.6 * section_part + 0.4 * paragraph_part, 4)


def _verdict(
    ref: str,
    *,
    decision: str,
    carrier: str | None,
    score: float,
    source_tier: str,
    signals: dict[str, Any],
    reasons: list[str],
    abandon_reason: str | None,
    thresholds_version: int,
) -> dict[str, Any]:
    return {
        "schemaVersion": WORKS_CLASSIFICATION_SCHEMA,
        "ref": ref,
        "decision": decision,
        "carrier": carrier,
        "score": round(float(score), 4),
        "sourceTier": source_tier,
        "signals": signals,
        "reasons": reasons,
        "abandonReason": abandon_reason,
        "thresholdsVersion": int(thresholds_version),
        "decidedAt": datetime.now(timezone.utc).isoformat(),
    }


def _resolve_work_carrier(
    declared_carrier: str | None,
    *,
    narrative_volume: int,
    image_count: int,
    config: Mapping[str, Any],
) -> str:
    declared = str(declared_carrier or "").strip().lower()
    if declared in ("image", "gallery"):
        return "image"
    if declared in ("article", "video", "homepage"):
        return declared
    rules = config.get("carrierRules") or {}
    min_images = int(rules.get("minImagesForImageWork", 4))
    low_narrative = int(rules.get("lowNarrativeForImage", 1))
    if image_count >= min_images and narrative_volume <= low_narrative:
        return "image"
    return "article"


def classify_works(
    ref: str,
    *,
    source_class: str,
    source_text: str,
    entity_name: str | None = None,
    narrative_volume: int = 0,
    image_count: int = 0,
    declared_carrier: str | None = None,
    rights_blocked: bool = False,
    registry: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """判定一个内容对象是 work / moment / abandoned，并给出建议载体与结构化原因。

    两条判定路径（载体语义不同，信号不同，禁止混用）：
    - 图片作品路径：作品性由『图片集合数量 + 权利 + 来源专业度』决定，不用文本质量硬否决
      （图片作品底稿文本天然稀薄甚至为空）。
    - 文本/文章路径：作品性由『来源专业度先验 + 文本质量/结构/事实密度/叙事量』决定；
      低专业度碎片来源(随记倾向)落 moment，证据不足/探针页落 abandoned。
    """
    config = config or load_works_classification_config()
    registry = registry if registry is not None else load_content_source_registry()
    version = int(config.get("version") or 1)

    tier_info = resolve_source_tier(source_class, data=registry)
    base_tier = tier_info["baseTier"]
    affinity = tier_info["worksAffinity"]

    assessment = score_source_markdown(ref, source_text, entity_name=entity_name)
    quality_tier = assessment.quality
    quality_score = int(assessment.score)

    cleaned = anonymize_source_markdown(source_text)
    compact_len = len(re.sub(r"\s+", " ", cleaned).strip())
    structure_score = _structure_score(cleaned, config=config)
    section_count = _section_count(cleaned, config=config)

    content_cfg = config.get("contentSignals") or {}
    reject_tier = str(content_cfg.get("rejectQualityTier") or "Reject")
    work_min_source = int(content_cfg.get("workMinSourceScore", 4))
    carrier_rules = config.get("carrierRules") or {}
    min_images = int(carrier_rules.get("minImagesForImageWork", 4))
    low_narrative = int(carrier_rules.get("lowNarrativeForImage", 1))

    tier_weights = config.get("tierWeights") or {}
    affinity_weights = config.get("affinityWeights") or {}
    score_weights = config.get("scoreWeights") or {}
    tier_weight = float(tier_weights.get(base_tier, 0.0))
    affinity_weight = float(affinity_weights.get(affinity, 0.5))

    declared = str(declared_carrier or "").strip().lower()
    explicit_image_carrier = declared in ("image", "gallery")
    is_image_work = explicit_image_carrier or (
        not declared and image_count >= min_images and narrative_volume <= low_narrative
    )

    reasons: list[str] = [
        f"sourceClass={source_class}", f"baseTier={base_tier}", f"affinity={affinity}",
        f"quality={quality_tier}({quality_score})", f"imageWork={is_image_work}",
    ]
    base_signals: dict[str, Any] = {
        "sourceClass": source_class,
        "sourceQualityTier": quality_tier,
        "sourceQualityScore": quality_score,
        "worksAffinity": affinity,
        "baseTier": base_tier,
        "structureScore": structure_score,
        "sectionCount": section_count,
        "factDensity": round(min(1.0, quality_score / 7.0), 4),
        "narrativeVolume": int(narrative_volume),
        "imageCount": int(image_count),
        "casualSignals": [],
    }

    # ── 权利受阻：任何形态硬丢弃 ──
    if rights_blocked:
        return _verdict(ref, decision="abandoned", carrier=None, score=0.0, source_tier="tier5_reject",
                        signals=base_signals, reasons=reasons + ["rights_blocked"],
                        abandon_reason="rights_blocked", thresholds_version=version)

    # ── 图片作品路径 ──
    if is_image_work:
        if base_tier == "tier5_reject":
            return _verdict(ref, decision="abandoned", carrier=None, score=0.0, source_tier=base_tier,
                            signals=base_signals, reasons=reasons + ["image_source_tier5"],
                            abandon_reason="insufficient_evidence", thresholds_version=version)
        required_image_count = 1 if explicit_image_carrier else min_images
        if image_count < required_image_count:
            return _verdict(ref, decision="abandoned", carrier=None, score=0.0, source_tier=base_tier,
                            signals=base_signals, reasons=reasons + [f"image_count={image_count}<min={required_image_count}"],
                            abandon_reason="insufficient_evidence", thresholds_version=version)
        image_norm = min(1.0, image_count / 8.0)
        works_score = (
            tier_weight * float(score_weights.get("tier", 0.45))
            + affinity_weight * float(score_weights.get("affinity", 0.25))
            + image_norm * float(score_weights.get("content", 0.30))
        )
        reasons.append(f"image_work imageCount={image_count} score={works_score:.3f}")
        return _verdict(ref, decision="work", carrier="image", score=works_score, source_tier=base_tier,
                        signals=base_signals, reasons=reasons, abandon_reason=None, thresholds_version=version)

    # ── 文本/文章路径 ──
    casual_cfg = config.get("casualHeuristics") or {}
    max_casual_chars = int(casual_cfg.get("maxCharsForCasual", 180))
    casual_classes = set(casual_cfg.get("casualAffinitySourceClasses") or [])
    casual_affinity = affinity == "moment" or source_class in casual_classes

    if base_tier == "tier5_reject":
        return _verdict(ref, decision="abandoned", carrier=None, score=0.0, source_tier=base_tier,
                        signals=base_signals, reasons=reasons + ["source_tier5"],
                        abandon_reason="insufficient_evidence", thresholds_version=version)
    if quality_tier == reject_tier:
        # 碎片来源(随记倾向)的低质短文是『随记』；其它低质来源是证据不足『丢弃』。
        if casual_affinity:
            return _verdict(ref, decision="moment", carrier=None, score=0.0, source_tier=base_tier,
                            signals=base_signals, reasons=reasons + ["reject_quality+casual_source"],
                            abandon_reason="casual_moment", thresholds_version=version)
        return _verdict(ref, decision="abandoned", carrier=None, score=0.0, source_tier=base_tier,
                        signals=base_signals, reasons=reasons + ["reject_quality"],
                        abandon_reason="insufficient_evidence", thresholds_version=version)

    fact_density = min(1.0, quality_score / 7.0)
    narrative_norm = min(1.0, narrative_volume / 6.0)
    image_norm = min(1.0, image_count / 8.0)
    content_signal = (
        structure_score * float(content_cfg.get("structureWeight", 0.35))
        + fact_density * float(content_cfg.get("factDensityWeight", 0.30))
        + narrative_norm * float(content_cfg.get("narrativeWeight", 0.20))
        + image_norm * float(content_cfg.get("imageWeight", 0.15))
    )
    works_score = (
        tier_weight * float(score_weights.get("tier", 0.45))
        + affinity_weight * float(score_weights.get("affinity", 0.25))
        + content_signal * float(score_weights.get("content", 0.30))
    )

    casual_signals: list[str] = []
    if compact_len <= max_casual_chars:
        casual_signals.append("too_short")
    if section_count == 0 and bool(casual_cfg.get("requireSectionForLongform", True)):
        casual_signals.append("no_section")
    if source_class in casual_classes:
        casual_signals.append("casual_source_class")
    if affinity == "moment":
        casual_signals.append("moment_affinity")
    base_signals["casualSignals"] = casual_signals

    bands = config.get("decisionBands") or {}
    work_min_score = float(bands.get("workMinScore", 0.50))
    abandoned_max_score = float(bands.get("abandonedMaxScore", 0.20))

    # 内容自证：高质量(A-story/B-fact，scorer 已含 length_ok)+有结构的文章，
    # 无论来源先验如何都判作品（对齐 article lanePolicy.noIntrinsicPriorityBySourceClass：
    # 文章只看内容质量，不按来源类别天然升降级；精炼知识卡片天然较短，不叠加随记篇幅上限）。
    self_prove_tiers = set(content_cfg.get("selfProveQualityTiers") or ["A-story", "B-fact"])
    content_self_proves = quality_tier in self_prove_tiers and section_count >= 1

    if casual_affinity and len(casual_signals) >= 2:
        decision, abandon_reason, carrier = "moment", "casual_moment", None
        reasons.append(f"casual_affinity+signals={casual_signals}")
    elif content_self_proves or (works_score >= work_min_score and quality_score >= work_min_source):
        decision, abandon_reason = "work", None
        carrier = _resolve_work_carrier(declared_carrier, narrative_volume=narrative_volume, image_count=image_count, config=config)
        reasons.append(
            f"content_self_proves={content_self_proves} work_score={works_score:.3f}(workMin={work_min_score})"
        )
    elif works_score < abandoned_max_score:
        decision, abandon_reason, carrier = "abandoned", "low_professionalism", None
        reasons.append(f"work_score={works_score:.3f}<abandonedMax={abandoned_max_score}")
    else:
        decision, abandon_reason, carrier = "moment", "casual_moment", None
        reasons.append(f"work_score={works_score:.3f} in moment band")

    return _verdict(ref, decision=decision, carrier=carrier, score=works_score, source_tier=base_tier,
                    signals=base_signals, reasons=reasons, abandon_reason=abandon_reason,
                    thresholds_version=version)


__all__ = [
    "WORKS_CLASSIFICATION_SCHEMA",
    "load_works_classification_config",
    "classify_works",
]
