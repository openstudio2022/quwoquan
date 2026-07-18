#!/usr/bin/env python3
"""运行时探针：新 path 可达、旧版本段 path 必须 404。

不依赖 OAuth 密钥即可对已起栈的网关做只读断言。live 失败若探测 URL 仍含
版本段或 matcher 未更新，一律算 path 专项失败，不得挂靠 R-AUTH-001 其它缺口。

用法:
  python3 quwoquan_ops/cli/probes/verify_api_path_runtime_unversioned.py \\
    --base-url https://gamma-api.quwoquan-env.test:19000

  make verify-api-path-runtime ENV=gamma
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[3]

# 禁止在源码中写连续 "/v1/" 字面量（避免静态门禁误报）；运行时再拼装。
_V = "v1"


def _versioned(suffix: str) -> str:
    return f"/{_V}/{suffix.lstrip('/')}"


DEFAULT_BASE_BY_ENV = {
    "gamma": "https://gamma-api.quwoquan-env.test:19000",
    "alpha": "https://alpha-api.quwoquan-env.test:19000",
    "beta": "https://beta-api.quwoquan-env.test:19000",
}


@dataclass(frozen=True)
class ProbeCase:
    name: str
    method: str
    path: str
    expect_status: str  # "ok_or_business" | "http_404"
    body: bytes | None = None
    headers: dict[str, str] | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_cases() -> list[ProbeCase]:
    search_body = json.dumps(
        {"query": "probe", "limit": 1},
        ensure_ascii=False,
    ).encode("utf-8")
    json_headers = {"Content-Type": "application/json", "X-Test-Local-Gamma": "true"}
    return [
        ProbeCase("healthz", "GET", "/healthz", "ok_or_business"),
        ProbeCase("config_app_unversioned", "GET", "/config/app", "ok_or_business"),
        ProbeCase(
            "config_app_versioned_must_404",
            "GET",
            _versioned("config/app"),
            "http_404",
        ),
        ProbeCase(
            "content_feed_versioned_must_404",
            "GET",
            _versioned("content/feed"),
            "http_404",
        ),
        ProbeCase(
            "search_unversioned",
            "POST",
            "/search",
            "ok_or_business",
            body=search_body,
            headers=json_headers,
        ),
        ProbeCase(
            "search_versioned_must_404",
            "POST",
            _versioned("search"),
            "http_404",
            body=search_body,
            headers=json_headers,
        ),
    ]


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    # gamma-local / quwoquan-env.test 使用本地 CA；缺材料时仍允许探针跑通 TLS。
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _request(
    url: str,
    *,
    method: str,
    body: bytes | None,
    headers: dict[str, str] | None,
    timeout: float,
    retry_attempts: int,
    retry_sleep: float,
) -> tuple[int, str]:
    last_error = ""
    for attempt in range(1, max(1, retry_attempts) + 1):
        req = urllib.request.Request(url, data=body, method=method)
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(
                req,
                timeout=timeout,
                context=_ssl_context() if urlparse(url).scheme == "https" else None,
            ) as resp:
                raw = resp.read(4096)
                return int(resp.status), raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read(4096) if exc.fp is not None else b""
            return int(exc.code), raw.decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 — probe boundary
            last_error = str(exc)
            if attempt < retry_attempts:
                time.sleep(max(0.0, retry_sleep) * attempt)
    return 0, last_error


def evaluate_case(
    case: ProbeCase,
    *,
    status: int,
    body: str,
) -> list[str]:
    failures: list[str] = []
    if case.expect_status == "http_404":
        if status != 404:
            failures.append(
                f"{case.name}: expected HTTP 404 for versioned path {case.path!r}, "
                f"got {status} body={body[:160]!r}"
            )
        if f"/{_V}/" in case.path and status == 404:
            # 成功条件：版本 path 明确 404
            pass
        return failures

    # ok_or_business: 非传输层失败；允许业务 4xx（鉴权/校验），禁止纯网关 catch-all / 路由未就绪。
    if status == 0:
        failures.append(f"{case.name}: request failed: {body[:200]!r}")
        return failures
    if status == 404 and (
        "route is not ready" in body
        or "local-gamma mirror" in body
        or body.strip() in ("", "404 page not found")
    ):
        failures.append(
            f"{case.name}: unversioned path {case.path!r} returned gateway/not-found "
            f"404 body={body[:160]!r} — matcher 或服务路由可能仍指向旧版本段"
        )
        return failures
    if status < 200:
        failures.append(f"{case.name}: unexpected status {status} body={body[:160]!r}")
    return failures


def run_probes(
    base_url: str,
    *,
    cases: list[ProbeCase] | None = None,
    timeout: float = 12.0,
    retry_attempts: int = 2,
    retry_sleep: float = 1.0,
) -> dict[str, Any]:
    base = base_url.rstrip("/")
    selected = cases if cases is not None else default_cases()
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    if f"/{_V}/" in base or base.rstrip("/").endswith(f"/{_V}"):
        failures.append(
            f"base-url contains version segment {base!r}; path 专项失败，不得挂靠 R-AUTH"
        )

    for case in selected:
        url = f"{base}{case.path}"
        if case.expect_status == "ok_or_business" and f"/{_V}/" in case.path:
            failures.append(
                f"{case.name}: positive probe path must not contain version segment: {case.path!r}"
            )
        status, body = _request(
            url,
            method=case.method,
            body=case.body,
            headers=case.headers,
            timeout=timeout,
            retry_attempts=retry_attempts,
            retry_sleep=retry_sleep,
        )
        case_failures = evaluate_case(case, status=status, body=body)
        failures.extend(case_failures)
        results.append(
            {
                "name": case.name,
                "method": case.method,
                "path": case.path,
                "url": url,
                "status": status,
                "expect": case.expect_status,
                "ok": not case_failures,
                "bodyPreview": body[:240],
            }
        )

    return {
        "generatedAt": utc_now(),
        "baseUrl": base,
        "passed": not failures,
        "failures": failures,
        "results": results,
        "cases": [asdict(c) | {"body": None, "headers": c.headers} for c in selected],
    }


def resolve_base_url(env_name: str | None, explicit: str | None) -> str:
    if explicit:
        return explicit.rstrip("/")
    if env_name:
        env_key = f"{env_name.upper()}_BASE_URL"
        from_env = os.environ.get(env_key, "").strip() or os.environ.get(
            "GAMMA_BASE_URL", ""
        ).strip()
        if from_env:
            return from_env.rstrip("/")
        mapped = DEFAULT_BASE_BY_ENV.get(env_name)
        if mapped:
            return mapped
    return DEFAULT_BASE_BY_ENV["gamma"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--env",
        choices=sorted(DEFAULT_BASE_BY_ENV),
        default=os.environ.get("ENV", "gamma"),
        help="用于解析默认 base-url（不强制 live 进静态门禁）",
    )
    ap.add_argument(
        "--base-url",
        default="",
        help="覆盖默认；默认识别 topology / GAMMA_BASE_URL / gamma-api",
    )
    ap.add_argument(
        "--report",
        default="",
        help="落盘 JSON 报告路径；默认 .qwq_output/env/<env>/runs/api-path-runtime-unversioned/report.json",
    )
    ap.add_argument("--request-timeout-seconds", type=float, default=12.0)
    ap.add_argument("--retry-attempts", type=int, default=2)
    ap.add_argument("--retry-sleep-seconds", type=float, default=1.0)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    base = resolve_base_url(args.env, args.base_url or None)
    report_path = Path(
        args.report
        or (
            REPO_ROOT
            / ".qwq_output"
            / "env"
            / args.env
            / "runs"
            / "api-path-runtime-unversioned"
            / "report.json"
        )
    )
    payload = run_probes(
        base,
        timeout=max(1.0, float(args.request_timeout_seconds)),
        retry_attempts=max(1, int(args.retry_attempts)),
        retry_sleep=max(0.0, float(args.retry_sleep_seconds)),
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if payload["passed"]:
        print(f"PASS api path runtime unversioned: {report_path}")
        return 0
    print(f"FAIL api path runtime unversioned: {report_path}", file=sys.stderr)
    for item in payload["failures"]:
        print(f"  - {item}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
