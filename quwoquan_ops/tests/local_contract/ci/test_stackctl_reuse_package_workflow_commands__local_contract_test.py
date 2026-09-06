"""Promotion and production workflows keep stackctl responsibilities separate.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PROMOTION = ROOT / ".github/workflows/delivery-gate.yml"
PROD = ROOT / ".github/workflows/deploy-prod-auto.yml"


def test_promotion_workflow_executes_no_stackctl() -> None:
    text = PROMOTION.read_text(encoding="utf-8")
    assert "python3 quwoquan_ops/cli/stackctl.py" not in text
    assert "--reuse-package" not in text


def test_prod_executes_only_the_permanent_five_rollout_stages() -> None:
    text = PROD.read_text(encoding="utf-8")
    assert "for stage in canary 5 20 50 100" in text
    assert text.count("python3 quwoquan_ops/cli/stackctl.py deploy") == 1
    assert "--target prod-hosted" in text
    assert '--stage "$stage"' in text
    assert 'case "$stage" in canary) step=0 ;; 5|20|50|100) step="$stage" ;; esac' in text
    assert "--reuse-package" not in text
    assert "stackctl.py verify" not in text
    assert "--service prod-stack" in text
    assert "--from-candidate-digest" in text
    assert "--to-candidate-digest" in text
    assert "--release-evidence-ref" not in text
    assert "--release-manifest" not in text
    assert '--prod-activation-admission "$STORE/$ADMISSION_LOCAL_REF"' in text
    assert '--promotion-evidence "$EVIDENCE"' in text
    assert "--promotion-deadline-epoch" in text
    assert "--hard-deadline-epoch" in text
    assert "--rollback-budget-seconds 300" in text
