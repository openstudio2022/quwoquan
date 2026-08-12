"""Execute selected typed acceptance-data request graphs for stackctl verify."""

from __future__ import annotations

import hashlib
import json
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping

from .common import write_json
from .test_data.api import CaseRef, TestDataSession
from .test_data.model import CandidateBinding, TestDataContext, canonical_digest
from .test_data.operations import TestDataRuntime
from .test_data.serialization import collect_request_graph, load_case_requests


CASE_RESULT_SCHEMA = "qwq.case_result"
EVIDENCE_SCHEMA = "qwq.test_data_evidence.v1"
SPEC_REFS = (
    "specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002",
    "specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md#gwt-001",
    "specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md#gwt-002",
)


def run_test_data_verification(
    *,
    environment: str,
    target: str,
    base_url: str,
    candidate_manifest: Mapping[str, Any],
    release_readiness: Mapping[str, Any],
    request_path: Path,
    evidence_path: Path | None,
    report_dir: Path,
    static_gate_ms: int = 0,
) -> dict[str, Any]:
    started = time.monotonic()
    preparation_started: float | None = None
    root_worker_count = 0
    report_dir.mkdir(parents=True, exist_ok=True)
    try:
        candidate = build_candidate_binding(
            environment=environment,
            target=target,
            manifest=candidate_manifest,
            readiness=release_readiness,
        )
        request_document = json.loads(request_path.read_text(encoding="utf-8"))
        if not isinstance(request_document, Mapping):
            raise ValueError("test-data request must be an object")
        cases = load_case_requests(request_document)
        required_providers = sorted(
            {
                request.capability.owner_service
                for case in cases
                for request in collect_request_graph((case.request,)).values()
            }
        )
        required_provider_capabilities = sorted(
            {
                provider_key.value
                for case in cases
                for request in collect_request_graph((case.request,)).values()
                for provider_key in (
                    request.capability.required_provider_capabilities
                )
            }
        )
        provider_evidence = load_provider_evidence(
            evidence_path,
            candidate,
            request_digest=str(request_document.get("requestDigest") or ""),
            required_capabilities=tuple(required_provider_capabilities),
        )
        runtime = TestDataRuntime()
        context = TestDataContext(
            candidate=candidate,
            base_url=base_url,
            output_root=report_dir,
            provider_evidence=provider_evidence,
            runtime=runtime,
        )
        preparation_started = time.monotonic()
        root_worker_count = min(context.max_concurrency, len(cases))
        if root_worker_count == 1:
            case_runs = [_execute_case(cases[0], context)]
        else:
            with ThreadPoolExecutor(
                max_workers=root_worker_count,
                thread_name_prefix="test-data-case",
            ) as pool:
                futures = tuple(
                    pool.submit(_execute_case, case, context)
                    for case in cases
                )
                # Preserve request-document order even though execution is
                # parallel, so evidence remains byte-stable and reviewable.
                case_runs = [future.result() for future in futures]
        case_session_wall_ms = _elapsed_ms(preparation_started)
        summaries = _load_run_summaries(report_dir)
        timings = _aggregate_timings(summaries)
        # Per-case preparation values overlap when roots execute concurrently.
        # Keep their maximum as diagnostic critical-path evidence, while the
        # suite KPI uses the actually observed wall time from dispatch through
        # every provision-test-cleanup CaseResult.  Summing branches would
        # over-report and taking only one branch would hide queueing/overhead.
        max_case_data_preparation_ms = timings.pop("dataPreparationMs")
        phase_work_ms = _aggregate_phase_work(summaries)
        timings["maxObservedConcurrency"] = max(
            timings["maxObservedConcurrency"],
            runtime.max_observed_concurrency,
        )
        capability_timings = _load_capability_timings(report_dir)
        operation_count = sum(int(item.get("operationCount") or 0) for item in summaries)
        loaded_providers = sorted(
            {
                provider
                for item in summaries
                for provider in item.get("loadedProviders", [])
                if isinstance(provider, str)
            }
        )
        case_results = [item["caseResult"] for item in case_runs]
        preparation_results = [
            item["preparationResult"]
            for item in case_runs
            if isinstance(item.get("preparationResult"), Mapping)
        ]
        infrastructure_issues = [
            str(issue)
            for item in case_runs
            for issue in item.get("issues", [])
        ]
        if loaded_providers != required_providers:
            infrastructure_issues.append(
                "GATE_BLOCK: loaded Provider closure does not match the "
                f"selected request closure: loaded={loaded_providers} "
                f"required={required_providers}"
            )
        failed_case_ids = [
            str(item.get("caseId") or "")
            for item in case_results
            if item.get("status") == "failed"
        ]
        status = (
            "GATE_BLOCK"
            if infrastructure_issues
            else ("failed" if failed_case_ids else "passed")
        )
        issues = [
            *infrastructure_issues,
            *(f"business case failed: {case_id}" for case_id in failed_case_ids),
        ]
        executed = sum(
            int(((item.get("testExecution") or {}).get("executed")) or 0)
            for item in case_results
            if isinstance(item, Mapping)
        )
        result = {
            "schema": CASE_RESULT_SCHEMA,
            "caseId": "alpha-beta-gamma-selected-test-data",
            "status": status,
            "preparationStatus": (
                "GATE_BLOCK" if infrastructure_issues else "passed"
            ),
            "preparedRequestCount": len(preparation_results),
            "rootWorkerCount": root_worker_count,
            "executed": executed,
            "skipped": 0,
            "target": target,
            "environment": environment,
            "machineFingerprint": _machine_fingerprint(),
            "candidateBindingDigest": candidate.digest,
            "requestDigest": request_document.get("requestDigest"),
            "caseResults": case_results,
            "preparationResults": preparation_results,
            "operationCount": operation_count,
            "loadedProviders": loaded_providers,
            "requiredProviders": required_providers,
            "environmentStartMs": 0,
            "environmentStartSource": "prestarted-environment",
            "staticGateMs": max(0, int(static_gate_ms)),
            "dataPreparationMs": case_session_wall_ms,
            "caseSessionWallMs": case_session_wall_ms,
            "maxCaseDataPreparationMs": max_case_data_preparation_ms,
            "phaseWorkMs": phase_work_ms,
            **timings,
            "capabilityTimings": capability_timings,
            "totalMs": _elapsed_ms(started),
            "baselineEligible": status == "passed" and executed == len(cases),
            "specRefs": list(SPEC_REFS),
            "issues": issues,
        }
        if not result["baselineEligible"]:
            result["baselineIneligibleReason"] = (
                "one or more selected business cases did not complete passed "
                "provision-test-cleanup execution"
            )
    except Exception as exc:  # noqa: BLE001 - verifier must emit fail-closed evidence
        result = {
            "schema": CASE_RESULT_SCHEMA,
            "caseId": "alpha-beta-gamma-selected-test-data",
            "status": "GATE_BLOCK",
            "preparationStatus": "GATE_BLOCK",
            "preparedRequestCount": 0,
            "rootWorkerCount": root_worker_count,
            "executed": 0,
            "skipped": 0,
            "caseResults": [],
            "preparationResults": [],
            "target": target,
            "environment": environment,
            "machineFingerprint": _machine_fingerprint(),
            "operationCount": 0,
            "loadedProviders": [],
            "requiredProviders": [],
            "environmentStartMs": 0,
            "environmentStartSource": "prestarted-environment",
            "staticGateMs": max(0, int(static_gate_ms)),
            "dataPreparationMs": (
                _elapsed_ms(preparation_started)
                if preparation_started is not None
                else 0
            ),
            "caseSessionWallMs": (
                _elapsed_ms(preparation_started)
                if preparation_started is not None
                else 0
            ),
            "maxCaseDataPreparationMs": 0,
            "phaseWorkMs": {},
            "requestCollectionMs": 0,
            "providerDiscoveryMs": 0,
            "planningMs": 0,
            "actorProvisionMs": 0,
            "testBodyMs": 0,
            "criticalPathMs": 0,
            "cleanupCriticalPathMs": 0,
            "receiptWriteMs": 0,
            "leaseWaitMs": 0,
            "cacheHits": 0,
            "cacheMisses": 0,
            "maxObservedConcurrency": 0,
            "capabilityTimings": [],
            "totalMs": _elapsed_ms(started),
            "baselineEligible": False,
            "specRefs": list(SPEC_REFS),
            "issues": [str(exc)],
        }
    write_json(report_dir / "case-result.json", result)
    return result


def _execute_case(
    case: CaseRef[Any],
    context: TestDataContext,
) -> dict[str, Any]:
    try:
        session = TestDataSession.for_case(case.case_id, context=context)
        executed = session.execute(case)
        return {
            "caseResult": executed.document(),
            "preparationResult": {
                "caseId": str(case.case_id.value),
                "requestId": case.request.request_id.value,
                "capabilityKey": case.request.capability.key.value,
                "receiptDigest": executed.provision_receipt.digest,
            },
            "issues": [],
        }
    except Exception as error:  # noqa: BLE001 - one case must not erase peer evidence
        case_id = str(case.case_id.value)
        return {
            "caseResult": {
                "caseId": case_id,
                "status": "GATE_BLOCK",
                "assertionIds": [],
                "assertions": [],
                "testExecution": {"executed": 0, "failed": 0, "skipped": 0},
            },
            "issues": [
                f"GATE_BLOCK: {case_id} did not complete typed Session: "
                f"{type(error).__name__}"
            ],
        }


def build_candidate_binding(
    *,
    environment: str,
    target: str,
    manifest: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> CandidateBinding:
    release = (manifest.get("release") or {}).get("candidate") or {}
    release_id = str(release.get("releaseId") or "").strip()
    release_digest = str(release.get("releaseDigest") or "").strip()
    if (
        readiness.get("passed") is not True
        or readiness.get("environment") != environment
        or readiness.get("releaseId") != release_id
        or readiness.get("manifestDigest") != release_digest
    ):
        raise ValueError("Data readiness is not bound to the package candidate release")
    post_ids = readiness.get("postIds")
    if not isinstance(post_ids, list) or not post_ids:
        raise ValueError("Data readiness must expose release post identities")
    return CandidateBinding(
        environment=environment,
        target=target,
        baseline_id=str(manifest.get("baselineId") or ""),
        package_digest=str(manifest.get("packageDigest") or ""),
        runtime_config_digest=str(manifest.get("runtimeConfigDigest") or ""),
        release_id=release_id,
        release_digest=release_digest,
        import_run_id=str(readiness.get("importRunId") or ""),
        release_post_ids=tuple(str(item).strip() for item in post_ids),
    )


def load_provider_evidence(
    path: Path | None,
    candidate: CandidateBinding,
    *,
    request_digest: str = "",
    required_capabilities: tuple[str, ...] = (),
) -> Mapping[str, Mapping[str, Any]]:
    if path is None:
        if required_capabilities:
            raise ValueError(
                "test-data Provider evidence is required for: "
                + ", ".join(required_capabilities)
            )
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError("test-data evidence schema mismatch")
    unsigned = {key: value for key, value in payload.items() if key != "evidenceDigest"}
    if payload.get("evidenceDigest") != canonical_digest(unsigned):
        raise ValueError("test-data evidence digest mismatch")
    if payload.get("candidateBindingDigest") != candidate.digest:
        raise ValueError("test-data evidence candidate binding mismatch")
    if payload.get("environment") != candidate.environment:
        raise ValueError("test-data evidence environment mismatch")
    if payload.get("target") != candidate.target:
        raise ValueError("test-data evidence target mismatch")
    if request_digest and payload.get("requestDigest") != request_digest:
        raise ValueError("test-data evidence request digest mismatch")
    evidence = payload.get("providerConformance")
    if not isinstance(evidence, Mapping):
        raise ValueError("test-data Provider evidence must be an object")
    if set(evidence) != set(required_capabilities):
        raise ValueError(
            "test-data Provider evidence closure mismatch: "
            f"actual={sorted(evidence)} required={sorted(required_capabilities)}"
        )
    result: dict[str, dict[str, Any]] = {}
    for name, item in evidence.items():
        if not isinstance(name, str) or not isinstance(item, Mapping):
            raise TypeError("test-data Provider evidence entry is invalid")
        if (
            item.get("providerCapabilityId") != name
            or item.get("status") != "passed"
            or item.get("candidateBindingDigest") != candidate.digest
            or not str(item.get("adapterId") or "").strip()
            or not str(item.get("readinessDigest") or "").startswith("sha256:")
        ):
            raise ValueError(f"test-data Provider evidence is invalid: {name}")
        result[name] = dict(item)
    return result


def build_provider_evidence_document(
    *,
    request_document: Mapping[str, Any],
    candidate: CandidateBinding,
    readiness_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Project only the selected request's canonical Provider capability closure."""

    cases = load_case_requests(request_document)
    required = sorted(
        {
            provider_key.value
            for case in cases
            for request in collect_request_graph((case.request,)).values()
            for provider_key in (
                request.capability.required_provider_capabilities
            )
        }
    )
    if readiness_report.get("schema") != "provider-conformance-readiness":
        raise ValueError("Provider readiness schema mismatch")
    source_issues = readiness_report.get("sourceCoverageIssues")
    if not isinstance(source_issues, list) or source_issues:
        raise ValueError("Provider readiness source coverage is incomplete")
    environments = readiness_report.get("readiness")
    selected = (
        environments.get(candidate.environment)
        if isinstance(environments, Mapping)
        else None
    )
    if not isinstance(selected, Mapping):
        raise ValueError("Provider readiness environment is missing")
    projected: dict[str, dict[str, Any]] = {}
    for capability_id in required:
        row = selected.get(capability_id)
        if (
            not isinstance(row, Mapping)
            or row.get("capability_ready") is not True
            or row.get("provider_conformance_required") is not True
            or not str(row.get("adapter_id") or "").strip()
        ):
            raise RuntimeError(
                "required Provider capability is not current and ready: "
                + capability_id
            )
        projected[capability_id] = {
            "providerCapabilityId": capability_id,
            "status": "passed",
            "candidateBindingDigest": candidate.digest,
            "adapterId": str(row["adapter_id"]),
            "readinessDigest": canonical_digest(row),
        }
    unsigned = {
        "schema": EVIDENCE_SCHEMA,
        "environment": candidate.environment,
        "target": candidate.target,
        "candidateBindingDigest": candidate.digest,
        "requestDigest": request_document.get("requestDigest"),
        "providerReadinessDigest": canonical_digest(readiness_report),
        "providerConformance": projected,
    }
    return {**unsigned, "evidenceDigest": canonical_digest(unsigned)}


def _load_run_summaries(root: Path) -> tuple[Mapping[str, Any], ...]:
    summaries: list[Mapping[str, Any]] = []
    for path in sorted(root.rglob("*-run-summary.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, Mapping) and isinstance(payload.get("payload"), Mapping):
            summaries.append(payload["payload"])
    return tuple(summaries)


def _aggregate_timings(
    summaries: tuple[Mapping[str, Any], ...],
) -> dict[str, int]:
    phase_fields = (
        "requestCollectionMs",
        "providerDiscoveryMs",
        "planningMs",
        "actorProvisionMs",
        "testBodyMs",
        "criticalPathMs",
        "cleanupCriticalPathMs",
        "receiptWriteMs",
        "leaseWaitMs",
        "dataPreparationMs",
    )
    result = {
        name: max(
            (int(item.get(name) or 0) for item in summaries),
            default=0,
        )
        for name in phase_fields
    }
    result["cacheHits"] = sum(int(item.get("cacheHits") or 0) for item in summaries)
    result["cacheMisses"] = sum(
        int(item.get("cacheMisses") or 0) for item in summaries
    )
    result["maxObservedConcurrency"] = max(
        (int(item.get("maxObservedConcurrency") or 0) for item in summaries),
        default=0,
    )
    return result


def _aggregate_phase_work(
    summaries: tuple[Mapping[str, Any], ...],
) -> dict[str, int]:
    names = {
        key
        for item in summaries
        for key in item
        if key.endswith("Ms") and isinstance(item.get(key), (int, float))
    }
    return {
        name: sum(int(item.get(name) or 0) for item in summaries)
        for name in sorted(names)
    }


def _load_capability_timings(root: Path) -> list[dict[str, Any]]:
    cleanup_by_request: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(document, Mapping):
            continue
        payload = document.get("payload")
        if not isinstance(payload, Mapping):
            continue
        if document.get("kind") == "cleanup":
            cleanup_by_request[str(payload.get("requestId") or "")] = int(
                payload.get("cleanupMs") or 0
            )
        elif document.get("kind") == "capability":
            rows.append(
                {
                    "requestId": str(payload.get("requestId") or ""),
                    "capabilityKey": str(payload.get("capabilityKey") or ""),
                    "ownerService": str(payload.get("ownerService") or ""),
                    "provisionMs": int(payload.get("provisionMs") or 0),
                    "readbackMs": int(payload.get("readbackMs") or 0),
                    "cleanupMs": 0,
                    "operationCount": int(payload.get("operationCount") or 0),
                }
            )
    for row in rows:
        row["cleanupMs"] = cleanup_by_request.get(str(row["requestId"]), 0)
    return rows


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _machine_fingerprint() -> str:
    value = "\0".join(
        (
            platform.node(),
            platform.system(),
            platform.machine(),
            platform.processor(),
        )
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(value).hexdigest()
