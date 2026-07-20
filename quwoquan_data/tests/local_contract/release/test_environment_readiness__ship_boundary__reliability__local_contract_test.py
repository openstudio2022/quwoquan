"""Ship consults only the target phase; execution creation is environment-free."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.environment.readiness import ShipReadinessPhase, phase_for_environment  # noqa: E402
from content.release.model import DeploymentEnvironment  # noqa: E402


def test_environment_readiness__maps_ship_action_to_minimal_phase__local_contract() -> None:
    assert phase_for_environment(DeploymentEnvironment.ALPHA, consumer=False) is None
    assert phase_for_environment(DeploymentEnvironment.BETA, consumer=False) is ShipReadinessPhase.IMPORT
    assert phase_for_environment(DeploymentEnvironment.GAMMA, consumer=False) is ShipReadinessPhase.IMPORT
    assert phase_for_environment(DeploymentEnvironment.GAMMA, consumer=True) is ShipReadinessPhase.CONSUMER
    assert phase_for_environment(DeploymentEnvironment.PROD, consumer=True) is ShipReadinessPhase.COMMERCIAL
