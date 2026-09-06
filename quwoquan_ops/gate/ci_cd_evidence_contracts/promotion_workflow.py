"""`03. Delivery Gate` 的静态合同：PR 只验真、main push 只封印、handoff 走原生 Actions check-run。"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from .findings import (
    Finding,
    job_checkout_ref,
    job_commands,
    negative_line,
    workflow_on,
)

PROMOTION_FORBIDDEN_EXECUTION = re.compile(
    r"(?:actions/setup-(?:go|node|java)|subosito/flutter-action|\bflutter\s+test\b|"
    r"\bgo\s+test\b|\bnpm\s|\bstackctl\.py\s+(?:package|up|health|verify|deploy)\b|"
    r"\b(?:build|package|ABG|device)\b|\bprovider(?:[-_ ]conformance)?\s+live\b|"
    r"\b(?:alpha|beta|gamma)[-_ ](?:environment|matrix|execution)\b)",
    re.IGNORECASE,
)


def promotion_workflow_findings(
    relative_path: str,
    text: str,
    workflow: Mapping[object, object] | None = None,
) -> list[Finding]:
    """`03. Delivery Gate` 静态合同：PR 只验真、main push 只封印、handoff 走原生 Actions check-run。"""
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if negative_line(line):
            continue
        match = PROMOTION_FORBIDDEN_EXECUTION.search(line)
        if match is not None:
            findings.append(
                Finding(
                    relative_path,
                    number,
                    f"03 Delivery Gate contains forbidden execution: {match.group(0)}",
                )
            )

    if workflow is None:
        return findings

    triggers = workflow_on(workflow)
    expected_triggers = {
        "pull_request": {"branches": ["main"]},
        "pull_request_review": {"types": ["submitted", "dismissed"]},
        "push": {"branches": ["main"]},
    }
    if triggers != expected_triggers:
        findings.append(
            Finding(
                relative_path,
                0,
                "promotion workflow must use only pull_request, pull_request_review re-evaluation and trusted post-merge main push",
            )
        )

    if workflow.get("permissions") != {"contents": "read"}:
        findings.append(
            Finding(relative_path, 0, "promotion workflow top-level permissions must be contents: read")
        )

    jobs = workflow.get("jobs")
    expected_jobs = ["promotion_verify", "main_source_seal"]
    if not isinstance(jobs, Mapping) or list(jobs) != expected_jobs:
        findings.append(
            Finding(
                relative_path,
                0,
                "promotion workflow must separate pre-merge verification and MainSourceSeal; source convergence to dev1.0 is the integration worktree fast-forward channel",
            )
        )
        return findings

    premerge = jobs["promotion_verify"]
    postmerge = jobs["main_source_seal"]
    pre_commands = job_commands(premerge)
    post_commands = job_commands(postmerge)
    expected_permissions = {
        "promotion_verify": {
            "contents": "read", "packages": "write",
            "checks": "write", "pull-requests": "read",
        },
        "main_source_seal": {
            "contents": "read", "packages": "write",
            "checks": "read", "pull-requests": "read",
        },
    }
    for job_name, job in (("promotion_verify", premerge), ("main_source_seal", postmerge)):
        if not isinstance(job, Mapping) or job.get("permissions") != expected_permissions[job_name]:
            findings.append(
                Finding(relative_path, 0, f"{job_name} permissions drifted from least privilege")
            )
        if not isinstance(job, Mapping) or job.get("runs-on") != "ubuntu-latest":
            findings.append(Finding(relative_path, 0, f"{job_name} must use a GitHub-hosted portable runner"))
        if not isinstance(job, Mapping) or job.get("timeout-minutes") != 5:
            findings.append(Finding(relative_path, 0, f"{job_name} must retain the five-minute job boundary"))
        job_env = job.get("env") if isinstance(job, Mapping) else None
        if isinstance(job_env, Mapping) and any("runner." in str(value) for value in job_env.values()):
            findings.append(
                Finding(relative_path, 0, f"{job_name} job-level env must not reference the runner context (invalid at job scope)")
            )

    pre_condition = str(premerge.get("if") or "") if isinstance(premerge, Mapping) else ""
    expected_pre_condition = "${{ github.event_name == 'pull_request' || github.event_name == 'pull_request_review' }}"
    if pre_condition != expected_pre_condition:
        findings.append(
            Finding(
                relative_path,
                0,
                "pre-merge job must run for every pull request or review event targeting main and fail closed inside the job",
            )
        )
    for token in (
        'values["HEAD_REF"] != "dev1.0"',
        'values["BASE_REF"] != "main"',
        'os.environ["PR_HEAD_REPOSITORY"] != os.environ["REPOSITORY"]',
        'required_keys = {"qualification_bundle_ref", "promotion_ready_at"}',
    ):
        if token not in pre_commands:
            findings.append(
                Finding(relative_path, 0, f"pre-merge qualification validation is missing: {token}")
            )
    required_premerge_tokens = (
        ("promotion_hosted.py materialize-oci-bundle", "exact IQF evidence bundle materialization"),
        ("integration_qualification.py", "IntegrationQualificationFact verification"),
        ("--signing-keyring quwoquan_ops/policies/evidence_signing_keyring.yaml", "in-repo Ed25519 public keyring verification"),
        ("--expected-qualification-signer-identity", "qualification signer identity binding"),
        ("/reviews", "hosted approval readback"),
        ("reviewThreads", "hosted review thread readback"),
        ("/rulesets", "hosted ruleset readback"),
        ("verify_git_branch_policy.py", "branch policy boundary"),
        ("verify_ci_changed_boundary.py", "changed-path secret/generated boundary"),
        ("--execution-profile promotion", "promotion impact profile"),
        ("promotion_hosted.py hosted-authority", "Gate-produced hosted authority facts"),
        ("promotion-admit", "PromotionAdmissionReceipt issuance"),
        ("promotion_evidence.py publish-oci", "PromotionAdmissionReceipt OCI publication"),
        ('--transport-tag "base-${BASE_SHA}-head-${HEAD_SHA}"', "deterministic admission transport tag"),
        ("promotion_evidence.py create-handoff", "handoff payload"),
        ("/check-runs", "handoff check-run"),
        ("actions/runs/${GITHUB_RUN_ID}/attempts/${GITHUB_RUN_ATTEMPT}", "handoff workflow attempt binding"),
        ('app.get("id") != 15368 or app.get("slug") != "github-actions"', "native GitHub Actions handoff identity readback"),
    )
    for token, description in required_premerge_tokens:
        if token not in pre_commands:
            findings.append(Finding(relative_path, 0, f"pre-merge path is missing {description}"))
    if "create-github-app-token" in text:
        findings.append(
            Finding(relative_path, 0, "promotion handoff must use the native GitHub Actions integration, not a self-hosted App")
        )
    if '"promotion_admission_ref"' in pre_commands:
        findings.append(Finding(relative_path, 0, "PR body must not self-assert final exact admission ref"))
    if "${{ vars." in text:
        findings.append(Finding(relative_path, 0, "promotion workflow must not read repository variables as authority"))

    expected_push_condition = (
        "${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}"
    )
    if not isinstance(postmerge, Mapping) or postmerge.get("if") != expected_push_condition:
        findings.append(
            Finding(relative_path, 0, "MainSourceSeal must run only for the trusted main push event")
        )

    expected_seal_outputs = {
        "source_sha": "${{ steps.readback.outputs.source_sha }}",
        "main_source_seal_ref": "${{ steps.seal.outputs.main_source_seal_ref }}",
        "main_source_seal_digest": "${{ steps.seal.outputs.main_source_seal_digest }}",
    }
    if not isinstance(postmerge, Mapping) or postmerge.get("outputs") != expected_seal_outputs:
        findings.append(
            Finding(
                relative_path,
                0,
                "MainSourceSeal job outputs must expose the exact readback source and seal ref/digest",
            )
        )

    if job_checkout_ref(premerge) != "${{ github.event.pull_request.head.sha }}":
        findings.append(Finding(relative_path, 0, "pre-merge checkout must bind the exact PR head SHA"))
    if job_checkout_ref(postmerge) != "${{ github.event.after }}":
        findings.append(Finding(relative_path, 0, "post-merge checkout must bind the exact main push after SHA"))
    if "github.sha" in text:
        findings.append(Finding(relative_path, 0, "github.sha fallback is forbidden in source promotion"))

    for token in (
        "main-seal",
        "main-source-seal",
        "promotion_timing_ratchet.py sample",
        "sync_hosted_ci_timing_ledger.py append-sample",
    ):
        if token in pre_commands:
            findings.append(
                Finding(relative_path, 0, f"pre-merge qualification must not issue post-merge evidence: {token}")
            )
    if "promotion-admit" not in pre_commands:
        findings.append(Finding(relative_path, 0, "pre-merge qualification must issue PromotionAdmissionReceipt"))
    if "promotion-admit" in post_commands:
        findings.append(
            Finding(relative_path, 0, "post-merge sealing must consume rather than recreate PromotionAdmissionReceipt")
        )

    required_postmerge_tokens = (
        ("refs/remotes/origin/main", "hosted main HEAD readback"),
        ("PUSH_BEFORE_SHA", "main push before identity"),
        ("PUSH_AFTER_SHA", "main push after identity"),
        ("/commits/${SOURCE_SHA}/check-runs", "exact hosted handoff lookup"),
        ("HANDOFF_COUNT", "create-once hosted handoff cardinality"),
        ("validate-hosted-handoff", "hosted Actions/workflow identity verification"),
        ("--expected-app-slug \"$TRUSTED_RECORDER_APP_SLUG\"", "native GitHub Actions handoff identity"),
        ("--ref \"$PROMOTION_ADMISSION_REF\"", "exact PromotionAdmissionReceipt materialization"),
        ("git merge-base --is-ancestor", "post-merge source reachability"),
        ("promotion_evidence.py main-seal", "MainSourceSeal exact predecessor issuance"),
        ("--admission-oci-ref \"$PROMOTION_ADMISSION_REF\"", "MainSourceSeal exact OCI binding"),
        ("--hosted-handoff", "MainSourceSeal hosted record binding"),
        ("main-source-seal-oci.json", "MainSourceSeal OCI publication"),
        ("--ref \"$MAIN_SOURCE_SEAL_REF\"", "hosted MainSourceSeal readback"),
        ("cmp \"$CONTROL_ROOT/$SEAL_PATH\" \"$RUNNER_TEMP/main-source-seal-readback.json\"", "exact MainSourceSeal byte readback"),
        ("promotion_timing_ratchet.py sample", "post-readback promotion timing sample"),
        ("sync_hosted_ci_timing_ledger.py append-sample", "hosted timing sample readback"),
    )
    for token, description in required_postmerge_tokens:
        if token not in post_commands:
            findings.append(Finding(relative_path, 0, f"post-merge path is missing {description}"))
    seal_env = "\n".join(
        json.dumps(step.get("env") or {}, sort_keys=True)
        for step in (postmerge.get("steps") or [])
        if isinstance(step, Mapping)
    ) if isinstance(postmerge, Mapping) else ""
    if '"TRUSTED_RECORDER_APP_SLUG": "github-actions"' not in seal_env or '"TRUSTED_RECORDER_APP_ID": "15368"' not in seal_env:
        findings.append(
            Finding(relative_path, 0, "post-merge handoff identity must be pinned to the GitHub Actions integration (github-actions / 15368)")
        )

    order_tokens = (
        "refs/remotes/origin/main",
        "/commits/${SOURCE_SHA}/check-runs",
        "validate-hosted-handoff",
        "promotion_evidence.py materialize-oci",
        "git merge-base --is-ancestor",
        "promotion_evidence.py main-seal",
        "main-source-seal-readback.json",
        'cmp "$CONTROL_ROOT/$SEAL_PATH" "$RUNNER_TEMP/main-source-seal-readback.json"',
        'MAIN_SOURCE_SEAL_DIGEST="${MAIN_SOURCE_SEAL_REF##*@}"',
        'echo "main_source_seal_digest=$MAIN_SOURCE_SEAL_DIGEST"',
        "promotion_timing_ratchet.py sample",
        "sync_hosted_ci_timing_ledger.py append-sample",
    )
    positions = [post_commands.find(token) for token in order_tokens]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        findings.append(
            Finding(
                relative_path,
                0,
                "post-merge order must preserve MainSourceSeal post-readback ref/digest outputs before timing",
            )
        )

    forbidden_authority = (
        "oras resolve", '"promotion_admission_ref"', "latest",
        "promotion-handoff-status", "$STORE/promotion-handoff",
    )
    for token in forbidden_authority:
        if token in post_commands:
            findings.append(
                Finding(relative_path, 0, f"post-merge mutable or local handoff authority is forbidden: {token}")
            )
    for fake in (
        "$STORE/main-source-seal.json",
        'cp "$SEAL_PATH" "$RUNNER_TEMP/main-source-seal-readback.json"',
        'cp "$CONTROL_ROOT/$SEAL_PATH" "$RUNNER_TEMP/main-source-seal-readback.json"',
    ):
        if fake in post_commands:
            findings.append(
                Finding(relative_path, 0, "local store must not masquerade as hosted MainSourceSeal readback")
            )
    return findings
