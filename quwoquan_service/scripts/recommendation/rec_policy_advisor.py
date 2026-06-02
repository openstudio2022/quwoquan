#!/usr/bin/env python3
"""
推荐策略顾问（大循环 · 只产建议，绝不自动改线上）。

读取 contracts/metadata/recommendation/rec_model/policy.yaml 的 guardrails（唯一
真相源：metric / baselinePreset / minRatio / minSamples / window / action），对照
按 cohort（preset × segment × bucket × policyVersion）观测到的 KPI，产出结构化
"建议"，并且**至多**把候选策略推进到 product-ops 控制面的 `:simulate`（停在
simulated 态）。

强约束（与 policy.yaml guardrails.action=suggest_only 对齐）：
  - 本脚本**没有任何**调用 `:activate` 的代码路径；activate 由人在 ops-portal 走
    双审完成。任何让 simulated 态继续向 review_pending / canary / active 推进的动作
    都不在本脚本职责内。
  - guardrail 命中回归时，本脚本只标 "reject / hold" 建议，**不**触发自动回滚或
    自动切换（区别于旧的 online_guardrail 自动 rule-only cutover）。

指标来源（二选一）：
  --metrics-file FILE   规范、可单测：预聚合的 cohort 指标 JSON（schema 见下）。
  --mongodb-uri URI     便捷：从 rec_learning_events 按 labels 聚合（bucket/policyVersion）。

cohort 指标文件 schema：
  {
    "policyVersion": "v1",
    "window": "24h",
    "cohorts": [
      {"preset": "control", "segment": "none", "bucket": "control",
       "samples": 5000, "metrics": {"ctr": 0.082, "dwell": 12.1, "next_day_retention": 0.31}},
      {"preset": "engagement_heavy", "segment": "none", "bucket": "engagement_heavy",
       "samples": 3000, "metrics": {"ctr": 0.079, "dwell": 13.0, "next_day_retention": 0.30}}
    ]
  }

用法：
  python3 scripts/recommendation/rec_policy_advisor.py --metrics-file cohorts.json
  python3 scripts/recommendation/rec_policy_advisor.py --metrics-file cohorts.json --output report.json
  # 仅当人决定让某候选进入 simulated 演练时（仍停在 simulated）：
  python3 scripts/recommendation/rec_policy_advisor.py --metrics-file cohorts.json \
      --simulate --policy-id policy_discovery_rank_v12 \
      --product-ops-url http://127.0.0.1:18090
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

try:
    import yaml
except ImportError:  # pragma: no cover - operational dependency
    print("pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REPO_DEFAULT_POLICY = "contracts/metadata/recommendation/rec_model/policy.yaml"

# Verdicts the advisor may emit. None of these auto-act; "recommend_review"
# only marks a candidate as eligible for a human-driven simulate/approve flow.
VERDICT_RECOMMEND_REVIEW = "recommend_review"
VERDICT_HOLD = "hold"  # insufficient samples / missing baseline
VERDICT_REJECT = "reject"  # at least one guardrail floor breached

ACTION_SUGGEST_ONLY = "suggest_only"


def load_guardrails(policy_path: str) -> tuple[str, str, list[dict]]:
    with open(policy_path, "r", encoding="utf-8") as f:
        policy = yaml.safe_load(f)
    policy_version = str(policy.get("policyVersion", ""))
    default_preset = str(policy.get("defaultPreset", ""))
    guardrails = policy.get("guardrails") or []
    normalized = []
    for g in guardrails:
        action = str(g.get("action", ""))
        if action != ACTION_SUGGEST_ONLY:
            # The policy schema (and Validate in runtime/recpolicy) only permits
            # suggest_only; refuse to operate on anything that claims otherwise
            # so the advisor can never be repurposed into an auto-actuator.
            raise ValueError(
                f"guardrail metric={g.get('metric')!r} action={action!r} != "
                f"{ACTION_SUGGEST_ONLY!r}; advisor refuses to run"
            )
        normalized.append(
            {
                "metric": str(g.get("metric", "")),
                "baselinePreset": str(g.get("baselinePreset", default_preset)),
                "minRatio": float(g.get("minRatio", 1.0)),
                "minSamples": int(g.get("minSamples", 0)),
                "window": str(g.get("window", "")),
                "action": action,
            }
        )
    return policy_version, default_preset, normalized


def cohort_key(c: dict) -> str:
    return f"{c.get('preset','?')}|seg={c.get('segment','none')}|bucket={c.get('bucket','?')}"


def find_baseline(cohorts: list[dict], baseline_preset: str) -> dict | None:
    # Baseline is the aggregate (segment none) cohort on the baseline preset.
    candidates = [
        c
        for c in cohorts
        if c.get("preset") == baseline_preset and (c.get("segment", "none") in ("none", "", None))
    ]
    if candidates:
        return max(candidates, key=lambda c: int(c.get("samples", 0)))
    # Fall back to any cohort on the baseline preset.
    matches = [c for c in cohorts if c.get("preset") == baseline_preset]
    return max(matches, key=lambda c: int(c.get("samples", 0))) if matches else None


def evaluate(cohorts: list[dict], guardrails: list[dict], policy_version: str) -> dict:
    findings: list[dict] = []
    # Per-candidate roll-up of guardrail outcomes.
    candidate_verdicts: dict[str, dict] = {}

    def note(candidate_key: str, candidate: dict, verdict: str, reason: str):
        entry = candidate_verdicts.setdefault(
            candidate_key,
            {
                "cohort": candidate_key,
                "preset": candidate.get("preset"),
                "segment": candidate.get("segment", "none"),
                "bucket": candidate.get("bucket"),
                "verdict": VERDICT_RECOMMEND_REVIEW,
                "reasons": [],
                "action": ACTION_SUGGEST_ONLY,
            },
        )
        entry["reasons"].append(reason)
        # Worst verdict wins: reject > hold > recommend_review.
        order = {VERDICT_RECOMMEND_REVIEW: 0, VERDICT_HOLD: 1, VERDICT_REJECT: 2}
        if order[verdict] > order[entry["verdict"]]:
            entry["verdict"] = verdict

    for g in guardrails:
        metric = g["metric"]
        baseline = find_baseline(cohorts, g["baselinePreset"])
        for c in cohorts:
            if c.get("preset") == g["baselinePreset"] and c.get("segment", "none") in ("none", "", None):
                continue  # baseline vs itself: skip
            ck = cohort_key(c)
            cand_metric = float((c.get("metrics") or {}).get(metric, 0.0))
            cand_samples = int(c.get("samples", 0))
            if baseline is None:
                note(ck, c, VERDICT_HOLD, f"{metric}: missing baseline preset {g['baselinePreset']}")
                findings.append({"cohort": ck, "metric": metric, "status": "no_baseline"})
                continue
            base_metric = float((baseline.get("metrics") or {}).get(metric, 0.0))
            base_samples = int(baseline.get("samples", 0))
            if cand_samples < g["minSamples"] or base_samples < g["minSamples"]:
                note(ck, c, VERDICT_HOLD, f"{metric}: samples<{g['minSamples']} (cand={cand_samples}, base={base_samples})")
                findings.append({"cohort": ck, "metric": metric, "status": "insufficient_samples",
                                 "candidateSamples": cand_samples, "baselineSamples": base_samples})
                continue
            ratio = (cand_metric / base_metric) if base_metric > 0 else 0.0
            status = "meets_floor" if ratio >= g["minRatio"] else "below_floor"
            if status == "below_floor":
                note(ck, c, VERDICT_REJECT,
                     f"{metric}: ratio {ratio:.3f} < floor {g['minRatio']} (cand={cand_metric}, base={base_metric})")
            else:
                note(ck, c, VERDICT_RECOMMEND_REVIEW,
                     f"{metric}: ratio {ratio:.3f} >= floor {g['minRatio']}")
            findings.append({
                "cohort": ck, "metric": metric, "status": status,
                "ratio": round(ratio, 4), "minRatio": g["minRatio"],
                "candidate": cand_metric, "baseline": base_metric,
            })

    suggestions = sorted(candidate_verdicts.values(), key=lambda e: e["cohort"])
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "policyVersion": policy_version,
        "guardrails": guardrails,
        "findings": findings,
        "suggestions": suggestions,
    }


def metrics_from_file(path: str) -> tuple[list[dict], str]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cohorts") or [], str(data.get("policyVersion", ""))


def metrics_from_mongo(uri: str, db_name: str, scenario: str, window_hours: int) -> list[dict]:  # pragma: no cover - needs live mongo
    from pymongo import MongoClient
    from datetime import timedelta

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        coll = client[db_name]["rec_learning_events"]
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        # Group impressions/engagements by the resolved scoring preset label.
        cohorts: dict[str, dict] = {}

        def bucket_of(doc: dict) -> str:
            labels = doc.get("labels") or {}
            return str(labels.get("scoringPreset") or labels.get("bucket") or "control")

        for doc in coll.find({"eventType": "rec_impression", "scenario": scenario, "createdAt": {"$gte": since}}):
            b = bucket_of(doc)
            c = cohorts.setdefault(b, {"preset": b, "segment": "none", "bucket": b, "samples": 0,
                                       "_clicks": 0, "_eng": 0, "metrics": {}})
            c["samples"] += 1
        for doc in coll.find({"eventType": "rec_engagement", "scenario": scenario, "createdAt": {"$gte": since}}):
            b = bucket_of(doc)
            c = cohorts.setdefault(b, {"preset": b, "segment": "none", "bucket": b, "samples": 0,
                                       "_clicks": 0, "_eng": 0, "metrics": {}})
            action = str((doc.get("labels") or {}).get("action", ""))
            if action == "click":
                c["_clicks"] += 1
            if action in ("click", "like", "favorite", "share", "comment", "follow"):
                c["_eng"] += 1
        for c in cohorts.values():
            imp = max(c["samples"], 1)
            c["metrics"]["ctr"] = c.pop("_clicks") / imp
            c["metrics"]["engagement"] = c.pop("_eng") / imp
        return list(cohorts.values())
    finally:
        client.close()


def simulate_url(base: str, policy_id: str) -> str:
    """Build the product-ops :simulate URL. There is intentionally NO activate
    counterpart in this module. Asserts the suffix so a typo can never escalate."""
    base = base.rstrip("/")
    url = f"{base}/v1/control-plane/product/recommendation/policies/{policy_id}:simulate"
    assert url.endswith(":simulate"), "advisor only ever calls :simulate"
    assert ":activate" not in url, "advisor must never call :activate"
    return url


def call_simulate(base: str, policy_id: str, timeout: float = 5.0) -> dict:  # pragma: no cover - needs live product-ops
    url = simulate_url(base, policy_id)
    req = urllib.request.Request(url, data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description="推荐策略顾问（只产建议 + 至多 :simulate）")
    p.add_argument("--policy", default=os.environ.get("REC_POLICY_PATH", REPO_DEFAULT_POLICY),
                   help="policy.yaml 路径（guardrails 真相源）")
    p.add_argument("--metrics-file", default="", help="cohort 指标 JSON（规范、可单测）")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", ""),
                   help="从 rec_learning_events 聚合（便捷）")
    p.add_argument("--db", default=os.environ.get("MONGODB_DATABASE", "quwoquan"))
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--window-hours", type=int, default=24)
    p.add_argument("--output", default="", help="报告写入路径（默认 stdout）")
    p.add_argument("--simulate", action="store_true",
                   help="把候选推进到 product-ops :simulate（停在 simulated；绝不 activate）")
    p.add_argument("--policy-id", default="", help="--simulate 时的目标 policy id")
    p.add_argument("--product-ops-url", default=os.environ.get("PRODUCT_OPS_URL", ""))
    args = p.parse_args()

    # Hard guard: a caller can only ever ask for :simulate. Reject any attempt
    # to smuggle an activate intent through the policy id.
    if args.policy_id and ":activate" in args.policy_id:
        print("FAIL: advisor never activates; policy-id must not contain ':activate'", file=sys.stderr)
        return 2

    try:
        policy_version, _default_preset, guardrails = load_guardrails(args.policy)
    except (OSError, ValueError) as e:
        print(f"FAIL: load guardrails: {e}", file=sys.stderr)
        return 2

    if args.metrics_file:
        cohorts, file_version = metrics_from_file(args.metrics_file)
        if file_version:
            policy_version = file_version
    elif args.mongodb_uri:
        cohorts = metrics_from_mongo(args.mongodb_uri, args.db, args.scenario, args.window_hours)
    else:
        print("FAIL: provide --metrics-file or --mongodb-uri", file=sys.stderr)
        return 2

    report = evaluate(cohorts, guardrails, policy_version)

    simulate_result = None
    if args.simulate:
        if not (args.policy_id and args.product_ops_url):
            print("FAIL: --simulate requires --policy-id and --product-ops-url", file=sys.stderr)
            return 2
        simulate_result = call_simulate(args.product_ops_url, args.policy_id)
        report["simulate"] = {
            "calledEndpoint": ":simulate",
            "policyId": args.policy_id,
            "result": simulate_result,
            "note": "stopped at simulated; activation is a separate human double-review",
        }

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
        print(f"rec-policy advisor report written to {args.output}", file=sys.stderr)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
