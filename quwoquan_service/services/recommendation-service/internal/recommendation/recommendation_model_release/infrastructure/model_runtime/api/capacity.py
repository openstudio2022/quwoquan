"""Capacity controls for recommendation-service scoring.

This module owns inference-only concerns: short TTL score cache,
micro-batch coalescing, timeout budget metadata, and guardrail mode export.
The model scorers stay focused on feature transformation and scoring.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

from api.metrics import (
    record_score_batch,
    record_score_cache_hit,
    record_score_cache_miss,
    set_guardrail_mode,
    set_timeout_budget,
)
from generated.recommendation.recommendation_model_release.models.request_response import (
    ModelScoreRequest,
    ModelScoreResponse,
)


@dataclass(frozen=True)
class InferenceCapacityConfig:
    cache_ttl_s: float
    max_cache_entries: int
    microbatch_window_ms: float
    model_budget_ms: float
    feature_budget_ms: float
    retry_budget_ms: float
    guardrail_mode: str


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_capacity_config() -> InferenceCapacityConfig:
    guardrail_mode = os.environ.get("REC_MODEL_GUARDRAIL_MODE", "suggest_only")
    return InferenceCapacityConfig(
        cache_ttl_s=max(0.0, _float_env("REC_MODEL_SCORE_CACHE_TTL_MS", 500.0) / 1000.0),
        max_cache_entries=max(0, _int_env("REC_MODEL_SCORE_CACHE_MAX_ENTRIES", 4096)),
        microbatch_window_ms=max(0.0, _float_env("REC_MODEL_MICROBATCH_WINDOW_MS", 2.0)),
        model_budget_ms=max(1.0, _float_env("REC_MODEL_MODEL_BUDGET_MS", 80.0)),
        feature_budget_ms=max(1.0, _float_env("REC_MODEL_FEATURE_BUDGET_MS", 20.0)),
        retry_budget_ms=max(0.0, _float_env("REC_MODEL_RETRY_BUDGET_MS", 15.0)),
        guardrail_mode=guardrail_mode,
    )


class ScoreCache:
    def __init__(self, ttl_s: float, max_entries: int) -> None:
        self._ttl_s = ttl_s
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, ModelScoreResponse]] = {}

    def get(self, key: str) -> ModelScoreResponse | None:
        if self._ttl_s <= 0 or self._max_entries <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            hit = self._entries.get(key)
            if hit is None:
                return None
            expires_at, value = hit
            if expires_at <= now:
                self._entries.pop(key, None)
                return None
            return value

    def set(self, key: str, value: ModelScoreResponse) -> None:
        if self._ttl_s <= 0 or self._max_entries <= 0:
            return
        expires_at = time.monotonic() + self._ttl_s
        with self._lock:
            if len(self._entries) >= self._max_entries:
                oldest_key = min(self._entries, key=lambda item: self._entries[item][0])
                self._entries.pop(oldest_key, None)
            self._entries[key] = (expires_at, value)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


class MicroBatcher:
    """Small same-request coalescer for concurrent duplicate score calls."""

    def __init__(self, window_ms: float) -> None:
        self._window_s = window_ms / 1000.0
        self._lock = threading.Lock()
        self._inflight: dict[str, "_BatchState"] = {}

    def run(
        self,
        *,
        key: str,
        scenario: str,
        scorer_kind: str,
        compute: Callable[[], ModelScoreResponse],
    ) -> ModelScoreResponse:
        if self._window_s <= 0:
            record_score_batch(scenario, scorer_kind, "direct", 1)
            return compute()

        with self._lock:
            state = self._inflight.get(key)
            if state is None:
                state = _BatchState()
                self._inflight[key] = state
                leader = True
            else:
                state.waiters += 1
                leader = False

        if leader:
            try:
                time.sleep(self._window_s)
                result = compute()
                with state.condition:
                    state.result = result
                    state.done = True
                    state.condition.notify_all()
                record_score_batch(scenario, scorer_kind, "coalesced", state.waiters)
                return result
            except BaseException as exc:
                with state.condition:
                    state.error = exc
                    state.done = True
                    state.condition.notify_all()
                raise
            finally:
                with self._lock:
                    self._inflight.pop(key, None)

        with state.condition:
            while not state.done:
                state.condition.wait()
            if state.error is not None:
                raise state.error
            if state.result is None:
                raise RuntimeError("microbatch completed without result")
            return state.result


@dataclass
class _BatchState:
    waiters: int = 1
    result: ModelScoreResponse | None = None
    error: BaseException | None = None
    done: bool = False

    def __post_init__(self) -> None:
        self.condition = threading.Condition()


def score_cache_key(body: ModelScoreRequest, scorer_kind: str) -> str:
    payload = {
        "scenario": body.scenario,
        "scorerKind": scorer_kind,
        "userFeatures": body.userFeatures or {},
        "sessionSignals": body.sessionSignals or {},
        "context": body.context or {},
        "candidates": [candidate.model_dump(mode="json") for candidate in body.candidates],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


_config = load_capacity_config()
_score_cache = ScoreCache(_config.cache_ttl_s, _config.max_cache_entries)
_micro_batcher = MicroBatcher(_config.microbatch_window_ms)


def refresh_capacity_metrics() -> None:
    set_timeout_budget("feature", _config.feature_budget_ms / 1000.0)
    set_timeout_budget("model", _config.model_budget_ms / 1000.0)
    set_timeout_budget("retry", _config.retry_budget_ms / 1000.0)
    set_guardrail_mode(_config.guardrail_mode)


def clear_score_cache() -> None:
    _score_cache.clear()


def score_with_capacity_controls(
    body: ModelScoreRequest,
    *,
    scorer_kind: str,
    compute: Callable[[], ModelScoreResponse],
) -> ModelScoreResponse:
    key = score_cache_key(body, scorer_kind)
    cached = _score_cache.get(key)
    if cached is not None:
        record_score_cache_hit(body.scenario, scorer_kind)
        return cached

    record_score_cache_miss(body.scenario, scorer_kind)
    started = time.perf_counter()
    result = _micro_batcher.run(
        key=key,
        scenario=body.scenario,
        scorer_kind=scorer_kind,
        compute=compute,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if elapsed_ms <= _config.model_budget_ms:
        _score_cache.set(key, result)
    return result
