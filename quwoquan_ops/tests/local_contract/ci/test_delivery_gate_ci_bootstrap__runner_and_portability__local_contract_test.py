"""The promotion workflow stays GitHub-hosted and macOS-shell portable."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github/workflows/delivery-gate.yml"


def test_promotion_jobs_are_hosted_and_use_exact_event_checkouts() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    # 回同步由 integration FF 通道执行（make promotion-backsync），Gate 不再挂 caller job；
    # 受管 system backsync 保留 reusable 合同但无 caller（daily-merge OPEN-004）。
    assert list(workflow["jobs"]) == ["promotion_verify", "main_source_seal"]
    promotion = workflow["jobs"]["promotion_verify"]
    sealing = workflow["jobs"]["main_source_seal"]

    assert promotion["runs-on"] == "ubuntu-latest"
    assert sealing["runs-on"] == "ubuntu-latest"
    assert "runs-on: [self-hosted" not in text
    assert next(step for step in promotion["steps"] if "uses" in step)["with"]["ref"] == "${{ github.event.pull_request.head.sha }}"
    assert next(step for step in sealing["steps"] if "uses" in step)["with"]["ref"] == "${{ github.event.after }}"
    assert text.count("oras-project/setup-oras@") == 2
    # 原生 GITHUB_TOKEN 的 checks: write 直接创建 check-run，不再依赖 GitHub App token。
    assert "actions/create-github-app-token@" not in text
    assert "checks: write" in text


def test_shell_commands_remain_compatible_with_macos_bash_tools() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for nonportable in (
        "sha256sum", "readlink -f", "realpath --", "stat -c",
        "date --iso-8601", "date --date", "grep -P", "sed -r",
    ):
        assert nonportable not in text
    assert "shasum -a 256" in text
    assert 'date -u +"%Y-%m-%dT%H:%M:%SZ"' in text


def test_gate_remains_source_evidence_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8").casefold()
    forbidden = (
        "setup-go", "setup-node", "setup_flutter_sdk", "flutter test", "go test",
        "npm ", "stackctl.py package", "stackctl.py up", "stackctl.py verify",
        "self-hosted", "device matrix",
    )
    assert not [token for token in forbidden if token.casefold() in text]
