"""local_contract：managed cursor run 的 authoritative token 计量。

背景：本地 bridge 的终态 ``RunResult`` 不携带 usage；authoritative 用量只出现在
流式 ``turn-ended`` interaction update 上。契约：

1. ``aggregate_turn_usage`` 能把多个 turn 的 usage 汇总为 authoritative 计量
   （source=stream_turn_ended），token 口径与 ``extract_cursor_usage`` 一致。
2. ``_prompt_cursor_agent_capturing_usage`` 在等待终态的同时捕获全部
   turn-ended usage，并保证 agent.close() 一定执行。
3. runner 侧优先 result 自带 usage；不可用时回退到流式汇总，禁止直接落回
   estimated_from_artifacts。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.cursor_usage import aggregate_turn_usage, extract_cursor_usage  # noqa: E402


def test_aggregate_turn_usage_sums_multiple_turns() -> None:
    usage = aggregate_turn_usage(
        [
            {"inputTokens": 1000, "outputTokens": 200, "costUsd": 0.05},
            {"inputTokens": 3000, "outputTokens": 500},
        ]
    )
    assert usage["available"] is True
    assert usage["usedTokens"] == 4700
    assert usage["costUsd"] == 0.05
    assert usage["source"] == "stream_turn_ended"


def test_aggregate_turn_usage_prefers_total_tokens_field() -> None:
    usage = aggregate_turn_usage([{"totalTokens": 8000, "inputTokens": 1}])
    assert usage["usedTokens"] == 8000


def test_aggregate_turn_usage_empty_is_not_available() -> None:
    for payload in ([], None, [None, {}]):
        usage = aggregate_turn_usage(payload)
        assert usage["available"] is False
        assert usage["usedTokens"] == 0
        assert usage["source"] == ""


def test_aggregate_turn_usage_matches_extract_semantics() -> None:
    """同一 usage payload，流式汇总与 result 提取的 token 口径必须一致。"""
    payload = {"inputTokens": 1200, "outputTokens": 340, "costUsd": 0.01}

    class _Result:
        usage = payload

    from_result = extract_cursor_usage(_Result())
    from_stream = aggregate_turn_usage([payload])
    assert from_result["usedTokens"] == from_stream["usedTokens"]
    assert from_result["costUsd"] == from_stream["costUsd"]


# ---------------------------------------------------------------------------
# _prompt_cursor_agent_capturing_usage 契约（用假 SDK 对象驱动）
# ---------------------------------------------------------------------------


@dataclass
class _FakeUpdate:
    type: str
    usage: dict[str, Any] | None = None


@dataclass
class _FakeEvent:
    interaction_update: Any = None


@dataclass
class _FakeResult:
    status: str = "finished"
    result: str = "ok"


class _FakeRun:
    def __init__(self, events: list[_FakeEvent]) -> None:
        self._events = events

    def events(self):
        yield from self._events

    def wait(self) -> _FakeResult:
        return _FakeResult()


@dataclass
class _FakeAgent:
    run: _FakeRun
    closed: bool = False
    sent_prompts: list[str] = field(default_factory=list)

    def send(self, prompt: str) -> _FakeRun:
        self.sent_prompts.append(prompt)
        return self.run

    def close(self) -> None:
        self.closed = True


class _FakeAgentCls:
    def __init__(self, agent: _FakeAgent) -> None:
        self._agent = agent

    def create(self, options: Any, *, client: Any) -> _FakeAgent:
        return self._agent


def _load_runner_module():
    import importlib

    return importlib.import_module("content.execution.agent.agent_runner")


def test_prompt_capturing_usage_collects_turn_ended_events() -> None:
    run_mod = _load_runner_module()
    events = [
        _FakeEvent(interaction_update=_FakeUpdate(type="text-delta")),
        _FakeEvent(
            interaction_update=_FakeUpdate(
                type="turn-ended", usage={"inputTokens": 10, "outputTokens": 2}
            )
        ),
        _FakeEvent(interaction_update=None),
        _FakeEvent(
            interaction_update=_FakeUpdate(
                type="turn-ended", usage={"inputTokens": 30, "outputTokens": 4}
            )
        ),
    ]
    agent = _FakeAgent(run=_FakeRun(events))
    result, turn_usages = run_mod._prompt_cursor_agent_capturing_usage(
        _FakeAgentCls(agent), "hello", object(), client=object()
    )
    assert result.status == "finished"
    assert turn_usages == [
        {"inputTokens": 10, "outputTokens": 2},
        {"inputTokens": 30, "outputTokens": 4},
    ]
    assert agent.closed is True
    assert agent.sent_prompts == ["hello"]

    aggregated = aggregate_turn_usage(turn_usages)
    assert aggregated == {
        "available": True,
        "usedTokens": 46,
        "costUsd": 0.0,
        "source": "stream_turn_ended",
    }


def test_prompt_capturing_usage_closes_agent_on_stream_error() -> None:
    run_mod = _load_runner_module()

    class _BrokenRun:
        def events(self):
            raise RuntimeError("stream broke")
            yield  # pragma: no cover

        def wait(self):  # pragma: no cover
            return _FakeResult()

    agent = _FakeAgent(run=_BrokenRun())  # type: ignore[arg-type]
    try:
        run_mod._prompt_cursor_agent_capturing_usage(
            _FakeAgentCls(agent), "hello", object(), client=object()
        )
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected stream error to propagate")
    assert agent.closed is True


def test_runner_source_prefers_result_usage_then_stream() -> None:
    """runner 侧回退顺序契约：result usage 可用则用之，否则用流式汇总。"""
    payload = {"inputTokens": 5, "outputTokens": 5}

    class _ResultWithUsage:
        usage = payload

    primary = extract_cursor_usage(_ResultWithUsage())
    assert primary["available"] is True

    class _ResultWithout:
        pass

    fallback = extract_cursor_usage(_ResultWithout())
    assert fallback["available"] is False
    stream = aggregate_turn_usage([payload])
    assert stream["available"] is True
    assert stream["usedTokens"] == 10
