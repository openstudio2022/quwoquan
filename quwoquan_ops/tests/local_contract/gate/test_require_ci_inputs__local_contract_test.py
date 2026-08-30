from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
GATE = ROOT / "quwoquan_ops/gate/require_ci_inputs.py"
DOMAIN_WORKFLOW = ROOT / ".github/workflows/domain-governance.yml"


def _run(*names: str, values: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for name in names:
        environment.pop(name, None)
    environment.update(values or {})
    return subprocess.run(
        [sys.executable, str(GATE), "--scope", "release-signing", *names],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_missing_inputs_are_one_typed_gate_block() -> None:
    result = _run("QWQ_ONE", "QWQ_TWO", values={"QWQ_ONE": "present"})

    assert result.returncode == 2
    assert result.stdout == (
        "::error::GATE_BLOCK: release-signing required inputs are missing: QWQ_TWO\n"
    )


def test_all_inputs_present_pass_without_printing_values() -> None:
    result = _run(
        "QWQ_ONE",
        "QWQ_TWO",
        values={"QWQ_ONE": "secret-one", "QWQ_TWO": "secret-two"},
    )

    assert result.returncode == 0
    assert result.stdout == "[require_ci_inputs] OK scope=release-signing inputs=2\n"
    assert "secret-one" not in result.stdout
    assert "secret-two" not in result.stdout


def test_invalid_input_name_is_rejected_before_environment_lookup() -> None:
    result = _run("not-an-environment-name")

    assert result.returncode == 2
    assert result.stdout == "::error::GATE_BLOCK: CI input name is invalid\n"


def test_domain_governance_wires_dns_acme_and_age_inputs_to_typed_gate() -> None:
    workflow = DOMAIN_WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count("quwoquan_ops/gate/require_ci_inputs.py") == 2
    assert workflow.count("--scope domain-governance") == 2
    for required in (
        "QWQ_DNS_PROVISIONING_API_TOKEN",
        "QWQ_ACME_DNS_API_TOKEN",
        "QWQ_TLS_AGE_RECIPIENT",
    ):
        assert required in workflow
    assert 'test -n "$QWQ_TLS_AGE_RECIPIENT"' not in workflow
    # zone 标识由 registrableDomain 派生，注册邮箱不是签发前提：两者都不是可配置输入。
    for retired in ("QWQ_DNS_ZONE_ID", "QWQ_ACME_ACCOUNT_EMAIL"):
        assert retired not in workflow
