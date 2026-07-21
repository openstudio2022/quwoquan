from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import external_provider_governance as governance


def test_prod_readiness_refuses_user_acceptance_before_required_capabilities_are_ready() -> None:
    compiled, issues = governance.load_and_compile()

    assert issues == []
    blocked = [
        capability_id
        for capability_id, readiness in compiled["readiness"]["prod"].items()
        if readiness["required"] and not readiness["capability_ready"]
    ]

    assert {
        "identity.sms.otp",
        "integration.push.delivery",
        "assistant.model.generation",
        "rtc.room.transport",
        "runtime.log.sink",
        "runtime.message.transport",
    }.issubset(blocked)
    assert "runtime.dns.resolution" not in blocked


if __name__ == "__main__":
    test_prod_readiness_refuses_user_acceptance_before_required_capabilities_are_ready()
