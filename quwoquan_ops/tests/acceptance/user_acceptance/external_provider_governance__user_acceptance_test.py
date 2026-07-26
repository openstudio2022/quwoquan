from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import external_provider_governance as governance


def test_local_test_environments_use_substitutes_and_prod_uses_real_adapters() -> None:
    compiled, issues = governance.load_and_compile()

    assert issues == []

    for environment in governance.SUBSTITUTE_ENVIRONMENTS:
        for capability_id, readiness in compiled["readiness"][environment].items():
            if not readiness["required"] or not readiness.get("adapter_id"):
                continue
            assert readiness["state"] == "enabled", (environment, capability_id)
            assert governance.is_local_substitute_adapter(
                readiness["adapter_id"]
            ), (environment, capability_id)

    for environment in governance.RELEASE_ADAPTER_ENVIRONMENTS:
        for capability_id, readiness in compiled["readiness"][environment].items():
            if not readiness["required"] or not readiness.get("adapter_id"):
                continue
            assert readiness["state"] == "enabled", (environment, capability_id)
            assert not governance.is_prod_forbidden_adapter(
                readiness["adapter_id"]
            ), (environment, capability_id)

    # Platform message transport may be enabled on prod; it is not a SaaS substitute.
    transport = compiled["readiness"]["prod"]["runtime.message.transport"]
    assert transport["required"]
    assert transport["adapter_id"] == "infra.redis.message_transport"

    assert "runtime.dns.resolution" not in compiled["readiness"]["prod"]


if __name__ == "__main__":
    test_local_test_environments_use_substitutes_and_prod_uses_real_adapters()
