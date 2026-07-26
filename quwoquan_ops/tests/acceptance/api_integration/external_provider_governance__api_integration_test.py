from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import external_provider_governance as governance


def test_gamma_integration_uses_enabled_release_candidate_bindings() -> None:
    """Gamma must bind enabled real adapters before runtime credential preflight."""
    compiled, issues = governance.load_and_compile()

    assert issues == []
    required = {
        capability_id: readiness
        for capability_id, readiness in compiled["readiness"]["gamma"].items()
        if readiness["required"]
    }
    assert required
    assert all(readiness["state"] == "enabled" for readiness in required.values())
    assert all(
        not governance.is_prod_forbidden_adapter(readiness["adapter_id"])
        for readiness in required.values()
        if readiness.get("adapter_id")
    )
    assert all(readiness["capability_ready"] for readiness in required.values())


if __name__ == "__main__":
    test_gamma_integration_uses_enabled_release_candidate_bindings()
