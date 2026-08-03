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
from content.release.environment.readiness import ShipReadinessPhase  # noqa: E402
from core.io import read_json  # noqa: E402
from content.release.model import DeploymentEnvironment  # noqa: E402


def test_consumer_readiness__fails_closed_without_release_identity(
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
            phase=ShipReadinessPhase.CONSUMER,
            run=tmp_path / "verify-001",
        )


def test_consumer_readiness__passes_exact_release_identity_to_stackctl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        observed.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "schema": "quwoquan_ops.ship_readiness_receipt",
                    "phase": "consumer",
                    "environment": "gamma",
                    "target": "gamma-local",
                    "outcome": "PASS",
                    "reportDir": "env/gamma/runs/content-readiness/verify-001",
                }
            ),
        )

    monkeypatch.setattr(subject.subprocess, "run", run)
    run_root = tmp_path / "verify-001"

    receipt = subject.require_environment_readiness(
        environment=DeploymentEnvironment.GAMMA,
        phase=ShipReadinessPhase.CONSUMER,
        run=run_root,
        release_id="pilot-003",
        verify_run_id="verify-001",
        manifest_digest="sha256:" + "a" * 64,
    )

    assert receipt is not None and receipt.passed
    command = observed[0]
    assert command[command.index("--release-id") + 1] == "pilot-003"
    assert command[command.index("--verify-run-id") + 1] == "verify-001"
    assert command[command.index("--manifest-digest") + 1] == "sha256:" + "a" * 64
    evidence = read_json(run_root / "environment-readiness.json")
    assert evidence["phase"] == "consumer"
    assert evidence["outcome"] == "PASS"


def test_commercial_readiness__passes_commercial_phase_to_stackctl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        observed.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "schema": "quwoquan_ops.ship_readiness_receipt",
                    "phase": "commercial",
                    "environment": "alpha",
                    "target": "alpha-local",
                    "outcome": "PASS",
                    "reportDir": "env/alpha/runs/content-readiness/verify-commercial",
                }
            ),
        )

    monkeypatch.setattr(subject.subprocess, "run", run)
    receipt = subject.require_environment_readiness(
        environment=DeploymentEnvironment.ALPHA,
        phase=ShipReadinessPhase.COMMERCIAL,
        run=tmp_path / "verify-commercial",
        release_id="pilot-003",
        verify_run_id="verify-commercial",
        manifest_digest="sha256:" + "a" * 64,
    )

    assert receipt is not None and receipt.phase is ShipReadinessPhase.COMMERCIAL
    command = observed[0]
    assert command[command.index("--phase") + 1] == "commercial"
