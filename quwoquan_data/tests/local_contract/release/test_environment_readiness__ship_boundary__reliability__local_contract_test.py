"""Ship consults only the target phase; execution creation is environment-free."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.environment import readiness as subject  # noqa: E402
from content.release.environment.readiness import ShipReadinessAction  # noqa: E402
from content.release.model import DeploymentEnvironment  # noqa: E402
from core.io import read_json  # noqa: E402



def _ops_receipt(tmp_path: Path, payload: dict[str, object]) -> str:
    report_dir = tmp_path / "canonical-ops-readiness" / str(payload["environment"])
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "workload": "full",
        "candidateDigest": "sha256:" + "c" * 64,
        "providerRuntimeDigest": "sha256:" + "d" * 64,
        "startupAttemptId": "startup-001",
        **payload,
        "reportDir": str(report_dir),
    }
    (report_dir / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return json.dumps(payload)

_LIFECYCLE_EXIT_REF = (
    "env/gamma/runs/release-lifecycle-exit/"
    "pilot-003/exit-001/lifecycle-exit.json"
)


def test_production_readiness__fails_closed_without_release_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        subject.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("incomplete identity must fail before stackctl")
        ),
    )

    with pytest.raises(SystemExit, match="releaseId, verifyRunId and manifestDigest"):
        subject.require_environment_readiness(
            environment=DeploymentEnvironment.GAMMA,
            action=ShipReadinessAction.VERIFY,
            run=tmp_path / "verify-001",
        )


def test_production_readiness__passes_exact_release_identity_to_stackctl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: list[tuple[list[str], dict[str, object]]] = []

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        observed.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=_ops_receipt(tmp_path,
                {
                    "schema": "quwoquan_ops.ship_readiness_receipt",
                    "action": "verify",
                    "environment": "gamma",
                    "target": "gamma-local",
                    "outcome": "PASS",
                    "reportDir": "env/gamma/runs/content-readiness/verify-001",
                }
            ),
        )

    monkeypatch.setattr(subject.subprocess, "run", run)
    for name in (
        "QWQ_DATA_ROOT", "QWQ_OUTPUT_ROOT", "QWQ_PUBLISH_ROOT",
        "QWQ_LIBRARY_ROOT", "QWQ_CARRIED_MEDIA_ROOT",
        "QWQ_DATA_PYTHON", "QWQ_DATA_CLI_BOOTSTRAPPED",
    ):
        monkeypatch.setenv(name, f"data-only-{name}")
    run_root = tmp_path / "verify-001"

    receipt = subject.require_environment_readiness(
        environment=DeploymentEnvironment.GAMMA,
        action=ShipReadinessAction.VERIFY,
        run=run_root,
        release_id="pilot-003",
        verify_run_id="verify-001",
        manifest_digest="sha256:" + "a" * 64,
    )

    assert receipt is not None and receipt.passed
    command, kwargs = observed[0]
    assert "--report-dir" not in command
    child_env = kwargs["env"]
    assert isinstance(child_env, dict)
    assert not any(
        name in child_env
        for name in (
            "QWQ_DATA_ROOT", "QWQ_OUTPUT_ROOT", "QWQ_PUBLISH_ROOT",
            "QWQ_LIBRARY_ROOT", "QWQ_CARRIED_MEDIA_ROOT",
            "QWQ_DATA_PYTHON", "QWQ_DATA_CLI_BOOTSTRAPPED",
        )
    )
    assert command[command.index("--release-id") + 1] == "pilot-003"
    assert command[command.index("--verify-run-id") + 1] == "verify-001"
    assert command[command.index("--manifest-digest") + 1] == "sha256:" + "a" * 64
    assert "--lifecycle-exit-ref" not in command
    evidence = read_json(run_root / "environment-readiness.json")
    assert evidence["action"] == "verify"
    assert evidence["outcome"] == "PASS"
    assert evidence["opsReceiptRef"].endswith("/report.json")
    assert evidence["opsReceiptDigest"].startswith("sha256:")
    assert "opsReportDir" not in evidence
    assert "lifecycleExitRef" not in evidence


def test_production_readiness__passes_lifecycle_exit_ref_to_stackctl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        observed.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout=_ops_receipt(tmp_path,
                {
                    "schema": "quwoquan_ops.ship_readiness_receipt",
                    "action": "verify",
                    "environment": "alpha",
                    "target": "alpha-local",
                    "outcome": "PASS",
                    "reportDir": "env/alpha/runs/content-readiness/verify-commercial",
                }
            ),
        )

    monkeypatch.setattr(subject.subprocess, "run", run)
    run_root = tmp_path / "verify-commercial"
    receipt = subject.require_environment_readiness(
        environment=DeploymentEnvironment.ALPHA,
        action=ShipReadinessAction.VERIFY,
        run=run_root,
        release_id="pilot-003",
        verify_run_id="verify-commercial",
        manifest_digest="sha256:" + "a" * 64,
        lifecycle_exit_ref=_LIFECYCLE_EXIT_REF,
    )

    assert receipt is not None and receipt.action is ShipReadinessAction.VERIFY
    command = observed[0]
    assert command[command.index("--action") + 1] == "verify"
    assert command[command.index("--lifecycle-exit-ref") + 1] == _LIFECYCLE_EXIT_REF
    evidence = read_json(run_root / "environment-readiness.json")
    assert evidence["lifecycleExitRef"] == _LIFECYCLE_EXIT_REF
    assert evidence["outcome"] == "PASS"


@pytest.mark.parametrize("environment", tuple(DeploymentEnvironment))
def test_production_readiness_is_release_bound_in_every_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    environment: DeploymentEnvironment,
) -> None:
    observed: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        observed.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout=_ops_receipt(tmp_path,
                {
                    "schema": "quwoquan_ops.ship_readiness_receipt",
                    "action": "verify",
                    "environment": environment.value,
                    "target": f"{environment.value}-research",
                    "outcome": "PASS",
                    "reportDir": (
                        f"env/{environment.value}/runs/content-readiness/research-001"
                    ),
                }
            ),
        )

    monkeypatch.setattr(subject.subprocess, "run", run)
    run_root = tmp_path / environment.value / "research-001"
    receipt = subject.require_environment_readiness(
        environment=environment,
        action=ShipReadinessAction.VERIFY,
        run=run_root,
        release_id="research-001",
        verify_run_id="verify-001",
        manifest_digest="sha256:" + "a" * 64,
    )

    assert receipt is not None and receipt.passed
    command = observed[0]
    assert command[command.index("--action") + 1] == "verify"
    assert command[command.index("--env") + 1] == environment.value
    assert "--lifecycle-exit-ref" not in command
    evidence = read_json(run_root / "environment-readiness.json")
    assert evidence["action"] == "verify"
    assert evidence["environment"] == environment.value
