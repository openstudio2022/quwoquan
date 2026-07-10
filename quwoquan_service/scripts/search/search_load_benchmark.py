#!/usr/bin/env python3
"""可重复的搜索高并发压测工具（stdlib-only，无外部依赖）。

驱动 search-service 的 /v1/search 与 /v1/search/feedback，按 search_slo.yaml#load_model
冻结的负载模型计算分位数/错误率/降级率，并对照 target 给出每场景 GO/NO-GO。

设计要点（吸收业界搜索压测实践）：
- 闭环并发模型：N 个 worker 持续循环发请求，报告实测 RPS（吞吐 = 并发/平均延迟的自然结果）。
- 场景区分 warm/cold cache：warm 固定热点 query（命中相关词缓存 + ES query cache），
  cold 轮转大量唯一 query（强制 miss），用于暴露穿透后端的真实成本。
- 统计真分位数（排序取值，绝不用算术平均替代 P95/P99）。
- 把 429/503 计为受控 shed，与真正 5xx error 区分；shed 不算可用性失败但计入退化。
- 报告落盘 .qwq_output/env/repo/runs/search-load/，可重复对比。

注意：本工具产出的是“被测环境”的数字。local-gamma 单节点 ES 不代表生产；真集群/prod-sim
数字才用于关闭 R-S06-S-1。无被测服务时退化为 dry-run（仍校验脚本可运行 + 报告 schema）。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

DEFAULT_BASE_URL = "http://127.0.0.1:19280"
SLO_REL = (
    "quwoquan_service/services/search-service/configs/observability/search_slo.yaml"
)

# 热点 query（warm）+ 长尾池（cold）。中文按真实索引内容选取，便于命中/不命中。
HOT_QUERIES = ["成都", "火锅", "九寨沟"]
COLD_PREFIXES = ["成都", "重庆", "西藏", "云南", "大理", "丽江", "青城山", "峨眉山", "都江堰", "宽窄巷子"]
COLD_SUFFIXES = ["攻略", "美食", "线路", "周末", "亲子", "自驾", "小众", "避坑", "三日", "人均"]


@dataclass
class Sample:
    latency_ms: float
    status: int
    degraded: bool
    error: bool
    # kind 区分受控退化与真实失败：
    #   ok                  正常 2xx
    #   rate_limited        429 全局限流（受控）
    #   backpressure_shed   503 in-flight 背压 shed（受控，本服务主动）
    #   upstream_unavailable 503 ES 检索失败/超时（可用性失败，需扩容/真集群）
    #   client_error        4xx（非 429）
    #   transport_error     连接/超时/未知（真实失败）
    kind: str = "ok"


@dataclass
class Result:
    scenario: str
    samples: list = field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cold_query(rng: random.Random) -> str:
    return rng.choice(COLD_PREFIXES) + rng.choice(COLD_SUFFIXES) + str(rng.randint(0, 9999))


def _build_request(scenario: str, rng: random.Random) -> tuple[str, dict]:
    """返回 (path, json_body)。"""
    if scenario == "feedback":
        return "/v1/search/feedback", {
            "searchRequestId": f"load-{rng.randint(0, 1 << 30)}",
            "eventType": rng.choice(["impression", "click", "dwell"]),
            "objectId": "posts/article/index/load/1",
            "rankPosition": rng.randint(1, 10),
        }
    if scenario in ("result_warm", "suggest_warm"):
        query = rng.choice(HOT_QUERIES)
    else:  # cold / mixed-cold
        query = _cold_query(rng)
    mode = "suggest" if scenario.startswith("suggest") else "result"
    limit = 12 if mode == "suggest" else 20
    return "/v1/search", {"query": query, "mode": mode, "limit": limit}


def _pick_mixed(rng: random.Random) -> str:
    # 业界混合读写：以读为主，feedback 写入次之；冷热混合暴露缓存命中曲线。
    r = rng.random()
    if r < 0.45:
        return "result_warm"
    if r < 0.75:
        return "result_cold"
    if r < 0.90:
        return "suggest_warm"
    return "feedback"


def _do_one(base_url: str, scenario: str, rng: random.Random, timeout: float, user_id: str) -> Sample:
    eff = _pick_mixed(rng) if scenario == "mixed" else scenario
    path, body = _build_request(eff, rng)
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base_url + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    # 稳定 subject 注入（与 AB 粘性/可重复性一致）：每个 worker 固定 user/session。
    req.add_header("X-User-Id", user_id)
    req.add_header("X-Session-Id", "load-" + user_id)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
            elapsed = (time.perf_counter() - start) * 1000.0
            degraded = b'"degradeSignals"' in payload and b'"degradeSignals":[]' not in payload
            return Sample(elapsed, resp.status, degraded, error=False, kind="ok")
    except urllib.error.HTTPError as e:
        elapsed = (time.perf_counter() - start) * 1000.0
        body = b""
        try:
            body = e.read()
        except Exception:
            pass
        kind = _classify_http_error(e.code, body)
        # 受控退化（429 限流 / 背压 shed）不计可用性 error；ES 不可用/4xx/未知计 error。
        is_controlled = kind in ("rate_limited", "backpressure_shed")
        return Sample(elapsed, e.code, degraded=is_controlled, error=not is_controlled, kind=kind)
    except Exception:
        elapsed = (time.perf_counter() - start) * 1000.0
        return Sample(elapsed, 0, degraded=False, error=True, kind="transport_error")


def _classify_http_error(code: int, body: bytes) -> str:
    if code == 429:
        return "rate_limited"
    if code == 503:
        text = body.decode("utf-8", "ignore")
        # search-service 背压 shed 的用户文案/调试串（见 MaxInflightMiddleware）。
        if "inflight" in text or "繁忙" in text:
            return "backpressure_shed"
        return "upstream_unavailable"
    if 400 <= code < 500:
        return "client_error"
    return "transport_error"


def run_scenario(base_url: str, scenario: str, duration: float, concurrency: int, timeout: float) -> Result:
    deadline = time.perf_counter() + duration
    res = Result(scenario=scenario)
    lock = threading.Lock()

    def worker(idx: int):
        rng = random.Random(1000 + idx)  # 固定种子 → 可重复负载序列
        user_id = f"loaduser-{idx % 64}"  # 有限用户集合 → 稳定 AB bucket 分布
        local = []
        while time.perf_counter() < deadline:
            local.append(_do_one(base_url, scenario, rng, timeout, user_id))
        with lock:
            res.samples.extend(local)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for i in range(concurrency):
            pool.submit(worker, i)
    return res


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def summarize(res: Result, duration: float, concurrency: int) -> dict:
    lat = sorted(s.latency_ms for s in res.samples)
    total = len(res.samples)
    errors = sum(1 for s in res.samples if s.error)
    rate_limited = sum(1 for s in res.samples if s.kind == "rate_limited")
    backpressure = sum(1 for s in res.samples if s.kind == "backpressure_shed")
    upstream = sum(1 for s in res.samples if s.kind == "upstream_unavailable")
    shed = rate_limited + backpressure  # 受控退化
    degraded = sum(1 for s in res.samples if s.degraded)
    status_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    for s in res.samples:
        status_counts[str(s.status)] = status_counts.get(str(s.status), 0) + 1
        kind_counts[s.kind] = kind_counts.get(s.kind, 0) + 1
    achieved_rps = total / duration if duration > 0 else 0.0
    # 成功延迟分位数：仅统计正常 ok 请求，避免快速 429/503 拉低分位数失真。
    ok_lat = sorted(s.latency_ms for s in res.samples if s.kind == "ok")
    return {
        "scenario": res.scenario,
        "duration_sec": round(duration, 2),
        "concurrency": concurrency,
        "total_requests": total,
        "achieved_rps": round(achieved_rps, 1),
        "error_count": errors,
        "error_rate": round(errors / total, 5) if total else 0.0,
        "upstream_unavailable_count": upstream,
        "rate_limited_count": rate_limited,
        "backpressure_shed_count": backpressure,
        "shed_count": shed,
        "shed_rate": round(shed / total, 5) if total else 0.0,
        "degrade_count": degraded,
        "degrade_rate": round(degraded / total, 5) if total else 0.0,
        "status_counts": status_counts,
        "kind_counts": kind_counts,
        "ok_count": len(ok_lat),
        "ok_latency_ms": {
            "p50": round(_percentile(ok_lat, 0.50), 1),
            "p95": round(_percentile(ok_lat, 0.95), 1),
            "p99": round(_percentile(ok_lat, 0.99), 1),
        },
        "latency_ms": {
            "p50": round(_percentile(lat, 0.50), 1),
            "p90": round(_percentile(lat, 0.90), 1),
            "p95": round(_percentile(lat, 0.95), 1),
            "p99": round(_percentile(lat, 0.99), 1),
            "max": round(lat[-1], 1) if lat else 0.0,
            "mean": round(statistics.fmean(lat), 1) if lat else 0.0,
        },
    }


# scenario → load_model traffic class（用于读取 target 阈值做 GO/NO-GO）
SCENARIO_CLASS = {
    "result_warm": "result",
    "result_cold": "result",
    "suggest_warm": "suggest",
    "suggest_cold": "suggest",
    "feedback": "feedback",
    "mixed": "result",
}


def load_slo_targets(repo_root: str) -> dict:
    path = os.path.join(repo_root, SLO_REL)
    try:
        import yaml  # type: ignore

        with open(path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        return doc.get("load_model", {}).get("traffic_classes", {})
    except Exception:
        return {}


def verdict(summary: dict, targets: dict) -> dict:
    cls = SCENARIO_CLASS.get(summary["scenario"], "result")
    tgt = targets.get(cls, {})
    checks = []
    ok = True
    p95_target = (tgt.get("server_latency_ms") or {}).get("p95")
    if p95_target is not None:
        # 用成功请求 p95（ok_latency）对照目标，避免快速失败拉低/拉高失真。
        actual_p95 = summary.get("ok_latency_ms", {}).get("p95", summary["latency_ms"]["p95"])
        passed = actual_p95 <= p95_target
        ok = ok and passed
        checks.append({"metric": "ok_p95_ms", "actual": actual_p95, "target_max": p95_target, "pass": passed})
    err_target = tgt.get("error_rate_max")
    if err_target is not None:
        passed = summary["error_rate"] <= err_target
        ok = ok and passed
        checks.append({"metric": "error_rate", "actual": summary["error_rate"], "target_max": err_target, "pass": passed})
    deg_target = tgt.get("degrade_rate_max")
    if deg_target is not None:
        passed = summary["degrade_rate"] <= deg_target
        ok = ok and passed
        checks.append({"metric": "degrade_rate", "actual": summary["degrade_rate"], "target_max": deg_target, "pass": passed})
    return {"traffic_class": cls, "checks": checks, "verdict": "GO" if ok else "NO-GO"}


def reachable(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(base_url + "/healthz", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="搜索高并发压测（stdlib-only，可重复）")
    ap.add_argument("--base-url", default=os.environ.get("SEARCH_LOAD_BASE_URL", DEFAULT_BASE_URL))
    ap.add_argument(
        "--scenario",
        default="result_warm",
        choices=list(SCENARIO_CLASS.keys()) + ["all"],
    )
    ap.add_argument("--duration-sec", type=float, default=10.0)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--timeout-sec", type=float, default=5.0)
    ap.add_argument("--out-dir", default=".qwq_output/env/repo/runs/search-load")
    ap.add_argument("--repo-root", default=os.getcwd())
    args = ap.parse_args()

    targets = load_slo_targets(args.repo_root)
    if not targets:
        print("WARN: 未能读取 search_slo.yaml load_model（缺 pyyaml？），GO/NO-GO 仅记录实测值", file=sys.stderr)

    live = reachable(args.base_url)
    if not live:
        print(f"WARN: {args.base_url} 不可达，进入 dry-run（仅校验脚本与报告 schema）", file=sys.stderr)

    scenarios = list(SCENARIO_CLASS.keys()) if args.scenario == "all" else [args.scenario]
    report = {
        "tool": "search_load_benchmark.py",
        "generated_at": _now_iso(),
        "base_url": args.base_url,
        "live": live,
        "config": {
            "duration_sec": args.duration_sec,
            "concurrency": args.concurrency,
            "timeout_sec": args.timeout_sec,
        },
        "slo_load_model_present": bool(targets),
        "scenarios": [],
    }

    for scenario in scenarios:
        if not live:
            summary = {"scenario": scenario, "skipped": "service_unreachable"}
            report["scenarios"].append({"summary": summary, "verdict": {"verdict": "SKIPPED"}})
            continue
        print(f"[load] scenario={scenario} dur={args.duration_sec}s conc={args.concurrency} ...", file=sys.stderr)
        res = run_scenario(args.base_url, scenario, args.duration_sec, args.concurrency, args.timeout_sec)
        summary = summarize(res, args.duration_sec, args.concurrency)
        v = verdict(summary, targets) if targets else {"verdict": "RECORDED_ONLY"}
        report["scenarios"].append({"summary": summary, "verdict": v})
        print(
            f"[load] scenario={scenario} rps={summary['achieved_rps']} "
            f"p95={summary['latency_ms']['p95']}ms p99={summary['latency_ms']['p99']}ms "
            f"err={summary['error_rate']} shed={summary['shed_rate']} -> {v['verdict']}",
            file=sys.stderr,
        )

    overall = "GO"
    for s in report["scenarios"]:
        v = s["verdict"]["verdict"]
        if v == "NO-GO":
            overall = "NO-GO"
            break
        if v in ("SKIPPED", "RECORDED_ONLY") and overall == "GO":
            overall = v
    report["overall_verdict"] = overall

    os.makedirs(args.out_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = args.scenario
    out_path = os.path.join(args.out_dir, f"search_load_{tag}_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[load] report -> {out_path} overall={overall}", file=sys.stderr)
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
