from __future__ import annotations

import json
import signal
import subprocess
from pathlib import Path

from content.execution.agent import codex_adapter, codex_probe_process
from content.execution.preflight import semantic_provider
from core.control_types import AgentFailureKind, AgentProvider


class _HangingProcess:
    pid = 7319
    returncode = None

    def __init__(self, *_args, **_kwargs) -> None:
        self.wait_count = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.wait_count += 1
        if self.wait_count < 3:
            raise subprocess.TimeoutExpired("codex-probe", timeout)
        self.returncode = -signal.SIGKILL
        return self.returncode


def test_probe_python_resolves_the_codex_module_runtime_not_outer_cli_python(
    monkeypatch,
    tmp_path,
) -> None:
    governed_python = tmp_path / "governed-codex-python"
    observed: dict[str, object] = {}

    def resolve(modules):
        observed["modules"] = tuple(modules)
        return governed_python

    monkeypatch.setattr(
        codex_probe_process,
        "resolve_python_for_modules",
        resolve,
    )

    assert codex_probe_process._probe_python() == governed_python
    assert observed["modules"] == codex_probe_process.agent_runtime_modules(
        AgentProvider.CODEX_SDK,
    )


def test_startup_probe_timeout_kills_the_entire_worker_process_group(
    monkeypatch,
    tmp_path,
) -> None:
    killed: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(codex_probe_process, "_probe_python", lambda: tmp_path / "python")
    monkeypatch.setattr(codex_probe_process.subprocess, "Popen", _HangingProcess)
    monkeypatch.setattr(
        codex_probe_process.os,
        "killpg",
        lambda pid, sent_signal: killed.append((pid, sent_signal)),
    )

    report = codex_probe_process.run_codex_startup_probe(
        model="gpt-5.6-terra",
        runtime="local",
        timeout_seconds=0.01,
        cwd=tmp_path,
    )

    assert killed == [
        (_HangingProcess.pid, signal.SIGTERM),
        (_HangingProcess.pid, signal.SIGKILL),
    ]
    assert report["ready"] is False
    assert report["errorClass"] == AgentFailureKind.SUBPROCESS_TIMEOUT.value
    assert report["errorCode"] == "semantic_provider_startup_probe_timeout"
    assert report["retryable"] is True


def test_isolated_probe_accepts_only_a_bounded_json_object_report(
    monkeypatch,
    tmp_path,
) -> None:
    expected = {
        "checked": True,
        "ready": True,
        "provider": "codex_sdk",
        "issues": [],
    }

    class CompletedProcess:
        pid = 7320
        returncode = 0

        def __init__(self, argv, **_kwargs) -> None:
            Path(argv[-1]).write_text(json.dumps(expected), encoding="utf-8")

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(codex_probe_process, "_probe_python", lambda: tmp_path / "python")
    monkeypatch.setattr(codex_probe_process.subprocess, "Popen", CompletedProcess)

    report = codex_probe_process.run_codex_startup_probe(
        model="gpt-5.6-terra",
        runtime="local",
        timeout_seconds=1,
        cwd=tmp_path,
    )

    assert report == expected


def test_isolated_probe_uses_the_governed_sdk_interpreter_not_cli_python(
    monkeypatch,
    tmp_path,
) -> None:
    expected = {
        "checked": True,
        "ready": True,
        "provider": "codex_sdk",
        "issues": [],
    }
    probe_python = tmp_path / "governed-python"
    observed: dict[str, object] = {}

    class CompletedProcess:
        pid = 7321
        returncode = 0

        def __init__(self, argv, **_kwargs) -> None:
            observed["argv"] = argv
            Path(argv[-1]).write_text(json.dumps(expected), encoding="utf-8")

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(codex_probe_process, "_probe_python", lambda: probe_python)
    monkeypatch.setattr(codex_probe_process.subprocess, "Popen", CompletedProcess)

    report = codex_probe_process.run_codex_startup_probe(
        model="gpt-5.6-terra",
        runtime="local",
        timeout_seconds=1,
        cwd=tmp_path,
    )

    assert report == expected
    assert observed["argv"][0] == str(probe_python)


def test_isolated_probe_fails_closed_when_no_governed_sdk_interpreter_exists(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(codex_probe_process, "_probe_python", lambda: None)

    report = codex_probe_process.run_codex_startup_probe(
        model="gpt-5.6-terra",
        runtime="local",
        timeout_seconds=1,
        cwd=tmp_path,
    )

    assert report["ready"] is False
    assert report["errorClass"] == AgentFailureKind.SDK_UNAVAILABLE.value
    assert report["errorCode"] == "semantic_provider_sdk_unavailable"


def test_worker_dispatch_is_closed_and_uses_the_official_sdk_primitive(
    monkeypatch,
) -> None:
    expected = {
        "source": "openai_codex_sdk",
        "present": True,
        "valid": True,
        "issues": [],
    }
    monkeypatch.setattr(
        codex_adapter,
        "_codex_credential_probe_in_process",
        lambda: expected,
    )

    assert codex_probe_process._dispatch_probe({"kind": "credential"}) == expected

    try:
        codex_probe_process._dispatch_probe(
            {"kind": "credential", "fallbackProvider": "cursor_sdk"}
        )
    except ValueError as exc:
        assert "unsupported Codex SDK probe request" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("probe worker accepted an undeclared fallback field")


def test_semantic_preflight_dispatches_codex_through_the_killable_boundary(
    monkeypatch,
    tmp_path,
) -> None:
    observed: dict[str, object] = {}

    def isolated_probe(**kwargs):
        observed.update(kwargs)
        return {
            "checked": True,
            "ready": False,
            "provider": "codex_sdk",
            "issues": ["typed test blocker"],
        }

    monkeypatch.setattr(
        codex_probe_process,
        "run_codex_startup_probe",
        isolated_probe,
    )
    monkeypatch.setattr(
        codex_adapter,
        "codex_startup_probe",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("preflight must not call the in-process primitive")
        ),
    )

    report = semantic_provider.semantic_agent_startup_probe(
        provider="codex_sdk",
        model="gpt-5.6-terra",
        runtime="local",
        timeout_seconds=3,
        cwd=tmp_path,
    )

    assert report["ready"] is False
    assert observed["timeout_seconds"] == 3
    assert observed["cwd"] == tmp_path
