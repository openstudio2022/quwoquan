from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
PROD_SIM_WORKFLOW = ROOT / ".github/workflows/prod-sim-manual-admission.yml"
SPEC_REF = (
    "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#req-001"
)


def _workflow(path: Path) -> dict[str, object]:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _prod_sim_ssh_gate() -> str:
    workflow = _workflow(PROD_SIM_WORKFLOW)
    steps = workflow["jobs"]["prod_sim_admission"]["steps"]
    return next(
        step["run"]
        for step in steps
        if step.get("name") == "Require runner-local prevalidation SSH credentials"
    )


def _write_runner_key(home: Path, account: str, *, mode: int = 0o600) -> None:
    key_dir = home / ".ssh" / "quwoquan-prod"
    key_dir.mkdir(parents=True, exist_ok=True)
    key = key_dir / account
    key.write_text("local-contract-key-material\n", encoding="utf-8")
    key.chmod(mode)


def _run_prod_sim_ssh_gate(home: Path, *, host: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", _prod_sim_ssh_gate()],
        cwd=ROOT,
        env={
            **os.environ,
            "HOME": str(home),
            "PROD_SIM_SSH_MANAGEMENT_HOST": host,
        },
        text=True,
        capture_output=True,
        check=False,
    )


def test_old_hosted_provider_and_device_entrypoints_are_deleted() -> None:
    for name in (
        "provider-release-evidence.yml",
        "app-env-device-matrix-self-hosted.yml",
        "beta-device-platform.yml",
        "pre-release-gate.yml",
    ):
        assert not (ROOT / ".github/workflows" / name).exists()


def test_prod_sim_is_manual_approved_and_explicitly_non_promotable() -> None:
    assert SPEC_REF
    payload = _workflow(PROD_SIM_WORKFLOW)
    text = PROD_SIM_WORKFLOW.read_text(encoding="utf-8")
    job = payload["jobs"]["prod_sim_admission"]

    assert set(payload["on"]) == {"workflow_dispatch"}
    assert job["environment"] == "prod-sim-admission"
    assert job["runs-on"] == ["self-hosted", "macOS", "ARM64"]
    assert job["env"]["PROD_SIM_SSH_MANAGEMENT_HOST"] == (
        "${{ vars.PROD_SIM_SSH_MANAGEMENT_HOST }}"
    )
    assert "--target prod-hosted" in text
    assert "--mode prevalidate" in text
    assert "--data-mode isolated" in text
    assert "--prevalidate-scope first-party" in text
    assert "PROD_SSH_HOST" not in text
    assert '--ssh-host "$PROD_SIM_SSH_MANAGEMENT_HOST"' in text
    assert "secrets.PROD_EDGE_SSH_KEY" not in text
    assert "secrets.PROD_SERVICE_SSH_KEY" not in text
    assert 'Path(os.environ["HOME"]) / ".ssh" / "quwoquan-prod"' in text
    assert '"prod-edge-svc", "prod-service-svc"' in text
    assert "stat.S_IMODE" in text
    assert '(report.get("releaseEligibility") or {}).get("status") != "GATE_BLOCK"' in text
    assert "environment-evidence" not in text
    assert "delivery-gate.yml" not in text
    assert "retention-days: 1" in text


def test_prod_sim_runner_local_ssh_gate_accepts_canonical_inputs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        _write_runner_key(home, "prod-edge-svc")
        _write_runner_key(home, "prod-service-svc")

        result = _run_prod_sim_ssh_gate(home, host="203.0.113.10")

    assert result.returncode == 0, result.stdout + result.stderr


def test_prod_sim_runner_local_ssh_gate_rejects_missing_or_invalid_host() -> None:
    for host in (
        "",
        "https://203.0.113.10",
        "-F",
        "..",
        ".hidden",
        "host..example",
        "-host.example",
        "host-.example",
        "2001:db8::1",
    ):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            _write_runner_key(home, "prod-edge-svc")
            _write_runner_key(home, "prod-service-svc")

            result = _run_prod_sim_ssh_gate(home, host=host)

        assert result.returncode == 2, result.stdout + result.stderr
        assert "PROD_SIM_SSH_MANAGEMENT_HOST must be a bare SSH host" in (
            result.stdout + result.stderr
        )


def test_prod_sim_runner_local_ssh_gate_rejects_missing_plane_key() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        _write_runner_key(home, "prod-edge-svc")

        result = _run_prod_sim_ssh_gate(home, host="203.0.113.10")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "runner-local SSH key is missing for prod-service-svc" in (
        result.stdout + result.stderr
    )


def test_prod_sim_runner_local_ssh_gate_rejects_non_private_permissions() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        _write_runner_key(home, "prod-edge-svc")
        _write_runner_key(home, "prod-service-svc", mode=0o644)

        result = _run_prod_sim_ssh_gate(home, host="203.0.113.10")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "runner-local SSH key must use mode 0600 for prod-service-svc" in (
        result.stdout + result.stderr
    )


def test_prod_sim_runner_local_ssh_gate_rejects_symlinked_key() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        _write_runner_key(home, "prod-edge-svc")
        key_dir = home / ".ssh" / "quwoquan-prod"
        target = key_dir / "prod-service-svc-target"
        target.write_text("local-contract-key-material\n", encoding="utf-8")
        target.chmod(0o600)
        (key_dir / "prod-service-svc").symlink_to(target)

        result = _run_prod_sim_ssh_gate(home, host="203.0.113.10")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "runner-local SSH key is missing for prod-service-svc" in (
        result.stdout + result.stderr
    )


def test_hosted_nightly_soak_entry_is_deleted_after_local_cutover() -> None:
    assert SPEC_REF
    workflows = ROOT / ".github/workflows"
    assert not (workflows / "app-env-device-matrix-self-hosted.yml").exists()
    assert not (workflows / "beta-device-platform.yml").exists()
    scheduler = (ROOT / "quwoquan_ops/ci/environment_scheduler.py").read_text(
        encoding="utf-8"
    )
    assert "safe_teardown_required" in scheduler
    assert '"cleanupEvidence": cleanup_evidence' in scheduler
    assert '"leaseClosureEvidence": lease_closure_evidence' in scheduler
