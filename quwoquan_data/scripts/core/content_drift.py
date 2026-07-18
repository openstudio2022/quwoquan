"""内容质量漂移检测 + 失败回灌闭环（drift detection + closed-loop golden growth）。

2026 LLM-eval playbook 的在线观测 + 自增长测试集纪律：

- sample-drift：对已产出内容抽样复跑同一 rule 门，统计 per-gate 触发率；
  与 baseline 比对，任一门触发率上升超阈值 → 漂移告警（线上质量退化早发现）。
- promote-golden：把人工确认的失败 trace 晋级 golden set（写 md + labels.json），
  使回归集随真实失败自增长（closed loop）。幂等：同 file 不重复追加。

纯函数为主，CLI 侧只做抽样/落盘；不 import post/verify，避免循环依赖。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from core import quality_gates as qg

# 触发率上升超过该幅度即判漂移（线上质量退化）。
DRIFT_RISE_LIMIT = 0.10


def firing_gates(article: str, meta: Mapping[str, Any], peers: Sequence[str]) -> list[str]:
    """对单篇跑 rule 层门，返回触发的门名（与 measure_gate_goldenset 同口径）。"""
    fired: list[str] = []
    carrier = str(meta.get("carrier") or "article")
    assets = meta.get("assets") if isinstance(meta.get("assets"), list) else []
    if qg.image_reference_closure_issues(article, assets, carrier=carrier):
        fired.append("imageReferenceClosure")
    if meta.get("writingIntent") and qg.writing_intent_consistency_issues(article, meta.get("writingIntent")):
        fired.append("writingIntentConsistency")
    banned = meta.get("bannedRegisterTerms") or []
    if banned and qg.register_lexicon_issues(article, [str(b) for b in banned]):
        fired.append("registerMismatch")
    if qg.skeleton_similarity_issues(article, list(peers)):
        fired.append("skeletonSimilarity")
    if qg.semantic_duplicate_issues(article, list(peers)):
        fired.append("semanticDuplicate")
    if qg.contact_info_issues(article):
        fired.append("contactInfo")
    if qg.mechanical_heading_issues(article):
        fired.append("mechanicalHeading")
    return fired


def drift_report(
    samples: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, Any] | None = None,
    *,
    rise_limit: float = DRIFT_RISE_LIMIT,
) -> dict[str, Any]:
    """samples: 每条 {ref, article, meta}。统计 per-gate 触发率；与 baseline 比对漂移。"""
    n = len(samples)
    articles = [str(s.get("article") or "") for s in samples]
    fired_counts: dict[str, int] = {}
    per_item: list[dict[str, Any]] = []
    for idx, s in enumerate(samples):
        peers = [a for j, a in enumerate(articles) if j != idx]
        fired = firing_gates(str(s.get("article") or ""), s.get("meta") or {}, peers)
        for g in fired:
            fired_counts[g] = fired_counts.get(g, 0) + 1
        per_item.append({"ref": s.get("ref"), "firingGates": fired})

    firing_rates = {g: round(c / n, 4) for g, c in fired_counts.items()} if n else {}
    alerts: list[str] = []
    if baseline:
        base_rates = baseline.get("firingRates") or {}
        for g, rate in firing_rates.items():
            base = float(base_rates.get(g, 0.0))
            if rate - base > rise_limit:
                alerts.append(f"drift: gate `{g}` firing rate rose {rate - base:.2f} (now {rate}, baseline {base})")

    return {
        "schema": "quwoquan_data.content_drift_report",
        "sampled": n,
        "firingRates": firing_rates,
        "alerts": alerts,
        "drifted": bool(alerts),
        "perItem": per_item,
    }


def promote_to_golden(
    golden_dir: Path,
    *,
    file_name: str,
    article: str,
    label: str,
    meta: Mapping[str, Any],
    expect_gates: Iterable[str] | None = None,
    category: str = "promoted_failure",
    confirmed: bool = False,
) -> dict[str, Any]:
    """把失败 trace 晋级 golden set：写 md + 追加 labels.json。

    confirmed 必须为 True（人工确认后才入集，防自动污染）；幂等：file 已存在则不重复追加。
    """
    if not confirmed:
        return {"promoted": False, "reason": "human confirmation required (confirmed=False)"}
    golden_dir = Path(golden_dir)
    labels_path = golden_dir / "labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.is_file() else {
        "schema": "quwoquan_data.gate_goldenset",
        "items": [],
    }
    items = labels.setdefault("items", [])
    if any(it.get("file") == file_name for it in items):
        return {"promoted": False, "reason": "already in golden set (idempotent)", "file": file_name}

    (golden_dir / file_name).write_text(article, encoding="utf-8")
    item: dict[str, Any] = {"file": file_name, "label": label, "category": category, "meta": dict(meta)}
    if expect_gates:
        item["expectGates"] = list(expect_gates)
    items.append(item)
    labels_path.write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"promoted": True, "file": file_name, "total": len(items)}


__all__ = ["DRIFT_RISE_LIMIT", "firing_gates", "drift_report", "promote_to_golden"]
