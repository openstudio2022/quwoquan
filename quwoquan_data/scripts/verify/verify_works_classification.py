#!/usr/bin/env python3
"""作品判定（WorksClassifier）契约门禁。

校验单一真相源闭环：
- works_classification.yaml：schema/必需键 + 权重覆盖全部 tier/affinity + video 后置。
- content_source_registry.yaml：sourceTierSignals 完整（复用 verify_content_source_registry）。
- 判定 smoke：代表样本 decision 正确，且裁决符合 schema/content/works_classification.schema.json。

接入 `qwq-data verify all`；改判定行为只改 canonical yaml，再过本门；
裁决通过配置内容摘要绑定精确策略身份。
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.content_source_registry import (  # noqa: E402
    VALID_SOURCE_TIERS,
    VALID_WORKS_AFFINITIES,
    verify_content_source_registry,
)
from core.schema import validate_result  # noqa: E402
from content.post.image.works_classifier import (  # noqa: E402
    classify_works,
    load_works_classification_config,
    works_classification_policy_digest,
)

_LONG = """# 九寨沟旅游全攻略

九寨沟位于四川省阿坝州，是著名的自然风景区。最佳游览时间为秋季十月。

## 交通与门票
门票旺季169元，观光车90元。从成都出发约8小时车程。

## 核心景点
五花海、诺日朗瀑布、长海等海子色彩斑斓，值得细细游览。海拔约2000米，注意高反。
"""
_CASUAL = "今天天气真好，随手拍了张照片，开心！这家店还不错下次再来。"

_SAMPLES = [
    ("art_pro", dict(source_class="vertical_professional", source_text=_LONG, entity_name="九寨沟",
                     narrative_volume=4, image_count=2), "work"),
    ("art_unknown", dict(source_class="", source_text=_LONG, entity_name="九寨沟",
                         narrative_volume=3, image_count=2), "work"),
    ("moment", dict(source_class="social_feed", source_text=_CASUAL, narrative_volume=0, image_count=1), "moment"),
    ("img_work", dict(source_class="photography_community", source_text="黄山日出", entity_name="黄山",
                      narrative_volume=0, image_count=6, declared_carrier="image"), "work"),
    ("img_few", dict(source_class="photography_community", source_text="黄山", narrative_volume=0,
                     image_count=1, declared_carrier="image"), "work"),
]

_REQUIRED_KEYS = (
    "tierWeights", "affinityWeights", "scoreWeights", "contentSignals",
    "casualHeuristics", "decisionBands", "carrierRules", "carrierQuotas", "samplingRates",
)


def check() -> list[str]:
    issues: list[str] = []
    cfg = load_works_classification_config()
    if "version" in cfg:
        issues.append("works_classification.yaml: parallel version is forbidden")
    for key in _REQUIRED_KEYS:
        if key not in cfg:
            issues.append(f"works_classification.yaml: missing required section {key!r}")

    tier_weights = cfg.get("tierWeights") or {}
    for tier in VALID_SOURCE_TIERS:
        if tier not in tier_weights:
            issues.append(f"tierWeights: missing weight for {tier!r}")
    affinity_weights = cfg.get("affinityWeights") or {}
    for affinity in VALID_WORKS_AFFINITIES:
        if affinity not in affinity_weights:
            issues.append(f"affinityWeights: missing weight for {affinity!r}")

    quotas = cfg.get("carrierQuotas") or {}
    video_quota = quotas.get("video") or {}
    if "deferred" in video_quota:
        issues.append("carrierQuotas.video.deferred is retired; formal video is an active lane")
    if float(video_quota.get("weight") or 0) <= 0:
        issues.append("carrierQuotas.video.weight must be positive")

    issues.extend(verify_content_source_registry())

    for ref, kwargs, expect in _SAMPLES:
        verdict = classify_works(ref, **kwargs)
        schema_errs = validate_result(verdict, "content", "works_classification")
        if schema_errs:
            issues.append(f"verdict[{ref}] schema violations: {schema_errs}")
        if str(verdict.get("decision")) != expect:
            issues.append(f"verdict[{ref}] decision={verdict.get('decision')!r} expected {expect!r}")
        if verdict.get("policyDigest") != works_classification_policy_digest(cfg):
            issues.append(f"verdict[{ref}] policyDigest drift from canonical config")
    return issues


def main() -> int:
    issues = check()
    if issues:
        print("FAIL works_classification contract:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("OK works_classification contract green")
    return 0
