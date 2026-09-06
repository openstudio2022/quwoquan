#!/usr/bin/env python3
"""Verify the stable-tag-only production workflow boundary."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/deploy-prod-auto.yml"
ALLOWED_PRODUCTION_JOBS = {"prod_activation_admission", "prod_rollout", "post_release_soak"}
FORMAL_SURFACES = (
    ROOT / ".github/workflows/deploy-prod-auto.yml",
    ROOT / "quwoquan_ops/cli/stackctl.py",
    ROOT / "quwoquan_ops/cli/commands/deploy_domain.py",
    ROOT / "quwoquan_ops/cli/commands/deploy_rollout.py",
    ROOT / "quwoquan_ops/cli/prod/load_prod_plane_images.py",
    ROOT / "quwoquan_ops/cli/prod/deploy_to_prod.sh",
    ROOT / "quwoquan_ops/cli/prod/hosted_release_ledger_lib/contract.py",
    ROOT / "quwoquan_ops/cli/prod/hosted_release_ledger_lib/request_validation.py",
    ROOT / "quwoquan_ops/cli/prod/hosted_release_ledger_lib/ledger_store.py",
    ROOT / "quwoquan_ops/cli/prod/hosted_release_ledger_lib/actions.py",
)
FORMAL_FORBIDDEN_TOKENS = (
    "releaseEvidenceRef",
    "release_evidence_ref",
    "--release-evidence-ref",
    "--release-manifest",
    "fetch_mainline_release_artifact.py",
    "_deployable_release_manifest",
    "fromReleaseEvidenceRef",
    "toReleaseEvidenceRef",
    "fromImageTransportTag",
    "toImageTransportTag",
    "RELEASE_MANIFEST",
    "RELEASE_EVIDENCE_DIGEST",
)


def _environment(spec: object) -> str:
    if not isinstance(spec, dict):
        return ""
    value = spec.get("environment")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return ""


def prod_environment_job_issues(path: Path) -> list[str]:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    jobs = document.get("jobs") or {}
    if not isinstance(jobs, dict):
        return [f"{path.name} jobs must be a mapping"]
    issues: list[str] = []
    for name, spec in jobs.items():
        environment = _environment(spec).strip()
        mentions_production = "production" in environment.lower()
        if name in ALLOWED_PRODUCTION_JOBS:
            if environment != "production":
                issues.append(
                    f"{path.name} production mutation job {name} must bind exact "
                    "environment: production"
                )
        elif mentions_production:
            issues.append(
                f"{path.name} production mutation job {name} must bind exact "
                "environment: production and be in the controlled job set"
            )
    return issues


def workflow_rollout_issues(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    issues = []
    required = (
        "name: 07. Deploy Qualified Stable Tag", "release_tag_admission_ref:",
        "@sha256:",
        "release_control.py", "prod-admit", "prod-stage-append",
        "prod-terminal-release", "prod-rollback", "prod-soak",
        "stackctl.py deploy", "--target prod-hosted", "canary 5 20 50 100",
        "cancel-in-progress: false",
    )
    forbidden = (
        "workflow_run:", "push:", "RELEASED_RELEASE_EVIDENCE_REF",
        "latestQualified", "qualification_fact_ref:",
        "previous_active_ledger_ref:", "source_sha:",
        "dry_run:", "Service Pipeline (same mainline DAG)",
        "App package evidence (same mainline DAG)", "stackctl.py package",
    )
    for token in required:
        if token not in text:
            issues.append(f"{path.name} missing stable-tag rollout token: {token}")
    for token in forbidden:
        if token in text:
            issues.append(f"{path.name} still contains legacy or mutable entry: {token}")
    return issues



def formal_surface_issues(paths: tuple[Path, ...] = FORMAL_SURFACES) -> list[str]:
    issues: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        if path.name == "deploy_domain.py":
            text = text[text.index("def register_parser") :]
        for token in FORMAL_FORBIDDEN_TOKENS:
            if token in text:
                try:
                    label = path.relative_to(ROOT)
                except ValueError:
                    label = path
                issues.append(f"{label} still contains formal legacy token: {token}")
    return issues

def main() -> int:
    issues = (
        workflow_rollout_issues(WORKFLOW)
        + prod_environment_job_issues(WORKFLOW)
        + formal_surface_issues()
    )
    if issues:
        print("[verify_prod_rollout_stackctl_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_prod_rollout_stackctl_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
