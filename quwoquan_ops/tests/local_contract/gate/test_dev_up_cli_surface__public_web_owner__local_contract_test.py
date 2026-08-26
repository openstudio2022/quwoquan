from __future__ import annotations

import subprocess

from quwoquan_ops.gate import verify_dev_up_cli_surface
from quwoquan_ops.tests.local_contract.gate.test_api_edge_single_track__local_contract_test import (
    ApiEdgeSingleTrackLocalContractTest,
)


def test_gamma_public_web_seo_owner_does_not_duplicate_business_ingress() -> None:
    ApiEdgeSingleTrackLocalContractTest().test_gamma_caddy_terminates_tls_without_copying_business_routes()


def test_gate_subprocesses_redirect_python_bytecode(monkeypatch) -> None:
    # spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
    captured: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(verify_dev_up_cli_surface.subprocess, "run", fake_run)
    verify_dev_up_cli_surface.run(["python3", "-V"])

    env = captured["env"]
    assert isinstance(env, dict)
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert str(env["PYTHONPYCACHEPREFIX"]).startswith(
        str(verify_dev_up_cli_surface.ROOT / ".qwq_output/")
    )
