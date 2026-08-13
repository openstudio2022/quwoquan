"""ContractGraph-resolved public operation executor for acceptance Providers."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import quote, urlencode

from ..local_environment_auth import (
    LocalAcceptanceActor,
    LocalEnvironmentHTTPError,
    request_local_environment_json,
)
from .capabilities.common import ActorHandle, ActorRole
from .model import ProvisionedCapability


ROOT = Path(__file__).resolve().parents[4]
CONTRACT_GRAPH = ROOT / "quwoquan_service/generated/contract_graph.json"


@dataclass(frozen=True)
class ContractOperation:
    operation_id: str
    method: str
    path_template: str

    def path(self, bindings: Mapping[str, str] | None = None) -> str:
        result = self.path_template
        supplied = dict(bindings or {})
        for name in re.findall(r"{([A-Za-z][A-Za-z0-9]*)}", result):
            value = str(supplied.pop(name, "")).strip()
            if not value:
                raise ValueError(f"operation {self.operation_id} missing binding {name}")
            result = result.replace("{" + name + "}", quote(value, safe=""))
        if supplied:
            raise ValueError(
                f"operation {self.operation_id} received unknown bindings "
                f"{sorted(supplied)}"
            )
        return result


class ContractOperationCatalog:
    def __init__(self, graph_path: Path = CONTRACT_GRAPH) -> None:
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
        rows = payload.get("operations") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("generated ContractGraph operations are unavailable")
        self._operations = {
            str(row["id"]): ContractOperation(
                operation_id=str(row["id"]),
                method=str(row.get("method") or ""),
                path_template=str(row.get("pathTemplate") or ""),
            )
            for row in rows
            if isinstance(row, dict) and str(row.get("id") or "")
        }

    def require(self, operation_id: str) -> ContractOperation:
        operation = self._operations.get(operation_id)
        if operation is None or not operation.method or not operation.path_template:
            raise ValueError(
                f"required ContractGraph operation is missing or incomplete: {operation_id}"
            )
        return operation


class TestDataRuntime:
    """Opaque session handles and per-run operation accounting shared by Providers."""

    def __init__(self, *, candidate_cache_enabled: bool = True) -> None:
        self._sessions: dict[str, LocalAcceptanceActor] = {}
        self._actor_handles: dict[tuple[str, ActorRole], ActorHandle] = {}
        self._candidate_cache: dict[tuple[str, str, str], ProvisionedCapability] = {}
        self._candidate_inflight: dict[
            tuple[str, str, str],
            threading.Event,
        ] = {}
        self._operation_catalog: ContractOperationCatalog | None = None
        self._operation_receipt_sinks: dict[
            str,
            Callable[[Mapping[str, Any]], None],
        ] = {}
        self._global_capacity: threading.BoundedSemaphore | None = None
        self._global_capacity_size = 0
        self._capability_capacities: dict[
            str,
            tuple[int, threading.BoundedSemaphore],
        ] = {}
        self._provider_capacities: dict[
            str,
            tuple[int, threading.BoundedSemaphore],
        ] = {}
        self._resource_capacities: dict[str, threading.BoundedSemaphore] = {}
        self._active_capabilities = 0
        self._max_observed_concurrency = 0
        self._candidate_cache_enabled = candidate_cache_enabled
        self._lock = threading.Lock()
        self.operation_receipts: list[dict[str, Any]] = []
        self.provider_overrides: dict[str, object] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    @contextmanager
    def capability_slot(
        self,
        *,
        provider_key: str,
        capability_key: str,
        resource_key: str = "",
        max_concurrency: int,
        capability_limit: int,
    ) -> Iterator[None]:
        """Apply one shared limit across every concurrently running case."""

        if not 1 <= max_concurrency <= 16:
            raise ValueError("global test-data concurrency must be within 1..16")
        if not 1 <= capability_limit <= 16:
            raise ValueError("capability concurrency must be within 1..16")
        with self._lock:
            if self._global_capacity is None:
                self._global_capacity = threading.BoundedSemaphore(max_concurrency)
                self._global_capacity_size = max_concurrency
            elif self._global_capacity_size != max_concurrency:
                raise RuntimeError(
                    "shared TestDataRuntime received conflicting global concurrency"
                )
            capability_entry = self._capability_capacities.get(capability_key)
            if capability_entry is None:
                capability_capacity = threading.BoundedSemaphore(capability_limit)
                self._capability_capacities[capability_key] = (
                    capability_limit,
                    capability_capacity,
                )
            else:
                configured_limit, capability_capacity = capability_entry
                if configured_limit != capability_limit:
                    raise RuntimeError(
                        "capability received conflicting concurrency limits: "
                        + capability_key
                    )
            provider_entry = self._provider_capacities.get(provider_key)
            if provider_entry is None:
                provider_capacity = threading.BoundedSemaphore(capability_limit)
                self._provider_capacities[provider_key] = (
                    capability_limit,
                    provider_capacity,
                )
            else:
                provider_limit, provider_capacity = provider_entry
                if provider_limit != capability_limit:
                    raise RuntimeError(
                        "Provider capabilities declare conflicting concurrency limits: "
                        + provider_key
                    )
            resource_capacity = (
                self._resource_capacities.setdefault(
                    resource_key,
                    threading.BoundedSemaphore(1),
                )
                if resource_key
                else None
            )
            global_capacity = self._global_capacity
        assert global_capacity is not None
        # Narrow resource and Provider capacities are acquired before the
        # global budget so queued work cannot occupy unrelated global slots.
        if resource_capacity is not None:
            resource_capacity.acquire()
        provider_capacity.acquire()
        capability_capacity.acquire()
        global_capacity.acquire()
        with self._lock:
            self._active_capabilities += 1
            self._max_observed_concurrency = max(
                self._max_observed_concurrency,
                self._active_capabilities,
            )
        try:
            yield
        finally:
            with self._lock:
                self._active_capabilities -= 1
            global_capacity.release()
            capability_capacity.release()
            provider_capacity.release()
            if resource_capacity is not None:
                resource_capacity.release()

    @property
    def max_observed_concurrency(self) -> int:
        with self._lock:
            return self._max_observed_concurrency

    def register_actor(
        self,
        handle: ActorHandle,
        actor: LocalAcceptanceActor,
        *,
        test_data_instance_id: str,
    ) -> None:
        with self._lock:
            if handle.session_handle in self._sessions:
                raise RuntimeError("actor session handle collision")
            key = (test_data_instance_id, handle.role)
            if key in self._actor_handles:
                raise RuntimeError("test-data Actor role is already registered")
            self._sessions[handle.session_handle] = actor
            self._actor_handles[key] = handle

    def actor(self, handle: ActorHandle) -> LocalAcceptanceActor:
        with self._lock:
            actor = self._sessions.get(handle.session_handle)
        if actor is None:
            raise RuntimeError("actor session handle is unavailable")
        if actor.session.owner_id != handle.account.object_id:
            raise RuntimeError("actor session/account binding mismatch")
        if actor.session.persona_id != handle.persona.object_id:
            raise RuntimeError("actor session/persona binding mismatch")
        return actor

    def actor_for(
        self,
        *,
        test_data_instance_id: str,
        role: ActorRole,
    ) -> ActorHandle:
        with self._lock:
            handle = self._actor_handles.get((test_data_instance_id, role))
        if handle is None:
            raise RuntimeError(
                f"test-data Actor role is unavailable: {role.value}"
            )
        self.actor(handle)
        return handle

    def register_operation_receipt_sink(
        self,
        test_data_instance_id: str,
        sink: Callable[[Mapping[str, Any]], None],
    ) -> None:
        with self._lock:
            if test_data_instance_id in self._operation_receipt_sinks:
                raise RuntimeError("operation receipt sink is already registered")
            self._operation_receipt_sinks[test_data_instance_id] = sink

    def unregister_operation_receipt_sink(self, test_data_instance_id: str) -> None:
        with self._lock:
            self._operation_receipt_sinks.pop(test_data_instance_id, None)

    def append_operation(
        self,
        receipt: Mapping[str, Any],
        *,
        test_data_instance_id: str,
    ) -> None:
        sink: Callable[[Mapping[str, Any]], None] | None
        with self._lock:
            sink = self._operation_receipt_sinks.get(test_data_instance_id)
        if sink is None:
            raise RuntimeError("operation receipt sink is unavailable")
        sink(receipt)
        # Publish the in-memory view only after durable append succeeds; a
        # failed receipt write must not leave a second, falsely successful
        # operation history in this process.
        with self._lock:
            self.operation_receipts.append(dict(receipt))

    def candidate_cache_get(
        self,
        *,
        candidate_binding_digest: str,
        capability_key: str,
        params_identity: str,
    ) -> tuple[ProvisionedCapability | None, bool, bool]:
        if not self._candidate_cache_enabled:
            with self._lock:
                self.cache_misses += 1
            return None, False, False
        key = (candidate_binding_digest, capability_key, params_identity)
        while True:
            with self._lock:
                value = self._candidate_cache.get(key)
                if value is not None:
                    self.cache_hits += 1
                    return value, True, False
                pending = self._candidate_inflight.get(key)
                if pending is None:
                    self._candidate_inflight[key] = threading.Event()
                    self.cache_misses += 1
                    return None, False, True
            # Another case owns the immutable lookup.  Wait outside the
            # runtime lock, then re-check; an aborted owner allows one waiter
            # to reserve and retry rather than publishing an empty cache hit.
            pending.wait()

    def candidate_cache_put(
        self,
        *,
        candidate_binding_digest: str,
        capability_key: str,
        params_identity: str,
        value: ProvisionedCapability,
    ) -> None:
        key = (candidate_binding_digest, capability_key, params_identity)
        with self._lock:
            self._candidate_cache.setdefault(key, value)
            pending = self._candidate_inflight.pop(key, None)
        if pending is not None:
            pending.set()

    def candidate_cache_abort(
        self,
        *,
        candidate_binding_digest: str,
        capability_key: str,
        params_identity: str,
    ) -> None:
        key = (candidate_binding_digest, capability_key, params_identity)
        with self._lock:
            pending = self._candidate_inflight.pop(key, None)
        if pending is not None:
            pending.set()

    def operation_catalog(self) -> ContractOperationCatalog:
        with self._lock:
            catalog = self._operation_catalog
            if catalog is None:
                catalog = ContractOperationCatalog()
                self._operation_catalog = catalog
            return catalog


class PublicOperationExecutor:
    def __init__(
        self,
        *,
        base_url: str,
        target: str,
        test_data_instance_id: str,
        capability_key: str,
        runtime: TestDataRuntime,
        catalog: ContractOperationCatalog | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.target = target
        self.test_data_instance_id = test_data_instance_id
        self.capability_key = capability_key
        self.runtime = runtime
        self.catalog = catalog or runtime.operation_catalog()
        self.operation_count = 0

    def call(
        self,
        operation_id: str,
        *,
        actor: ActorHandle,
        step_id: str,
        bindings: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
        query: Mapping[str, str | int] | None = None,
    ) -> dict[str, Any]:
        operation = self.catalog.require(operation_id)
        path = operation.path(bindings)
        if query:
            path += "?" + urlencode(
                [(name, str(value)) for name, value in sorted(query.items())]
            )
        idempotency_key = "/".join(
            (
                self.target,
                self.test_data_instance_id,
                self.capability_key,
                actor.role.value,
                operation_id,
                step_id,
            )
        )
        response = request_local_environment_json(
            self.base_url,
            path=path,
            session=self.runtime.actor(actor).session,
            method=operation.method,
            body=dict(body) if body is not None else None,
            headers={"Idempotency-Key": idempotency_key},
        )
        self.operation_count += 1
        self.runtime.append_operation(
            {
                "operationId": operation_id,
                "actorRole": actor.role.value,
                "stepId": step_id,
                "requestDigest": _digest(
                    {
                        "bindings": dict(bindings or {}),
                        "body": dict(body or {}),
                        "query": dict(query or {}),
                        "idempotencyKey": idempotency_key,
                    }
                ),
                "responseDigest": _digest(response),
            },
            test_data_instance_id=self.test_data_instance_id,
        )
        return response

    def expect_status(
        self,
        operation_id: str,
        *,
        actor: ActorHandle,
        step_id: str,
        expected_status: int,
        bindings: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> None:
        operation = self.catalog.require(operation_id)
        path = operation.path(bindings)
        idempotency_key = "/".join(
            (
                self.target,
                self.test_data_instance_id,
                self.capability_key,
                actor.role.value,
                operation_id,
                step_id,
            )
        )
        try:
            request_local_environment_json(
                self.base_url,
                path=path,
                session=self.runtime.actor(actor).session,
                method=operation.method,
                body=dict(body) if body is not None else None,
                headers={"Idempotency-Key": idempotency_key},
            )
        except LocalEnvironmentHTTPError as exc:
            if exc.status != expected_status:
                raise RuntimeError(
                    f"{operation_id} returned HTTP {exc.status}, expected {expected_status}"
                ) from exc
            self.operation_count += 1
            self.runtime.append_operation(
                {
                    "operationId": operation_id,
                    "actorRole": actor.role.value,
                    "stepId": step_id,
                    "requestDigest": _digest(
                        {
                            "bindings": dict(bindings or {}),
                            "body": dict(body or {}),
                            "idempotencyKey": idempotency_key,
                        }
                    ),
                    "expectedStatus": expected_status,
                    "actualStatus": exc.status,
                },
                test_data_instance_id=self.test_data_instance_id,
            )
            return
        raise RuntimeError(
            f"{operation_id} unexpectedly succeeded; expected HTTP {expected_status}"
        )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
