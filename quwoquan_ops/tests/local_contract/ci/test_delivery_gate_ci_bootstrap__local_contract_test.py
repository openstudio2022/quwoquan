"""Atomic two-event contract for source promotion and post-merge sealing."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github/workflows/delivery-gate.yml"


def _commands(job: dict[str, object]) -> str:
    return "\n".join(
        str(step.get("run") or "")
        for step in job.get("steps") or []
        if isinstance(step, dict)
    )


def test_delivery_gate_uses_two_exact_sha_bounded_jobs() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    assert list(workflow["jobs"]) == ["promotion_verify", "main_source_seal"]
    assert workflow["permissions"] == {"contents": "read"}

    promotion = workflow["jobs"]["promotion_verify"]
    sealing = workflow["jobs"]["main_source_seal"]
    assert promotion["timeout-minutes"] == 5
    assert sealing["timeout-minutes"] == 5
    assert promotion["permissions"] == {
        "contents": "read", "packages": "write", "checks": "write", "pull-requests": "read",
    }
    assert sealing["permissions"] == {
        "contents": "read", "packages": "write",
        "checks": "read", "pull-requests": "read",
    }
    assert sealing["outputs"] == {
        "source_sha": "${{ steps.readback.outputs.source_sha }}",
        "main_source_seal_ref": "${{ steps.seal.outputs.main_source_seal_ref }}",
        "main_source_seal_digest": "${{ steps.seal.outputs.main_source_seal_digest }}",
    }
    # main→dev1.0 回同步由 integration 工作区按 FF 通道执行（make promotion-backsync），workflow 不再承载 backsync caller。
    assert "system_backsync" not in workflow["jobs"]
    assert "git push" not in text
    assert "git update-ref" not in text
    assert "github.sha" not in text


def test_pull_request_and_push_paths_have_disjoint_evidence_effects() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    promotion = _commands(workflow["jobs"]["promotion_verify"])
    sealing = _commands(workflow["jobs"]["main_source_seal"])

    for token in (
        "HEAD_REF", "BASE_REF", "HEAD_SHA", "BASE_SHA", "MERGE_SHA",
        "QUALIFICATION_BUNDLE_REF", "materialize-oci-bundle", "hosted-authority",
        "APPROVAL", "THREADS", "RULESET", "BOUNDARY", "REQUIRED_EVIDENCE", "promotion-admit",
    ):
        assert token in promotion
    assert "main-seal" not in promotion
    assert "MAIN_READBACK_AT" not in promotion

    for token in (
        "PUSH_BEFORE_SHA", "PUSH_AFTER_SHA", "refs/remotes/origin/main",
        "PROMOTION_ADMISSION_REF", "validate-hosted-handoff", "main-seal", "MAIN_SOURCE_SEAL_REF",
        "main-source-seal-readback.json", "promotion_timing_ratchet.py sample",
        "sync_hosted_ci_timing_ledger.py append-sample",
    ):
        assert token in sealing
    assert "promotion-admit" not in sealing
    assert "oras resolve" not in sealing
    assert "$STORE/promotion-handoff" not in sealing
    assert "$STORE/main-source-seal.json" not in sealing


def test_main_push_fail_closed_checks_exact_merge_and_reachability() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    sealing = _commands(workflow["jobs"]["main_source_seal"])

    for token in (
        "GATE_BLOCK: main push before SHA must be exact",
        "GATE_BLOCK: main push after SHA must be exact",
        "GATE_BLOCK: hosted main readback drifted from push after SHA",
        "GATE_BLOCK: main push must contain exactly one admitted merge commit",
        "GATE_BLOCK: main merge first parent must equal push before SHA",
        "GATE_BLOCK: merged source is not reachable from hosted main",
        "GATE_BLOCK: PromotionAdmissionReceipt does not bind merged main",
        "GATE_BLOCK: exact promotion handoff must exist exactly once",
        "GATE_BLOCK: promotion handoff must be verified against the GitHub Actions integration",
    ):
        assert token in sealing
