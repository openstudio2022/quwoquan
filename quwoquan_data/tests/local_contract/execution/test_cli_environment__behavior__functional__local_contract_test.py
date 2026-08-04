"""Current qwq-data CLI and key-file environment contracts."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
CLI = SCRIPTS_ROOT / "cli.py"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core import cursor_credentials, cursor_startup_probe, python_environment, python_network, python_runtime  # noqa: E402
from content.execution.preflight import handler as preflight_handler  # noqa: E402


def _key_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None = None) -> Path:
    path = tmp_path / "cursor_api_key"
    path.write_text(value or ("crsr_" + "x" * 32), encoding="utf-8")
    path.chmod(0o600)
    monkeypatch.setenv("QWQ_CURSOR_API_KEY_FILE", str(path))
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    return path


def test_cli_exposes_only_durable_task_facades():
    task = subprocess.run(
        [sys.executable, str(CLI), "task", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert task.returncode == 0, task.stderr
    command_rows = [line.strip().split(maxsplit=1)[0] for line in task.stdout.splitlines() if line.startswith("    ")]
    assert command_rows == ["preflight", "execute", "discard"]

    preflight = subprocess.run(
        [sys.executable, str(CLI), "task", "preflight", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert preflight.returncode == 0, preflight.stderr
    for name in ("--json", "--no-network", "--no-cursor-key", "--report-out"):
        assert name in preflight.stdout
    for name in (
        "--python",
        "--requirements",
        "--timeout-seconds",
        "--model",
        "--runtime",
        "--startup-timeout-seconds",
    ):
        assert name not in preflight.stdout


def test_python_runtime_prefers_data_venv_when_current_lacks_cursor_sdk(monkeypatch):
    current = Path("/usr/bin/python3")
    data_python = python_environment.DATA_VENV_PYTHON
    monkeypatch.setattr(
        python_environment,
        "candidate_pythons",
        lambda include_current=True: [current, data_python],
    )
    monkeypatch.setattr(
        python_environment,
        "python_has_modules",
        lambda python, modules: (Path(python) == data_python, [] if Path(python) == data_python else ["missing"]),
    )
    assert python_environment.resolve_data_agent_python(include_current=True) == data_python


def test_python_tool_cache_rejects_disposable_output_root() -> None:
    with pytest.raises(ValueError, match="must not be inside .qwq_output"):
        python_environment.resolve_python_cache_root(
            str(DATA_ROOT.parent / ".qwq_output" / "env" / "repo"),
        )


def test_agent_reexec_keeps_bytecode_out_of_the_source_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def capture_execvpe(executable: str, argv: list[str], env: dict[str, str]) -> None:
        captured["executable"] = executable
        captured["argv"] = argv
        captured["env"] = env
        raise RuntimeError("stop after capturing re-exec")

    monkeypatch.delenv(python_environment.BOOTSTRAP_ENV, raising=False)
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)
    monkeypatch.setattr(python_environment, "agent_command_needs_bootstrap", lambda _argv: True)
    monkeypatch.setattr(python_environment, "python_has_modules", lambda *_args: (False, ["missing"]))
    monkeypatch.setattr(
        python_environment,
        "resolve_data_agent_python",
        lambda **_kwargs: Path("/tmp/quwoquan-data-python"),
    )
    monkeypatch.setattr(python_environment.os, "execvpe", capture_execvpe)

    with pytest.raises(RuntimeError, match="stop after capturing re-exec"):
        python_environment.maybe_reexec_for_agent_command(["cli.py", "task", "execute"])

    env = captured["env"]
    assert isinstance(env, dict)
    assert env[python_environment.BOOTSTRAP_ENV] == "1"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["cli.py", "task", "execute"], True),
        (["cli.py", "task", "preflight"], False),
    ],
)
def test_agent_runtime_commands_are_explicitly_bootstrapped(
    argv: list[str],
    expected: bool,
) -> None:
    assert python_environment.agent_command_needs_bootstrap(argv) is expected


def test_data_python_tool_cache_is_rebuilt_from_repo_truth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "tool-cache" / "quwoquan-data"
    create_calls: list[Path] = []

    def create_cache(path: Path, *, with_pip: bool) -> None:
        assert with_pip is True
        create_calls.append(Path(path))
        python = python_environment._venv_python(Path(path))
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_text("", encoding="utf-8")

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(python_environment.venv, "create", create_cache)
    monkeypatch.setattr(
        python_environment.subprocess,
        "run",
        lambda *_args, **_kwargs: Completed(),
    )
    monkeypatch.setattr(
        python_environment,
        "python_has_modules",
        lambda _python, _modules: (True, []),
    )
    monkeypatch.setattr(python_environment.shutil, "which", lambda _name: "/usr/bin/tool")

    first = python_environment.prepare_data_runtime_cache(cache_dir=cache_dir)
    shutil.rmtree(cache_dir)
    second = python_environment.prepare_data_runtime_cache(cache_dir=cache_dir)

    assert create_calls == [cache_dir, cache_dir]
    assert ".qwq_output" not in cache_dir.parts
    assert first["sourceTruth"] == str(DATA_ROOT / "requirements.txt")
    assert second["sourceTruth"] == str(DATA_ROOT / "requirements.txt")
    assert first["toolCache"] == str(cache_dir)
    assert second["cachePersistenceRequired"] is False


def test_environment_preflight_requires_restricted_key_file(monkeypatch, tmp_path):
    monkeypatch.delenv("QWQ_CURSOR_API_KEY_FILE", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.setattr(cursor_credentials, "DEFAULT_CURSOR_API_KEY_FILE", tmp_path / "missing")
    monkeypatch.setattr(python_runtime, "runtime_report", lambda: {"ready": True})

    missing = python_runtime.environment_preflight(check_network=True)
    assert missing["ready"] is False
    assert missing["cursorApiKey"]["source"] == "missing"
    assert missing["network"]["skipped"] is True
    assert "cursor API key file missing or unreadable" in missing["issues"]

    key_file = _key_file(tmp_path, monkeypatch)
    key_file.chmod(0o644)
    permissive = python_runtime.environment_preflight(check_network=True)
    assert permissive["ready"] is False
    assert any("permissions" in issue for issue in permissive["issues"])


def test_environment_preflight_never_exports_key_to_parent_environment(monkeypatch, tmp_path):
    key_file = _key_file(tmp_path, monkeypatch, "crsr_" + "a" * 32)
    monkeypatch.setattr(python_runtime, "runtime_report", lambda: {"ready": True})
    monkeypatch.setattr(
        python_runtime,
        "check_network_endpoints",
        lambda **kwargs: {"checked": True, "skipped": False, "ready": True, "endpoints": [], "issues": []},
    )
    seen: list[str] = []

    def startup_probe(**kwargs):
        seen.append(os.environ.get("CURSOR_API_KEY", ""))
        return {"checked": True, "ready": True, "started": True, "issues": []}

    monkeypatch.setattr(python_runtime, "cached_cursor_startup_probe", startup_probe)
    first = python_runtime.environment_preflight(check_network=True, check_cursor_startup=True)
    key_file.write_text("crsr_" + "b" * 32, encoding="utf-8")
    second = python_runtime.environment_preflight(check_network=True, check_cursor_startup=True)

    assert first["ready"] is True and second["ready"] is True
    assert seen == ["", ""]
    assert "CURSOR_API_KEY" not in os.environ
    assert second["cursorApiKey"] == {
        "source": "key_file",
        "present": True,
        "valid": True,
        "issues": [],
    }

def test_cursor_key_redaction_covers_hyphen_and_underscore_suffixes():
    value = "cursor crsr_fake-key_value failed"
    redacted = python_environment._redact_secret_text(value)
    assert "crsr_fake-key_value" not in redacted
    assert redacted == "cursor <redacted-cursor-key> failed"


def test_cursor_startup_probe_preserves_redacted_diagnostics(monkeypatch, tmp_path):
    key = "crsr_" + "x" * 32
    _key_file(tmp_path, monkeypatch, key)
    monkeypatch.setattr(
        cursor_startup_probe,
        "resolve_data_agent_python",
        lambda include_current=True: Path(sys.executable),
    )

    class Completed:
        returncode = 0
        stderr = ""
        stdout = json.dumps(
            {
                "ready": False,
                "started": False,
                "probeType": "agent_prompt_smoke",
                "status": "error",
                "errorClass": "InternalServerError",
                "error": f"internal error {key}",
                "errorCode": "internal",
                "httpStatus": "500",
            }
        )

    calls: list[int] = []
    launch: dict = {}

    def run(*args, **kwargs):
        calls.append(1)
        launch.update({"args": args, "kwargs": kwargs})
        return Completed()

    monkeypatch.setattr(cursor_startup_probe.subprocess, "run", run)
    monkeypatch.setattr(cursor_startup_probe.time, "sleep", lambda _seconds: None)
    report = cursor_startup_probe.cursor_startup_probe(timeout_seconds=1)
    assert report["ready"] is False
    assert report["probeType"] == "agent_prompt_smoke"
    assert report["errorClass"] == "InternalServerError"
    assert report["retryable"] is True
    assert report["attemptCount"] == len(calls)
    assert len(calls) > 1
    assert key not in json.dumps(report)
    assert launch["kwargs"]["input"] == f"{key}\n"
    assert "CURSOR_API_KEY" not in launch["kwargs"]["env"]
    assert key not in "\n".join(launch["args"][0])
    assert "allow_api_key_env_fallback=False" in launch["args"][0][2]


def test_network_probe_falls_back_from_head_to_get(monkeypatch):
    methods: list[str] = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def open_request(request, timeout):  # noqa: ARG001
        methods.append(request.get_method())
        if request.get_method() == "HEAD":
            raise python_network.urlerror.HTTPError(request.full_url, 500, "head failed", None, None)
        return Response()

    monkeypatch.setattr(python_network.urlrequest, "urlopen", open_request)
    report = python_network._probe_endpoint("https://example.test", timeout_seconds=1)
    assert report["reachable"] is True
    assert report["method"] == "GET"
    assert methods == ["HEAD", "GET"]


def test_env_ready_writes_compact_failure_evidence(monkeypatch, tmp_path):
    report_out = tmp_path / "runtime_preflight.json"
    monkeypatch.setattr(
        preflight_handler,
        "prepare_data_runtime_cache",
        lambda **_kwargs: {"ready": True, "python": sys.executable, "missing": [], "stdoutTail": "noisy"},
    )
    monkeypatch.setattr(
        preflight_handler,
        "_preflight_in_python",
        lambda _args, _python: {
            "ready": False,
            "issues": ["cursor API key file missing or unreadable"],
            "runtime": {"ready": True, "resolvedPython": sys.executable},
            "cursorApiKey": {
                "source": "missing",
                "present": False,
                "valid": False,
                "issues": ["cursor API key file missing or unreadable"],
            },
            "network": {"checked": False, "ready": True, "issues": []},
            "cursorStartup": {"checked": False, "ready": True, "runtime": "local", "model": "composer"},
        },
    )
    args = argparse.Namespace(
        python=None,
        requirements=None,
        json=True,
        no_cursor_key=False,
        no_network=False,
        endpoint=None,
        timeout_seconds=5.0,
        no_cursor_startup=False,
        cursor_startup=True,
        model="composer",
        runtime="local",
        startup_timeout_seconds=30.0,
        report_out=str(report_out),
    )
    with pytest.raises(SystemExit):
        preflight_handler.handle_ready(args)
    evidence = json.loads(report_out.read_text(encoding="utf-8"))
    assert evidence["ready"] is False
    assert evidence["credential"]["source"] == "missing"
    assert evidence["issues"] == ["cursor API key file missing or unreadable"]
    assert evidence["network"]["ready"] is False
    assert evidence["cursorStartup"]["ready"] is False
    assert "stdoutTail" not in json.dumps(evidence)


def test_compact_preflight_evidence_preserves_reliabletask_fleet_receipt() -> None:
    evidence = preflight_handler._compact_ready_evidence(
        {
            "ready": True,
            "prepare": {"ready": True, "python": sys.executable},
            "preflight": {
                "ready": True,
                "runtime": {"ready": True, "resolvedPython": sys.executable},
                "cursorApiKey": {"source": "key_file", "present": True, "valid": True},
                "network": {"checked": True, "ready": True},
                "cursorStartup": {"checked": True, "ready": True},
                "reliableTaskFleet": {
                    "checked": True,
                    "ready": True,
                    "target": "beta-local",
                    "mongo": True,
                    "redis": True,
                    "issues": [],
                },
            },
            "cursorStartup": {"checked": True, "ready": True},
        }
    )

    assert evidence["reliableTaskFleet"] == {
        "checked": True,
        "ready": True,
        "target": "beta-local",
        "mongo": True,
        "redis": True,
        "issues": [],
    }


def test_env_ready_does_not_repeat_runtime_child_fleet_reconciliation(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        preflight_handler,
        "prepare_data_runtime_cache",
        lambda **_kwargs: {
            "ready": True,
            "python": sys.executable,
            "missing": [],
        },
    )
    monkeypatch.setattr(
        preflight_handler,
        "_preflight_in_python",
        lambda _args, _python: {
            "ready": True,
            "issues": [],
            "runtime": {"ready": True, "resolvedPython": sys.executable},
            "cursorApiKey": {
                "source": "key_file",
                "present": True,
                "valid": True,
                "issues": [],
            },
            "network": {"checked": False, "ready": True, "issues": []},
            "cursorStartup": {"checked": False, "ready": True},
            "reliableTaskFleet": {
                "checked": True,
                "ready": True,
                "target": "beta-local",
                "mongo": True,
                "redis": True,
                "issues": [],
            },
        },
    )
    repeated: list[bool] = []
    monkeypatch.setattr(
        preflight_handler,
        "_apply_reliabletask_fleet_gate",
        lambda *_args, **_kwargs: repeated.append(True),
    )
    args = argparse.Namespace(
        python=None,
        requirements=None,
        json=True,
        no_cursor_key=False,
        no_network=True,
        endpoint=None,
        timeout_seconds=5.0,
        no_cursor_startup=True,
        cursor_startup=False,
        model="auto",
        runtime="local",
        startup_timeout_seconds=30.0,
        report_out=None,
        require_reliabletask_fleet=True,
        workspace_smoke=False,
        soak=0,
    )

    assert preflight_handler.handle_ready(args) is None
    assert repeated == []


def test_preflight_evidence_rejects_retired_data_local_branch(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    tasks_root = data_root / "tasks"
    local_root = data_root / "local"
    monkeypatch.setattr(preflight_handler, "DATA_EXECUTIONS_ROOT", tasks_root)
    monkeypatch.setattr(preflight_handler, "DATA_LOCAL_ROOT", local_root)

    assert preflight_handler._report_output_path(tasks_root / "execution" / "evidence" / "ready.json").name == "ready.json"
    assert preflight_handler._report_output_path(local_root / "cache" / "preflight" / "ready.json").name == "ready.json"
    with pytest.raises(SystemExit, match="data/local/cache"):
        preflight_handler._report_output_path(local_root / "preflight" / "ready.json")
