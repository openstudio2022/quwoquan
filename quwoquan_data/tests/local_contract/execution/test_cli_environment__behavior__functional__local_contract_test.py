"""Current qwq-data CLI and semantic-agent environment contracts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
CLI = SCRIPTS_ROOT / "cli.py"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.execution.preflight import handler as preflight_handler  # noqa: E402
from content.execution.preflight import semantic_provider  # noqa: E402
from content.execution.preflight.evidence import compact_ready_evidence  # noqa: E402
from core import (  # noqa: E402
    cursor_credentials,
    cursor_startup_probe,
    cursor_workspace_probe,
    python_environment,
    python_network,
)
from core.control_types import AgentProvider  # noqa: E402


def _key_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None = None
) -> Path:
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
    choices = next(
        line.strip()[1:-1]
        for line in task.stdout.splitlines()
        if line.strip().startswith("{") and line.strip().endswith("}")
    )
    assert choices.split(",") == [
            "preflight",
            "prepare-campaign",
            "execute",
            "drain-pool-delivery",
            "discard",
        "supersede-execution",
        "plan-images",
            "probe-images",
            "acquire-images",
            "prepare-image-supported-api-input",
            "prepare-video-manual-input",
            "acquire-videos",
        "review-asset",
        "reconcile-stale",
        "reconcile-failed-campaign",
        "reconcile-submissions",
        "runtime-evidence",
    ]

    runtime_evidence = subprocess.run(
        [sys.executable, str(CLI), "task", "runtime-evidence", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert runtime_evidence.returncode == 0, runtime_evidence.stderr
    compact_help = "".join(runtime_evidence.stdout.split())
    assert (
        "{create-session,sample,inject-worker-termination,inject-lease-expiry,"
        "inject-redis-restart,inject-mongo-reconnect,inject-provider-timeout,"
        "inject-provider-rate-limit,finalize}"
    ) in compact_help

    inject = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "task",
            "runtime-evidence",
            "inject-worker-termination",
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert inject.returncode == 0, inject.stderr
    assert "--confirm-active-worker-termination" in inject.stdout
    for forbidden in (
        "--environment",
        "--output-root",
        "--run-id",
        "--generation",
        "--fencing-token",
        "--fault-type",
        "--provider",
        "--command",
        "--argv",
        "--shell",
    ):
        assert forbidden not in inject.stdout

    preflight = subprocess.run(
        [sys.executable, str(CLI), "task", "preflight", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert preflight.returncode == 0, preflight.stderr
    for name in (
        "--json",
        "--no-network",
        "--no-semantic-agent-credential",
        "--report-out",
        "--semantic-selection-id",
        "--soak",
        "--receipt-out",
    ):
        assert name in preflight.stdout
    assert "--no-cursor-key" not in preflight.stdout
    for name in (
        "--python",
        "--requirements",
        "--timeout-seconds",
        "--model",
        "--runtime",
        "--startup-timeout-seconds",
    ):
        assert name not in preflight.stdout

    prepare = subprocess.run(
        [sys.executable, str(CLI), "task", "prepare-campaign", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert prepare.returncode == 0, prepare.stderr
    for name in (
        "--phase",
        "--scale",
        "--region-ref",
        "--run-date",
        "--sequence",
        "--handoff-id",
        "--handoff-revision",
        "--supersedes-handoff-ref",
        "--handoff-ref",
        "--semantic-selection-id",
        "--semantic-preflight-receipt",
        "--homepage-image-input",
        "--image-input",
        "--video-input",
    ):
        assert name in prepare.stdout
    for forbidden in (
        "--output-root",
        "--kind",
        "--acquisition-root-ref",
        "--article-image-input",
    ):
        assert forbidden not in prepare.stdout

    for command in ("acquire-images", "acquire-videos"):
        acquisition = subprocess.run(
            [sys.executable, str(CLI), "task", command, "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert acquisition.returncode == 0, acquisition.stderr
        assert "--handoff-ref" in acquisition.stdout

    review = subprocess.run(
        [sys.executable, str(CLI), "task", "review-asset", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert review.returncode == 0, review.stderr
    for name in (
        "--acquisition-receipt",
        "--asset-kind",
        "--asset-id",
        "--execution-manifest",
        "--author-evidence",
        "--reviewer-evidence",
        "--object-ref",
        "--judgment",
    ):
        assert name in review.stdout
    for forbidden in (
        "--provider",
        "--model",
        "--run-id",
        "--output-root",
    ):
        assert forbidden not in review.stdout


def test_python_runtime_prefers_data_venv_when_current_lacks_agent_modules(monkeypatch):
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
        lambda python, modules: (
            Path(python) == data_python,
            [] if Path(python) == data_python else ["missing"],
        ),
    )
    assert (
        python_environment.resolve_data_agent_python(include_current=True)
        == data_python
    )


def test_python_module_probe_does_not_inherit_closed_worker_stdin(monkeypatch):
    captured: dict[str, object] = {}

    class Completed:
        returncode = 0
        stdout = '{"missing": []}'
        stderr = ""

    def run(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr(python_environment.subprocess, "run", run)

    assert python_environment.python_has_modules(
        Path(sys.executable), ("cursor_sdk",)
    ) == (True, [])
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL


def test_python_module_probe_runs_from_a_worker_with_fd_zero_closed() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SCRIPTS_ROOT)
    code = (
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "os.close(0)\n"
        "from core.python_environment import python_has_modules\n"
        "ok, missing = python_has_modules(Path(sys.executable), ('json',))\n"
        "print(json.dumps({'ok': ok, 'missing': missing}))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=DATA_ROOT.parent,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"ok": True, "missing": []}


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
    monkeypatch.setattr(
        python_environment, "agent_command_needs_bootstrap", lambda _argv: True
    )
    monkeypatch.setattr(
        python_environment, "python_has_modules", lambda *_args: (False, ["missing"])
    )
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
        (["cli.py", "task", "acquire-videos"], True),
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
    monkeypatch.setattr(
        python_environment.shutil, "which", lambda _name: "/usr/bin/tool"
    )

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
    monkeypatch.setattr(
        cursor_credentials, "DEFAULT_CURSOR_API_KEY_FILE", tmp_path / "missing"
    )
    monkeypatch.setattr(semantic_provider, "runtime_report", lambda: {"ready": True})

    missing = semantic_provider.semantic_agent_environment_preflight(
        provider=AgentProvider.CURSOR_SDK,
        check_network=True,
    )
    assert missing["ready"] is False
    assert missing["semanticAgentCredential"]["source"] == "missing"
    assert missing["network"]["skipped"] is True
    assert "cursor API key file missing or unreadable" in missing["issues"]

    key_file = _key_file(tmp_path, monkeypatch)
    key_file.chmod(0o644)
    permissive = semantic_provider.semantic_agent_environment_preflight(
        provider=AgentProvider.CURSOR_SDK,
        check_network=True,
    )
    assert permissive["ready"] is False
    assert any("permissions" in issue for issue in permissive["issues"])


def test_environment_preflight_never_exports_key_to_parent_environment(
    monkeypatch, tmp_path
):
    key_file = _key_file(tmp_path, monkeypatch, "crsr_" + "a" * 32)
    monkeypatch.setattr(semantic_provider, "runtime_report", lambda: {"ready": True})
    monkeypatch.setattr(
        semantic_provider,
        "check_network_endpoints",
        lambda **kwargs: {
            "checked": True,
            "skipped": False,
            "ready": True,
            "endpoints": [],
            "issues": [],
        },
    )
    seen: list[str] = []

    def startup_probe(**kwargs):
        seen.append(os.environ.get("CURSOR_API_KEY", ""))
        return {"checked": True, "ready": True, "started": True, "issues": []}

    monkeypatch.setattr(
        semantic_provider,
        "semantic_agent_startup_probe",
        startup_probe,
    )
    first = semantic_provider.semantic_agent_environment_preflight(
        provider=AgentProvider.CURSOR_SDK,
        check_network=True,
        check_startup=True,
        startup_model="auto",
        startup_runtime="local",
    )
    key_file.write_text("crsr_" + "b" * 32, encoding="utf-8")
    second = semantic_provider.semantic_agent_environment_preflight(
        provider=AgentProvider.CURSOR_SDK,
        check_network=True,
        check_startup=True,
        startup_model="auto",
        startup_runtime="local",
    )

    assert first["ready"] is True and second["ready"] is True
    assert seen == ["", ""]
    assert "CURSOR_API_KEY" not in os.environ
    assert second["semanticAgentCredential"] == {
        "provider": "cursor_sdk",
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
    assert "input" not in launch["kwargs"]
    assert launch["kwargs"]["stdin"] is subprocess.DEVNULL
    assert launch["kwargs"]["pass_fds"]
    assert "CURSOR_API_KEY" not in launch["kwargs"]["env"]
    assert key not in json.dumps(launch["kwargs"]["env"])
    assert key not in "\n".join(launch["args"][0])
    assert "sys.stdin" not in launch["args"][0][2]
    assert "QWQ_CURSOR_API_KEY_FD" in launch["args"][0][2]
    assert "protected_cursor_client" in launch["args"][0][2]
    assert "Client.launch_bridge(" not in launch["args"][0][2]


def test_cursor_model_catalog_uses_protected_fd_without_secret_process_fields(
    monkeypatch, tmp_path
):
    key = "crsr_" + "y" * 32
    _key_file(tmp_path, monkeypatch, key)
    monkeypatch.setattr(
        cursor_workspace_probe,
        "resolve_data_agent_python",
        lambda include_current=True: Path(sys.executable),
    )

    class Completed:
        returncode = 0
        stderr = ""
        stdout = json.dumps(
            {"ready": True, "sdkVersion": "1.0.26", "modelIds": ["default"]}
        )

    launch: dict = {}

    def run(*args, **kwargs):
        launch.update({"args": args, "kwargs": kwargs})
        return Completed()

    monkeypatch.setattr(cursor_workspace_probe.subprocess, "run", run)
    report = cursor_workspace_probe.cursor_model_catalog()

    assert report["ready"] is True
    assert "input" not in launch["kwargs"]
    assert launch["kwargs"]["stdin"] is subprocess.DEVNULL
    assert launch["kwargs"]["pass_fds"]
    assert "CURSOR_API_KEY" not in launch["kwargs"]["env"]
    assert key not in json.dumps(launch["kwargs"]["env"])
    assert key not in "\n".join(launch["args"][0])
    assert "sys.stdin" not in launch["args"][0][2]
    assert "QWQ_CURSOR_API_KEY_FD" in launch["args"][0][2]


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
            raise python_network.urlerror.HTTPError(
                request.full_url, 500, "head failed", None, None
            )
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
        lambda **_kwargs: {
            "ready": True,
            "python": sys.executable,
            "missing": [],
            "stdoutTail": "noisy",
        },
    )
    monkeypatch.setattr(
        "content.execution.preflight.runtime.python_has_modules",
        lambda *_args: (True, []),
    )
    monkeypatch.setattr(
        preflight_handler,
        "_preflight_in_python",
        lambda _args, _python: {
            "provider": "codex_sdk",
            "ready": False,
            "issues": ["cursor API key file missing or unreadable"],
            "runtime": {"ready": True, "resolvedPython": sys.executable},
            "semanticAgentCredential": {
                "provider": "codex_sdk",
                "source": "missing",
                "present": False,
                "valid": False,
                "issues": ["cursor API key file missing or unreadable"],
            },
            "network": {"checked": False, "ready": True, "issues": []},
            "semanticAgentStartup": {
                "checked": False,
                "ready": True,
                "provider": "codex_sdk",
                "runtime": "local",
                "model": "gpt-5.6-terra",
            },
        },
    )
    args = argparse.Namespace(
        python=None,
        requirements=None,
        json=True,
        no_semantic_agent_credential=False,
        no_network=False,
        endpoint=None,
        timeout_seconds=5.0,
        no_semantic_agent_startup=False,
        semantic_agent_startup=True,
        report_out=str(report_out),
    )
    with pytest.raises(SystemExit):
        preflight_handler.handle_ready(args)
    evidence = json.loads(report_out.read_text(encoding="utf-8"))
    assert evidence["ready"] is False
    assert evidence["provider"] == "codex_sdk"
    assert evidence["credential"]["provider"] == "codex_sdk"
    assert evidence["credential"]["source"] == "missing"
    assert evidence["issues"] == ["cursor API key file missing or unreadable"]
    assert evidence["network"]["ready"] is False
    assert evidence["semanticAgentStartup"]["ready"] is False
    assert "stdoutTail" not in json.dumps(evidence)


def test_compact_semantic_preflight_evidence_excludes_reliabletask_fleet() -> None:
    evidence = compact_ready_evidence(
        {
            "ready": True,
            "provider": "codex_sdk",
            "prepare": {"ready": True, "python": sys.executable},
            "preflight": {
                "ready": True,
                "runtime": {"ready": True, "resolvedPython": sys.executable},
                "semanticAgentCredential": {
                    "provider": "codex_sdk",
                    "source": "codex_cli",
                    "present": True,
                    "valid": True,
                },
                "network": {"checked": True, "ready": True},
                "semanticAgentStartup": {"checked": True, "ready": True},
                "reliableTaskFleet": {
                    "checked": True,
                    "ready": True,
                    "target": "beta-local",
                    "mongo": True,
                    "redis": True,
                    "owned": True,
                    "issues": [],
                },
            },
            "semanticAgentCredential": {
                "provider": "codex_sdk",
                "source": "codex_cli",
                "present": True,
                "valid": True,
            },
            "semanticAgentStartup": {
                "provider": "codex_sdk",
                "checked": True,
                "ready": True,
            },
        }
    )

    assert "reliableTaskFleet" not in evidence
    assert evidence["provider"] == "codex_sdk"
    assert evidence["semanticAgentStartup"]["provider"] == "codex_sdk"


def test_semantic_ready_does_not_reconcile_runtime_child_fleet(
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
        "content.execution.preflight.runtime.python_has_modules",
        lambda *_args: (True, []),
    )
    monkeypatch.setattr(
        preflight_handler,
        "_preflight_in_python",
        lambda _args, _python: {
            "ready": True,
            "issues": [],
            "runtime": {"ready": True, "resolvedPython": sys.executable},
            "semanticAgentCredential": {
                "provider": "codex_sdk",
                "source": "key_file",
                "present": True,
                "valid": True,
                "issues": [],
            },
            "network": {"checked": False, "ready": True, "issues": []},
            "semanticAgentStartup": {"checked": False, "ready": True},
            "reliableTaskFleet": {
                "checked": True,
                "ready": True,
                "target": "beta-local",
                "mongo": True,
                "redis": True,
                "owned": True,
                "issues": [],
            },
        },
    )
    args = argparse.Namespace(
        python=None,
        requirements=None,
        json=True,
        no_semantic_agent_credential=False,
        no_network=True,
        endpoint=None,
        timeout_seconds=5.0,
        no_semantic_agent_startup=True,
        semantic_agent_startup=False,
        report_out=None,
        workspace_smoke=False,
        soak=0,
    )

    assert preflight_handler.handle_ready(args) is None


def test_preflight_evidence_rejects_retired_data_local_branch(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    tasks_root = data_root / "tasks"
    local_root = data_root / "local"
    monkeypatch.setattr(preflight_handler, "DATA_EXECUTIONS_ROOT", tasks_root)
    monkeypatch.setattr(preflight_handler, "DATA_LOCAL_ROOT", local_root)

    assert (
        preflight_handler._report_output_path(
            tasks_root / "execution" / "evidence" / "ready.json"
        ).name
        == "ready.json"
    )
    assert (
        preflight_handler._report_output_path(
            local_root / "cache" / "preflight" / "ready.json"
        ).name
        == "ready.json"
    )
    with pytest.raises(SystemExit, match="data/local/cache"):
        preflight_handler._report_output_path(local_root / "preflight" / "ready.json")
