"""The promotion workflow stays GitHub-hosted and macOS-shell portable."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github/workflows/delivery-gate.yml"


def test_promotion_jobs_are_hosted_and_use_exact_event_checkouts() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    promotion = workflow["jobs"]["promotion_verify"]
    sealing = workflow["jobs"]["main_source_seal"]
    caller = workflow["jobs"]["system_backsync"]

    assert promotion["runs-on"] == "ubuntu-latest"
    assert sealing["runs-on"] == "ubuntu-latest"
    assert "runs-on: [self-hosted" not in text
    assert next(step for step in promotion["steps"] if "uses" in step)["with"]["ref"] == "${{ github.event.pull_request.head.sha }}"
    assert next(step for step in sealing["steps"] if "uses" in step)["with"]["ref"] == "${{ github.event.after }}"
    assert caller["uses"] == "./.github/workflows/system-backsync.yml"
    assert caller["needs"] == "main_source_seal"
    assert "runs-on" not in caller
    assert "steps" not in caller
    assert "secrets" not in caller
    assert text.count("oras-project/setup-oras@") == 2
    assert text.count("actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1") == 1
    assert "permission-checks: write" in text


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
