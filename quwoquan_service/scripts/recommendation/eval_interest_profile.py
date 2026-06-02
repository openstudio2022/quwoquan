#!/usr/bin/env python3
"""
兴趣画像生产评估（大循环飞轮指标）。

读取 user 域 rm_user_profile_view.interestProfile（由 content 派生经
UserInterestRecomputed 事件投影，单一真相源），离线计算飞轮评估指标：

  - coverage_rate     画像覆盖率 = 有非空 topInterests 的画像 / 总画像
  - lifecycle         new / active / dormant 人群分布
  - freshness_days    画像新鲜度（now - recomputedAt）分位与分桶
  - top_interests     每画像 topInterests 数量分位（画像丰富度）
  - entropy_bits      topInterests 分数分布的香农熵分位（兴趣多样性）

与运行时 Prometheus 指标互补：Prometheus 看实时吞吐/滞后，本脚本看
存量画像的人群级覆盖/多样性，供运营飞轮评估与回归对照。

用法：
  python3 scripts/recommendation/eval_interest_profile.py
  python3 scripts/recommendation/eval_interest_profile.py --output report.json
  python3 scripts/recommendation/eval_interest_profile.py --min-coverage 0.6   # 不达标 exit 1
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

try:
    from pymongo import MongoClient
except ImportError:  # pragma: no cover - operational dependency
    print("pip install pymongo", file=sys.stderr)
    sys.exit(2)

COLLECTION = "rm_user_profile_view"


def shannon_entropy(top_interests: list[dict]) -> float:
    """香农熵（bits），与 Go InterestEntropy 对齐：分数归一为概率分布。"""
    scores = [float(t.get("score", 0.0)) for t in top_interests]
    scores = [s for s in scores if s > 0]
    total = sum(scores)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for s in scores:
        p = s / total
        entropy -= p * math.log2(p)
    return max(0.0, entropy)


def percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(round(q * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def summarize(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "avg": 0.0, "p50": 0.0, "p90": 0.0, "max": 0.0}
    s = sorted(values)
    return {
        "count": len(s),
        "avg": round(sum(s) / len(s), 4),
        "p50": round(percentile(s, 0.5), 4),
        "p90": round(percentile(s, 0.9), 4),
        "max": round(s[-1], 4),
    }


def freshness_buckets(days: list[float]) -> dict:
    buckets = {"0-1": 0, "1-3": 0, "3-7": 0, "7-21": 0, "21+": 0}
    for d in days:
        if d < 1:
            buckets["0-1"] += 1
        elif d < 3:
            buckets["1-3"] += 1
        elif d < 7:
            buckets["3-7"] += 1
        elif d < 21:
            buckets["7-21"] += 1
        else:
            buckets["21+"] += 1
    return buckets


def evaluate(db) -> dict:
    coll = db[COLLECTION]
    now = datetime.now(timezone.utc)

    total = 0
    covered = 0
    lifecycle = {"new": 0, "active": 0, "dormant": 0, "unknown": 0}
    top_counts: list[float] = []
    entropies: list[float] = []
    freshness_days: list[float] = []

    cursor = coll.find({"interestProfile": {"$exists": True}}, {"interestProfile": 1})
    for doc in cursor:
        prof = doc.get("interestProfile") or {}
        total += 1

        tops = prof.get("topInterests") or []
        if tops:
            covered += 1
            top_counts.append(float(len(tops)))
            entropies.append(shannon_entropy(tops))

        stage = prof.get("lifecycleStage") or "unknown"
        lifecycle[stage] = lifecycle.get(stage, 0) + 1

        recomputed = prof.get("recomputedAt")
        if isinstance(recomputed, datetime):
            ref = recomputed if recomputed.tzinfo else recomputed.replace(tzinfo=timezone.utc)
            lag_days = max(0.0, (now - ref).total_seconds() / 86400.0)
            freshness_days.append(lag_days)

    coverage_rate = round(covered / total, 4) if total else 0.0
    return {
        "generatedAt": now.isoformat(),
        "collection": COLLECTION,
        "totalProfiles": total,
        "coveredProfiles": covered,
        "coverageRate": coverage_rate,
        "lifecycle": lifecycle,
        "topInterests": summarize(top_counts),
        "entropyBits": summarize(entropies),
        "freshnessDays": summarize(freshness_days),
        "freshnessBuckets": freshness_buckets(freshness_days),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="兴趣画像生产评估（大循环飞轮指标）")
    p.add_argument(
        "--mongodb-uri",
        default=os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true"),
    )
    p.add_argument("--db", default=os.environ.get("MONGODB_DATABASE", "quwoquan"))
    p.add_argument("--output", default="", help="报告写入路径（默认 stdout）")
    p.add_argument(
        "--min-coverage",
        type=float,
        default=-1.0,
        help="覆盖率门槛；设置后未达标返回 exit 1（评估/门禁用）",
    )
    args = p.parse_args()

    client = MongoClient(args.mongodb_uri, serverSelectionTimeoutMS=5000)
    try:
        report = evaluate(client[args.db])
    finally:
        client.close()

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
        print(f"interest-profile report written to {args.output}", file=sys.stderr)
    else:
        print(payload)

    if args.min_coverage >= 0 and report["coverageRate"] < args.min_coverage:
        print(
            f"FAIL: coverageRate {report['coverageRate']} < min {args.min_coverage}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
