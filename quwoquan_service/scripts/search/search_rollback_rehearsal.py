#!/usr/bin/env python3
"""搜索故障/回滚演练（gamma-local）。

对 search-service / Elasticsearch / Redis 注入受控故障，观察搜索主路径的退化语义
（typed degrade / 受控错误 / best-effort 不阻塞），再「回滚到已知良好态」（重启容器）
并验证恢复。产出结构化回滚证据。

回滚粒度（gamma-local）：
  - service rollback   = 重启 search-service 容器（等价于回退到上一个已知良好镜像/配置）
  - dependency restore = 重启 ES / Redis 容器（依赖恢复）
真集群版本回滚（image/config rollout）走 `stackctl deploy --target prod-hosted`，
不在本地演练面内；本脚本演练的是「故障注入 + 恢复（restart-to-known-good）」闭环。

仅用 stdlib + docker CLI。默认面向 gamma-local docker compose 容器名。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

SEARCH_BASE = "http://localhost:19280"
ES_HEALTH = "http://localhost:19430/_cluster/health"

CONTAINERS = {
    "search": "quwoquan_service-search-service-1",
    "elasticsearch": "quwoquan_service-elasticsearch-1",
    "redis": "quwoquan_service-redis-1",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def docker(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=120
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def container_healthy(name: str) -> bool:
    code, out = docker(
        "inspect", "-f", "{{.State.Health.Status}}", name
    )
    return code == 0 and out.strip() == "healthy"


def wait_healthy(name: str, timeout_s: float = 150) -> dict:
    started = time.time()
    while time.time() - started < timeout_s:
        if container_healthy(name):
            return {"healthy": True, "waited_s": round(time.time() - started, 1)}
        time.sleep(2)
    return {"healthy": False, "waited_s": round(time.time() - started, 1)}


def probe_search(query: str = "成都", timeout_s: float = 5.0) -> dict:
    """一次搜索探针；返回 http 码 / 耗时 / provider / 命中数 / 降级信号 / 错误码。"""
    body = json.dumps(
        {
            "query": query,
            "mode": "result",
            "objectTypes": ["content.post", "entity.homepage"],
            "limit": 5,
        }
    ).encode()
    req = urllib.request.Request(
        f"{SEARCH_BASE}/v1/search",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-User-Id": "fixture_user_current",
        },
    )
    started = time.time()
    out: dict = {"ts": now(), "query": query}
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            elapsed = time.time() - started
            payload = json.loads(resp.read().decode())
            out.update(
                http=resp.status,
                elapsed_ms=round(elapsed * 1000, 1),
                provider=(payload.get("provenance") or {}).get("Provider"),
                hit_count=len(payload.get("hits") or []),
                degrade_signals=payload.get("degradeSignals")
                or payload.get("DegradeSignals"),
                experiment_bucket=payload.get("experimentBucket"),
            )
    except urllib.error.HTTPError as e:
        elapsed = time.time() - started
        raw = e.read().decode(errors="replace")
        code = None
        try:
            code = (json.loads(raw).get("error") or {}).get("code")
        except Exception:
            pass
        out.update(
            http=e.code, elapsed_ms=round(elapsed * 1000, 1),
            error_code=code, error_body=raw[:300],
        )
    except Exception as e:  # connection refused / timeout
        elapsed = time.time() - started
        out.update(
            http=None, elapsed_ms=round(elapsed * 1000, 1),
            transport_error=type(e).__name__ + ": " + str(e)[:200],
        )
    return out


def healthz() -> int | None:
    try:
        with urllib.request.urlopen(f"{SEARCH_BASE}/healthz", timeout=3) as r:
            return r.status
    except Exception:
        return None


def scenario_es(report: dict) -> None:
    s = {"name": "es_down_degrade_then_restore", "steps": []}
    s["steps"].append({"step": "baseline", "probe": probe_search()})
    docker("stop", CONTAINERS["elasticsearch"])
    s["steps"].append({"step": "es_stopped", "ts": now()})
    time.sleep(2)
    s["steps"].append({"step": "during_es_down", "probe": probe_search()})
    s["steps"].append({"step": "during_es_down_2", "probe": probe_search("九寨沟")})
    docker("start", CONTAINERS["elasticsearch"])
    s["steps"].append(
        {"step": "es_restart_rollback", "wait": wait_healthy(CONTAINERS["elasticsearch"])}
    )
    # ES 健康后给检索一点缓冲再复验
    time.sleep(3)
    s["steps"].append({"step": "after_restore", "probe": probe_search()})
    report["scenarios"].append(s)


def scenario_redis(report: dict) -> None:
    s = {"name": "redis_down_best_effort_then_restore", "steps": []}
    s["steps"].append({"step": "baseline", "probe": probe_search()})
    docker("stop", CONTAINERS["redis"])
    s["steps"].append({"step": "redis_stopped", "ts": now()})
    time.sleep(2)
    # Redis 仅承载信号发布(best-effort)；检索主路径应仍返回结果。
    s["steps"].append({"step": "during_redis_down", "probe": probe_search()})
    docker("start", CONTAINERS["redis"])
    s["steps"].append(
        {"step": "redis_restart_rollback", "wait": wait_healthy(CONTAINERS["redis"])}
    )
    s["steps"].append(
        {"step": "content_service_health", "healthy": container_healthy(CONTAINERS_CONTENT)}
    )
    s["steps"].append({"step": "after_restore", "probe": probe_search()})
    report["scenarios"].append(s)


CONTAINERS_CONTENT = "quwoquan_service-content-service-1"


def scenario_search_service(report: dict) -> None:
    s = {"name": "search_service_unavailable_then_rollback", "steps": []}
    s["steps"].append({"step": "baseline", "probe": probe_search(), "healthz": healthz()})
    docker("stop", CONTAINERS["search"])
    s["steps"].append({"step": "search_stopped", "ts": now()})
    time.sleep(2)
    # 直连应连接失败（受控不可用，不应 hang）。
    s["steps"].append(
        {"step": "during_search_down", "probe": probe_search(), "healthz": healthz()}
    )
    docker("start", CONTAINERS["search"])
    s["steps"].append(
        {"step": "search_restart_rollback", "wait": wait_healthy(CONTAINERS["search"])}
    )
    s["steps"].append(
        {"step": "after_restore", "probe": probe_search(), "healthz": healthz()}
    )
    report["scenarios"].append(s)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=".qwq_output/local/gamma-local/search_rollback_rehearsal_report.json",
    )
    parser.add_argument(
        "--only",
        choices=["es", "redis", "search", "all"],
        default="all",
    )
    args = parser.parse_args()

    report = {
        "kind": "search_rollback_rehearsal",
        "env": "gamma-local",
        "started_at": now(),
        "rollback_semantics": {
            "service_rollback": "docker restart search-service (= roll back to last known-good image/config locally)",
            "dependency_restore": "docker restart elasticsearch/redis",
            "prod_version_rollback": "stackctl deploy --target prod-hosted (gray-initial/carry-on/full); not in local rehearsal scope",
        },
        "scenarios": [],
    }
    if args.only in ("es", "all"):
        scenario_es(report)
    if args.only in ("redis", "all"):
        scenario_redis(report)
    if args.only in ("search", "all"):
        scenario_search_service(report)
    report["finished_at"] = now()

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
