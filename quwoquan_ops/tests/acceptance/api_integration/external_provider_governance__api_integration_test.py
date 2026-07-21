from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import external_provider_governance as governance


def test_gamma_integration_is_blocked_until_real_provider_bindings_are_injected() -> None:
    """A missing secret must remain a release blocker, never become a local success."""
    compiled, issues = governance.load_and_compile()

    assert issues == []
    required = {
        capability_id: readiness
        for capability_id, readiness in compiled["readiness"]["gamma"].items()
        if readiness["required"]
    }
    assert required
    assert all(readiness["state"] == "blocked" for readiness in required.values())
    assert not any(readiness["capability_ready"] for readiness in required.values())


if __name__ == "__main__":
    test_gamma_integration_is_blocked_until_real_provider_bindings_are_injected()
