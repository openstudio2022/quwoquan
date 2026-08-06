"""Execute one fixed native harness and emit its owned Provider CaseResult."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Mapping, Sequence

from quwoquan_ops.cli.lib.provider_conformance import required_metric_refs


_NETWORK_BOUNDARIES = {
    "local_contract": "offline_harness",
    "api_integration": "remote_protocol",
    "user_acceptance": "user_journey",
}
_ROOT = Path(__file__).resolve().parents[3]
_PATROL_SUITE_ID = "environment_page_smoke"
_PATROL_ENVIRONMENT_ALIASES = {
    "alpha": "alpha-local",
    "beta": "local-beta",
    "gamma": "local-gamma",
    "prod": "prod-hosted",
}
_UNKNOWN_IDENTITIES = {"", "unknown", "none", "null", "n/a"}
_PLACEHOLDER_TOKENS = {"unknown", "none", "null", "placeholder", "todo", "tbd"}
_ASSERTION_MARKER = "QWQ_PROVIDER_CONFORMANCE_ASSERTION:"
_CLEANUP_MARKER = "QWQ_PROVIDER_CONFORMANCE_CLEANUP:"
_RECEIPT_REF_RE = re.compile(r"^receipt:[a-z0-9][a-z0-9._:-]{2,255}$")
_SENSITIVE_REF_RE = re.compile(
    r"(?:endpoint|secret|credential|token|password|https?|://)",
    re.IGNORECASE,
)


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _receipt(kind: str, digest: str) -> str:
    return f"receipt:{kind}-{digest.removeprefix('sha256:')[:32]}"


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _identity(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Patrol report {name} must be a string identity")
    normalized = value.strip()
    if normalized.lower() in _UNKNOWN_IDENTITIES:
        raise ValueError(f"Patrol report {name} must not be empty or unknown")
    return normalized


def _marker_payloads(
    stdout: bytes,
    stderr: bytes,
    *,
    prefix: str,
) -> list[Mapping[str, Any]]:
    payloads: list[Mapping[str, Any]] = []
    for stream_name, raw in (("stdout", stdout), ("stderr", stderr)):
        if not isinstance(raw, bytes):
            raise ValueError(f"native Provider harness {stream_name} must be bytes")
        for line_number, line in enumerate(
            raw.decode("utf-8", errors="replace").splitlines(),
            start=1,
        ):
            normalized = line.strip()
            if not normalized.startswith(prefix):
                continue
            encoded = normalized[len(prefix) :].strip()
            try:
                payload = json.loads(encoded)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"native Provider harness {prefix} marker at "
                    f"{stream_name}:{line_number} is not valid JSON"
                ) from exc
            if not isinstance(payload, Mapping):
                raise ValueError(
                    f"native Provider harness {prefix} marker at "
                    f"{stream_name}:{line_number} must be a JSON object"
                )
            payloads.append(payload)
    return payloads


def _contains_placeholder(value: str) -> bool:
    tokens = set(re.split(r"[^a-z0-9]+", value.lower()))
    return bool(tokens & _PLACEHOLDER_TOKENS)


def _receipt_ref(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"native Provider harness {name} must be a receipt reference")
    normalized = value.strip()
    if (
        _RECEIPT_REF_RE.fullmatch(normalized) is None
        or _SENSITIVE_REF_RE.search(normalized) is not None
        or _contains_placeholder(normalized)
    ):
        raise ValueError(
            f"native Provider harness {name} must be a canonical non-sensitive "
            "receipt reference"
        )
    return normalized


def _observability_ref(
    value: object,
    *,
    name: str,
    prefixes: tuple[str, ...],
) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"native Provider harness {name} must be an observability reference"
        )
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 512
        or any(character.isspace() for character in normalized)
        or not normalized.startswith(prefixes)
        or _contains_placeholder(normalized)
    ):
        raise ValueError(
            f"native Provider harness {name} must be a canonical non-placeholder "
            "observability reference"
        )
    return normalized


def _validate_non_user_acceptance_markers(
    *,
    stdout: bytes,
    stderr: bytes,
    assertion_ids: Sequence[str],
    capability_id: str,
) -> tuple[list[dict[str, Any]], dict[str, list[str]], str]:
    assertion_payloads = _marker_payloads(
        stdout,
        stderr,
        prefix=_ASSERTION_MARKER,
    )
    cleanup_payloads = _marker_payloads(
        stdout,
        stderr,
        prefix=_CLEANUP_MARKER,
    )
    if not assertion_payloads:
        raise ValueError(
            "native Provider harness produced no assertion markers; refusing to "
            "infer assertion passes from exit zero"
        )
    if len(cleanup_payloads) != 1:
        raise ValueError(
            "native Provider harness must produce exactly one cleanup marker"
        )

    expected = set(assertion_ids)
    observed: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(assertion_payloads):
        if set(item) != {
            "assertionId",
            "status",
            "sceneReceiptRef",
            "logRef",
            "traceRef",
            "metricRefs",
        }:
            raise ValueError(
                f"native Provider assertion marker[{index}] has an invalid shape"
            )
        assertion_id = item.get("assertionId")
        if (
            not isinstance(assertion_id, str)
            or not assertion_id.strip()
            or assertion_id not in expected
            or assertion_id in observed
            or item.get("status") != "passed"
        ):
            raise ValueError(
                "native Provider assertion markers must uniquely cover passed "
                "source-declared assertions"
            )
        _receipt_ref(
            item.get("sceneReceiptRef"),
            name=f"assertion marker[{index}].sceneReceiptRef",
        )
        log_ref = _observability_ref(
            item.get("logRef"),
            name=f"assertion marker[{index}].logRef",
            prefixes=("log:",),
        )
        trace_ref = _observability_ref(
            item.get("traceRef"),
            name=f"assertion marker[{index}].traceRef",
            prefixes=("trace:",),
        )
        raw_metric_refs = item.get("metricRefs")
        if not isinstance(raw_metric_refs, list) or not raw_metric_refs:
            raise ValueError(
                f"native Provider assertion marker[{index}].metricRefs must be "
                "a non-empty list"
            )
        metric_refs = [
            _observability_ref(
                ref,
                name=f"assertion marker[{index}].metricRefs[{metric_index}]",
                prefixes=(
                    "metric:",
                    "prometheus://",
                    "promql://",
                    "provider-conformance://",
                ),
            )
            for metric_index, ref in enumerate(raw_metric_refs)
        ]
        if len(metric_refs) != len(set(metric_refs)):
            raise ValueError(
                f"native Provider assertion marker[{index}].metricRefs must be unique"
            )
        observed[assertion_id] = {
            "assertionId": assertion_id,
            "status": "passed",
            "logRef": log_ref,
            "traceRef": trace_ref,
            "metricRefs": metric_refs,
        }
    if set(observed) != expected:
        raise ValueError(
            "native Provider assertion markers do not exactly cover source-declared "
            "assertions"
        )

    cleanup = cleanup_payloads[0]
    if set(cleanup) != {"status", "receiptRef"} or cleanup.get("status") != "restored":
        raise ValueError(
            "native Provider cleanup marker must report exactly status=restored and "
            "receiptRef"
        )
    cleanup_receipt = _receipt_ref(
        cleanup.get("receiptRef"),
        name="cleanup marker receiptRef",
    )

    ordered = [observed[assertion_id] for assertion_id in assertion_ids]
    observability_refs = {
        "logs": list(dict.fromkeys(item["logRef"] for item in ordered)),
        "traces": list(dict.fromkeys(item["traceRef"] for item in ordered)),
        "metrics": list(
            dict.fromkeys(ref for item in ordered for ref in item["metricRefs"])
        ),
    }
    required_metrics = set(required_metric_refs(capability_id))
    if not required_metrics.issubset(observability_refs["metrics"]):
        raise ValueError(
            "native Provider assertion markers omit capability-required metric "
            "references"
        )
    return ordered, observability_refs, cleanup_receipt


def _patrol_report_target(
    command: Sequence[str],
    *,
    provider_target: str,
) -> str:
    """Resolve the report-owned Dart journey from the fixed native command."""

    if not any(Path(item).name == "run_provider_patrol_uat.py" for item in command):
        return provider_target
    indexes = [index for index, item in enumerate(command) if item == "--target"]
    if len(indexes) != 1 or indexes[0] + 1 >= len(command):
        raise ValueError(
            "Provider Patrol native command must declare exactly one fixed --target"
        )
    journey_target = command[indexes[0] + 1].strip()
    if not journey_target or journey_target.startswith("-"):
        raise ValueError("Provider Patrol native command --target is invalid")
    return journey_target


def _validate_test_execution(value: object, *, location: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"Patrol report {location}.testExecution is required")
    _identity(value.get("framework"), name=f"{location} framework")
    executed = value.get("executed")
    failed = value.get("failed")
    skipped = value.get("skipped")
    if isinstance(executed, bool) or not isinstance(executed, int) or executed <= 0:
        raise ValueError(
            f"Patrol report {location}.testExecution executed must be > 0"
        )
    if isinstance(failed, bool) or not isinstance(failed, int) or failed != 0:
        raise ValueError(
            f"Patrol report {location}.testExecution failed must be 0"
        )
    if isinstance(skipped, bool) or not isinstance(skipped, int) or skipped != 0:
        raise ValueError(
            f"Patrol report {location}.testExecution skipped must be 0"
        )


def _validate_patrol_assertions(
    report: Mapping[str, Any],
    *,
    assertion_ids: Sequence[str],
    case_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    assertions = report.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        raise ValueError(
            "Patrol report does not provide assertion-level evidence; refusing "
            "to synthesize metadata assertions from a successful process exit"
        )
    expected = set(assertion_ids)
    observed: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(assertions):
        if not isinstance(item, Mapping) or set(item) != {
            "assertionId",
            "caseId",
            "status",
            "logRef",
            "traceRef",
            "metricRefs",
        }:
            raise ValueError(
                f"Patrol report assertions[{index}] has an invalid evidence shape"
            )
        assertion_id = _identity(
            item.get("assertionId"), name=f"assertions[{index}] assertionId"
        )
        case_id = _identity(item.get("caseId"), name=f"assertions[{index}] caseId")
        log_ref = _identity(item.get("logRef"), name=f"assertions[{index}] logRef")
        trace_ref = _identity(
            item.get("traceRef"), name=f"assertions[{index}] traceRef"
        )
        metric_refs = item.get("metricRefs")
        if (
            assertion_id not in expected
            or assertion_id in observed
            or case_id not in case_ids
            or item.get("status") != "passed"
            or not log_ref.startswith("log:")
            or not trace_ref.startswith("trace:")
            or not isinstance(metric_refs, list)
            or not metric_refs
            or any(
                not isinstance(ref, str)
                or ref.strip().lower() in _UNKNOWN_IDENTITIES
                or not ref.strip().startswith("metric:")
                for ref in metric_refs
            )
        ):
            raise ValueError(
                "Patrol report assertion evidence must uniquely cover one declared "
                "assertion, bind a passed executed case, and own log/trace/metric refs"
            )
        observed[assertion_id] = {
            "assertionId": assertion_id,
            "status": "passed",
            "logRef": log_ref,
            "traceRef": trace_ref,
            "metricRefs": [ref.strip() for ref in metric_refs],
        }
    if set(observed) != expected:
        raise ValueError(
            "Patrol report assertion evidence does not exactly cover metadata assertions"
        )
    ordered = [observed[assertion_id] for assertion_id in assertion_ids]
    observability_refs = {
        "logs": list(dict.fromkeys(item["logRef"] for item in ordered)),
        "traces": list(dict.fromkeys(item["traceRef"] for item in ordered)),
        "metrics": list(
            dict.fromkeys(
                ref for item in ordered for ref in item["metricRefs"]
            )
        ),
    }
    return ordered, observability_refs


def _validate_user_acceptance_report(
    report: object,
    *,
    environment: str,
    target: str,
    assertion_ids: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    if not isinstance(report, Mapping):
        raise ValueError("Patrol report root must be an object")
    expected_alias = _PATROL_ENVIRONMENT_ALIASES.get(environment)
    if report.get("suiteId") != _PATROL_SUITE_ID:
        raise ValueError("Patrol report suiteId is not environment_page_smoke")
    if report.get("status") != "passed":
        raise ValueError("Patrol report status must be passed")
    if (
        expected_alias is None
        or report.get("environmentAlias") != expected_alias
        or report.get("runtimeEnv") != environment
        or report.get("apiContractEnv") != environment
    ):
        raise ValueError("Patrol report environment does not match the requested cell")
    if report.get("composition") != "production_remote":
        raise ValueError("Patrol report composition must be production_remote")
    if report.get("target") != target:
        raise ValueError("Patrol report target does not match the executed source")
    if not _is_sha256(report.get("candidateDigest")):
        raise ValueError("Patrol report candidateDigest must be a non-empty sha256")

    devices = report.get("devices")
    runs = report.get("runs")
    cases = report.get("caseResults")
    if not all(isinstance(value, list) and value for value in (devices, runs, cases)):
        raise ValueError("Patrol report devices, runs, and caseResults must be non-empty")
    assert isinstance(devices, list)
    assert isinstance(runs, list)
    assert isinstance(cases, list)

    device_ids: set[str] = set()
    for index, device in enumerate(devices):
        if not isinstance(device, Mapping):
            raise ValueError(f"Patrol report devices[{index}] must be an object")
        device_id = _identity(device.get("id"), name=f"devices[{index}] id")
        _identity(
            device.get("targetPlatform"), name=f"devices[{index}] targetPlatform"
        )
        if device_id in device_ids:
            raise ValueError("Patrol report device identity must be unique")
        device_ids.add(device_id)

    run_device_ids: set[str] = set()
    for index, run in enumerate(runs):
        if not isinstance(run, Mapping):
            raise ValueError(f"Patrol report runs[{index}] must be an object")
        device = run.get("device")
        evidence = run.get("evidence")
        if not isinstance(device, Mapping) or not isinstance(evidence, Mapping):
            raise ValueError(f"Patrol report runs[{index}] lacks device/run evidence")
        device_id = _identity(device.get("id"), name=f"runs[{index}] device id")
        _identity(
            evidence.get("runDirectory"), name=f"runs[{index}] runDirectory"
        )
        if (
            device_id not in device_ids
            or device_id in run_device_ids
            or run.get("exitCode") != 0
            or run.get("timedOut") is not False
        ):
            raise ValueError(
                f"Patrol report runs[{index}] must bind one successful device run"
            )
        _validate_test_execution(run.get("testExecution"), location=f"runs[{index}]")
        run_device_ids.add(device_id)

    case_ids: set[str] = set()
    case_device_ids: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping):
            raise ValueError(f"Patrol report caseResults[{index}] must be an object")
        case_id = _identity(case.get("caseId"), name=f"caseResults[{index}] caseId")
        device_id = _identity(
            case.get("deviceId"), name=f"caseResults[{index}] deviceId"
        )
        if (
            case_id in case_ids
            or device_id not in device_ids
            or device_id in case_device_ids
            or case.get("status") != "passed"
        ):
            raise ValueError(
                f"Patrol report caseResults[{index}] must bind one passed device case"
            )
        _validate_test_execution(
            case.get("testExecution"), location=f"caseResults[{index}]"
        )
        case_ids.add(case_id)
        case_device_ids.add(device_id)

    if not (device_ids == run_device_ids == case_device_ids):
        raise ValueError(
            "Patrol report device, run, and case identities must match exactly"
        )
    return _validate_patrol_assertions(
        report,
        assertion_ids=assertion_ids,
        case_ids=case_ids,
    )


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
        or len(set(assertion_ids)) != len(assertion_ids)
    ):
        raise ValueError("native Provider harness execution context is invalid")

    environment_alias = _PATROL_ENVIRONMENT_ALIASES.get(environment, environment)
    resolved_command = tuple(
        item.replace("{environment}", environment).replace(
            "{environment_alias}", environment_alias
        )
        for item in command
    )
    patrol_report_target = _patrol_report_target(
        resolved_command,
        provider_target=target,
    )
    patrol_report_path = result_path.with_name(
        f"{result_path.stem}.patrol-report.json"
    )
    if layer == "user_acceptance" and patrol_report_path.exists():
        raise ValueError("Patrol report must be created by the current native execution")
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
    patrol_report_raw: bytes | None = None
    patrol_report_digest = ""
    if completed.returncode == 0 and layer == "user_acceptance":
        try:
            patrol_report_raw = patrol_report_path.read_bytes()
        except OSError as exc:
            raise ValueError(
                "user_acceptance native harness did not produce its sibling "
                ".patrol-report.json"
            ) from exc
        patrol_report_digest = _digest_bytes(patrol_report_raw)
    execution = {
        "schema": "provider-conformance-native-execution",
        "target": target,
        "executable": Path(resolved_command[0]).name,
        "commandDigest": command_digest,
        "exitCode": completed.returncode,
        "startedUnixNs": started_ns,
        "finishedUnixNs": finished_ns,
        "stdoutDigest": _digest_bytes(completed.stdout),
        "stderrDigest": _digest_bytes(completed.stderr),
    }
    if patrol_report_digest:
        execution["patrolReportDigest"] = patrol_report_digest
    execution_raw = json.dumps(
        execution,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    execution_digest = _digest_bytes(execution_raw)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    telemetry_path = result_path.with_name(
        f"{result_path.stem}.native-execution.json"
    )
    telemetry_path.write_bytes(execution_raw + b"\n")
    if completed.returncode != 0:
        stderr_tail = completed.stderr.decode("utf-8", errors="replace")[-4000:]
        stdout_tail = completed.stdout.decode("utf-8", errors="replace")[-2000:]
        detail_path = result_path.with_name(
            f"{result_path.stem}.native-execution.stderr.txt"
        )
        detail_path.write_text(
            "\n".join(
                [
                    f"target={target}",
                    f"exitCode={completed.returncode}",
                    f"execution={execution_digest}",
                    "--- stdout tail ---",
                    stdout_tail,
                    "--- stderr tail ---",
                    stderr_tail,
                ]
            ),
            encoding="utf-8",
        )
        raise ValueError(
            f"native Provider harness failed for {target}; "
            f"execution={execution_digest}; detail={detail_path}"
        )
    if layer == "user_acceptance":
        assert patrol_report_raw is not None
        try:
            patrol_report = json.loads(patrol_report_raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Patrol report is not valid JSON") from exc
        case_results, observability_refs = _validate_user_acceptance_report(
            patrol_report,
            environment=environment,
            target=patrol_report_target,
            assertion_ids=assertion_ids,
        )
        cleanup_receipt = _receipt("cleanup", execution_digest)
    else:
        case_results, observability_refs, cleanup_receipt = (
            _validate_non_user_acceptance_markers(
                stdout=completed.stdout,
                stderr=completed.stderr,
                assertion_ids=assertion_ids,
                capability_id=capability_id,
            )
        )
    case_result = {
        "schema": "provider-conformance-case-results",
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
        "caseResults": case_results,
        "dataDigest": execution_digest,
        "cleanupReceipt": cleanup_receipt,
        "observabilityRefs": observability_refs,
    }
    result_path.write_text(
        json.dumps(case_result, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return 0
