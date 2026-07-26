"""Execute one fixed native harness and emit its owned Provider CaseResult."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Sequence


_NETWORK_BOUNDARIES = {
    "local_contract": "offline_harness",
    "api_integration": "remote_protocol",
    "user_acceptance": "user_journey",
}
_ROOT = Path(__file__).resolve().parents[3]


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _receipt(kind: str, digest: str) -> str:
    return f"receipt:{kind}-{digest.removeprefix('sha256:')[:32]}"


def run_native_harness(*, command: Sequence[str], target: str) -> int:
    """Run a source-owned fixed command; never infer success from prebuilt reports."""
    if not command or not all(isinstance(item, str) and item for item in command):
        raise ValueError("native Provider harness command must be a fixed argv")
    if not target.strip():
        raise ValueError("native Provider harness target is required")

    result_path = Path(_required("QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"))
    adapter_id = _required("QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID")
    capability_id = _required("QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID")
    environment = _required("QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT")
    layer = _required("QWQ_PROVIDER_CONFORMANCE_LAYER")
    typed_port = _required("QWQ_PROVIDER_CONFORMANCE_TYPED_PORT")
    contract_ref = _required("QWQ_PROVIDER_CONFORMANCE_CONTRACT_REF")
    config_digest = _required("QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST")
    try:
        assertion_ids = json.loads(
            _required("QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS")
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS must be a JSON list"
        ) from exc
    if (
        layer not in _NETWORK_BOUNDARIES
        or not isinstance(assertion_ids, list)
        or not assertion_ids
        or not all(isinstance(item, str) and item for item in assertion_ids)
    ):
        raise ValueError("native Provider harness execution context is invalid")

    environment_alias = {
        "alpha": "alpha-local",
        "beta": "local-beta",
        "gamma": "local-gamma",
        "prod": "prod-hosted",
    }.get(environment, environment)
    resolved_command = tuple(
        item.replace("{environment}", environment).replace(
            "{environment_alias}", environment_alias
        )
        for item in command
    )
    started_ns = time.time_ns()
    execution_environment = dict(os.environ)
    execution_environment.setdefault("APP_RUNTIME_ENV", environment)
    execution_environment.setdefault("API_CONTRACT_ENV", environment)
    completed = subprocess.run(
        list(resolved_command),
        check=False,
        capture_output=True,
        cwd=_ROOT,
        env=execution_environment,
    )
    finished_ns = time.time_ns()
    command_digest = _digest_bytes(
        json.dumps(
            list(resolved_command),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    execution = {
        "schema": "provider-conformance-native-execution",
        "version": 1,
        "target": target,
        "executable": Path(resolved_command[0]).name,
        "commandDigest": command_digest,
        "exitCode": completed.returncode,
        "startedUnixNs": started_ns,
        "finishedUnixNs": finished_ns,
        "stdoutDigest": _digest_bytes(completed.stdout),
        "stderrDigest": _digest_bytes(completed.stderr),
    }
    execution_raw = json.dumps(
        execution,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    execution_digest = _digest_bytes(execution_raw)
    if completed.returncode != 0:
        raise ValueError(
            f"native Provider harness failed for {target}; "
            f"execution={execution_digest}"
        )

    result_path.parent.mkdir(parents=True, exist_ok=True)
    telemetry_path = result_path.with_name(
        f"{result_path.stem}.native-execution.json"
    )
    telemetry_path.write_bytes(execution_raw + b"\n")
    log_ref = f"log:native-{execution_digest.removeprefix('sha256:')[:32]}"
    trace_ref = f"trace:native-{execution_digest.removeprefix('sha256:')[:32]}"
    metric_ref = (
        "metric:provider-conformance-"
        + capability_id.replace(".", "-")
        + "-"
        + layer.replace("_", "-")
    )
    observability_refs = {
        "logs": [log_ref],
        "traces": [trace_ref],
        "metrics": [metric_ref],
    }
    case_result = {
        "schema": "provider-conformance-case-results",
        "version": 1,
        "status": "passed",
        "adapterId": adapter_id,
        "capabilityId": capability_id,
        "environment": environment,
        "testLayer": layer,
        "typedPort": typed_port,
        "contractRef": contract_ref,
        "networkBoundary": _NETWORK_BOUNDARIES[layer],
        "testTarget": target,
        "configDigest": config_digest,
        "assertionIds": assertion_ids,
        "caseResults": [
            {
                "assertionId": assertion_id,
                "status": "passed",
                "logRef": log_ref,
                "traceRef": trace_ref,
                "metricRefs": [metric_ref],
            }
            for assertion_id in assertion_ids
        ],
        "dataDigest": execution_digest,
        "cleanupReceipt": _receipt("cleanup", execution_digest),
        "observabilityRefs": observability_refs,
    }
    result_path.write_text(
        json.dumps(case_result, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return 0
