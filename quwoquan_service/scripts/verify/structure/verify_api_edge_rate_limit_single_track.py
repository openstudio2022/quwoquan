#!/usr/bin/env python3
"""阻断 owner 进程限流、旧配置真相源与公开入口旁路。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


_BOOTSTRAP = next(
    p for p in Path(__file__).resolve().parents if (p / "repository_root.py").is_file()
)
sys.path.insert(0, str(_BOOTSTRAP))
from repository_root import repository_root  # noqa: E402

REPO_ROOT = repository_root()
SERVICE_ROOT = REPO_ROOT / "quwoquan_service"

OWNER_LIMIT_PATTERNS = (
    re.compile(r"\b(?:Canonical)?RateLimitMiddleware\s*\("),
    re.compile(r"\b(?:new|New)[A-Za-z0-9_]*RateLimiter\s*\("),
    re.compile(r"\btype\s+[A-Za-z0-9_]*RateLimiter\s+struct\s*\{"),
)
RETIRED_TRUTHS = (
    "sys.gateway.rate_limit.per_user_rps",
    "sys.content-service.feed.rate_limit_per_second",
)
OWNER_UPSTREAMS = (
    "assistant-service",
    "chat-service",
    "circle-service",
    "content-service",
    "entity-service",
    "integration-service",
    "notification-service",
    "product-ops-service",
    "platform-ops-service",
    "recommendation-service",
    "rtc-service",
    "search-service",
    "tag-service",
    "user-service",
)
REQUIRED_POLICY_KEYS = (
    "sys.api-edge.rate_limit.command.limit",
    "sys.api-edge.rate_limit.command.window_seconds",
    "sys.api-edge.rate_limit.command.state_failure",
    "sys.api-edge.rate_limit.query.limit",
    "sys.api-edge.rate_limit.query.window_seconds",
    "sys.api-edge.rate_limit.query.state_failure",
    "sys.api-edge.rate_limit.session.limit",
    "sys.api-edge.rate_limit.session.window_seconds",
    "sys.api-edge.rate_limit.session.state_failure",
)


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _owner_composition_files() -> tuple[Path, ...]:
    paths = set(SERVICE_ROOT.glob("services/*/cmd/api/**/*.go"))
    paths.update(SERVICE_ROOT.glob("control-plane/*/cmd/api/**/*.go"))
    return tuple(sorted(path for path in paths if not path.name.endswith("_test.go")))


def _retired_truth_files() -> tuple[Path, ...]:
    roots = (
        SERVICE_ROOT / "runtime",
        SERVICE_ROOT / "services",
        SERVICE_ROOT / "control-plane",
        SERVICE_ROOT / "contracts",
        SERVICE_ROOT / "generated",
    )
    paths: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".go", ".py", ".yaml", ".yml", ".md", ".json"}:
                continue
            if "tests" in path.parts or "testdata" in path.parts or path.name.endswith("_test.go"):
                continue
            paths.add(path)
    return tuple(sorted(paths))


def collect_issues() -> list[str]:
    issues: list[str] = []

    operations = (
        SERVICE_ROOT
        / "services/api-edge/contracts/edge_security/rate_limit_bucket/operations.yaml"
    )
    try:
        payload = yaml.safe_load(operations.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        issues.append(f"{_relative(operations)}: cannot load canonical entrypoint: {exc}")
        payload = {}
    if payload.get("api_routes") != []:
        issues.append(
            f"{_relative(operations)}: rate-limit bucket must not expose an admission HTTP API"
        )
    entrypoints = payload.get("runtime_entrypoints")
    if not isinstance(entrypoints, list) or len(entrypoints) != 1:
        issues.append(
            f"{_relative(operations)}: runtime_entrypoints must contain exactly one entry"
        )
    else:
        expected = {
            "name": "SharedAdmission",
            "kind": "middleware",
            "phase": "post_authorization_pre_owner_proxy",
            "application": {
                "kind": "session",
                "facet": "RateLimitAdmissionFacade",
                "method": "admit",
                "object_owner": "RateLimitBucket",
            },
            "telemetry": {
                "metric": "api_edge_admission_decisions_total",
                "trace": True,
                "attributes": [
                    "environment",
                    "operation",
                    "outcome",
                    "failurePolicy",
                ],
            },
            "slo": {
                "latency_p95_ms": 20,
                "failure_ratio_percent": 0.1,
            },
        }
        if entrypoints[0] != expected:
            issues.append(
                f"{_relative(operations)}: canonical runtime entrypoint drifted from "
                "RateLimitAdmissionFacade.admit"
            )

    for path in _owner_composition_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in OWNER_LIMIT_PATTERNS:
            if pattern.search(text):
                issues.append(
                    f"{_relative(path)}: owner HTTP composition contains per-process "
                    f"arrival limiter {pattern.pattern!r}"
                )

    for path in _retired_truth_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in RETIRED_TRUTHS:
            if token in text:
                issues.append(f"{_relative(path)}: retired rate-limit truth {token!r}")

    schema = SERVICE_ROOT / "services/api-edge/config/schema.yaml"
    schema_text = schema.read_text(encoding="utf-8") if schema.exists() else ""
    for key in REQUIRED_POLICY_KEYS:
        if key not in schema_text:
            issues.append(f"{_relative(schema)}: missing canonical policy key {key!r}")

    for environment in ("alpha", "beta", "gamma", "prod"):
        config = SERVICE_ROOT / f"services/api-edge/environments/{environment}/config.yaml"
        text = config.read_text(encoding="utf-8") if config.exists() else ""
        for key in REQUIRED_POLICY_KEYS:
            if key not in text:
                issues.append(f"{_relative(config)}: missing explicit {environment} value for {key!r}")
        if "state_failure: fail_closed" not in text:
            issues.append(f"{_relative(config)}: no explicit fail-closed admission policy")

    caddy = REPO_ROOT / "quwoquan_ops/environments/gamma/local/Caddyfile"
    caddy_text = caddy.read_text(encoding="utf-8") if caddy.exists() else ""
    if caddy_text.count("reverse_proxy api-edge:18079") != 1:
        issues.append(f"{_relative(caddy)}: public business proxy must have exactly one api-edge upstream")
    public_content_proxy = (
        "\thandle @public_web_seo {\n"
        "\t\trewrite * /public-web{uri}\n"
        "\t\treverse_proxy content-service:18080\n"
        "\t}"
    )
    if caddy_text.count(public_content_proxy) != 1:
        issues.append(
            f"{_relative(caddy)}: public Web SEO/transfer projection must have "
            "exactly one content-service owner route"
        )
    owner_scan_text = caddy_text.replace(public_content_proxy, "", 1)
    for owner in OWNER_UPSTREAMS:
        if f"reverse_proxy {owner}:" in owner_scan_text:
            issues.append(f"{_relative(caddy)}: public Caddy bypasses api-edge to {owner}")

    prod_renderer = REPO_ROOT / "quwoquan_ops/cli/prod/render_prod_plane_stack.py"
    renderer_text = prod_renderer.read_text(encoding="utf-8") if prod_renderer.exists() else ""
    if "reverse_proxy api-edge:18079" not in renderer_text or "(business_api_edge)" not in renderer_text:
        issues.append(f"{_relative(prod_renderer)}: prod renderer lacks canonical api-edge route")
    for owner in OWNER_UPSTREAMS:
        if f"reverse_proxy {owner}:" in renderer_text:
            issues.append(f"{_relative(prod_renderer)}: prod renderer bypasses api-edge to {owner}")

    return sorted(set(issues))


def main() -> int:
    issues = collect_issues()
    if issues:
        for issue in issues:
            print(f"[api-edge-rate-limit-single-track] FAIL: {issue}", file=sys.stderr)
        print(
            f"[api-edge-rate-limit-single-track] FAIL: {len(issues)} single-track violations",
            file=sys.stderr,
        )
        return 1
    print(
        "[api-edge-rate-limit-single-track] OK: api-edge is the sole business "
        "arrival-quota owner; service owners retain only resource backpressure"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
