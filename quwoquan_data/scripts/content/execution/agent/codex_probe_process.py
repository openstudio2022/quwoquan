"""Killable process boundary for official Codex SDK preflight probes.

The SDK deliberately owns its Codex runtime transport.  Preflight nevertheless
needs a parent-owned wall-clock deadline so a stalled account or startup call
cannot pin the controller forever.  This module launches a short-lived Python
worker in a new process group, passes only non-secret governed inputs through a
0600 temporary file, and kills the whole group when the deadline expires.

This is not a CLI fallback: the child calls the official ``openai-codex`` SDK
adapter and returns the adapter's typed report.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from core.control_types import AgentFailureKind, AgentProvider
from core.cursor_model import CursorModelSelection
from core.python_environment import agent_runtime_modules, resolve_python_for_modules
from core.runtime_policy import active_runtime_policy

_MAX_REPORT_BYTES = 1_048_576


def _probe_python() -> Path | None:
    """Resolve the governed Codex SDK interpreter for an isolated worker.

    ``task preflight`` may be entered through the system Python while its
    disposable Data runtime is a separate interpreter.  A child launched from
    ``sys.executable`` would then falsely report the SDK as unavailable even
    though the prepared runtime passed admission.  The worker is therefore
    bound to the same provider-module resolver as preflight; it never falls
    back to a different provider or a module-less system interpreter.
    """
    return resolve_python_for_modules(
        agent_runtime_modules(AgentProvider.CODEX_SDK),
    )


def _positive_timeout(value: float) -> float:
    timeout = float(value)
    if timeout <= 0:
        raise ValueError("Codex SDK probe timeout must be positive")
    return timeout


def _selection_from_request(request: dict[str, object]) -> CursorModelSelection:
    return CursorModelSelection.from_config(
        request.get("model"),
        request.get("modelParameters"),
        label="codexStartupProbe",
    )


def _credential_failure(message: str, *, error_code: str) -> dict[str, object]:
    return {
        "source": "openai_codex_sdk",
        "present": False,
        "valid": False,
        "errorCode": error_code,
        "retryable": True,
        "issues": [message],
    }


def _startup_failure(
    request: dict[str, object],
    message: str,
    *,
    error_class: AgentFailureKind,
    error_code: str,
) -> dict[str, object]:
    selection = _selection_from_request(request)
    return {
        "checked": True,
        "ready": False,
        "started": False,
        "provider": AgentProvider.CODEX_SDK.value,
        "runtime": str(request["runtime"]),
        "model": selection.model_id,
        "modelParameters": selection.parameters_document(),
        "status": "failed",
        "errorClass": error_class.value,
        "errorCode": error_code,
        "retryAfterSeconds": None,
        "httpStatus": None,
        "retryable": True,
        "cacheHit": False,
        "agentId": None,
        "runId": None,
        "durationMs": 0,
        "issues": [message],
    }


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    grace = float(active_runtime_policy().process_termination_timeout_seconds)
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        process.wait(timeout=grace)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        pass
    process.wait()


def _read_report(path: Path) -> dict[str, object] | None:
    try:
        if not path.is_file() or path.stat().st_size > _MAX_REPORT_BYTES:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _run_isolated_probe(
    request: dict[str, object],
    *,
    timeout_seconds: float,
) -> tuple[dict[str, object] | None, str]:
    timeout = _positive_timeout(timeout_seconds)
    python = _probe_python()
    if python is None:
        return None, "runtime_unavailable"
    scripts_root = Path(__file__).resolve().parents[3]
    with tempfile.TemporaryDirectory(prefix="qwq-codex-probe-") as temporary:
        temporary_root = Path(temporary)
        input_path = temporary_root / "input.json"
        output_path = temporary_root / "output.json"
        input_path.write_text(
            json.dumps(request, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        input_path.chmod(0o600)
        environment = os.environ.copy()
        existing_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            str(scripts_root)
            if not existing_pythonpath
            else str(scripts_root) + os.pathsep + existing_pythonpath
        )
        process = subprocess.Popen(
            [
                str(python),
                "-c",
                (
                    "from content.execution.agent.codex_probe_process "
                    "import _probe_worker_main; _probe_worker_main()"
                ),
                str(input_path),
                str(output_path),
            ],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_process_group(process)
            return None, "timeout"
        if process.returncode != 0:
            return None, "worker_exit"
        report = _read_report(output_path)
        return (report, "") if report is not None else (None, "invalid_output")


def run_codex_credential_probe(*, timeout_seconds: float) -> dict[str, object]:
    report, failure = _run_isolated_probe(
        {"kind": "credential"},
        timeout_seconds=timeout_seconds,
    )
    if report is not None:
        return report
    if failure == "timeout":
        return _credential_failure(
            f"Codex SDK account probe exceeded the governed {timeout_seconds:g}s deadline",
            error_code="semantic_provider_credential_probe_timeout",
        )
    if failure == "runtime_unavailable":
        return _credential_failure(
            "official openai-codex SDK runtime is unavailable for the probe worker",
            error_code="semantic_provider_sdk_unavailable",
        )
    return _credential_failure(
        "Codex SDK account probe worker failed without a valid report",
        error_code="semantic_provider_credential_probe_failed",
    )


def run_codex_startup_probe(
    *,
    model: str | CursorModelSelection,
    runtime: str,
    timeout_seconds: float,
    cwd: Path | None = None,
) -> dict[str, object]:
    selection = CursorModelSelection.from_value(model)
    request: dict[str, object] = {
        "kind": "startup",
        "model": selection.model_id,
        "modelParameters": selection.parameters_document(),
        "runtime": runtime,
        "cwd": str((cwd or Path.cwd()).resolve()),
        "timeoutSeconds": _positive_timeout(timeout_seconds),
    }
    report, failure = _run_isolated_probe(
        request,
        timeout_seconds=timeout_seconds,
    )
    if report is not None:
        return report
    if failure == "timeout":
        return _startup_failure(
            request,
            f"Codex SDK startup probe exceeded the governed {timeout_seconds:g}s deadline",
            error_class=AgentFailureKind.SUBPROCESS_TIMEOUT,
            error_code="semantic_provider_startup_probe_timeout",
        )
    if failure == "runtime_unavailable":
        return _startup_failure(
            request,
            "official openai-codex SDK runtime is unavailable for the probe worker",
            error_class=AgentFailureKind.SDK_UNAVAILABLE,
            error_code="semantic_provider_sdk_unavailable",
        )
    return _startup_failure(
        request,
        "Codex SDK startup probe worker failed without a valid report",
        error_class=AgentFailureKind.SUBPROCESS_EXITED,
        error_code="semantic_provider_startup_probe_failed",
    )


def _dispatch_probe(request: dict[str, object]) -> dict[str, object]:
    kind = request.get("kind")
    if kind == "credential" and set(request) == {"kind"}:
        from content.execution.agent.codex_adapter import (
            _codex_credential_probe_in_process,
        )

        return _codex_credential_probe_in_process()
    if kind == "startup" and set(request) == {
        "kind",
        "model",
        "modelParameters",
        "runtime",
        "cwd",
        "timeoutSeconds",
    }:
        from content.execution.agent.codex_probe import (
            _codex_startup_probe_in_process,
        )

        cwd = request.get("cwd")
        runtime = request.get("runtime")
        timeout = request.get("timeoutSeconds")
        if not isinstance(cwd, str) or not isinstance(runtime, str):
            raise ValueError("Codex startup probe runtime input is invalid")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("Codex startup probe timeout input is invalid")
        return _codex_startup_probe_in_process(
            model=_selection_from_request(request),
            runtime=runtime,
            timeout_seconds=_positive_timeout(float(timeout)),
            cwd=Path(cwd),
        )
    raise ValueError("unsupported Codex SDK probe request")


def _probe_worker_main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(2)
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("probe request must be an object")
        report = _dispatch_probe(payload)
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        if len(encoded.encode("utf-8")) > _MAX_REPORT_BYTES:
            raise ValueError("probe report exceeds the governed size limit")
        output_path.write_text(encoded, encoding="utf-8")
        output_path.chmod(0o600)
    except Exception:  # noqa: BLE001 -- parent receives only a typed worker failure.
        raise SystemExit(3) from None


__all__ = ["run_codex_credential_probe", "run_codex_startup_probe"]
