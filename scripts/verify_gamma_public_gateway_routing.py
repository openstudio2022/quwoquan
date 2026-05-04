#!/usr/bin/env python3
"""验证公网 gamma-proxy（Caddy）是否将 /v1/content、/v1/chat、/v1/user、/v1/assistant 正确反代，而非落入默认占位响应。

用于 ECS onebox / local-gamma 镜像公网入口自检。仅依赖 urllib，不读取密钥。

用法:
  python3 scripts/verify_gamma_public_gateway_routing.py [--base-url URL]

环境变量（与探针一致）:
  GAMMA_BASE_URL — 默认 http://127.0.0.1:18080
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request


def _req(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 12.0,
) -> tuple[int, str]:
    ctx = ssl._create_unverified_context()
    h = dict(headers or {})
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), body
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return int(e.code), raw


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--base-url",
        default=os.environ.get("GAMMA_BASE_URL", "http://127.0.0.1:18080").rstrip("/"),
    )
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    failures: list[str] = []

    code, health = _req(f"{base}/healthz", timeout=8.0)
    if code < 200 or code >= 300 or '"ok"' not in health and '"status"' not in health:
        failures.append(f"healthz: http {code} body={health[:200]!r}")

    # content：任意受管控 JSON 即可（404 若路由正确也可能是业务 JSON）
    code, content_body = _req(
        f"{base}/v1/content/posts?limit=1",
        headers={"X-Client-User-Id": "gamma_route_smoke", "X-Test-Local-Gamma": "true"},
    )
    if "local-gamma mirror http endpoint is ready" in content_body:
        failures.append("content: still hitting Caddy catch-all (plain 'ready' text)")
    if "route is not ready" in content_body and code == 404:
        failures.append("content: Caddy 404 catch-all — check path /v1/content*")

    payload = json.dumps(
        {
            "type": "group",
            "title": "gamma-route-smoke",
            "initialMemberIds": ["gamma_smoke_m02"],
            "maxGroupSize": 100},
    ).encode()
    code, chat_body = _req(
        f"{base}/v1/chat/conversations",
        method="POST",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Client-User-Id": "gamma_smoke_m01",
            "X-Test-Local-Gamma": "true",
        },
    )
    if "local-gamma mirror http endpoint is ready" in chat_body:
        failures.append("chat: still hitting Caddy plain-text catch-all — 部署的 Caddyfile 可能过旧")
    if "local-gamma mirror route is not ready" in chat_body:
        failures.append("chat: Caddy 404 catch-all — /v1/chat* 未反代到 chat-service")
    stripped = chat_body.strip()
    if code >= 200 and code < 300 and stripped and not stripped.startswith("{"):
        failures.append(f"chat: expected JSON body, got http {code}: {stripped[:160]!r}")
    if code == 404 and "CONTENT.USER.route_not_found" in chat_body:
        failures.append(
            "chat: 命中 content-service 404（公网端口可能直连 content 而非 Caddy）；"
            "请使用 LOCAL_GAMMA_HTTP_PORT 映射的 gamma-proxy 端口作为 GAMMA_BASE_URL",
        )

    user_sync_payload = json.dumps({"afterSeq": 0, "limit": 1}).encode("utf-8")
    code, user_body = _req(
        f"{base}/v1/user/sync",
        method="POST",
        data=user_sync_payload,
        headers={
            "Content-Type": "application/json",
            "X-Client-User-Id": "gamma_route_smoke",
            "X-Test-Local-Gamma": "true",
        },
    )
    if "local-gamma mirror http endpoint is ready" in user_body:
        failures.append("user: still hitting Caddy plain-text catch-all — /v1/user* 未反代到 user-service")
    if "local-gamma mirror route is not ready" in user_body:
        failures.append("user: Caddy 404 catch-all — /v1/user* 未反代到 user-service")
    stripped = user_body.strip()
    if 200 <= code < 300:
        if not stripped.startswith("{"):
            failures.append(f"user: expected JSON body, got http {code}: {stripped[:160]!r}")
        else:
            try:
                user_json = json.loads(stripped)
            except json.JSONDecodeError as exc:
                failures.append(f"user: invalid JSON body http {code}: {exc}")
            else:
                if "patches" not in user_json:
                    failures.append("user: sync response missing patches field")

    assistant_payload = json.dumps({"summary": "gamma-route-smoke"}).encode("utf-8")
    code, assistant_body = _req(
        f"{base}/v1/assistant/conversations",
        method="POST",
        data=assistant_payload,
        headers={
            "Content-Type": "application/json",
            "X-Client-User-Id": "gamma_route_smoke",
            "X-Test-Local-Gamma": "true",
        },
    )
    if "local-gamma mirror http endpoint is ready" in assistant_body:
        failures.append(
            "assistant: still hitting Caddy plain-text catch-all — /v1/assistant* 未反代到 assistant-service",
        )
    if "local-gamma mirror route is not ready" in assistant_body:
        failures.append(
            "assistant: Caddy 404 catch-all — /v1/assistant* 未反代到 assistant-service",
        )
    stripped = assistant_body.strip()
    if 200 <= code < 300:
        if not stripped.startswith("{"):
            failures.append(
                f"assistant: expected JSON body, got http {code}: {stripped[:160]!r}",
            )
        else:
            try:
                assistant_json = json.loads(stripped)
            except json.JSONDecodeError as exc:
                failures.append(f"assistant: invalid JSON body http {code}: {exc}")
            else:
                if not str(assistant_json.get("conversationId", "")).strip():
                    failures.append(
                        "assistant: conversation response missing conversationId",
                    )

    if failures:
        print("[gamma-gateway-routing] FAIL")
        for f in failures:
            print(f"  - {f}")
        return 2

    print("[gamma-gateway-routing] OK", base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
