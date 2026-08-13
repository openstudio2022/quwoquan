"""Dependency-checked, on-demand and bounded-parallel test-data scheduler."""

from __future__ import annotations

import dataclasses
import time
import uuid
from threading import Event, Lock, Thread
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .api import (
    AssertionStatus,
    CaseExecution,
    CaseExecutionContext,
    CaseRef,
    CapabilityRequest,
    ExecutedCase,
    OutputRef,
    Provisioned,
    ReceiptRef,
    TestDataSession,
    validate_result,
)
from .capabilities.common import AcceptanceActorSet
from .discovery import load_provider
from .lease import ActorLease, ActorLeaseManager
from .model import (
    AcceptanceDataProvider,
    CapabilityDefinition,
    CleanupResult,
    NodeResult,
    ProviderPlan,
    PartialProvisioningError,
    ProvisionedCapability,
    TestDataContext,
    canonical_digest,
)
from .operations import TestDataRuntime
from .receipts import ReceiptJournal
from .serialization import collect_request_graph, request_graph_document


@dataclass(frozen=True)
class _PreparedNode:
    request: CapabilityRequest[Any, Any]
    provider: AcceptanceDataProvider
    definition: CapabilityDefinition
    plan: ProviderPlan


class _SessionImpl(TestDataSession):
    def __init__(self, *, case_id: Enum, context: TestDataContext) -> None:
        self._case_id = case_id
        self._context = context

    def provision(self, request: CapabilityRequest[Any, Any]) -> "_Scope":
        if not isinstance(request, CapabilityRequest):
            raise TypeError("provision requires a strongly typed CapabilityRequest")
        return _Scope(case_id=self._case_id, context=self._context, root=request)

    def execute(self, case: CaseRef[Any]) -> ExecutedCase:
        if not isinstance(case, CaseRef):
            raise TypeError("execute requires a strongly typed CaseRef")
        if case.case_id != self._case_id:
            raise ValueError("Session case identity does not match selected CaseRef")
        scope = _Scope(
            case_id=self._case_id,
            context=self._context,
            root=case.request,
        )
        with scope as provisioned:
            executed = scope.execute_case(case, provisioned)
        return scope.complete_executed_case(executed)


class _Scope:
    def __init__(
        self,
        *,
        case_id: Enum,
        context: TestDataContext,
        root: CapabilityRequest[Any, Any],
    ) -> None:
        self._case_id = str(case_id.value)
        self._base_context = context
        self._root = root
        self._entered = False
        self._results: dict[str, NodeResult] = {}
        self._provisioned_for_cleanup: dict[str, ProvisionedCapability] = {}
        self._result_lock = Lock()
        self._prepared: dict[str, _PreparedNode] = {}
        self._levels: tuple[tuple[str, ...], ...] = ()
        self._lease: ActorLease | None = None
        self._lease_manager: ActorLeaseManager | None = None
        self._test_body_started = 0.0
        self._started = 0.0
        self._metrics: dict[str, Any] = {}
        self._journal: ReceiptJournal | None = None
        self._context: TestDataContext | None = None
        self._cache_hits = 0
        self._cache_misses = 0
        self._cleanup_operation_count = 0
        self._activity_lock = Lock()
        self._active_operations = 0
        self._max_observed_concurrency = 0
        self._lease_stop = Event()
        self._lease_thread: Thread | None = None
        self._lease_renewal_error = ""
        self._case_execution: CaseExecution | None = None
        self._readback_receipts: list[ReceiptRef] = []
        self._cleanup_receipts: list[ReceiptRef] = []

    def __enter__(self) -> Provisioned[Any]:
        if self._entered:
            raise RuntimeError("test-data scope cannot be entered twice")
        self._entered = True
        self._started = time.monotonic()
        request_started = time.monotonic()
        graph = collect_request_graph((self._root,))
        request_document = request_graph_document((self._root,))
        self._metrics["requestCollectionMs"] = _elapsed_ms(request_started)
        instance_id = self._base_context.test_data_instance_id or str(uuid.uuid4())
        runtime = self._base_context.runtime or TestDataRuntime()
        context = replace(
            self._base_context,
            runtime=runtime,
            test_data_instance_id=instance_id,
        )
        self._context = context
        discovery_started = time.monotonic()
        providers = self._discover_providers(graph, context)
        self._metrics["providerDiscoveryMs"] = _elapsed_ms(discovery_started)
        self._metrics["loadedProviders"] = sorted(providers)
        self._metrics["requiredProviders"] = sorted(providers)
        self._validate_provider_evidence(graph, context)
        planning_started = time.monotonic()
        self._levels = _dependency_levels(graph)
        self._prepared = self._plan(graph, providers, context)
        self._metrics["planningMs"] = _elapsed_ms(planning_started)
        journal_root = (
            context.output_root
            / context.candidate.environment
            / "test-data"
            / self._case_id
            / instance_id
        )
        self._journal = ReceiptJournal(
            root=journal_root,
            case_id=self._case_id,
            test_data_instance_id=instance_id,
            candidate_binding_digest=context.candidate.digest,
        )
        try:
            self._journal.append(
                "request",
                {
                    "requestDigest": request_document["requestDigest"],
                    "rootRequestIds": request_document["roots"],
                    "requestCount": len(graph),
                },
            )
            self._metrics["leaseWaitMs"] = 0
            if any(
                request.capability.mutates_environment
                for request in graph.values()
            ):
                actor_started = time.monotonic()
                self._lease_manager = ActorLeaseManager(self._journal)
                self._lease = self._lease_manager.acquire(
                    lease_id=f"{self._case_id}-{instance_id}",
                    case_run_id=instance_id,
                )
                self._start_lease_renewal()
                self._metrics["actorProvisionMs"] = _elapsed_ms(actor_started)
            else:
                self._metrics["actorProvisionMs"] = 0
        except BaseException:
            self._journal.close()
            raise
        critical_started = time.monotonic()
        runtime.register_operation_receipt_sink(
            instance_id,
            lambda payload: self._journal.append("operation", payload),
        )
        try:
            for level in self._levels:
                self._provision_level(level, context)
            if self._lease_renewal_error:
                raise RuntimeError(
                    "actor lease renewal failed: " + self._lease_renewal_error
                )
        except BaseException as error:
            self._stop_lease_renewal()
            cleanup_started = time.monotonic()
            cleanup_issues: list[str] = []
            for level in reversed(self._levels):
                cleanup_issues.extend(self._cleanup_level(level, context))
            if self._lease is not None and self._lease_manager is not None:
                self._lease_manager.quarantine(
                    generation=self._lease.generation,
                    reason="provision did not produce a complete cleanup closure",
                )
            self._metrics.update(
                {
                    "criticalPathMs": _elapsed_ms(critical_started),
                    "dataPreparationMs": _elapsed_ms(self._started),
                    "testBodyMs": 0,
                    "cleanupCriticalPathMs": _elapsed_ms(cleanup_started),
                    "totalMs": _elapsed_ms(self._started),
                    "operationCount": sum(
                        result.provisioned.operation_count
                        for result in self._results.values()
                    )
                    + sum(
                        provisioned.operation_count
                        for request_id, provisioned in self._provisioned_for_cleanup.items()
                        if request_id not in self._results
                    )
                    + self._cleanup_operation_count,
                    "cleanupOperationCount": self._cleanup_operation_count,
                    "cacheHits": self._cache_hits,
                    "cacheMisses": self._cache_misses,
                    "maxObservedConcurrency": max(
                        self._max_observed_concurrency,
                        runtime.max_observed_concurrency,
                    ),
                    "status": "GATE_BLOCK",
                    "issues": [type(error).__name__, *cleanup_issues],
                    "receiptWriteMs": self._journal.write_ms,
                }
            )
            self._journal.append("run-summary", self._metrics)
            runtime.unregister_operation_receipt_sink(instance_id)
            self._journal.close()
            raise
        self._metrics["criticalPathMs"] = _elapsed_ms(critical_started)
        self._metrics["dataPreparationMs"] = _elapsed_ms(self._started)
        self._metrics["maxObservedConcurrency"] = max(
            self._max_observed_concurrency,
            runtime.max_observed_concurrency,
        )
        self._metrics["operationCount"] = sum(
            result.provisioned.operation_count for result in self._results.values()
        )
        self._metrics["cacheHits"] = self._cache_hits
        self._metrics["cacheMisses"] = self._cache_misses
        root_result = self._results[self._root.request_id.value]
        self._test_body_started = time.monotonic()
        return Provisioned(
            value=root_result.provisioned.value,
            receipt=root_result.receipt,
        )

    def execute_case(
        self,
        case: CaseRef[Any],
        provisioned: Provisioned[Any],
    ) -> ExecutedCase:
        if self._context is None or self._journal is None:
            raise RuntimeError("test-data scope is not active")
        execution_context = CaseExecutionContext(
            environment=self._context.candidate.environment,
            target=self._context.candidate.target,
            base_url=self._context.base_url,
            candidate_binding_digest=self._context.candidate.digest,
            test_data_instance_id=self._context.test_data_instance_id,
            request_id=case.request.request_id,
            provision_receipt=provisioned.receipt,
            runtime=self._context.runtime,
        )
        try:
            execution = case.runner_type.execute(
                provisioned.value,
                execution_context,
            )
            if type(execution) is not CaseExecution:
                raise TypeError("business case runner must return CaseExecution")
            test_body_receipt = self._journal.append(
                "test-body",
                {
                    "caseId": str(case.case_id.value),
                    "requestId": case.request.request_id.value,
                    "provisionReceiptDigest": provisioned.receipt.digest,
                    "status": execution.status.value,
                    "assertions": [
                        {
                            "assertionId": assertion.assertion_id,
                            "status": assertion.status.value,
                        }
                        for assertion in execution.assertions
                    ],
                },
            )
        except BaseException as error:
            self._journal.append(
                "test-body",
                {
                    "caseId": str(case.case_id.value),
                    "requestId": case.request.request_id.value,
                    "status": "GATE_BLOCK",
                    "errorType": type(error).__name__,
                },
            )
            raise
        self._case_execution = execution
        return ExecutedCase(
            case_id=str(case.case_id.value),
            execution=execution,
            candidate_binding_digest=self._context.candidate.digest,
            test_data_instance_id=self._context.test_data_instance_id,
            request_id=case.request.request_id,
            provision_receipt=provisioned.receipt,
            test_body_receipt=test_body_receipt,
        )

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if self._context is None or self._journal is None:
            return False
        runtime = self._context.runtime
        self._metrics["testBodyMs"] = _elapsed_ms(self._test_body_started)
        cleanup_started = time.monotonic()
        cleanup_issues: list[str] = []
        for level in reversed(self._levels):
            cleanup_issues.extend(self._cleanup_level(level, self._context))
        self._stop_lease_renewal()
        if self._lease_renewal_error:
            cleanup_issues.append(
                f"actor-lease-renewal:{self._lease_renewal_error}"
            )
        self._metrics["cleanupCriticalPathMs"] = _elapsed_ms(cleanup_started)
        self._metrics["cleanupOperationCount"] = self._cleanup_operation_count
        self._metrics["operationCount"] += self._cleanup_operation_count
        if self._case_execution is not None:
            self._metrics["executed"] = 1
            self._metrics["assertionCount"] = len(
                self._case_execution.assertions
            )
        else:
            self._metrics["executed"] = 0
            self._metrics["assertionCount"] = 0
        if self._lease is not None and self._lease_manager is not None:
            if not self._lease.actor_set_digest:
                cleanup_issues.append("actor-lease-unbound")
            if cleanup_issues:
                self._lease_manager.quarantine(
                    generation=self._lease.generation,
                    reason="cleanup did not reach a certain released state",
                )
            else:
                self._lease_manager.release(generation=self._lease.generation)
        self._metrics["totalMs"] = _elapsed_ms(self._started)
        self._metrics["issues"] = cleanup_issues
        self._metrics["status"] = (
            "GATE_BLOCK"
            if cleanup_issues
            else (
                "failed"
                if exc_type
                else (
                    self._case_execution.status.value
                    if self._case_execution is not None
                    else "prepared"
                )
            )
        )
        self._metrics["baselineEligible"] = (
            not cleanup_issues
            and exc_type is None
            and self._case_execution is not None
            and self._case_execution.status is AssertionStatus.PASSED
        )
        if not self._metrics["baselineEligible"]:
            self._metrics["baselineIneligibleReason"] = (
                "a completed passed business CaseResult is required in the "
                "same provision-test-cleanup scope"
            )
        if isinstance(runtime, TestDataRuntime):
            self._metrics["maxObservedConcurrency"] = max(
                int(self._metrics.get("maxObservedConcurrency") or 0),
                runtime.max_observed_concurrency,
            )
        self._metrics["receiptWriteMs"] = self._journal.write_ms
        self._journal.append("run-summary", self._metrics)
        if isinstance(runtime, TestDataRuntime):
            runtime.unregister_operation_receipt_sink(
                self._context.test_data_instance_id
            )
        self._journal.close()
        if cleanup_issues and exc_type is None:
            raise RuntimeError("test-data cleanup is quarantined: " + "; ".join(cleanup_issues))
        return False

    def _discover_providers(
        self,
        graph: Mapping[str, CapabilityRequest[Any, Any]],
        context: TestDataContext,
    ) -> dict[str, AcceptanceDataProvider]:
        owners = sorted({request.capability.owner_service for request in graph.values()})
        return {owner: load_provider(owner, context) for owner in owners}

    def _validate_provider_evidence(
        self,
        graph: Mapping[str, CapabilityRequest[Any, Any]],
        context: TestDataContext,
    ) -> None:
        required = {
            provider_capability
            for request in graph.values()
            for provider_capability in request.capability.required_provider_capabilities
        }
        for capability in sorted(required):
            capability_id = capability.value
            evidence = context.provider_evidence.get(capability_id)
            if not isinstance(evidence, Mapping) or evidence.get("status") != "passed":
                raise RuntimeError(
                    f"required Provider evidence is unavailable: {capability_id}"
                )
            if evidence.get("candidateBindingDigest") != context.candidate.digest:
                raise RuntimeError(
                    f"Provider evidence candidate binding mismatch: {capability_id}"
                )

    def _plan(
        self,
        graph: Mapping[str, CapabilityRequest[Any, Any]],
        providers: Mapping[str, AcceptanceDataProvider],
        context: TestDataContext,
    ) -> dict[str, _PreparedNode]:
        prepared: dict[str, _PreparedNode] = {}
        for request_id, request in graph.items():
            provider = providers[request.capability.owner_service]
            definitions = tuple(
                definition
                for definition in provider.describe()
                if definition.capability == request.capability
            )
            if len(definitions) != 1:
                raise RuntimeError(
                    f"Provider must own exactly one definition for {request.capability.key.value}"
                )
            definition = definitions[0]
            resolved = _resolve_value(request.params, self._results, allow_unresolved=True)
            plan = provider.plan(context, request, resolved)
            if plan.request_id != request_id:
                raise RuntimeError("Provider plan request identity mismatch")
            if plan.capability_definition_digest != definition.digest:
                raise RuntimeError("Provider plan capability definition digest mismatch")
            if plan.operations != definition.operations:
                raise RuntimeError("Provider plan operation closure mismatch")
            prepared[request_id] = _PreparedNode(
                request=request,
                provider=provider,
                definition=definition,
                plan=plan,
            )
        return prepared

    def _provision_level(self, level: tuple[str, ...], context: TestDataContext) -> None:
        with ThreadPoolExecutor(
            max_workers=min(context.max_concurrency, len(level)),
            thread_name_prefix="test-data-provision",
        ) as pool:
            futures = {
                request_id: pool.submit(self._provision_node, request_id, context)
                for request_id in level
            }
            errors: list[tuple[str, BaseException]] = []
            for request_id in level:
                try:
                    self._results[request_id] = futures[request_id].result()
                except BaseException as error:
                    errors.append((request_id, error))
            if errors:
                request_id, error = errors[0]
                raise RuntimeError(
                    f"capability provision failed for {request_id}: "
                    f"{type(error).__name__}: {error}"
                ) from error

    def _provision_node(self, request_id: str, context: TestDataContext) -> NodeResult:
        prepared = self._prepared[request_id]
        resolved = _resolve_value(prepared.request.params, self._results)
        plan = replace(prepared.plan, resolved_params=resolved)
        runtime = context.runtime
        if not isinstance(runtime, TestDataRuntime):
            raise TypeError("TestData runtime is unavailable")
        params_identity = canonical_digest({"repr": repr(resolved)})
        cached: ProvisionedCapability | None = None
        cache_reservation = False
        if prepared.request.capability.candidate_cacheable:
            cached, cache_hit, cache_reservation = runtime.candidate_cache_get(
                candidate_binding_digest=context.candidate.digest,
                capability_key=prepared.request.capability.key.value,
                params_identity=params_identity,
            )
            with self._activity_lock:
                if cache_hit:
                    self._cache_hits += 1
                else:
                    self._cache_misses += 1
        started = time.monotonic()
        try:
            with runtime.capability_slot(
                provider_key=prepared.request.capability.owner_service,
                capability_key=prepared.request.capability.key.value,
                resource_key=(
                    f"actor-lease:{context.test_data_instance_id}"
                    if prepared.request.capability.mutates_environment
                    else ""
                ),
                max_concurrency=context.max_concurrency,
                capability_limit=prepared.definition.concurrency_limit,
            ):
                self._operation_started()
                try:
                    if cached is not None:
                        provisioned = cached
                    else:
                        provisioned = prepared.provider.provision(context, plan)
                    with self._result_lock:
                        self._provisioned_for_cleanup[request_id] = provisioned
                    provision_ms = _elapsed_ms(started)
                    value = validate_result(
                        provisioned.value,
                        prepared.request.capability.result_type,
                    )
                    self._bind_actor_set(value)
                    provisioned = replace(provisioned, value=value)
                    with self._result_lock:
                        self._provisioned_for_cleanup[request_id] = provisioned
                    assert self._journal is not None
                    provision_receipt = self._journal.append(
                        "provision",
                        {
                            "requestId": request_id,
                            "capabilityKey": prepared.request.capability.key.value,
                            "ownerService": prepared.request.capability.owner_service,
                            "provisionMs": provision_ms,
                            "operationCount": provisioned.operation_count,
                        },
                    )
                    readback_started = time.monotonic()
                    readback = prepared.provider.readback(context, provisioned)
                    readback_ms = _elapsed_ms(readback_started)
                    readback_receipt = self._journal.append(
                        "readback",
                        {
                            "requestId": request_id,
                            "capabilityKey": prepared.request.capability.key.value,
                            "passed": readback.passed,
                            "readbackMs": readback_ms,
                            "operationCount": readback.operation_count,
                            "details": dict(readback.details),
                        },
                    )
                    with self._result_lock:
                        self._readback_receipts.append(readback_receipt)
                finally:
                    self._operation_finished()
        except PartialProvisioningError as error:
            with self._result_lock:
                self._provisioned_for_cleanup[request_id] = error.provisioned
            if cache_reservation:
                runtime.candidate_cache_abort(
                    candidate_binding_digest=context.candidate.digest,
                    capability_key=prepared.request.capability.key.value,
                    params_identity=params_identity,
                )
            raise
        except BaseException:
            if cache_reservation:
                runtime.candidate_cache_abort(
                    candidate_binding_digest=context.candidate.digest,
                    capability_key=prepared.request.capability.key.value,
                    params_identity=params_identity,
                )
            raise
        if not readback.passed:
            if cache_reservation:
                runtime.candidate_cache_abort(
                    candidate_binding_digest=context.candidate.digest,
                    capability_key=prepared.request.capability.key.value,
                    params_identity=params_identity,
                )
            raise RuntimeError(
                f"capability readback failed: {prepared.request.capability.key.value}"
            )
        if cache_reservation:
            runtime.candidate_cache_put(
                candidate_binding_digest=context.candidate.digest,
                capability_key=prepared.request.capability.key.value,
                params_identity=params_identity,
                value=provisioned,
            )
        assert self._journal is not None
        self._journal.append(
            "capability",
            {
                "requestId": request_id,
                "capabilityKey": prepared.request.capability.key.value,
                "capabilityDefinitionDigest": prepared.definition.digest,
                "ownerService": prepared.request.capability.owner_service,
                "provisionReceiptDigest": provision_receipt.digest,
                "readbackReceiptDigest": readback_receipt.digest,
                "provisionMs": provision_ms,
                "readbackMs": readback_ms,
                "operationCount": provisioned.operation_count + readback.operation_count,
                "readback": dict(readback.details),
            },
        )
        return NodeResult(
            provisioned=replace(
                provisioned,
                operation_count=provisioned.operation_count + readback.operation_count,
            ),
            receipt=provision_receipt,
            provision_ms=provision_ms,
            readback_ms=readback_ms,
        )

    def _cleanup_level(self, level: tuple[str, ...], context: TestDataContext) -> list[str]:
        issues: list[str] = []
        with ThreadPoolExecutor(
            max_workers=min(context.max_concurrency, len(level)),
            thread_name_prefix="test-data-cleanup",
        ) as pool:
            futures: dict[str, Future[tuple[CleanupResult, int]]] = {
                request_id: pool.submit(self._cleanup_node, request_id, context)
                for request_id in level
                if request_id in self._results
                or request_id in self._provisioned_for_cleanup
            }
            for request_id, future in futures.items():
                try:
                    result, cleanup_ms = future.result()
                except Exception as error:  # noqa: BLE001
                    issues.append(f"{request_id}:{type(error).__name__}")
                    continue
                if result.state != "released":
                    issues.append(f"{request_id}:{result.state}")
                self._cleanup_operation_count += result.operation_count
                assert self._journal is not None
                cleanup_receipt = self._journal.append(
                    "cleanup",
                    {
                        "requestId": request_id,
                        "state": result.state,
                        "cleanupMs": cleanup_ms,
                        "operationCount": result.operation_count,
                        "details": dict(result.details),
                    },
                )
                with self._result_lock:
                    self._cleanup_receipts.append(cleanup_receipt)
        return issues

    def _cleanup_node(
        self,
        request_id: str,
        context: TestDataContext,
    ) -> tuple[CleanupResult, int]:
        prepared = self._prepared[request_id]
        started = time.monotonic()
        runtime = context.runtime
        if not isinstance(runtime, TestDataRuntime):
            raise TypeError("TestData runtime is unavailable")
        with runtime.capability_slot(
            provider_key=prepared.request.capability.owner_service,
            capability_key=prepared.request.capability.key.value,
            resource_key=(
                f"actor-lease:{context.test_data_instance_id}"
                if prepared.request.capability.mutates_environment
                else ""
            ),
            max_concurrency=context.max_concurrency,
            capability_limit=prepared.definition.concurrency_limit,
        ):
            self._operation_started()
            try:
                with self._result_lock:
                    provisioned = self._results.get(request_id)
                    cleanup_value = (
                        provisioned.provisioned
                        if provisioned is not None
                        else self._provisioned_for_cleanup[request_id]
                    )
                result = prepared.provider.cleanup(
                    context,
                    cleanup_value,
                )
            finally:
                self._operation_finished()
        return result, _elapsed_ms(started)

    def _operation_started(self) -> None:
        with self._activity_lock:
            self._active_operations += 1
            self._max_observed_concurrency = max(
                self._max_observed_concurrency,
                self._active_operations,
            )

    def _operation_finished(self) -> None:
        with self._activity_lock:
            self._active_operations -= 1

    def _bind_actor_set(self, value: object) -> None:
        if not isinstance(value, AcceptanceActorSet):
            return
        if self._lease is None or self._lease_manager is None:
            raise RuntimeError("mutable ActorSet was provisioned without an ActorLease")
        self._lease = self._lease_manager.bind_actor_set(
            generation=self._lease.generation,
            actor_set_digest=value.identity_digest,
        )

    def complete_executed_case(self, executed: ExecutedCase) -> ExecutedCase:
        if not self._readback_receipts or not self._cleanup_receipts:
            raise RuntimeError(
                "CaseResult requires provision, test-body, readback and cleanup receipts"
            )
        return replace(
            executed,
            readback_receipts=tuple(
                sorted(
                    self._readback_receipts,
                    key=lambda receipt: receipt.path.as_posix(),
                )
            ),
            cleanup_receipts=tuple(
                sorted(
                    self._cleanup_receipts,
                    key=lambda receipt: receipt.path.as_posix(),
                )
            ),
        )

    def _start_lease_renewal(self) -> None:
        if self._lease is None or self._lease_manager is None:
            return
        interval = max(0.1, self._lease.renewal_interval.total_seconds())
        generation = self._lease.generation

        def renew_until_stopped() -> None:
            while not self._lease_stop.wait(interval):
                try:
                    renewed = self._lease_manager.renew(generation=generation)
                except Exception as error:  # noqa: BLE001
                    self._lease_renewal_error = type(error).__name__
                    self._lease_stop.set()
                    return
                self._lease = renewed

        self._lease_thread = Thread(
            target=renew_until_stopped,
            name="test-data-actor-lease-renewal",
            daemon=True,
        )
        self._lease_thread.start()

    def _stop_lease_renewal(self) -> None:
        self._lease_stop.set()
        if self._lease_thread is not None:
            self._lease_thread.join(timeout=1)
            self._lease_thread = None


def build_session(*, case_id: Enum, context: object | None) -> TestDataSession:
    if not isinstance(context, TestDataContext):
        raise TypeError("TestDataSession requires a TestDataContext")
    return _SessionImpl(case_id=case_id, context=context)


def _dependency_levels(
    graph: Mapping[str, CapabilityRequest[Any, Any]],
) -> tuple[tuple[str, ...], ...]:
    dependencies = {
        request_id: {
            ref.request_id.value
            for ref in _refs(request.params)
        }
        for request_id, request in graph.items()
    }
    levels: list[tuple[str, ...]] = []
    remaining = set(graph)
    completed: set[str] = set()
    while remaining:
        ready = tuple(sorted(node for node in remaining if dependencies[node] <= completed))
        if not ready:
            raise ValueError("test-data request graph contains a cycle")
        levels.append(ready)
        completed.update(ready)
        remaining.difference_update(ready)
    return tuple(levels)


def _refs(value: object):
    if isinstance(value, OutputRef):
        yield value
    elif is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            yield from _refs(getattr(value, field.name))
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _refs(item)


def _resolve_value(
    value: object,
    results: Mapping[str, NodeResult],
    *,
    allow_unresolved: bool = False,
) -> object:
    if isinstance(value, OutputRef):
        result = results.get(value.request_id.value)
        if result is None:
            if allow_unresolved:
                return value
            raise RuntimeError(f"dependency result is unavailable: {value.request_id.value}")
        resolved = result.provisioned.value
        for name in value.field_path:
            if not is_dataclass(resolved) or not hasattr(resolved, name):
                raise RuntimeError(f"dependency output field is unavailable: {name}")
            resolved = getattr(resolved, name)
        if type(resolved) is not value.value_type:
            raise TypeError(
                f"dependency output expected {value.value_type.__name__}, "
                f"got {type(resolved).__name__}"
            )
        return resolved
    if is_dataclass(value) and not isinstance(value, type):
        return type(value)(
            **{
                field.name: _resolve_value(
                    getattr(value, field.name),
                    results,
                    allow_unresolved=allow_unresolved,
                )
                for field in fields(value)
            }
        )
    if isinstance(value, tuple):
        return tuple(
            _resolve_value(item, results, allow_unresolved=allow_unresolved)
            for item in value
        )
    if isinstance(value, list):
        return [
            _resolve_value(item, results, allow_unresolved=allow_unresolved)
            for item in value
        ]
    return value


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))
