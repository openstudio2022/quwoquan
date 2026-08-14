#!/usr/bin/env python3
"""可重复的推荐 feed 高并发压测画像（stdlib-only，无外部依赖）。

驱动网关的 GET /content/feed（channelId=recommend 推荐主链路）与
POST /content/behaviors，按 recommendation_slo.yaml#load_model 冻结的负载模型
计算真分位数/错误率/受控 shed 率，并对照 target 给出每场景 GO/NO-GO。
与 quwoquan_service/scripts/search-service/tools/search_load_benchmark.py 同一
方法论与报告口径，搜推压测证据可绑定同一候选 release 一次采集。

场景与 load_model traffic class 的对应：

  first_page  → feed_first_page：每次请求新 session（触发排序窗口创建 +
                召回 + 打分，冷路径成本）。
  pagination  → feed_pagination：worker 固定 session，首刷后沿 nextCursor
                连续续页（不可变 RankedFeedWindow 只读路径）；首刷请求不计入
                本场景样本。
  behavior    → behavior_ingest：impression/dwell batch 上报（clientEventId
                幂等，feedRequestId 归因来自真实首刷响应）。
  mixed       → 业界混合画像：续页为主、首刷次之、行为写入常态化。

model_score（internal API，principal=service）不经网关，不在本画像内；
其压测由 `stackctl loadtest --operation recommendation/...#ScoreRecommendationCandidates`
与 capacity 预算合约测试承载。

统计口径：闭环并发（N worker 循环压满）、真分位数（排序取值）、429/503 计为
受控 shed 不计可用性失败但计入退化。无被测服务时退化为 dry-run（仅校验脚本
与报告 schema）。报告落 .qwq_output/env/<env>/observability/recommendation-load/。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import ssl
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# 本地管理 TLS 环境（*-local）的网关根证书；由 --ca-file 注入，走正常验证。
_SSL_CONTEXT: ssl.SSLContext | None = None
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:19000"
SLO_REL = (
    "quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml"
)


def _default_out_dir(env: str) -> str:
    return str(
        Path(
            os.environ.get(
                "QWQ_OUTPUT_ROOT",
                # scripts/recommendation-service/tools/ 相对仓库根共四级。
                Path(__file__).resolve().parents[4] / ".qwq_output",
            )
        )
        / "env"
        / env
        / "observability"
        / "recommendation-load"
    )


@dataclass
class Sample:
    latency_ms: float
    status: int
    error: bool
    #   ok                  正常 2xx
    #   rate_limited        429 全局限流（受控）
    #   backpressure_shed   503 背压 shed（受控）
    #   upstream_unavailable 503 依赖失败（可用性失败）
    #   client_error        4xx（非 429）
    #   transport_error     连接/超时/未知（真实失败）
    kind: str = "ok"


@dataclass
class Result:
    scenario: str
    samples: list = field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify_http_error(code: int, body: bytes) -> str:
    if code == 429:
        return "rate_limited"
    if code == 503:
        text = body.decode("utf-8", "ignore")
        if "inflight" in text or "繁忙" in text:
            return "backpressure_shed"
        return "upstream_unavailable"
    if 400 <= code < 500:
        return "client_error"
    return "transport_error"


def _http(
    base_url: str,
    method: str,
    path: str,
    *,
    session_id: str,
    token: str,
    timeout: float,
    query: dict | None = None,
    body: dict | None = None,
) -> tuple[Sample, dict | None]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = None
    req = urllib.request.Request(url, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("X-Client-Session-Id", session_id)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(
            req, data=data, timeout=timeout, context=_SSL_CONTEXT
        ) as resp:
            payload = resp.read()
            elapsed = (time.perf_counter() - start) * 1000.0
            parsed = None
            try:
                parsed = json.loads(payload)
            except Exception:
                pass
            return Sample(elapsed, resp.status, error=False, kind="ok"), parsed
    except urllib.error.HTTPError as e:
        elapsed = (time.perf_counter() - start) * 1000.0
        raw = b""
        try:
            raw = e.read()
        except Exception:
            pass
        kind = _classify_http_error(e.code, raw)
        controlled = kind in ("rate_limited", "backpressure_shed")
        return Sample(elapsed, e.code, error=not controlled, kind=kind), None
    except Exception:
        elapsed = (time.perf_counter() - start) * 1000.0
        return Sample(elapsed, 0, error=True, kind="transport_error"), None


def _feed_query(cursor: str | None, feed_request_id: str | None, limit: int) -> dict:
    query = {"channelId": "recommend", "sort": "recommend", "limit": str(limit)}
    if cursor:
        query["cursor"] = cursor
    if feed_request_id:
        query["feedRequestId"] = feed_request_id
    return query


def _behavior_body(rng: random.Random, feed_request_id: str, content_id: str) -> dict:
    action = rng.choice(["impression", "dwell", "click"])
    event = {
        "clientEventId": f"load-{uuid.uuid4().hex}",
        "occurredAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "contentId": content_id,
        "action": action,
        "feedRequestId": feed_request_id,
        "channelId": "recommend",
    }
    if action == "impression":
        event["state"] = "impressed"
    if action == "dwell":
        event["duration"] = float(rng.randint(2, 30))
    return {"events": [event]}


class _Worker:
    """单 worker 状态机：pagination/mixed 场景维护 session/cursor 连续性。"""

    def __init__(self, idx: int, base_url: str, token: str, timeout: float, limit: int) -> None:
        self.rng = random.Random(1000 + idx)  # 固定种子 → 可重复负载序列
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.limit = limit
        self.session_id = f"load-rec-{idx}-{uuid.uuid4().hex[:8]}"
        self.cursor: str | None = None
        self.feed_request_id: str | None = None
        self.last_content_id: str | None = None

    def _consume_feed(self, parsed: dict | None) -> None:
        if not isinstance(parsed, dict):
            self.cursor = None
            return
        self.cursor = (parsed.get("nextCursor") or "").strip() or None
        self.feed_request_id = (parsed.get("feedRequestId") or "").strip() or None
        items = parsed.get("items") or []
        if items and isinstance(items[0], dict):
            content_id = str(
                items[0].get("postId") or items[0].get("id") or ""
            ).strip()
            self.last_content_id = content_id or self.last_content_id

    def first_page(self) -> Sample:
        # 每次新 session → 每次都是窗口创建冷路径。
        self.session_id = f"load-rec-first-{uuid.uuid4().hex[:12]}"
        sample, parsed = _http(
            self.base_url,
            "GET",
            "/content/feed",
            session_id=self.session_id,
            token=self.token,
            timeout=self.timeout,
            query=_feed_query(None, None, self.limit),
        )
        self._consume_feed(parsed)
        return sample

    def continuation(self) -> tuple[Sample, bool]:
        """返回 (sample, is_continuation)。cursor 耗尽时做一次首刷（不计样本）。"""
        if not self.cursor:
            self.session_id = f"load-rec-page-{uuid.uuid4().hex[:12]}"
            warmup, parsed = _http(
                self.base_url,
                "GET",
                "/content/feed",
                session_id=self.session_id,
                token=self.token,
                timeout=self.timeout,
                query=_feed_query(None, None, self.limit),
            )
            self._consume_feed(parsed)
            if warmup.error or not self.cursor:
                # 首刷失败或无续页：把首刷样本计为该轮样本，避免死循环空转。
                return warmup, False
        sample, parsed = _http(
            self.base_url,
            "GET",
            "/content/feed",
            session_id=self.session_id,
            token=self.token,
            timeout=self.timeout,
            query=_feed_query(self.cursor, self.feed_request_id, self.limit),
        )
        self._consume_feed(parsed)
        return sample, True

    def behavior(self) -> Sample:
        if not self.feed_request_id or not self.last_content_id:
            warmup = self.first_page()
            if warmup.error or not self.feed_request_id or not self.last_content_id:
                return warmup
        sample, _ = _http(
            self.base_url,
            "POST",
            "/content/behaviors",
            session_id=self.session_id,
            token=self.token,
            timeout=self.timeout,
            body=_behavior_body(self.rng, self.feed_request_id, self.last_content_id),
        )
        return sample

    def step(self, scenario: str) -> tuple[Sample, str]:
        eff = scenario
        if scenario == "mixed":
            # 业界混合画像：续页为主（55%）、首刷次之（25%）、行为写入 20%。
            r = self.rng.random()
            eff = "pagination" if r < 0.55 else ("first_page" if r < 0.80 else "behavior")
        if eff == "first_page":
            return self.first_page(), "first_page"
        if eff == "behavior":
            return self.behavior(), "behavior"
        sample, is_continuation = self.continuation()
        return sample, "pagination" if is_continuation else "first_page"


def run_scenario(
    base_url: str,
    scenario: str,
    duration: float,
    concurrency: int,
    timeout: float,
    token: str,
    limit: int,
) -> dict[str, Result]:
    deadline = time.perf_counter() + duration
    results: dict[str, Result] = {}
    lock = threading.Lock()

    def worker(idx: int) -> None:
        state = _Worker(idx, base_url, token, timeout, limit)
        local: list[tuple[str, Sample]] = []
        while time.perf_counter() < deadline:
            sample, effective = state.step(scenario)
            local.append((effective, sample))
        with lock:
            for effective, sample in local:
                results.setdefault(effective, Result(scenario=effective)).samples.append(sample)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(concurrency)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


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
    shed = sum(1 for s in res.samples if s.kind in ("rate_limited", "backpressure_shed"))
    status_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    for s in res.samples:
        status_counts[str(s.status)] = status_counts.get(str(s.status), 0) + 1
        kind_counts[s.kind] = kind_counts.get(s.kind, 0) + 1
    ok_lat = sorted(s.latency_ms for s in res.samples if s.kind == "ok")
    return {
        "scenario": res.scenario,
        "duration_sec": round(duration, 2),
        "concurrency": concurrency,
        "total_requests": total,
        "achieved_rps": round(total / duration, 1) if duration > 0 else 0.0,
        "error_count": errors,
        "error_rate": round(errors / total, 5) if total else 0.0,
        "shed_count": shed,
        "shed_rate": round(shed / total, 5) if total else 0.0,
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


# 有效场景 → load_model traffic class（读取 target 阈值做 GO/NO-GO）
SCENARIO_CLASS = {
    "first_page": "feed_first_page",
    "pagination": "feed_pagination",
    "behavior": "behavior_ingest",
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
    cls = SCENARIO_CLASS.get(summary["scenario"], "feed_first_page")
    tgt = targets.get(cls, {})
    checks = []
    ok = True
    p95_target = (tgt.get("server_latency_ms") or {}).get("p95")
    if p95_target is not None:
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
        passed = summary["shed_rate"] <= deg_target
        ok = ok and passed
        checks.append({"metric": "shed_rate", "actual": summary["shed_rate"], "target_max": deg_target, "pass": passed})
    return {"traffic_class": cls, "checks": checks, "verdict": "GO" if ok else "NO-GO"}


def reachable(base_url: str) -> bool:
    for probe in ("/healthz", "/health"):
        try:
            with urllib.request.urlopen(
                base_url.rstrip("/") + probe, timeout=2, context=_SSL_CONTEXT
            ) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            continue
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="推荐 feed 高并发压测画像（stdlib-only，可重复）")
    ap.add_argument("--base-url", default=os.environ.get("REC_LOAD_BASE_URL", DEFAULT_BASE_URL))
    ap.add_argument("--env", default="gamma", choices=("alpha", "beta", "gamma"))
    ap.add_argument(
        "--scenario",
        default="mixed",
        choices=list(SCENARIO_CLASS.keys()) + ["mixed", "all"],
    )
    ap.add_argument("--duration-sec", type=float, default=15.0)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--timeout-sec", type=float, default=5.0)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument(
        "--test-auth-token",
        default=os.environ.get("GAMMA_TEST_AUTH_TOKEN") or os.environ.get("TEST_AUTH_TOKEN") or "",
    )
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--repo-root", default=os.getcwd())
    ap.add_argument(
        "--ca-file",
        default=os.environ.get("QWQ_PROBE_CA_FILE", ""),
        help="本地管理 TLS 环境（*-local）的根证书路径",
    )
    args = ap.parse_args()

    if args.env == "prod":  # argparse 已挡，双保险：压测不打生产
        print("prod is refused", file=sys.stderr)
        return 1
    if args.ca_file:
        global _SSL_CONTEXT
        _SSL_CONTEXT = ssl.create_default_context(cafile=args.ca_file)

    targets = load_slo_targets(args.repo_root)
    if not targets:
        print(
            "WARN: 未能读取 recommendation_slo.yaml load_model（缺 pyyaml？），GO/NO-GO 仅记录实测值",
            file=sys.stderr,
        )

    live = reachable(args.base_url)
    if not live:
        print(f"WARN: {args.base_url} 不可达，进入 dry-run（仅校验脚本与报告 schema）", file=sys.stderr)

    scenarios = (
        list(SCENARIO_CLASS.keys()) + ["mixed"] if args.scenario == "all" else [args.scenario]
    )
    report = {
        "tool": "recommendation_load_profile.py",
        "generated_at": _now_iso(),
        "base_url": args.base_url,
        "env": args.env,
        "live": live,
        "config": {
            "duration_sec": args.duration_sec,
            "concurrency": args.concurrency,
            "timeout_sec": args.timeout_sec,
            "limit": args.limit,
        },
        "slo_load_model_present": bool(targets),
        "scenarios": [],
    }

    for scenario in scenarios:
        if not live:
            report["scenarios"].append(
                {
                    "summary": {"scenario": scenario, "skipped": "service_unreachable"},
                    "verdict": {"verdict": "SKIPPED"},
                }
            )
            continue
        print(
            f"[load] scenario={scenario} dur={args.duration_sec}s conc={args.concurrency} ...",
            file=sys.stderr,
        )
        results = run_scenario(
            args.base_url,
            scenario,
            args.duration_sec,
            args.concurrency,
            args.timeout_sec,
            args.test_auth_token,
            args.limit,
        )
        for effective, res in sorted(results.items()):
            summary = summarize(res, args.duration_sec, args.concurrency)
            summary["requested_scenario"] = scenario
            v = verdict(summary, targets) if targets else {"verdict": "RECORDED_ONLY"}
            report["scenarios"].append({"summary": summary, "verdict": v})
            print(
                f"[load] {scenario}/{effective} rps={summary['achieved_rps']} "
                f"ok_p95={summary['ok_latency_ms']['p95']}ms err={summary['error_rate']} "
                f"shed={summary['shed_rate']} -> {v['verdict']}",
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

    out_dir = args.out_dir or _default_out_dir(args.env)
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = os.path.join(out_dir, f"recommendation_load_{args.scenario}_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[load] report -> {out_path} overall={overall}", file=sys.stderr)
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
