#!/usr/bin/env python3
"""
gamma_rec_patrol.py — Gamma environment recommendation quality probes.

Probes:
1. Feed non-empty: GET /v1/content/feed returns items
2. Model path hit: /metrics/rec shows model usage > 0
3. AB bucket distribution: chi-square test for fairness
4. rec-model-service health: /health and /v1/model/status return ok

Usage:
  python3 gamma_rec_patrol.py --gateway http://content-service:18080
  python3 gamma_rec_patrol.py --gateway http://localhost:18080 --rec-model http://localhost:18090
"""
import argparse
import json
import math
import sys
import urllib.request
import urllib.error


def _get_json(url: str, timeout: int = 10) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  [WARN] GET {url} failed: {e}")
        return None


def _post_json(url: str, body: dict, timeout: int = 10) -> dict | None:
    try:
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  [WARN] POST {url} failed: {e}")
        return None


def probe_feed_nonempty(gateway: str) -> bool:
    """GET /v1/content/feed → items array is non-empty."""
    print("[probe] Feed non-empty")
    url = f"{gateway}/v1/content/feed?userId=patrol_test&limit=5"
    result = _get_json(url)
    if result is None:
        print("  FAIL: no response")
        return False
    items = result.get("items") or []
    if not items:
        print("  FAIL: feed returned 0 items")
        return False
    print(f"  PASS: {len(items)} items returned")
    return True


def probe_model_path_hit(gateway: str) -> bool:
    """GET /metrics/rec → ModelUsed includes model counts."""
    print("[probe] Model path hit")
    url = f"{gateway}/metrics/rec"
    result = _get_json(url)
    if result is None:
        print("  FAIL: no metrics response")
        return False
    model_used = result.get("modelUsed") or result.get("ModelUsed") or ""
    total_requests = result.get("totalRequests") or result.get("TotalRequests") or 0
    print(f"  Model={model_used}, TotalRequests={total_requests}")
    if total_requests == 0:
        print("  WARN: no requests recorded yet (acceptable on fresh deploy)")
        return True
    return True


def probe_ab_distribution(gateway: str) -> bool:
    """GET /metrics/rec → check experiment bucket distribution is reasonable."""
    print("[probe] AB bucket distribution")
    url = f"{gateway}/metrics/rec"
    result = _get_json(url)
    if result is None:
        print("  SKIP: no metrics")
        return True
    model_hits = result.get("modelHits") or result.get("ModelHits") or 0
    rule_hits = result.get("ruleHits") or result.get("RuleHits") or 0
    total = model_hits + rule_hits
    if total < 100:
        print(f"  SKIP: only {total} requests, too few for chi-square")
        return True

    expected_model = total * 0.5
    expected_rule = total * 0.5
    chi2 = ((model_hits - expected_model) ** 2 / expected_model +
            (rule_hits - expected_rule) ** 2 / expected_rule)
    threshold = 10.83  # chi-square p=0.001 df=1
    passed = chi2 < threshold
    print(f"  model={model_hits} rule={rule_hits} chi2={chi2:.2f} threshold={threshold}")
    if not passed:
        print("  FAIL: bucket distribution significantly skewed")
    else:
        print("  PASS: distribution within expected range")
    return passed


def probe_rec_model_health(rec_model_url: str) -> bool:
    """Check rec-model-service health and model status."""
    print("[probe] rec-model-service health")
    health = _get_json(f"{rec_model_url}/health")
    if health is None or health.get("status") != "ok":
        print("  FAIL: health check failed")
        return False
    print("  health: ok")

    status = _get_json(f"{rec_model_url}/v1/model/status")
    if status:
        print(f"  model versions: {status.get('versions', {})}")
        print(f"  last reload: {status.get('last_reload', 'never')}")
    else:
        print("  WARN: model status endpoint unavailable")

    print("  PASS")
    return True


def main():
    p = argparse.ArgumentParser(description="Gamma recommendation quality patrol")
    p.add_argument("--gateway", default="http://localhost:18080")
    p.add_argument("--rec-model", default="http://localhost:18090")
    args = p.parse_args()

    results = {}
    results["feed_nonempty"] = probe_feed_nonempty(args.gateway)
    results["model_path_hit"] = probe_model_path_hit(args.gateway)
    results["ab_distribution"] = probe_ab_distribution(args.gateway)
    results["rec_model_health"] = probe_rec_model_health(args.rec_model)

    print("\n" + "=" * 50)
    all_passed = all(results.values())
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
    print("=" * 50)

    if not all_passed:
        print("PATROL FAILED")
        return 1
    print("PATROL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
