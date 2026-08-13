"""Cross-process fairness and fast-fail state for semantic-agent providers.

The broker owns only disposable runtime coordination under ``data/local``. It
does not become a content, release, or billing truth source. Every real agent
invocation must acquire one lease; account/auth rejection opens a short-lived
provider circuit so sibling campaign lanes stop spending capacity immediately.
"""
from __future__ import annotations

import json
import hashlib
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Mapping

from core.control_types import AgentFailureKind, AgentProvider
from core.paths import DATA_RUNTIME_WORKSPACE_ROOT, SCHEMA_ROOT
from core.runtime_policy import runtime_profile_digest

if TYPE_CHECKING:
    from content.execution.agent.outcome import AgentRunOutcome


class SemanticCapacityTimeout(RuntimeError):
    """No governed provider slot became available before the caller deadline."""


class SemanticProviderCircuitOpen(RuntimeError):
    """A sibling run already proved a non-retryable provider-wide blocker."""

    def __init__(self, circuit: Mapping[str, object]):
        self.circuit = dict(circuit)
        super().__init__(str(circuit.get("message") or "semantic provider circuit is open"))


def semantic_provider_capacity(policy: object) -> int:
    """Reserve one semantic slot per configured campaign lane.

    A lane remains serial (``author_workers``), while independent homepage,
    article, image and video processes may progress together. This derives from
    the governed worker policy instead of an environment override.
    """
    lane_workers = max(1, int(getattr(policy, "campaign_lane_workers", 1)))
    author_workers = max(1, int(getattr(policy, "author_workers", 1)))
    return lane_workers * author_workers


def semantic_provider_lane(ctx: object) -> str:
    spec = getattr(ctx, "spec", None)
    content = getattr(spec, "content", None)
    carriers = tuple(getattr(content, "carriers", ()) or ())
    if len(carriers) == 1:
        return str(getattr(carriers[0], "value", carriers[0])).strip() or "unknown"
    return "unknown"


@dataclass(slots=True)
class SemanticCapacityLease:
    broker: "SemanticCapacityBroker"
    provider: AgentProvider
    request_id: str
    lane: str
    capacity: int
    lane_capacity: int
    requests_per_minute: int
    burst_limit: int
    acquired_at: float
    wait_duration_ms: int
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        self.broker.release(self.provider, self.request_id)
        self._released = True

    def __enter__(self) -> "SemanticCapacityLease":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.release()


class SemanticCapacityBroker:
    """Small flock-backed broker shared by detached campaign processes."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        account_scope_id: str = "default-account",
        host_scope_id: str = "local-host",
        pid: int | None = None,
        wall_clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        pid_alive: Callable[[int], bool] | None = None,
    ) -> None:
        self.root = root or (DATA_RUNTIME_WORKSPACE_ROOT / "semantic-agent-capacity")
        self.account_scope_id = str(account_scope_id or "").strip()
        self.host_scope_id = str(host_scope_id or "").strip()
        if not self.account_scope_id or not self.host_scope_id:
            raise ValueError("semantic capacity account/host scope is required")
        self.pid = int(pid or os.getpid())
        self._wall_clock = wall_clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._pid_alive = pid_alive or self._default_pid_alive

    @staticmethod
    def _default_pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _paths(self, provider: AgentProvider) -> tuple[Path, Path]:
        self.root.mkdir(parents=True, exist_ok=True)
        scope = hashlib.sha256(
            f"{provider.value}\0{self.account_scope_id}\0{self.host_scope_id}".encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        return (
            self.root / f"{provider.value}.{scope}.state.json",
            self.root / f"{provider.value}.{scope}.lock",
        )

    @staticmethod
    def _empty_state(provider: AgentProvider) -> dict[str, object]:
        return {
            "schema": "quwoquan_data.semantic_agent_capacity_state",
            "provider": provider.value,
            "nextTicket": 1,
            "lastGrantedLane": "",
            "waiters": [],
            "leases": [],
            "circuit": None,
        }

    def _read_state(self, path: Path, provider: AgentProvider) -> dict[str, object]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return self._empty_state(provider)
        if not isinstance(raw, dict) or raw.get("provider") != provider.value:
            return self._empty_state(provider)
        return raw

    @staticmethod
    def _write_state(path: Path, state: Mapping[str, object]) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(state, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)

    def _prune(self, state: dict[str, object], *, now: float) -> None:
        leases = state.get("leases") if isinstance(state.get("leases"), list) else []
        state["leases"] = [
            row
            for row in leases
            if isinstance(row, dict)
            and float(row.get("expiresAt") or 0) > now
            and self._pid_alive(int(row.get("pid") or 0))
        ]
        waiters = state.get("waiters") if isinstance(state.get("waiters"), list) else []
        state["waiters"] = [
            row
            for row in waiters
            if isinstance(row, dict) and self._pid_alive(int(row.get("pid") or 0))
        ]
        circuit = state.get("circuit")
        if isinstance(circuit, dict) and float(circuit.get("expiresAt") or 0) <= now:
            state["circuit"] = None

    def _mutate(
        self,
        provider: AgentProvider,
        callback: Callable[[dict[str, object], float], object],
    ) -> object:
        try:
            import fcntl
        except ImportError as exc:  # pragma: no cover - production targets Unix
            raise RuntimeError("semantic capacity broker requires flock") from exc
        state_path, lock_path = self._paths(provider)
        with lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            state = self._read_state(state_path, provider)
            now = self._wall_clock()
            self._prune(state, now=now)
            result = callback(state, now)
            self._write_state(state_path, state)
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            return result

    @staticmethod
    def _next_waiter(state: Mapping[str, object]) -> str:
        rows = [row for row in state.get("waiters") or [] if isinstance(row, dict)]
        lanes = sorted({str(row.get("lane") or "unknown") for row in rows})
        if not lanes:
            return ""
        last = str(state.get("lastGrantedLane") or "")
        if last in lanes:
            lane = lanes[(lanes.index(last) + 1) % len(lanes)]
        else:
            lane = lanes[0]
        candidates = [row for row in rows if str(row.get("lane") or "unknown") == lane]
        selected = min(candidates, key=lambda row: int(row.get("ticket") or 0))
        return str(selected.get("requestId") or "")

    def acquire(
        self,
        provider: AgentProvider,
        *,
        lane: str,
        capacity: int,
        lane_capacity: int | None = None,
        requests_per_minute: int | None = None,
        burst_limit: int | None = None,
        wait_timeout_seconds: float,
        lease_ttl_seconds: float,
    ) -> SemanticCapacityLease:
        resolved_lane_capacity = int(lane_capacity or capacity)
        resolved_requests_per_minute = int(requests_per_minute or 60_000)
        resolved_burst = int(burst_limit or max(capacity, 1_000))
        if (
            capacity < 1
            or resolved_lane_capacity < 1
            or resolved_requests_per_minute < 1
            or resolved_burst < 1
            or wait_timeout_seconds <= 0
            or lease_ttl_seconds <= 0
        ):
            raise ValueError("semantic capacity limits must be positive")
        normalized_lane = str(lane or "unknown").strip() or "unknown"
        request_id = str(uuid.uuid4())
        wait_started = self._monotonic()
        deadline = self._monotonic() + wait_timeout_seconds

        def attempt(state: dict[str, object], now: float) -> str:
            circuit = state.get("circuit")
            if isinstance(circuit, dict):
                state["waiters"] = [
                    row
                    for row in state.get("waiters") or []
                    if isinstance(row, dict) and row.get("requestId") != request_id
                ]
                return "circuit"
            waiters = state.get("waiters") if isinstance(state.get("waiters"), list) else []
            if not any(
                isinstance(row, dict) and row.get("requestId") == request_id
                for row in waiters
            ):
                ticket = int(state.get("nextTicket") or 1)
                waiters.append(
                    {
                        "requestId": request_id,
                        "ticket": ticket,
                        "lane": normalized_lane,
                        "pid": self.pid,
                        "createdAt": now,
                    }
                )
                state["nextTicket"] = ticket + 1
                state["waiters"] = waiters
            leases = state.get("leases") if isinstance(state.get("leases"), list) else []
            lane_leases = sum(
                isinstance(row, dict) and row.get("lane") == normalized_lane
                for row in leases
            )
            bucket = state.get("tokenBucket")
            bucket = bucket if isinstance(bucket, dict) else {}
            last_refill = float(bucket.get("lastRefillAt") or now)
            tokens = min(
                float(resolved_burst),
                float(bucket.get("tokens", resolved_burst))
                + max(0.0, now - last_refill)
                * resolved_requests_per_minute
                / 60.0,
            )
            state["tokenBucket"] = {
                "requestsPerMinute": resolved_requests_per_minute,
                "burstLimit": resolved_burst,
                "tokens": tokens,
                "lastRefillAt": now,
            }
            if (
                len(leases) >= capacity
                or lane_leases >= resolved_lane_capacity
                or tokens < 1.0
                or self._next_waiter(state) != request_id
            ):
                return "waiting"
            state["waiters"] = [
                row
                for row in state.get("waiters") or []
                if isinstance(row, dict) and row.get("requestId") != request_id
            ]
            leases.append(
                {
                    "requestId": request_id,
                    "lane": normalized_lane,
                    "pid": self.pid,
                    "acquiredAt": now,
                    "expiresAt": now + lease_ttl_seconds,
                }
            )
            state["leases"] = leases
            state["lastGrantedLane"] = normalized_lane
            state["tokenBucket"]["tokens"] = tokens - 1.0
            return "granted"

        while True:
            decision = str(self._mutate(provider, attempt))
            if decision == "granted":
                return SemanticCapacityLease(
                    self,
                    provider,
                    request_id,
                    normalized_lane,
                    capacity,
                    resolved_lane_capacity,
                    resolved_requests_per_minute,
                    resolved_burst,
                    self._wall_clock(),
                    int(max(0.0, self._monotonic() - wait_started) * 1000),
                )
            if decision == "circuit":
                circuit = self.check_circuit(provider) or {}
                raise SemanticProviderCircuitOpen(circuit)
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                self._cancel_waiter(provider, request_id)
                raise SemanticCapacityTimeout(
                    f"semantic provider capacity wait timed out: {provider.value}/{normalized_lane}"
                )
            self._sleep(min(0.1, remaining))

    def _cancel_waiter(self, provider: AgentProvider, request_id: str) -> None:
        def cancel(state: dict[str, object], _now: float) -> None:
            state["waiters"] = [
                row
                for row in state.get("waiters") or []
                if isinstance(row, dict) and row.get("requestId") != request_id
            ]

        self._mutate(provider, cancel)

    def release(self, provider: AgentProvider, request_id: str) -> None:
        def remove(state: dict[str, object], _now: float) -> None:
            state["leases"] = [
                row
                for row in state.get("leases") or []
                if isinstance(row, dict) and row.get("requestId") != request_id
            ]

        self._mutate(provider, remove)

    def check_circuit(self, provider: AgentProvider) -> dict[str, object] | None:
        return self._mutate(
            provider,
            lambda state, _now: (
                dict(state["circuit"])
                if isinstance(state.get("circuit"), dict)
                else None
            ),
        )  # type: ignore[return-value]

    def open_circuit(
        self,
        provider: AgentProvider,
        *,
        model: str,
        failure_kind: AgentFailureKind,
        message: str,
        cooldown_seconds: float,
        retryable: bool = False,
        retry_after_seconds: int = 0,
    ) -> dict[str, object]:
        if cooldown_seconds <= 0:
            raise ValueError("semantic provider circuit cooldown must be positive")

        def open_state(state: dict[str, object], now: float) -> dict[str, object]:
            circuit = {
                "provider": provider.value,
                "model": str(model).strip(),
                "failureKind": failure_kind.value,
                "message": " ".join(str(message).split())[:800],
                "retryable": bool(retryable),
                "retryAfterSeconds": max(0, int(retry_after_seconds)),
                "openedAt": now,
                "expiresAt": now + cooldown_seconds,
                "openedByPid": self.pid,
            }
            state["circuit"] = circuit
            return circuit

        return self._mutate(provider, open_state)  # type: ignore[return-value]

    def close_circuit(self, provider: AgentProvider) -> None:
        self._mutate(provider, lambda state, _now: state.update({"circuit": None}))

    def snapshot(self, provider: AgentProvider) -> dict[str, object]:
        return self._mutate(provider, lambda state, _now: dict(state))  # type: ignore[return-value]

    def write_capacity_receipt(
        self,
        lease: SemanticCapacityLease,
        *,
        execution_id: str = "",
        source_review: Mapping[str, object] | None = None,
        model: str,
        role: str,
        prompt: str,
        outcome: "AgentRunOutcome",
        runtime_profile_id: str,
        recorded_at: str | None = None,
    ) -> tuple[dict[str, object], Path]:
        """Persist one create-once invocation capacity receipt."""
        if lease.broker is not self:
            raise ValueError("capacity lease belongs to another broker")
        normalized_execution_id = str(execution_id or "").strip()
        normalized_source_review = dict(source_review or {})
        normalized_model = str(model or "").strip()
        normalized_role = str(role or "").strip()
        if normalized_role not in {"author", "reviewer", "calibration"}:
            raise ValueError("capacity receipt role is invalid")
        if bool(normalized_execution_id) == bool(normalized_source_review):
            raise ValueError(
                "capacity receipt requires exactly one executionId or sourceReview identity"
            )
        if not normalized_model:
            raise ValueError("capacity receipt model is required")
        from core.schema import assert_valid

        stable_identity = {
            "provider": lease.provider.value,
            "model": normalized_model,
            "role": normalized_role,
            "requestId": lease.request_id,
        }
        if normalized_execution_id:
            stable_identity["executionId"] = normalized_execution_id
            receipt_scope = normalized_execution_id
        else:
            required = {
                "sourceRevision", "sourceDigest", "entityCatalogDigest",
                "executionBundleDigest", "handoffDigest", "requestDigest",
            }
            if set(normalized_source_review) != required:
                raise ValueError("sourceReview identity fields are invalid")
            stable_identity["sourceReview"] = normalized_source_review
            receipt_scope = "source-review-" + str(
                normalized_source_review["requestDigest"]
            ).removeprefix("sha256:")[:20]
        receipt_id = "sha256:" + hashlib.sha256(
            json.dumps(
                stable_identity,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        payload: dict[str, object] = {
            "schema": "quwoquan_data.semantic_capacity_receipt",
            "receiptId": receipt_id,
            **stable_identity,
            "lane": lease.lane,
            "capacityLimit": lease.capacity,
            "laneCapacityLimit": lease.lane_capacity,
            "requestsPerMinute": lease.requests_per_minute,
            "burstLimit": lease.burst_limit,
            "accountScopeId": self.account_scope_id,
            "hostScopeId": self.host_scope_id,
            "acquiredAt": _iso_time(lease.acquired_at),
            "waitDurationMs": lease.wait_duration_ms,
            "runtimeProfileId": runtime_profile_id,
            "runtimeProfileDigest": runtime_profile_digest(runtime_profile_id),
            "sdkVersion": _provider_runtime_version(lease.provider),
            "promptSha256": _sha256_text(prompt),
            "outputSchemaDigest": _output_schema_digest(normalized_role),
            "status": outcome.status.value,
            "failureKind": (
                outcome.failure_kind.value if outcome.failure_kind else None
            ),
            "errorCode": outcome.error_code or None,
            "retryable": outcome.retryable,
            "retryAfterSeconds": outcome.retry_after_seconds,
            "runId": outcome.run_id or None,
            "resultSha256": _sha256_text(outcome.result_text),
            "recordedAt": recorded_at or _iso_time(self._wall_clock()),
        }
        assert_valid(
            payload,
            "execution",
            "semantic_capacity_receipt",
            label=f"semantic capacity receipt:{receipt_id}",
        )
        receipt_root = self.root / "receipts" / receipt_scope
        receipt_root.mkdir(parents=True, exist_ok=True)
        path = receipt_root / f"{receipt_id.removeprefix('sha256:')}.json"
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"
        if path.is_file():
            if path.read_text(encoding="utf-8") != encoded:
                raise RuntimeError(f"capacity receipt identity collision: {path}")
            return payload, path
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(encoded)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != encoded:
                raise RuntimeError(f"capacity receipt identity collision: {path}")
        return payload, path


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _iso_time(epoch_seconds: float) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat().replace(
        "+00:00",
        "Z",
    )


def _provider_runtime_version(provider: AgentProvider) -> str:
    if provider is AgentProvider.CURSOR_SDK:
        try:
            return f"cursor-sdk {metadata.version('cursor-sdk')}"
        except metadata.PackageNotFoundError:
            return "cursor-sdk-version-unavailable"
    from content.execution.agent.codex_adapter import codex_sdk_version

    return codex_sdk_version()


def _output_schema_digest(role: str) -> str:
    schema_name = (
        "agent_result_envelope.schema.json"
        if role == "author"
        else "reviewer_result.schema.json"
    )
    return "sha256:" + hashlib.sha256(
        (SCHEMA_ROOT / "content" / schema_name).read_bytes()
    ).hexdigest()


__all__ = [
    "SemanticCapacityBroker",
    "SemanticCapacityLease",
    "SemanticCapacityTimeout",
    "SemanticProviderCircuitOpen",
    "semantic_provider_capacity",
    "semantic_provider_lane",
]
