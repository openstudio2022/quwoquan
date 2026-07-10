#!/usr/bin/env python3
"""Golden set 门标定与度量：对好稿/坏稿样本跑语义门，计算拦截率/误杀率。

整改计划第六阶段（算法专家视角 + gate-calibration-goldenset）：
- 门上线前必须在 golden set 上度量 precision/recall，避免漏检与误杀。
- label=bad 期望被任一门拦截（intercept）；label=good 期望全门放行。
- 输出每门触发分布，便于单独标定阈值。

可直接运行：python3 quwoquan_data/scripts/verify/measure_gate_goldenset.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common import quality_gates as qg  # noqa: E402
from _common import rubric_judge as rj  # noqa: E402

GOLDEN_DIR = DATA_ROOT / "tests" / "support" / "fixtures" / "golden_set"
INTERCEPT_TARGET = 0.95
FALSE_POSITIVE_TARGET = 0.05
# 判官校准门（2026 LLM-as-judge playbook）：门判决 vs 人工标注的一致性。
KAPPA_TARGET = rj.KAPPA_MIN          # Cohen's kappa < 0.6 → 判官需重调
AGREEMENT_TARGET = rj.AGREEMENT_MIN  # agreement < 85% → 判官需重调
# 内容质量地板（per-rubric 绝对下限）。
FAITHFULNESS_FLOOR = 0.75
TASK_COMPLETION_FLOOR = 0.85
# 回归漂移：较 baseline 任一指标下跌超过该幅度即 BLOCK（2 分制→0.02）。
REGRESSION_DROP_LIMIT = 0.02


def _firing_gates(article: str, meta: dict[str, Any], peers: list[str]) -> list[str]:
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
    if qg.skeleton_similarity_issues(article, peers):
        fired.append("skeletonSimilarity")
    if qg.semantic_duplicate_issues(article, peers):
        fired.append("semanticDuplicate")
    return fired


def evaluate_goldenset(golden_dir: Path = GOLDEN_DIR) -> dict[str, Any]:
    labels = json.loads((golden_dir / "labels.json").read_text(encoding="utf-8"))
    items = labels.get("items") or []
    articles: dict[str, str] = {}
    for item in items:
        articles[item["file"]] = (golden_dir / item["file"]).read_text(encoding="utf-8")

    per_item: list[dict[str, Any]] = []
    per_gate: dict[str, dict[str, int]] = {}
    tp = fp = fn = tn = 0
    for item in items:
        f = item["file"]
        article = articles[f]
        peers = [a for k, a in articles.items() if k != f]
        fired = _firing_gates(article, item.get("meta") or {}, peers)
        blocked = bool(fired)
        is_bad = item.get("label") == "bad"
        if is_bad and blocked:
            tp += 1
        elif is_bad and not blocked:
            fn += 1
        elif not is_bad and blocked:
            fp += 1
        else:
            tn += 1
        for g in fired:
            bucket = per_gate.setdefault(g, {"firedOnBad": 0, "firedOnGood": 0})
            bucket["firedOnBad" if is_bad else "firedOnGood"] += 1
        per_item.append({"file": f, "label": item.get("label"), "blocked": blocked, "firingGates": fired})

    intercept_rate = tp / (tp + fn) if (tp + fn) else 1.0
    false_positive_rate = fp / (fp + tn) if (fp + tn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0

    # 判官校准：门判决（blocked）vs 人工标注（bad）的一致性（Cohen's kappa + agreement）。
    judge_labels = ["bad" if p["blocked"] else "good" for p in per_item]
    human_labels = [str(p["label"]) for p in per_item]
    kappa = rj.cohen_kappa(judge_labels, human_labels)
    agreement = round(rj.agreement_rate(judge_labels, human_labels), 4)

    return {
        "total": len(items),
        "confusion": {"TP": tp, "FP": fp, "FN": fn, "TN": tn},
        "interceptRate": round(intercept_rate, 4),
        "falsePositiveRate": round(false_positive_rate, 4),
        "precision": round(precision, 4),
        "calibration": {"cohenKappa": kappa, "agreement": agreement},
        "perGate": per_gate,
        "perItem": per_item,
        "thresholds": {
            "skeletonHeading": qg.SKELETON_HEADING_SIMILARITY,
            "skeletonEnding": qg.SKELETON_ENDING_SIMILARITY,
            "skeletonNgram": qg.SKELETON_NGRAM_SIMILARITY,
            "semanticSimhash": qg.SEMANTIC_DUP_SIMHASH,
        },
        "targets": {
            "interceptRate": INTERCEPT_TARGET,
            "falsePositiveRate": FALSE_POSITIVE_TARGET,
            "cohenKappa": KAPPA_TARGET,
            "agreement": AGREEMENT_TARGET,
        },
    }


def calibration_gate_issues(report: dict[str, Any], baseline: dict[str, Any] | None = None) -> list[str]:
    """判官校准 CI 门：地板 + kappa/agreement + 较 baseline 回归漂移。"""
    issues: list[str] = []
    if report["interceptRate"] < INTERCEPT_TARGET:
        issues.append(f"interceptRate {report['interceptRate']} < {INTERCEPT_TARGET}")
    if report["falsePositiveRate"] > FALSE_POSITIVE_TARGET:
        issues.append(f"falsePositiveRate {report['falsePositiveRate']} > {FALSE_POSITIVE_TARGET}")
    cal = report.get("calibration") or {}
    if float(cal.get("cohenKappa", 1.0)) < KAPPA_TARGET:
        issues.append(f"cohenKappa {cal.get('cohenKappa')} < {KAPPA_TARGET} (judge needs re-tuning)")
    if float(cal.get("agreement", 1.0)) < AGREEMENT_TARGET:
        issues.append(f"agreement {cal.get('agreement')} < {AGREEMENT_TARGET} (judge needs re-tuning)")
    if baseline:
        for key in ("interceptRate", "precision"):
            cur = float(report.get(key, 0.0))
            base = float(baseline.get(key, 0.0))
            if base - cur > REGRESSION_DROP_LIMIT:
                issues.append(f"regression: {key} dropped {base - cur:.4f} from baseline (> {REGRESSION_DROP_LIMIT})")
        base_cal = baseline.get("calibration") or {}
        cur_k = float(cal.get("cohenKappa", 0.0))
        base_k = float(base_cal.get("cohenKappa", 0.0))
        if base_k - cur_k > REGRESSION_DROP_LIMIT:
            issues.append(f"regression: cohenKappa dropped {base_k - cur_k:.4f} from baseline (> {REGRESSION_DROP_LIMIT})")
    return issues


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="golden set 门标定 + 判官校准（kappa/agreement/回归漂移）")
    parser.add_argument("--baseline", help="可选 baseline 报告 JSON，用于回归漂移比对")
    parser.add_argument("--report-out", help="可选：把本次报告写出（供下次作 baseline）")
    args = parser.parse_args(argv)

    report = evaluate_goldenset()
    print(json.dumps(report, ensure_ascii=False, indent=2))

    baseline = None
    if args.baseline and Path(args.baseline).is_file():
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    if args.report_out:
        Path(args.report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    issues = calibration_gate_issues(report, baseline)
    if issues:
        print("[goldenset] FAILED:", file=sys.stderr)
        for i in issues:
            print(f"  - {i}", file=sys.stderr)
        sys.exit(1)
    cal = report["calibration"]
    print(
        f"[goldenset] PASSED: intercept={report['interceptRate']} falsePositive={report['falsePositiveRate']} "
        f"kappa={cal['cohenKappa']} agreement={cal['agreement']}"
    )


if __name__ == "__main__":
    main()
