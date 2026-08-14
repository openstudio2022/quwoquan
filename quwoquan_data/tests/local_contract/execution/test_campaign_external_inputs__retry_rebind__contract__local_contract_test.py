# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""controller 重试进程必须重新绑定 frozen external input context。

lane 启动进程通过 require_campaign_external_inputs 完成进程内 bind；
controller 重试/恢复是新进程，不经过该入口。此时 canonical envelope
文件是唯一真相源：它存在就必须 resolve+bind，绝不允许静默返回 None
降级为公开 discovery（历史缺陷：image lane 重试后为 96 个实体写出
acquisitionReceiptRefs=[] 的 plan，download_fetch 阶段 UNDECLARED 崩溃）。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from content.execution.campaign import external_input_runtime as runtime_module
from content.execution.campaign.external_input_runtime import (
    ExternalInputRuntimeContext,
    bound_runtime_external_input_context,
    execution_external_input_envelope_path,
)

_EXECUTION_ID = "20260813--travel-image-m100--china--scale-099"


@pytest.fixture(autouse=True)
def _clean_bound_contexts():
    with runtime_module._BOUND_CONTEXTS_LOCK:
        runtime_module._BOUND_CONTEXTS.clear()
    yield
    with runtime_module._BOUND_CONTEXTS_LOCK:
        runtime_module._BOUND_CONTEXTS.clear()


class _FakeRuntimePaths:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root


def _context(carrier: str) -> ExternalInputRuntimeContext:
    return ExternalInputRuntimeContext(
        root=Path("/dev/null"),
        envelope={"executionId": _EXECUTION_ID, "carrier": carrier},
        refs=(),
        blob_refs_by_digest={},
    )


def test_missing_envelope_returns_none_for_non_campaign_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        runtime_module, "_runtime_paths", lambda: _FakeRuntimePaths(tmp_path)
    )

    assert bound_runtime_external_input_context(_EXECUTION_ID, "image") is None


def test_retry_process_rebinds_from_canonical_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    envelope_path = execution_external_input_envelope_path(
        tmp_path / "data" / "tasks" / _EXECUTION_ID
    )
    envelope_path.parent.mkdir(parents=True)
    envelope_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        runtime_module, "_runtime_paths", lambda: _FakeRuntimePaths(tmp_path)
    )
    resolved = _context("image")
    calls: list[tuple[str, str]] = []

    def fake_resolve(execution_id, carrier, *, runtime_paths=None):
        calls.append((execution_id, carrier))
        return resolved

    monkeypatch.setattr(
        runtime_module, "resolve_runtime_external_input_context", fake_resolve
    )

    context = bound_runtime_external_input_context(_EXECUTION_ID, "image")

    assert context is resolved
    assert calls == [(_EXECUTION_ID, "image")]
    # rebind 后进入进程内缓存：后续调用不再重复 resolve。
    assert bound_runtime_external_input_context(_EXECUTION_ID, "image") is resolved
    assert calls == [(_EXECUTION_ID, "image")]


def test_envelope_resolve_failure_stays_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    envelope_path = execution_external_input_envelope_path(
        tmp_path / "data" / "tasks" / _EXECUTION_ID
    )
    envelope_path.parent.mkdir(parents=True)
    envelope_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        runtime_module, "_runtime_paths", lambda: _FakeRuntimePaths(tmp_path)
    )

    def fake_resolve(execution_id, carrier, *, runtime_paths=None):
        raise runtime_module._typed("ENVELOPE_INVALID", "broken envelope")

    monkeypatch.setattr(
        runtime_module, "resolve_runtime_external_input_context", fake_resolve
    )

    with pytest.raises(Exception, match="EXTERNAL_INPUT_ENVELOPE_INVALID"):
        bound_runtime_external_input_context(_EXECUTION_ID, "image")


def test_cached_carrier_drift_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with runtime_module._BOUND_CONTEXTS_LOCK:
        runtime_module._BOUND_CONTEXTS[_EXECUTION_ID] = _context("video")

    with pytest.raises(Exception, match="IDENTITY_DRIFT"):
        bound_runtime_external_input_context(_EXECUTION_ID, "image")
