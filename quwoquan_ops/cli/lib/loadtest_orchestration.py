"""契约驱动压测编排：从 operations.yaml 派生负载画像并调用 Go loadgen 执行。

operation、method、path 与 slo 阈值全部来自 services/<svc>/contracts/**/operations.yaml
单一真相源；本模块不承载第二套 path 或阈值清单。压测只允许 alpha/beta/gamma，
Prod 在任何压测请求前拒绝。

spec_ref: specs/feature-tree/runtime/runtime-testinfra/performance-load-harness/spec.md#gwt-001
"""

from __future__ import annotations

import json
import subprocess
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.common import load_json_yaml, utc_now, write_json
from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology

PROFILE_SCHEMA = "quwoquan.loadgen.profile"
REPORT_SCHEMA = "quwoquan_ops.loadtest.report"
ALLOWED_ENVIRONMENTS = frozenset({"alpha", "beta", "gamma"})
READONLY_METHODS = frozenset({"GET", "HEAD"})

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SERVICE_ROOT = _REPO_ROOT / "quwoquan_service"

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
        cwd=str(_SERVICE_ROOT),
    )


def parse_operation_selector(selector: str) -> dict[str, str]:
    """解析 `<service>/<context>/<object>#<OperationName>` 选择器。"""
    head, separator, operation = selector.partition("#")
    parts = head.split("/")
    if separator != "#" or len(parts) != 3 or not operation or not all(parts):
        raise ValueError(
            "operation selector must look like "
            f"<service>/<context>/<object>#<OperationName>; got {selector!r}"
        )
    return {
        "service": parts[0],
        "context": parts[1],
        "object": parts[2],
        "operation": operation,
    }


def derive_operation_profile(selector: str) -> dict[str, Any]:
    """从对象 operations.yaml 契约派生单个 operation 的负载画像条目。"""
    parsed = parse_operation_selector(selector)
    contract_path = (
        _SERVICE_ROOT
        / "services"
        / parsed["service"]
        / "contracts"
        / parsed["context"]
        / parsed["object"]
        / "operations.yaml"
    )
    if not contract_path.is_file():
        raise ValueError(f"operations contract not found: {contract_path}")
    document = load_json_yaml(contract_path)
    routes = document.get("api_routes") if isinstance(document, dict) else None
    if not isinstance(routes, list):
        raise ValueError(f"{contract_path} declares no api_routes")
    for route in routes:
        if not isinstance(route, dict) or route.get("operation") != parsed["operation"]:
            continue
        method = str(route.get("method") or "").upper()
        path = str(route.get("path") or "")
        if not method or not path:
            raise ValueError(f"operation {selector} has no method/path in contract")
        if "{" in path:
            raise ValueError(
                f"operation {selector} uses a parameterized path {path!r}; "
                "loadtest currently only supports literal paths"
            )
        slo = route.get("slo") if isinstance(route.get("slo"), dict) else {}
        return {
            "operationId": selector,
            "method": method,
            "path": path,
            "sloLatencyP95Ms": int(slo.get("latency_p95_ms") or 0),
            "sloAvailabilityPercent": float(slo.get("availability_percent") or 0.0),
        }
    raise ValueError(f"operation {parsed['operation']} not declared in {contract_path}")


def build_load_profile(
    *,
    base_url: str,
    operation_selectors: Sequence[str],
    concurrency: int,
    requests_per_operation: int,
    timeout_seconds: float,
    tls_insecure_skip_verify: bool = False,
) -> dict[str, Any]:
    operations = [derive_operation_profile(selector) for selector in operation_selectors]
    non_readonly = [
        item["operationId"] for item in operations if item["method"] not in READONLY_METHODS
    ]
    if non_readonly:
        raise ValueError(
            "loadtest only accepts read-only operations; rejected: " + ", ".join(non_readonly)
        )
    return {
        "schema": PROFILE_SCHEMA,
        "baseUrl": base_url,
        "concurrency": int(concurrency),
        "requestsPerOperation": int(requests_per_operation),
        "timeoutMs": max(1, int(timeout_seconds * 1000)),
        "allowMutations": False,
        "tlsInsecureSkipVerify": bool(tls_insecure_skip_verify),
        "headers": {
            # 推荐路由等公开只读 operation 要求合法客户端会话标识；
            # 压测按游客会话形态携带确定性 session id。
            "X-Client-Session-Id": f"loadtest-{uuid.uuid4().hex}",
        },
        "operations": operations,
    }


def run_loadtest(
    *,
    env_name: str,
    target_name: str,
    operation_selectors: Sequence[str],
    concurrency: int,
    requests_per_operation: int,
    timeout_seconds: float,
    report_dir: Path,
    runner: CommandRunner = _run,
    base_url_override: str = "",
) -> dict[str, Any]:
    if env_name not in ALLOWED_ENVIRONMENTS or target_name.startswith("prod"):
        raise ValueError("loadtest only accepts alpha/beta/gamma targets; prod is refused")
    if not operation_selectors:
        raise ValueError("loadtest requires at least one --operation selector")
    if base_url_override:
        base_url = base_url_override
    else:
        target = get_target(load_environment_topology(), target_name)
        public_bases = target.get("publicBases")
        if not isinstance(public_bases, dict) or not str(public_bases.get("api") or "").strip():
            raise ValueError(f"target {target_name} has no canonical API public base")
        base_url = str(public_bases["api"]).rstrip("/")
    profile = build_load_profile(
        base_url=base_url,
        operation_selectors=operation_selectors,
        concurrency=concurrency,
        requests_per_operation=requests_per_operation,
        timeout_seconds=timeout_seconds,
        # 本地受管 target 使用自签 CA 的 HTTPS；仅此形态允许跳过校验。
        tls_insecure_skip_verify=target_name.endswith("-local"),
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    profile_path = report_dir / "profile.json"
    write_json(profile_path, profile)
    result = runner(["go", "run", "./tools/loadgen", "--profile", str(profile_path)])
    if result.returncode not in (0, 1) or not result.stdout.strip():
        detail = (result.stderr or result.stdout or "").strip()[:600]
        raise RuntimeError(f"loadgen execution failed (exit={result.returncode}): {detail}")
    loadgen_report = json.loads(result.stdout)
    payload: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "generatedAt": utc_now(),
        "environment": env_name,
        "target": target_name,
        "baseUrl": base_url,
        "profilePath": str(profile_path),
        "loadgen": loadgen_report,
        "verdict": loadgen_report.get("verdict"),
        "status": "ok" if loadgen_report.get("verdict") != "fail" else "failed",
    }
    write_json(report_dir / "report.json", payload)
    return payload
