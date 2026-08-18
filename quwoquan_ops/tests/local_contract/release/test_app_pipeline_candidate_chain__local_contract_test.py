from __future__ import annotations

import re
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github/workflows/app_pipeline.yml"
DEVICE_WORKFLOW = ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml"
PLATFORM_WORKFLOW = ROOT / ".github/workflows/beta-device-platform.yml"
DEVICE_EVIDENCE = ROOT / "quwoquan_ops/ci/render_beta_device_evidence.py"
DEVICE_LEASE = ROOT / "quwoquan_ops/ci/device_runner_lease.py"
PLATFORM_RUNNER = ROOT / "quwoquan_ops/ci/run_mobile_platform_matrix.sh"
TIMING_BUDGETS = ROOT / "quwoquan_ops/environments/pr_gate_timing_budgets.json"
EVIDENCE_DOCKERFILE = ROOT / "quwoquan_ops/ci/app_candidate_evidence.Dockerfile"
SPEC_REF = "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001"


def test_app_pipeline_is_reusable_only_and_publishes_immutable_oci() -> None:
    assert SPEC_REF
    text = WORKFLOW.read_text(encoding="utf-8")
    payload = yaml.load(text, Loader=yaml.BaseLoader)
    triggers = payload["on"]

    assert set(triggers) == {"workflow_call"}
    outputs = triggers["workflow_call"]["outputs"]
    assert set(outputs) == {
        "app_evidence_ref",
        "app_evidence_digest",
        "source_git_sha",
        "machine_critical_path_seconds",
    }
    assert "refs/tags" not in text
    assert "workflow_dispatch" not in text
    assert "environment: production" not in text
    assert "app-candidate-artifact@" in text
    assert "docker/build-push-action@" in text
    assert "render_app_candidate_timing.py" in text
    assert "actions/upload-artifact@" not in text
    assert "actions/download-artifact@" not in text
    assert "oras-project/setup-oras@1d808f7d7f6995cc68b7bf507bfe5c5446e1dc9d" in text
    assert "app_candidate_oci_transport.py materialize-shards" in text
    assert 'CMD ["/evidence"]' in EVIDENCE_DOCKERFILE.read_text(encoding="utf-8")
    assert text.count("environment: [alpha, beta, gamma, prod]") == 4
    assert 'for env_name in "${{ matrix.environment }}"' in text


def test_app_pipeline_requires_four_environment_platform_package_set() -> None:
    assert SPEC_REF
    text = WORKFLOW.read_text(encoding="utf-8")
    for environment in ("alpha", "beta", "gamma", "prod"):
        assert environment in text
    for surface in ("android", "ios", "web", "macos"):
        assert f"--surface {surface}" in text
    for evidence in (
        "public-web-manifest.json",
        "android-release-manifest.json",
        "ops-portal-provenance.json",
        "application-packages",
        "payloads",
    ):
        assert evidence in text
    assert "QWQ_ANDROID_ALPHA_GOOGLE_SERVICES_JSON" in text
    assert "QWQ_ANDROID_BETA_GOOGLE_SERVICES_JSON" in text
    assert "QWQ_ANDROID_GAMMA_GOOGLE_SERVICES_JSON" in text
    assert "QWQ_ANDROID_PROD_GOOGLE_SERVICES_JSON" in text


def test_app_pipeline_missing_signing_inputs_are_typed_gate_blocks() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert text.count("quwoquan_ops/gate/require_ci_inputs.py") == 3
    assert text.count("../quwoquan_ops/gate/require_ci_inputs.py") == 1
    assert text.count("--scope release-signing") == 3
    for required in (
        "QWQ_ANDROID_RELEASE_KEYSTORE_B64",
        "QWQ_IOS_DISTRIBUTION_CERT_P12_B64",
        "PROD_OPS_OIDC_ISSUER",
    ):
        assert required in text


def test_app_release_evidence_identity_has_no_contract_number_suffix() -> None:
    assert SPEC_REF
    sources = (
        WORKFLOW,
        ROOT / "quwoquan_ops/ci/render_release_application_package.py",
        ROOT / "quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    for forbidden in (
        "schemaVersion",
        "contractVersion",
        "registryRevision",
        "app-launcher-handoff-v1",
        "app-effective-launch-manifest-v1",
    ):
        assert forbidden not in combined


def test_beta_device_receipt_binds_candidate_directly_without_identity_shim() -> None:
    assert SPEC_REF
    workflow = DEVICE_WORKFLOW.read_text(encoding="utf-8")
    evidence = DEVICE_EVIDENCE.read_text(encoding="utf-8")
    text = workflow + evidence

    assert "--identity-evidence" not in text
    assert "release-bound-environment-identity" not in text
    assert '"candidateId": candidate' in evidence
    assert '"sourceGitSha": git_sha' in evidence
    assert '"sourceTreeDigest": tree_digest' in evidence
    assert '--evidence "devices=$RAW/devices.json"' in workflow


def test_device_matrix_nightly_schedule_selects_full_profile() -> None:
    assert SPEC_REF
    text = DEVICE_WORKFLOW.read_text(encoding="utf-8")
    payload = yaml.load(text, Loader=yaml.BaseLoader)

    assert payload["on"]["schedule"] == [{"cron": "0 18 * * *"}]
    assert 'if [ "$EVENT_NAME" = "schedule" ]; then PROFILE="nightly_full"; fi' in text
    assert "vars.RELEASED_RELEASE_EVIDENCE_REF" in text
    assert "consume_released_release_evidence.py" in text
    assert "NIGHTLY_" not in text
    assert "stackctl.py dev-session" in text
    assert "--env gamma" in text
    assert "managed_runtime_started" in text
    assert "Inspect and doctor the managed Gamma runtime before soak" in text
    assert "Inspect and doctor the managed Gamma runtime after soak" in text
    assert text.count("stackctl.py inspect") >= 2
    assert text.count("stackctl.py doctor") >= 2
    assert '--budget-profile "$VALIDATION_PROFILE"' in text
    assert "canonical App device timing status" in text


def test_beta_android_and_ios_run_in_parallel_before_one_receipt_aggregation() -> None:
    assert SPEC_REF
    text = DEVICE_WORKFLOW.read_text(encoding="utf-8")
    platform_text = PLATFORM_WORKFLOW.read_text(encoding="utf-8")
    lease_text = DEVICE_LEASE.read_text(encoding="utf-8")
    runner_text = PLATFORM_RUNNER.read_text(encoding="utf-8")
    payload = yaml.load(text, Loader=yaml.BaseLoader)
    jobs = payload["jobs"]
    outputs = payload["on"]["workflow_call"]["outputs"]
    aggregate_job = jobs["mobile_matrix"]

    assert set(outputs) == {
        "discover_duration_seconds",
        "mobile_duration_seconds",
        "android_result",
        "ios_result",
        "allow_missing_platforms",
        "has_android",
        "has_ios",
        "machine_critical_path_seconds",
        "summary_result",
        "receipt_ref",
        "receipt_digest",
    }
    assert (
        outputs["receipt_ref"]["value"]
        == "${{ jobs.mobile_matrix.outputs.receipt_ref }}"
    )
    assert (
        outputs["receipt_digest"]["value"]
        == "${{ jobs.mobile_matrix.outputs.receipt_digest }}"
    )
    assert set(aggregate_job["needs"]) == {
        "beta_stack",
        "android_device_matrix",
        "ios_device_matrix",
    }
    assert aggregate_job["name"] == "Aggregate mobile matrix evidence"
    assert aggregate_job["runs-on"] == "ubuntu-latest"
    canonical_mobile_runner = ["self-hosted", "macOS", "ARM64"]
    assert jobs["beta_stack"]["runs-on"] == canonical_mobile_runner
    assert jobs["beta_teardown"]["runs-on"] == canonical_mobile_runner
    assert jobs["android_device_matrix"]["uses"] == "./.github/workflows/beta-device-platform.yml"
    assert jobs["ios_device_matrix"]["uses"] == "./.github/workflows/beta-device-platform.yml"
    assert jobs["android_device_matrix"]["needs"] == "beta_stack"
    assert jobs["ios_device_matrix"]["needs"] == "beta_stack"
    assert jobs["android_device_matrix"]["with"]["platform"] == "android"
    assert jobs["ios_device_matrix"]["with"]["platform"] == "ios"
    for job_name in ("android_device_matrix", "ios_device_matrix"):
        inputs = jobs[job_name]["with"]
        assert (
            inputs["account_closure_disposable_ack"]
            == "${{ inputs.account_closure_disposable_ack == true }}"
        )
        assert (
            inputs["account_closure_prod_platform"]
            == "${{ inputs.account_closure_prod_platform || 'ios' }}"
        )
    assert jobs["beta_teardown"]["needs"][-1] == "mobile_matrix"
    assert 'runs-on: [self-hosted, macOS, ARM64]' in platform_text
    assert "PUB_HOSTED_URL: https://pub.flutter-io.cn" in platform_text
    assert "FLUTTER_STORAGE_BASE_URL: https://storage.flutter-io.cn" in platform_text
    assert "flutter pub get --enforce-lockfile" in platform_text
    assert "run: flutter pub get\n" not in platform_text
    assert "MOBILE_MATRIX_ENV_JSON: ${{ inputs.env_json }}" in platform_text
    assert 'MATRIX_ENV_ARGS+=(--environment "$environment")' in platform_text
    assert '"${MATRIX_ENV_ARGS[@]}"' in platform_text
    assert 'runs-on: [self-hosted, macOS, ARM64, "mobile-${{ inputs.platform }}"]' not in platform_text
    assert '--runner-label "mobile-${{ inputs.platform }}"' in platform_text
    assert "device_runner_lease.py acquire" in platform_text
    assert "device_runner_lease.py release" in platform_text
    assert "expected-host-digest" in platform_text
    assert "execution-started-at" in platform_text
    assert "execution-ended-at" in platform_text
    assert "did not overlap" in DEVICE_EVIDENCE.read_text(encoding="utf-8")
    assert "MOBILE_DEVICE_ID" in runner_text
    assert "--device-id \"$MOBILE_DEVICE_ID\"" in runner_text
    assert "Beta receipt requires one immutable stack" in text
    assert "render_beta_device_evidence.py merge" in text
    assert "render_beta_device_evidence.py stack" in text
    assert "--android-ref \"$ANDROID_REF\"" in text
    assert "--ios-ref \"$IOS_REF\"" in text
    assert "materialize_evidence_oci.py" in text
    assert "@${{ steps.receipt_bundle.outputs.digest }}" in text
    combined = f"{text}\n{platform_text}\n{lease_text}\n{runner_text}"
    assert 'export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"' in runner_text
    assert 'cd "$ROOT"' in runner_text
    assert "actions/upload-artifact@" not in combined
    assert "actions/download-artifact@" not in combined
    assert "rm -rf" not in combined
    assert "git clean" not in combined
    assert "ASSISTANT_MODEL_PROVIDER: deterministic" not in combined
    assert "docker pull" not in text
    assert "RepoDigests" not in text
    assert "timeout-minutes: 120" not in combined
    assert "timeout-minutes: 30" not in combined
    assert jobs["beta_stack"]["timeout-minutes"] == "20"
    assert "mainline_auto_prod" in aggregate_job["timeout-minutes"]
    assert "20" in aggregate_job["timeout-minutes"]
    assert "|| 2" in aggregate_job["timeout-minutes"]
    aggregate_checkout = next(
        step
        for step in aggregate_job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert aggregate_checkout["if"] == (
        "${{ needs.beta_stack.outputs.profile == 'mainline_auto_prod' }}"
    )
    assert "10 || 1" in jobs["beta_teardown"]["timeout-minutes"]
    platform_payload = yaml.load(platform_text, Loader=yaml.BaseLoader)
    platform_timeout = platform_payload["jobs"]["device"]["timeout-minutes"]
    assert "nightly_full" in platform_timeout
    assert "120" in platform_timeout
    assert "release_candidate" in platform_timeout
    assert "manual_full" in platform_timeout
    assert "mainline_auto_prod" in platform_timeout
    assert "90" in platform_timeout
    assert "|| 60" in platform_timeout
    assert re.search(r"\|\|\s+4(?:\D|$)", platform_timeout) is None
    timing_gate = json.loads(TIMING_BUDGETS.read_text(encoding="utf-8"))["gates"][
        "05.app_env_device_matrix_pr"
    ]
    assert timing_gate["profileHardFailSeconds"]["mainline_auto_prod"] == 480
    assert timing_gate["profileHardFailSeconds"]["nightly_full"] == 7200
    assert '--budget-profile "$VALIDATION_PROFILE"' in text
    assert 'canonical App device timing status=${timing_status}' in text
    assert '"$calendar_lead_time_seconds" -gt "$profile_hard_fail_seconds"' not in text
    assert 'if [ "$calendar_lead_time_seconds" -gt 480 ]' not in text
    assert "STACKCTL_AUTO_WIPE_MIGRATION_DRIFT: \"0\"" in text
    assert "stackctl.py up" in text
    assert "--formal-release" in text
    assert '--release-manifest "$QWQ_PROD_RELEASE_ARTIFACT_ROOT/manifest.json"' in text
    assert "--skip-build" in text
    assert "--skip-app" in text
    formal_teardown = next(
        step
        for step in jobs["beta_teardown"]["steps"]
        if step.get("name") == "Teardown only the recorded formal Beta runtime"
    )
    assert formal_teardown["if"] == (
        "${{ needs.beta_stack.outputs.formal_runtime_started == 'true' }}"
    )
    formal_teardown_run = formal_teardown["run"]
    assert "stackctl.py down" in formal_teardown_run
    assert "--target beta-local" in formal_teardown_run
    assert "--formal-release" in formal_teardown_run
    assert (
        '--release-manifest "$QWQ_OUTPUT_ROOT/env/repo/runs/beta-stack/'
        'release-evidence-manifest/manifest.json"'
    ) in formal_teardown_run
    assert text.count("Require exact clean candidate checkout") == 1
    assert platform_text.count("Require exact clean candidate checkout") == 1
    assert text.count('[[ "$EXPECTED_SOURCE" =~ ^[0-9a-f]{40}$ ]]') == 1
    assert platform_text.count('[[ "$EXPECTED_SOURCE" =~ ^[0-9a-f]{40}$ ]]') == 1
    assert 'test -z "$(git status --porcelain --untracked-files=all)"' in text
    assert (
        'test -z "$(git status --porcelain --untracked-files=all)"'
        in platform_text
    )
    assert "docker compose up --build" not in text
    assert "source-built or destructive Beta formal runtime" not in text
    assert "steps.formal_runtime.outputs.started" in text
    assert "destructiveActions" in DEVICE_EVIDENCE.read_text(encoding="utf-8")
    assert combined.count("persist-credentials: false") == 10
    assert "config --local http.https://github.com/.extraheader" not in combined
    checkout_steps = [
        step
        for job in jobs.values()
        for step in job.get("steps", [])
        if str(step.get("uses") or "").startswith("actions/checkout@")
    ]
    called_checkout_steps = [
        step
        for job in platform_payload["jobs"].values()
        for step in job.get("steps", [])
        if str(step.get("uses") or "").startswith("actions/checkout@")
    ]
    assert len(checkout_steps) == 9
    assert len(called_checkout_steps) == 1
    assert sum(
        step["with"].get("clean") == "false" for step in checkout_steps
    ) == 7
    assert all(step["with"]["clean"] == "false" for step in called_checkout_steps)
    assert all(
        step["with"]["persist-credentials"] == "false"
        for step in checkout_steps
    )
    assert all(
        step["with"]["persist-credentials"] == "false"
        for step in called_checkout_steps
    )
