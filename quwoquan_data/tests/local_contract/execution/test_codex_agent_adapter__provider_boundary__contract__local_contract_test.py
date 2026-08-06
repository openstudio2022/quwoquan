from __future__ import annotations

import json
from types import SimpleNamespace

from content.execution.agent import codex_adapter
from core.control_types import AgentFailureKind, AgentProvider, RuntimeEnvironment
from core.cursor_model import CursorModelParameter, CursorModelSelection
from core.python_environment import agent_runtime_modules


class _FakeSandbox:
    read_only = object()
    workspace_write = object()


class _FakeApprovalMode:
    deny_all = object()


def _bindings(codex_class=object) -> codex_adapter._CodexSdkBindings:
    return codex_adapter._CodexSdkBindings(
        codex_class=codex_class,
        sandbox_class=_FakeSandbox,
        approval_mode_class=_FakeApprovalMode,
        is_retryable_error=lambda _exc: False,
    )


def _sdk_failure(
    message: str,
    *,
    started: bool = True,
    retryable: bool = False,
) -> codex_adapter._CodexSdkInvocationError:
    return codex_adapter._CodexSdkInvocationError(
        RuntimeError(message),
        started=started,
        retryable=retryable,
    )


def test_codex_adapter_uses_official_sdk_sandbox_and_structured_output(
    monkeypatch,
    tmp_path,
) -> None:
    observed: dict[str, object] = {}

    class FakeThread:
        id = "codex-thread-1"

        def run(self, prompt, **kwargs):
            observed["prompt"] = prompt
            observed["turn"] = kwargs
            return SimpleNamespace(
                id="codex-turn-1",
                status=SimpleNamespace(value="completed"),
                duration_ms=17,
                final_response=json.dumps(
                    {"status": "completed", "summary": "probe completed"}
                ),
            )

    class FakeCodex:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def thread_start(self, **kwargs):
            observed["thread"] = kwargs
            return FakeThread()

    monkeypatch.setattr(codex_adapter, "_load_codex_sdk", lambda: _bindings(FakeCodex))

    report = codex_adapter.codex_startup_probe(
        model="gpt-5.6-terra",
        runtime="local",
        timeout_seconds=5,
        cwd=tmp_path,
    )

    thread = observed["thread"]
    turn = observed["turn"]
    assert isinstance(thread, dict)
    assert isinstance(turn, dict)
    assert thread == {
        "approval_mode": _FakeApprovalMode.deny_all,
        "config": None,
        "cwd": str(tmp_path),
        "ephemeral": True,
        "model": "gpt-5.6-terra",
        "sandbox": _FakeSandbox.read_only,
        "service_name": "quwoquan_data",
    }
    assert turn["approval_mode"] is _FakeApprovalMode.deny_all
    assert turn["cwd"] == str(tmp_path)
    assert turn["sandbox"] is _FakeSandbox.read_only
    schema = turn["output_schema"]
    assert isinstance(schema, dict)
    assert schema["properties"]["status"] == {
        "type": "string",
        "const": "completed",
    }
    assert observed["prompt"] not in thread.values()
    assert report["provider"] == "codex_sdk"
    assert report["runId"] == "codex-thread-1"
    assert report["ready"] is True


def test_codex_adapter_runs_author_with_workspace_write_without_fallback(
    monkeypatch,
) -> None:
    observed: dict[str, object] = {}

    def invoke(_bindings, **kwargs):
        observed.update(kwargs)
        return codex_adapter._CodexSdkResult(
            thread_id="author-thread",
            turn_id="author-turn",
            final_response=json.dumps(
                {"status": "completed", "summary": "author completed"}
            ),
            status="completed",
            duration_ms=23,
        )

    monkeypatch.setattr(codex_adapter, "_load_codex_sdk", lambda: _bindings())
    monkeypatch.setattr(codex_adapter, "_invoke_codex_sdk", invoke)
    context = SimpleNamespace(
        runtime=RuntimeEnvironment.LOCAL,
        model_selection=CursorModelSelection(model_id="gpt-5.6-terra"),
    )

    result = codex_adapter.run_codex_agent(context, "author prompt")

    assert result.succeeded is True
    assert result.provider is AgentProvider.CODEX_SDK
    assert result.agent_id == "openai-codex-python-sdk"
    assert result.run_id == "author-thread"
    assert result.request_id == "author-turn"
    assert observed["sandbox"] == "workspace-write"
    assert observed["prompt"] == "author prompt"


def test_codex_adapter_classifies_usage_exhaustion_without_retry(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(codex_adapter, "_load_codex_sdk", lambda: _bindings())
    monkeypatch.setattr(
        codex_adapter,
        "_invoke_codex_sdk",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            _sdk_failure("You've hit your usage limit; capacity is unavailable")
        ),
    )

    report = codex_adapter.codex_startup_probe(
        model="gpt-5.6-terra",
        runtime="local",
        timeout_seconds=5,
        cwd=tmp_path,
    )

    assert report["ready"] is False
    assert report["errorClass"] == AgentFailureKind.PROVIDER_REJECTED.value
    assert report["errorCode"] == "semantic_provider_quota_exhausted"
    assert report["retryable"] is False


def test_codex_adapter_classifies_authentication_rejection(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(codex_adapter, "_load_codex_sdk", lambda: _bindings())
    monkeypatch.setattr(
        codex_adapter,
        "_invoke_codex_sdk",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            _sdk_failure("Not logged in; authentication required", started=False)
        ),
    )

    report = codex_adapter.codex_startup_probe(
        model="gpt-5.6-terra",
        runtime="local",
        timeout_seconds=5,
        cwd=tmp_path,
    )

    assert report["errorClass"] == AgentFailureKind.AUTHENTICATION_REJECTED.value
    assert report["retryable"] is False
    assert report["started"] is False


def test_codex_adapter_rejects_unknown_model_parameter_before_launch(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        codex_adapter,
        "_load_codex_sdk",
        lambda: (_ for _ in ()).throw(AssertionError("must not load SDK")),
    )
    selection = CursorModelSelection(
        model_id="gpt-5.6-terra",
        parameters=(CursorModelParameter(id="temperature", value="0.2"),),
    )

    report = codex_adapter.codex_startup_probe(
        model=selection,
        runtime="local",
        timeout_seconds=5,
        cwd=tmp_path,
    )

    assert report["ready"] is False
    assert report["errorClass"] == AgentFailureKind.SDK_EXECUTION_FAILED.value
    assert "unsupported codex model parameter" in report["issues"][0]


def test_codex_adapter_classifies_dns_as_typed_retryable_transport(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(codex_adapter, "_load_codex_sdk", lambda: _bindings())
    monkeypatch.setattr(
        codex_adapter,
        "_invoke_codex_sdk",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            _sdk_failure("Could not resolve host: chatgpt.com")
        ),
    )

    report = codex_adapter.codex_startup_probe(
        model="gpt-5.6-terra",
        runtime="local",
        timeout_seconds=5,
        cwd=tmp_path,
    )

    assert report["errorCode"] == "semantic_provider_dns_unavailable"
    assert report["retryable"] is True


def test_codex_adapter_preserves_rate_limit_retry_after(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(codex_adapter, "_load_codex_sdk", lambda: _bindings())
    monkeypatch.setattr(
        codex_adapter,
        "_invoke_codex_sdk",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            _sdk_failure("HTTP 429 rate limit; Retry-After: 45 seconds")
        ),
    )

    report = codex_adapter.codex_startup_probe(
        model="gpt-5.6-terra",
        runtime="local",
        timeout_seconds=5,
        cwd=tmp_path,
    )

    assert report["errorCode"] == "semantic_provider_rate_limited"
    assert report["retryAfterSeconds"] == 45
    assert report["retryable"] is True


def test_codex_adapter_rejects_ungoverned_model_before_loading_sdk(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        codex_adapter,
        "_load_codex_sdk",
        lambda: (_ for _ in ()).throw(AssertionError("must not load SDK")),
    )

    report = codex_adapter.codex_startup_probe(
        model="gpt-5.6-luna",
        runtime="local",
        timeout_seconds=5,
        cwd=tmp_path,
    )

    assert report["errorCode"] == "semantic_provider_selection_not_governed"


def test_codex_adapter_fails_closed_when_official_sdk_is_missing(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        codex_adapter,
        "_load_codex_sdk",
        lambda: (_ for _ in ()).throw(ModuleNotFoundError("openai_codex")),
    )

    report = codex_adapter.codex_startup_probe(
        model="gpt-5.6-terra",
        runtime="local",
        timeout_seconds=5,
        cwd=tmp_path,
    )

    assert report["ready"] is False
    assert report["errorClass"] == AgentFailureKind.SDK_UNAVAILABLE.value
    assert report["errorCode"] == "semantic_provider_sdk_unavailable"
    assert report["started"] is False


def test_codex_runtime_requires_official_sdk_module() -> None:
    modules = agent_runtime_modules(AgentProvider.CODEX_SDK)

    assert modules[0] == "openai_codex"
    assert "cursor_sdk" not in modules
