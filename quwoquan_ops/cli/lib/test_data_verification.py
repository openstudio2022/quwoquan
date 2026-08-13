"""Execute selected typed acceptance-data request graphs for stackctl verify."""

from __future__ import annotations

import hashlib
import json
import platform
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping

from .common import write_json
from .test_data.api import BusinessObjectRef, CaseRef, TestDataSession
from .test_data.discovery import load_provider
from .test_data.model import CandidateBinding, TestDataContext, canonical_digest
from .test_data.operations import TestDataRuntime
from .test_data.serialization import collect_request_graph, load_case_requests


CASE_RESULT_SCHEMA = "qwq.case_result"
EVIDENCE_SCHEMA = "qwq.test_data_evidence.v1"
HANDOFF_SCHEMA = "qwq.test_data_handoff"
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
    handoff_path: Path | None = None,
    static_gate_ms: int = 0,
    environment_start_ms: int = 0,
    environment_start_source: str = "prestarted-environment",
    benchmark_policy: str = "normal",
) -> dict[str, Any]:
    started = time.monotonic()
    run_id = uuid.uuid4().hex
    preparation_started: float | None = None
    root_worker_count = 0
    report_dir.mkdir(parents=True, exist_ok=True)
    try:
        if benchmark_policy not in {"normal", "serial-no-cache"}:
            raise ValueError("unsupported test-data benchmark policy")
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
        evidence_document: Mapping[str, Any] = {}
        if evidence_path is not None:
            loaded_evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            if not isinstance(loaded_evidence, Mapping):
                raise ValueError("test-data evidence must be an object")
            evidence_document = loaded_evidence
        provider_evidence = load_provider_evidence(
            evidence_path,
            candidate,
            request_digest=str(request_document.get("requestDigest") or ""),
            required_capabilities=tuple(required_provider_capabilities),
        )
        handoff_document: Mapping[str, Any] = {}
        if handoff_path is not None:
            if not evidence_document:
                raise ValueError("test-data handoff requires exact Provider evidence")
            handoff_document = load_test_data_handoff(
                handoff_path,
                candidate=candidate,
                readiness=release_readiness,
                request_document=request_document,
                evidence=evidence_document,
            )
        runtime = TestDataRuntime(
            candidate_cache_enabled=benchmark_policy == "normal"
        )
        context = TestDataContext(
            candidate=candidate,
            base_url=base_url,
            output_root=report_dir,
            provider_evidence=provider_evidence,
            max_concurrency=1 if benchmark_policy == "serial-no-cache" else 4,
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
        operation_count = len(runtime.operation_receipts)
        executed_operation_ids = sorted(
            {
                str(item.get("operationId") or "").strip()
                for item in runtime.operation_receipts
                if str(item.get("operationId") or "").strip()
            }
        )
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
            "runId": run_id,
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
            "sourceRevision": candidate.source_revision,
            "packageDigest": candidate.package_digest,
            "runtimeConfigDigest": candidate.runtime_config_digest,
            "releaseId": candidate.release_id,
            "manifestDigest": candidate.release_digest,
            "importRunId": candidate.import_run_id,
            "readinessReceiptDigest": candidate.readiness_receipt_digest,
            "requestDigest": request_document.get("requestDigest"),
            "evidenceDigest": evidence_document.get("evidenceDigest", ""),
            "handoffDigest": handoff_document.get("handoffDigest", ""),
            "caseResults": case_results,
            "preparationResults": preparation_results,
            "operationCount": operation_count,
            "executedOperationIds": executed_operation_ids,
            "loadedProviders": loaded_providers,
            "requiredProviders": required_providers,
            "requiredProviderCapabilities": required_provider_capabilities,
            "environmentStartMs": max(0, int(environment_start_ms)),
            "environmentStartSource": environment_start_source,
            "benchmarkPolicy": benchmark_policy,
            "benchmarkOnly": benchmark_policy != "normal",
            "staticGateMs": max(0, int(static_gate_ms)),
            "dataPreparationMs": case_session_wall_ms,
            "caseSessionWallMs": case_session_wall_ms,
            "maxCaseDataPreparationMs": max_case_data_preparation_ms,
            "phaseWorkMs": phase_work_ms,
            "controlPlaneOverheadMs": (
                int(timings["requestCollectionMs"])
                + int(timings["providerDiscoveryMs"])
                + int(timings["planningMs"])
            ),
            **timings,
            "capabilityTimings": capability_timings,
            "totalMs": max(0, int(environment_start_ms)) + _elapsed_ms(started),
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
            "runId": run_id,
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
            "executedOperationIds": [],
            "loadedProviders": [],
            "requiredProviders": [],
            "requiredProviderCapabilities": [],
            "environmentStartMs": max(0, int(environment_start_ms)),
            "environmentStartSource": environment_start_source,
            "benchmarkPolicy": benchmark_policy,
            "benchmarkOnly": benchmark_policy != "normal",
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
            "controlPlaneOverheadMs": 0,
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
            "totalMs": max(0, int(environment_start_ms)) + _elapsed_ms(started),
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
            "caseResult": executed.document(
                receipt_path_base=context.output_root,
            ),
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
    readiness_phase = str(readiness.get("readinessPhase") or "").strip()
    if readiness_phase not in {"research", "commercial"}:
        raise ValueError(
            "test-data readiness must be an immutable research or commercial release"
        )
    if (
        readiness.get("releaseClass") != readiness_phase
        or readiness.get("productLifecycleState") != readiness_phase
    ):
        raise ValueError(
            "Data readiness releaseClass/productLifecycleState drift from phase"
        )
    readiness_unsigned = {
        key: value for key, value in readiness.items() if key != "verificationChecksum"
    }
    readiness_receipt_digest = str(
        readiness.get("verificationChecksum") or ""
    ).strip()
    if readiness_receipt_digest != canonical_digest(readiness_unsigned):
        raise ValueError("Data readiness verification checksum mismatch")
    source_revision = str(manifest.get("sourceRevision") or "").strip()
    if (
        len(source_revision) != 40
        or any(character not in "0123456789abcdef" for character in source_revision)
        or readiness.get("sourceRevision") != source_revision
    ):
        raise ValueError(
            "Data readiness sourceRevision is not bound to the package candidate"
        )
    posts = _release_references(
        readiness.get("postIds"),
        field="postIds",
        object_type="Post",
    )
    creators = _release_references(
        readiness.get("creatorIds"),
        field="creatorIds",
        object_type="Creator",
    )
    entities = _release_references(
        readiness.get("entityRefs"),
        field="entityRefs",
        object_type="Entity",
    )
    tags = _release_references(
        readiness.get("tagRefs"),
        field="tagRefs",
        object_type="Tag",
    )
    media_assets = _release_references(
        readiness.get("mediaAssetIds"),
        field="mediaAssetIds",
        object_type="MediaAsset",
    )
    return CandidateBinding(
        environment=environment,
        target=target,
        source_revision=source_revision,
        baseline_id=str(manifest.get("baselineId") or ""),
        package_digest=str(manifest.get("packageDigest") or ""),
        runtime_config_digest=str(manifest.get("runtimeConfigDigest") or ""),
        release_id=release_id,
        release_digest=release_digest,
        import_run_id=str(readiness.get("importRunId") or ""),
        readiness_phase=readiness_phase,
        readiness_receipt_digest=readiness_receipt_digest,
        release_posts=posts,
        release_creators=creators,
        release_entities=entities,
        release_homepages=tuple(
            BusinessObjectRef("EntityHomepage", entity.object_id)
            for entity in entities
        ),
        release_tags=tags,
        release_media_assets=media_assets,
    )


def _release_references(
    value: object,
    *,
    field: str,
    object_type: str,
) -> tuple[BusinessObjectRef, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"Data readiness must expose release {field}")
    object_ids = tuple(str(item).strip() for item in value)
    if any(not object_id for object_id in object_ids) or len(object_ids) != len(
        set(object_ids)
    ):
        raise ValueError(
            f"Data readiness {field} must contain unique non-empty release identities"
        )
    return tuple(
        BusinessObjectRef(object_type=object_type, object_id=object_id)
        for object_id in object_ids
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


def build_test_data_handoff(
    *,
    candidate: CandidateBinding,
    readiness: Mapping[str, Any],
    request_document: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Freeze a redacted, exact candidate/request/evidence handoff contract."""

    source_revision = str(readiness.get("sourceRevision") or "").strip()
    if source_revision != candidate.source_revision:
        raise ValueError("canonical Data readiness sourceRevision drifted from candidate")
    evidence_unsigned = {
        key: value for key, value in evidence.items() if key != "evidenceDigest"
    }
    evidence_digest = str(evidence.get("evidenceDigest") or "").strip()
    if (
        evidence.get("schema") != EVIDENCE_SCHEMA
        or evidence_digest != canonical_digest(evidence_unsigned)
        or evidence.get("candidateBindingDigest") != candidate.digest
        or evidence.get("requestDigest") != request_document.get("requestDigest")
    ):
        raise ValueError("test-data evidence cannot be bound to this handoff")
    cases = load_case_requests(request_document)
    graph = {
        request_id: request
        for case in cases
        for request_id, request in collect_request_graph((case.request,)).items()
    }
    context = TestDataContext(
        candidate=candidate,
        base_url="https://test-data-handoff.invalid",
        output_root=Path("."),
        runtime=TestDataRuntime(),
    )
    provider_owners = sorted(
        {request.capability.owner_service for request in graph.values()}
    )
    allowed_operations: set[str] = set()
    required_operations: set[str] = set()
    for owner in provider_owners:
        provider = load_provider(owner, context)
        definitions = provider.describe()
        definitions_by_capability = {
            definition.capability: definition for definition in definitions
        }
        for request in graph.values():
            if request.capability.owner_service != owner:
                continue
            definition = definitions_by_capability.get(request.capability)
            if definition is None:
                raise ValueError(
                    f"handoff capability is absent from its Provider: "
                    f"{request.capability.key.value}"
                )
            allowed_operations.update(definition.operations)
            plan = provider.plan(context, request, request.params)
            if not set(plan.operations).issubset(definition.operations):
                raise ValueError(
                    "handoff required operation closure exceeds Provider definition: "
                    f"{request.capability.key.value}"
                )
            required_operations.update(plan.operations)
    unsigned = {
        "schema": HANDOFF_SCHEMA,
        "environment": candidate.environment,
        "target": candidate.target,
        "sourceRevision": candidate.source_revision,
        "baselineId": candidate.baseline_id,
        "packageDigest": candidate.package_digest,
        "runtimeConfigDigest": candidate.runtime_config_digest,
        "releaseId": candidate.release_id,
        "manifestDigest": candidate.release_digest,
        "importRunId": candidate.import_run_id,
        "readinessPhase": candidate.readiness_phase,
        "readinessReceiptDigest": candidate.readiness_receipt_digest,
        "requestDigest": request_document.get("requestDigest"),
        "evidenceDigest": evidence_digest,
        "candidateBindingDigest": candidate.digest,
        "expectedCases": [str(case.case_id.value) for case in cases],
        "expectedProviderOwners": provider_owners,
        "expectedProviderCapabilities": sorted(
            str(item)
            for item in (evidence.get("providerConformance") or {}).keys()
        ),
        # The request-specific ProviderPlan is the minimum closure; the
        # CapabilityDefinition remains the larger authorization surface.
        "requiredOperations": sorted(required_operations),
        "allowedOperations": sorted(allowed_operations),
    }
    return {**unsigned, "handoffDigest": canonical_digest(unsigned)}


def load_test_data_handoff(
    path: Path,
    *,
    candidate: CandidateBinding,
    readiness: Mapping[str, Any],
    request_document: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Accept only the byte-canonical handoff for this exact execution input."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("test-data handoff must be an object")
    expected = build_test_data_handoff(
        candidate=candidate,
        readiness=readiness,
        request_document=request_document,
        evidence=evidence,
    )
    if dict(payload) != expected:
        raise ValueError(
            "test-data handoff does not match the exact candidate/request/evidence"
        )
    return payload


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
