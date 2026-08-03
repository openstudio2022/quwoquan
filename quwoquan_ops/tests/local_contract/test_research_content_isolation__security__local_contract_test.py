from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from quwoquan_ops.cli.lib.research_content_isolation import (
    verify_research_content_isolation,
)


def test_all_four_environment_research_isolation_contracts_are_fail_closed() -> None:
    for environment in ("alpha", "beta", "gamma", "prod"):
        receipt = verify_research_content_isolation(environment)
        assert receipt["productLifecycleState"] == "research"
        assert receipt["identityWhitelistRequired"] is True
        assert receipt["anonymousContentAccess"] is False
        assert receipt["anonymousMediaAccess"] is False
        assert receipt["publicContentDistribution"] is False
        assert receipt["signedMediaUrlMaxTtlSeconds"] <= 900


def test_missing_whitelist_proof_is_blocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = {
        "productLifecycleState": "research",
        "researchContentIsolation": {},
    }
    path = tmp_path / "quwoquan_ops/environments/alpha/runtime.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(runtime), encoding="utf-8")

    import quwoquan_ops.cli.lib.research_content_isolation as isolation

    monkeypatch.setattr(isolation, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="identityWhitelistRequired"):
        isolation.verify_research_content_isolation("alpha")

