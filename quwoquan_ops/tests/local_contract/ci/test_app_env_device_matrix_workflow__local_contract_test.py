"""Removed GitHub ABG/device workflow remains absent after atomic cutover."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RETIRED = (
    "pre-release-gate.yml",
    "app-env-device-matrix-self-hosted.yml",
    "beta-device-platform.yml",
    "provider-release-evidence.yml",
)


def test_old_hosted_environment_and_device_workflows_are_deleted() -> None:
    for name in RETIRED:
        assert not (ROOT / ".github/workflows" / name).exists()
