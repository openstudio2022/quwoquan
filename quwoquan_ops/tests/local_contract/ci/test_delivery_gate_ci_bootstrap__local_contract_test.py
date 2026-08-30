from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001.t2

import json
import os
import re
import subprocess
import textwrap
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[4]
GATE_REPO_PATH = ROOT / "quwoquan_ops/gate/gate_repo.sh"


def _workflow_jobs() -> dict[str, object]:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    return yaml.safe_load(workflow)["jobs"]


def _job_body(workflow: str, job_name: str) -> str:
    job_start = workflow.index(f"  {job_name}:\n")
    next_job = re.search(
        r"^  [a-z_]+:\n", workflow[job_start + 1 :], flags=re.MULTILINE
    )
    job_end = job_start + 1 + next_job.start() if next_job else None
    return workflow[job_start:job_end]


def _delivery_change_range_script() -> str:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    step_start = workflow.index("      - id: change_range\n")
    run_start = workflow.index("        run: |\n", step_start) + len("        run: |\n")
    run_end = workflow.index("      - name: 设置 Go\n", run_start)
    return textwrap.dedent(workflow[run_start:run_end])


def _run_delivery_change_range(
    tmp_path: Path,
    *,
    event_name: str,
    checkout_ref: str = "",
    base_sha: str = "",
    head_sha: str = "",
    pr_base_sha: str = "",
    pr_head_sha: str = "",
    push_before_sha: str = "",
    event_sha: str = "",
) -> subprocess.CompletedProcess[str]:
    output = tmp_path / "github-output"
    environment = {
        **os.environ,
        "EVENT_NAME": event_name,
        "INPUT_CHECKOUT_REF": checkout_ref,
        "INPUT_BASE_SHA": base_sha,
        "INPUT_HEAD_SHA": head_sha,
        "PR_BASE_SHA": pr_base_sha,
        "PR_HEAD_SHA": pr_head_sha,
        "PUSH_BEFORE_SHA": push_before_sha,
        "DISPATCH_SHA": event_sha,
        "GITHUB_OUTPUT": str(output),
    }
    return subprocess.run(
        ["bash", "-c", _delivery_change_range_script()],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_stubbed_app_test_phase(
    tmp_path: Path,
    *,
    phase: str = "tests",
    shard_total: str | None = "4",
    shard_index: str | None = "0",
) -> tuple[subprocess.CompletedProcess[str], Path]:
    source = GATE_REPO_PATH.read_text(encoding="utf-8")
    start = re.search(r"(?m)^run_app\(\)\s+\{", source)
    end = re.search(r"(?m)^run_portal\(\)\s+\(", source)
    assert start is not None and end is not None and start.start() < end.start()
    app = source[start.start() : end.start()]
    total_label = shard_total if shard_total is not None else "unset"
    index_label = shard_index if shard_index is not None else "unset"
    case_dir = tmp_path / f"shard-{total_label}-{index_label}"
    stub_dir = case_dir / "bin"
    stub_dir.mkdir(parents=True)
    log_path = case_dir / "commands.log"
    stub = '#!/usr/bin/env sh\nprintf "%s %s\\n" "$0" "$*" >>"$GATE_STUB_LOG"\n'
    for executable in ("python3", "dart", "flutter", "make"):
        path = stub_dir / executable
        path.write_text(stub, encoding="utf-8")
        path.chmod(0o755)
    harness = case_dir / "run_app_tests.sh"
    harness.write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        f"ROOT={str(ROOT)!r}\ncd \"$ROOT\"\n{app}\nrun_app\n",
        encoding="utf-8",
    )
    harness.chmod(0o755)
    environment = os.environ.copy()
    environment.pop("FLUTTER_TEST_TOTAL_SHARDS", None)
    environment.pop("FLUTTER_TEST_SHARD_INDEX", None)
    environment.update(
        {
            "GATE_APP_PHASE": phase,
            "GATE_STUB_LOG": str(log_path),
            "PATH": f"{stub_dir}:/usr/bin:/bin",
        }
    )
    if shard_total is not None:
        environment["FLUTTER_TEST_TOTAL_SHARDS"] = shard_total
    if shard_index is not None:
        environment["FLUTTER_TEST_SHARD_INDEX"] = shard_index
    completed = subprocess.run(
        ["/bin/bash", str(harness)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, log_path


def _run_stubbed_service_phase(
    tmp_path: Path, *, phase: str
) -> subprocess.CompletedProcess[str]:
    source = GATE_REPO_PATH.read_text(encoding="utf-8")
    wrapper_start = source.index("run_service() {")
    wrapper_end = source.index("\n\nrun_app() {", wrapper_start)
    wrapper = source[wrapper_start:wrapper_end]
    harness = tmp_path / f"run-service-{phase}.sh"
    harness.write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        'run_service_core_before_packaging() { echo core-before; }\n'
        'run_service_packaging() { echo packaging; }\n'
        'run_service_core_after_packaging() { echo core-after; }\n'
        'run_service_canonical_coverage() { echo coverage; }\n'
        f"service_phase={phase!r}\n{wrapper}\nrun_service\n",
        encoding="utf-8",
    )
    harness.chmod(0o755)
    return subprocess.run(
        ["/bin/bash", str(harness)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_delivery_gate_bootstrap_uses_pinned_verified_toolchains() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")

    assert "subosito/flutter-action@" not in workflow
    assert "quwoquan_app/.flutter-version" in workflow
    assert "python3 quwoquan_ops/ci/setup_flutter_sdk.py resolve" in workflow
    assert "python3 quwoquan_ops/ci/setup_flutter_sdk.py install" in workflow
    assert "Cache lock-bound Dart dependencies" in workflow
    assert (
        "path: |\n            ${{ steps.flutter.outputs.cache_path }}" not in workflow
    )
    assert "cache-dependency-path: quwoquan_ops/portal/package-lock.json" in workflow
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in workflow
    assert "pip install -r quwoquan_data/requirements.txt" in workflow
    assert "github.com/rhysd/actionlint/cmd/actionlint@v1.7.7" in workflow
    assert 'actionlint\" -version | head -n 1)\" = \"v1.7.7\"' in workflow


def test_common_governance_is_one_exact_sha_bounded_job() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    jobs = _workflow_jobs()

    assert list(jobs).count("common_governance") == 1
    common = _job_body(workflow, "common_governance")
    assert "timeout-minutes: 15" in common
    assert "github.event.pull_request.head.sha || github.sha" in common
    assert "git rev-parse HEAD" in common
    assert "git status --porcelain" in common
    assert common.count("verify_git_branch_policy.py") == 1
    assert common.count("verify_github_supply_chain.py") == 1
    assert "github.com/rhysd/actionlint/cmd/actionlint@v1.7.7" in common
    assert "Validate optional LocalReadiness verifier wiring" in common
    assert "quwoquan_ops/policies/local_readiness_contract.yaml" in common
    assert "quwoquan_ops/cli/local_readiness.py" in common
    assert 'python3 "$VERIFIER" verify --help' in common
    assert "LocalReadiness contract exists without its canonical verifier" in common
    assert "bash quwoquan_ops/gate/gate_repo.sh" not in common
    assert "GATE_SKIP" not in workflow
    topology = _job_body(workflow, "topology_regression")
    assert "needs: common_governance" in topology
    assert "verify_git_branch_policy.py" not in topology
    assert "verify_github_supply_chain.py" not in topology


def test_data_jobs_are_impact_gated_as_one_complete_closure() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    expected_if = "if: ${{ needs.topology_regression.outputs.data == 'true' }}"
    data = _job_body(workflow, "quwoquan_data")
    shards = _job_body(workflow, "quwoquan_data_tests")

    assert expected_if in data
    assert expected_if in shards
    assert "GATE_DATA_PHASE: verify" in data
    assert "GATE_DATA_PHASE: local_contract" in shards
    assert 'DATA_TEST_TOTAL_SHARDS: "4"' in shards
    assert "shard_index: [0, 1, 2, 3]" in shards
    assert 'if [[ "$DATA_IMPACTED" == "true" ]]; then' in workflow
    assert '--require-count "data=1" --require-count "data_tests=4"' in workflow
    assert 'expect_typed_pending_or_skipped "quwoquan_data"' in workflow
    assert 'expect_typed_pending_or_skipped "quwoquan_data_tests"' in workflow
    assert 'expect_typed_pending_or_skipped "quwoquan_data"' in workflow
    assert 'expect_typed_pending_or_skipped "quwoquan_data_tests"' in workflow
    assert 'if [ "$impacted" = "true" ]; then' in workflow
    assert 'expect_success "$name" "$val" "$hint"' in workflow


def test_pull_request_avoids_release_and_canonical_coverage_workloads() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    pr_exclusion = "github.event_name != 'pull_request'"

    for job_name in (
        "quwoquan_service",
        "quwoquan_service_packaging",
        "quwoquan_service_coverage",
    ):
        assert pr_exclusion in _job_body(workflow, job_name)
    for job_name in (
        "quwoquan_app_static",
        "quwoquan_app_tests",
        "quwoquan_app_serial",
        "quwoquan_app_coverage",
    ):
        assert pr_exclusion in _job_body(workflow, job_name)
    release = _job_body(workflow, "release_evidence")
    assert "if: always() && inputs.produce_release_evidence" in release
    assert "schedule:" not in workflow


def test_delivery_uses_lock_bound_hosted_dependency_caches() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    for job_name in ("quwoquan_service", "quwoquan_service_coverage", "search_contract_smoke"):
        job = _job_body(workflow, job_name)
        assert "cache: false" in job
        assert "Cache lock-bound Go modules and build outputs" in job
        assert "hashFiles('quwoquan_service/go.sum')" in job
        assert "~/go/pkg/mod" in job
        assert "~/.cache/go-build" in job
    for job_name in ("quwoquan_data", "quwoquan_data_tests"):
        job = _job_body(workflow, job_name)
        assert "cache: 'pip'" in job
        assert "cache-dependency-path: quwoquan_data/requirements.txt" in job
    assert "cache-dependency-path: quwoquan_ops/portal/package-lock.json" in workflow
    assert "Cache lock-bound Dart dependencies" in workflow


def test_delivery_pub_cache_is_hosted_only() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )
    jobs = {
        "static": ("quwoquan_app_static", "quwoquan_app_tests"),
        "tests": ("quwoquan_app_tests", "quwoquan_app_serial"),
        "serial": ("quwoquan_app_serial", "quwoquan_app_coverage"),
        "coverage": ("quwoquan_app_coverage", "quwoquan_app"),
    }
    bodies = {
        phase: workflow[
            workflow.index(f"  {job_name}:\n") : workflow.index(
                f"\n  {next_job_name}:\n", workflow.index(f"  {job_name}:\n")
            )
        ]
        for phase, (job_name, next_job_name) in jobs.items()
    }
    cache_action = "uses: actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830"

    for phase in ("static", "tests"):
        body = bodies[phase]
        assert "runs-on: ubuntu-latest" in body
        assert "Cache lock-bound Dart dependencies" in body
        assert cache_action in body
        assert "path: ~/.pub-cache" in body

    for phase in ("serial", "coverage"):
        body = bodies[phase]
        assert "runs-on: [self-hosted, macOS, ARM64]" in body
        assert "Cache lock-bound Dart dependencies" not in body
        assert cache_action not in body
        assert "path: ~/.pub-cache" not in body

    for phase, body in bodies.items():
        assert "flutter pub get --enforce-lockfile" in body
        assert f"GATE_APP_PHASE: {phase}" in body
        assert "bash quwoquan_ops/gate/gate_repo.sh --scope app" in body


def test_ops_portal_build_receives_the_external_deploy_root() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    job_start = workflow.index("  ops_portal:\n")
    job_end = workflow.index("\n  release_evidence:\n", job_start)
    job = workflow[job_start:job_end]

    assert "Configure Ops Portal CI paths" in job
    assert (
        'echo "QWQ_DEPLOY_WORK_ROOT=$RUNNER_TEMP/quwoquan-deploy" '
        '>> "$GITHUB_ENV"'
    ) in job


def test_service_gate_installs_required_native_test_dependencies() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    job_start = workflow.index("  quwoquan_service:\n")
    job_end = workflow.index("\n  quwoquan_service_packaging:\n", job_start)
    job = workflow[job_start:job_end]

    assert "prometheus tesseract-ocr ffmpeg redis-server" in job
    assert "run_bounded_apt_install.sh" in job
    assert "QWQ_TEST_MONGO_URI:" not in job
    assert job.count("run_recommendation_test_mongodb.sh") == 1

    # 采集格自己重跑被测模块，同样要 mongo；两处都必须走同一个 canonical 引导脚本，
    # 不允许谁在作业里临时起一个容器。
    coverage_start = workflow.index("  quwoquan_service_coverage:\n")
    coverage_end = workflow.index("\n  search_contract_smoke:\n", coverage_start)
    coverage = workflow[coverage_start:coverage_end]
    assert "prometheus tesseract-ocr ffmpeg redis-server" in coverage
    assert coverage.count("run_recommendation_test_mongodb.sh") == 1
    assert "docker run -d --name qwq-rec-mongo" not in workflow
    assert "rs.initiate" not in workflow


def test_service_gate_phase_partition_preserves_default_full_gate() -> None:
    gate = GATE_REPO_PATH.read_text(encoding="utf-8")
    before_start = gate.index("run_service_core_before_packaging()")
    packaging_start = gate.index("run_service_packaging()", before_start)
    after_start = gate.index("run_service_core_after_packaging()", packaging_start)
    wrapper_start = gate.index("run_service()", after_start)
    app_start = gate.index("run_app()", wrapper_start)

    before = gate[before_start:packaging_start]
    packaging = gate[packaging_start:after_start]
    after = gate[after_start:wrapper_start]
    wrapper = gate[wrapper_start:app_start]
    package_commands = (
        "make verify-env-packaging",
        "make verify-prod-packaging-contract",
        "python3 quwoquan_ops/gate/verify_output_layout.py",
    )
    for command in package_commands:
        assert command in packaging
        assert command not in before
        assert command not in after
    assert wrapper.index("run_service_core_before_packaging") < wrapper.index(
        "run_service_packaging"
    ) < wrapper.index("run_service_core_after_packaging")
    assert 'service_phase="${GATE_SERVICE_PHASE:-all}"' in gate
    assert 'if [[ "$service_phase" != "packaging" ]]; then' in gate

    invalid = subprocess.run(
        ["bash", str(GATE_REPO_PATH), "--scope", "service"],
        cwd=ROOT,
        env={**os.environ, "GATE_SERVICE_PHASE": "unknown"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert invalid.returncode == 2
    assert "invalid GATE_SERVICE_PHASE=unknown" in invalid.stderr


def test_service_gate_phase_partition_executes_each_exact_call_set(
    tmp_path: Path,
) -> None:
    expected = {
        "all": ["core-before", "packaging", "core-after", "coverage"],
        "core": ["core-before", "core-after"],
        "packaging": ["packaging"],
        "coverage": ["coverage"],
    }
    for phase, calls in expected.items():
        completed = _run_stubbed_service_phase(tmp_path, phase=phase)
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.splitlines() == calls


def test_delivery_runs_service_core_and_packaging_as_parallel_siblings() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )
    core_start = workflow.index("  quwoquan_service:\n")
    packaging_start = workflow.index("  quwoquan_service_packaging:\n")
    coverage_start = workflow.index("  quwoquan_service_coverage:\n")
    search_start = workflow.index("  search_contract_smoke:\n")
    core = workflow[core_start:packaging_start]
    packaging = workflow[packaging_start:coverage_start]
    coverage = workflow[coverage_start:search_start]

    assert "needs: topology_regression" in core
    assert "needs: topology_regression" in packaging
    assert "timeout-minutes: 40" in core
    assert "timeout-minutes: 30" in packaging
    assert "GATE_SERVICE_PHASE: core" in core
    assert "GATE_SERVICE_PHASE: packaging" in packaging
    assert "设置 Go" not in packaging
    assert "设置 Dart" not in packaging
    assert "run_bounded_apt_install.sh tesseract-ocr" in packaging
    assert "needs: topology_regression" in coverage
    assert "GATE_SERVICE_PHASE: coverage" in coverage
    coverage_fn = GATE_REPO_PATH.read_text(encoding="utf-8")
    coverage_fn = coverage_fn[
        coverage_fn.index("run_service_canonical_coverage()") : coverage_fn.index(
            "\nrun_service() {"
        )
    ]
    assert (
        "make -C quwoquan_service/services/recommendation-service prepare-test-python"
        in coverage_fn
    )
    assert coverage_fn.index("prepare-test-python") < coverage_fn.index(
        "verify_canonical_coverage.py --collect --scope cloud"
    )
    assert (
        '--require-count "service=1" --require-count "service_packaging=3"'
        ' --require-count "service_coverage=1"'
    ) in workflow
    assert "FANOUT+=(service service_packaging service_coverage)" in workflow
    assert (
        "--local-required service --local-required service_packaging"
        " --local-required service_coverage"
    ) in workflow
    assert "SERVICE_PACKAGING: ${{ needs.quwoquan_service_packaging.result }}" in workflow
    assert "SERVICE_COVERAGE: ${{ needs.quwoquan_service_coverage.result }}" in workflow
    summary_start = workflow.index("      - name: 汇总并阻断失败项")
    summary = workflow[summary_start:]
    assert "        if: always()" in summary


def test_service_gate_passes_the_exact_reviewed_change_range() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    gate = GATE_REPO_PATH.read_text(encoding="utf-8")
    job_start = workflow.index("  quwoquan_service:\n")
    job_end = workflow.index("\n  search_contract_smoke:\n", job_start)
    job = workflow[job_start:job_end]

    assert "id: change_range" in job
    assert "Resolve immutable Delivery change range" in job
    assert "GATE_CHANGE_BASE_SHA: ${{ steps.change_range.outputs.base_sha }}" in job
    assert "GATE_CHANGE_HEAD_SHA: ${{ steps.change_range.outputs.candidate_sha }}" in job
    assert "GRAPHQL_MIGRATION_BASE_SHA: ${{ steps.change_range.outputs.base_sha }}" in job
    assert "git merge-base --is-ancestor \"$BASE_SHA\" \"$CANDIDATE_SHA\"" in job
    assert "GATE_CHANGE_BASE_SHA and GATE_CHANGE_HEAD_SHA must be provided together" in gate
    assert '--base-sha "$GATE_CHANGE_BASE_SHA"' in gate
    assert '--head-sha "$GATE_CHANGE_HEAD_SHA"' in gate
    # set -u 下空数组展开会直接炸，所以调用侧用的是 ${arr[@]+"${arr[@]}"} 保护形式。
    assert "verify_gate_local_contract_execution.py" in gate
    assert '${gate_change_range_args[@]+"${gate_change_range_args[@]}"}' in gate


def test_delivery_change_range_requires_complete_workflow_call_identity(
    tmp_path: Path,
) -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    workflow_call_inputs = workflow.split("  workflow_call:\n", 1)[1].split(
        "    outputs:\n", 1
    )[0]
    for input_name in ("checkout_ref", "base_sha", "head_sha"):
        match = re.search(
            rf"(?m)^      {input_name}:\n(?P<body>(?:        .*\n)+)",
            workflow_call_inputs,
        )
        assert match is not None
        input_block = match.group("body")
        assert "required: true" in input_block
        assert "default:" not in input_block

    head_sha = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    base_sha = subprocess.run(
        ("git", "rev-parse", "HEAD^"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    for checkout_ref, requested_base, requested_head in (
        (head_sha, "", head_sha),
        (head_sha, base_sha, ""),
        ("", base_sha, head_sha),
    ):
        result = _run_delivery_change_range(
            tmp_path,
            event_name="workflow_call",
            checkout_ref=checkout_ref,
            base_sha=requested_base,
            head_sha=requested_head,
        )
        assert result.returncode == 2
        assert "requires checkout_ref, base_sha and head_sha together" in result.stdout

    mismatch = _run_delivery_change_range(
        tmp_path,
        event_name="workflow_call",
        checkout_ref=base_sha,
        base_sha=base_sha,
        head_sha=head_sha,
    )
    assert mismatch.returncode == 2
    assert "checkout_ref must equal head_sha" in mismatch.stdout

    success = _run_delivery_change_range(
        tmp_path,
        event_name="workflow_dispatch",
        event_sha=head_sha,
    )
    assert success.returncode == 0, success.stderr

    pull_request = _run_delivery_change_range(
        tmp_path,
        event_name="pull_request",
        pr_base_sha=base_sha,
        pr_head_sha=head_sha,
    )
    assert pull_request.returncode == 0, pull_request.stderr

    push = _run_delivery_change_range(
        tmp_path,
        event_name="push",
        push_before_sha=base_sha,
        event_sha=head_sha,
    )
    assert push.returncode == 0, push.stderr

    for invalid_before in ("", "0" * 40):
        blocked_push = _run_delivery_change_range(
            tmp_path,
            event_name="push",
            push_before_sha=invalid_before,
            event_sha=head_sha,
        )
        assert blocked_push.returncode == 2
        assert "push requires an exact non-zero before SHA" in blocked_push.stdout


def test_pull_request_jobs_checkout_and_diff_the_exact_event_head() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")

    exact_checkout = (
        "${{ inputs.checkout_ref || "
        "github.event.pull_request.head.sha || github.sha }}"
    )
    # 按 job 逐个判，而不是数 checkout 总数：计数写死时新增一个 job 就得改数字，
    # 而改数字的人未必检查了新 job 是否真的钉了 exact ref。
    document = yaml.safe_load(workflow)
    checkouts = [
        (job_name, (step.get("with") or {}).get("ref"))
        for job_name, job in document["jobs"].items()
        for step in job.get("steps") or []
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert checkouts, "Delivery Gate 必须有 checkout 步骤"
    drifted = [job_name for job_name, ref in checkouts if ref != exact_checkout]
    assert not drifted, f"这些 job 的 checkout 没钉到事件 head：{drifted}"
    assert "PR_BASE_SHA: ${{ github.event.pull_request.base.sha || '' }}" in workflow
    assert "PR_HEAD_SHA: ${{ github.event.pull_request.head.sha || '' }}" in workflow
    assert "PUSH_BEFORE_SHA: ${{ github.event.before || '' }}" in workflow
    assert (
        "HEAD_SHA: ${{ inputs.head_sha || "
        "github.event.pull_request.head.sha || github.sha }}"
    ) in workflow
    assert (
        '--source-git-sha "${{ inputs.source_git_sha || '
        'github.event.pull_request.head.sha || github.sha }}"'
    ) in workflow


def test_delivery_and_promotion_gates_defer_edges_to_canonical_evaluator() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    pre_release = (ROOT / ".github/workflows/pre-release-gate.yml").read_text(encoding="utf-8")

    assert "pull_request:\n    branches:" not in workflow
    assert "pull_request:\n    branches:" not in pre_release
    for source in (workflow, pre_release):
        assert "\n  push:\n    branches: [dev1.0]\n" in source
    app_matrix = (
        ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml"
    ).read_text(encoding="utf-8")
    assert "\n  push:\n    branches: [dev1.0]\n" in app_matrix
    assert (
        "github.event.pull_request.base.sha || github.event.before || ''"
        in workflow
    )
    for source in (workflow, pre_release, app_matrix):
        assert "Enforce canonical repository branch admission" in source
        assert "python3 quwoquan_ops/gate/verify_git_branch_policy.py" in source
    assert "Admit direct dev1.0 integration push" not in pre_release
    assert "Admit direct dev1.0 integration push" not in app_matrix
    assert "verify_git_branch_policy.py" in workflow
    assert "Pre-Release — Branch Policy" in pre_release
    assert "needs: branch_policy" in pre_release


def test_app_pipeline_uses_only_the_repository_pinned_flutter_version() -> None:
    workflow = (ROOT / ".github/workflows/app_pipeline.yml").read_text(encoding="utf-8")

    # 装 Flutter 的作业数会随流水线收敛增减，绑死数量只会把测试变成待改的常量；
    # 真正的约束是「每一次装 Flutter 都从仓库 pin 读版本」，两侧计数必须相等且非零。
    pinned_reads = workflow.count("quwoquan_app/.flutter-version")
    assert pinned_reads > 0
    assert workflow.count("subosito/flutter-action") == pinned_reads
    assert (
        workflow.count("flutter-version: '${{ steps.flutter_version.outputs.value }}'")
        == pinned_reads
    )
    assert "channel: stable" not in workflow
    assert (ROOT / "quwoquan_app/.flutter-version").read_text(encoding="utf-8") == "3.47.0\n"


def test_delivery_gate_has_bounded_jobs() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )

    expected_timeouts = {
        "common_governance": 15,
        "topology_regression": 10,
        "quwoquan_service": 40,
        "quwoquan_service_packaging": 30,
        "search_contract_smoke": 10,
        "quwoquan_app_static": 20,
        "quwoquan_app_tests": 40,
        "quwoquan_app_serial": 40,
        "quwoquan_service_coverage": 40,
        "quwoquan_app_coverage": 60,
        "quwoquan_app": 30,
        "quwoquan_data": 10,
        "quwoquan_data_tests": 25,
        "ops_portal": 10,
        "release_evidence": 10,
        "delivery_gate_summary": 5,
    }
    # 清单写死时，新增的 job 落在清单外——它的 timeout 是多少、有没有 timeout，
    # 这条测试都不会过问。先钉住清单本身覆盖全部 job。
    declared = set(yaml.safe_load(workflow)["jobs"])
    assert declared == set(expected_timeouts), (
        f"清单与 workflow 的 job 集合不一致：只在 workflow={sorted(declared - set(expected_timeouts))}，"
        f"只在清单={sorted(set(expected_timeouts) - declared)}"
    )
    for job, minutes in expected_timeouts.items():
        job_start = workflow.index(f"  {job}:\n")
        next_job = re.search(
            r"^  [a-z_]+:\n", workflow[job_start + 1 :], flags=re.MULTILINE
        )
        job_end = job_start + 1 + next_job.start() if next_job else None
        job_body = workflow[job_start:job_end]
        assert f"    timeout-minutes: {minutes}" in job_body


def test_delivery_gate_shards_app_contract_without_weakening_local_full_gate() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    gate = (ROOT / "quwoquan_ops/gate/gate_repo.sh").read_text(encoding="utf-8")

    assert "quwoquan_app_static:" in workflow
    assert "quwoquan_app_tests:" in workflow
    assert "quwoquan_app_serial:" in workflow
    assert "quwoquan_app_coverage:" in workflow
    assert "shard_index: [0, 1, 2, 3]" in workflow
    assert 'FLUTTER_TEST_TOTAL_SHARDS: "4"' in workflow
    assert "FLUTTER_TEST_SHARD_INDEX: ${{ matrix.shard_index }}" in workflow
    assert "GATE_APP_PHASE: static" in workflow
    assert "GATE_APP_PHASE: tests" in workflow
    assert "GATE_APP_PHASE: serial" in workflow
    assert "GATE_APP_PHASE: coverage" in workflow
    assert 'local app_phase="${GATE_APP_PHASE:-all}"' in gate
    assert 'run_app_flutter_tests "${FLUTTER_TEST_SERIAL_MODE:-exclude}"' in gate


def test_canonical_coverage_uses_the_serial_golden_platform() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )
    coverage_start = workflow.index("  quwoquan_app_coverage:\n")
    aggregate_start = workflow.index("\n  quwoquan_app:\n", coverage_start)
    coverage = workflow[coverage_start:aggregate_start]

    assert "runs-on: [self-hosted, macOS, ARM64]" in coverage
    assert "GATE_APP_PHASE: coverage" in coverage


def test_app_shard_zero_owns_native_dependencies_and_shared_contracts() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    job_start = workflow.index("  quwoquan_app_tests:\n")
    job_end = workflow.index("\n  quwoquan_app_serial:\n", job_start)
    job = workflow[job_start:job_end]
    gate = (ROOT / "quwoquan_ops/gate/gate_repo.sh").read_text(encoding="utf-8")

    assert "Install App shared contract native dependencies" in job
    assert "if: ${{ matrix.shard_index == 0 }}" in job
    assert "tesseract-ocr" in job
    assert "run_bounded_apt_install.sh" in job
    assert "apt-get" not in job
    assert 'local app_test_shared_suite="run"' in gate
    assert 'if (( 10#${FLUTTER_TEST_SHARD_INDEX} != 0 )); then' in gate
    assert 'app_test_shared_suite="skip"' in gate
    assert 'if [[ "$app_test_shared_suite" == "run" ]]; then' in gate
    assert "run_app_python_local_contract_tests || return 1" in gate
    assert 'if [[ "$app_phase" == "coverage" ]]; then' in gate
    assert "run_app_canonical_coverage" in gate
    assert "quwoquan_app_coverage" in workflow
    assert "--local-required app_coverage" in workflow


def test_hosted_delivery_budgets_match_observed_parallel_shape() -> None:
    budgets = json.loads(
        (ROOT / "quwoquan_ops/environments/pr_gate_timing_budgets.json").read_text(
            encoding="utf-8"
        )
    )
    delivery = budgets["gates"]["03.delivery_gate"]
    assert delivery["budgetSeconds"] == 1500
    assert delivery["hardFailSeconds"] == 1800
    assert delivery["machinePath"] == (
        "topology_regression + max(quwoquan_service, "
        "quwoquan_service_packaging, quwoquan_service_coverage, "
        "search_contract_smoke, "
        "quwoquan_app_static, quwoquan_app_tests, "
        "quwoquan_app_serial, quwoquan_app_coverage, quwoquan_data, ops_portal); "
        "pull_request sources quwoquan_app_* from verified push evidence while "
        "calendar still ends at its own verifier completion"
    )
    assert set(delivery["phaseBudgetsSeconds"]) >= {
        "quwoquan_app_static",
        "quwoquan_app_tests",
        "quwoquan_app_serial",
        "quwoquan_app_coverage",
    }


def test_app_test_phase_executes_shared_contracts_only_on_shard_zero(
    tmp_path: Path,
) -> None:
    for shard_index in ("0", "1", "2", "3"):
        completed, log_path = _run_stubbed_app_test_phase(
            tmp_path,
            shard_index=shard_index,
        )
        assert completed.returncode == 0, completed.stderr
        commands = log_path.read_text(encoding="utf-8").splitlines()
        python_contract_commands = [
            command
            for command in commands
            if "test-app-python-local-contract" in command
        ]
        canonical_coverage_commands = [
            command
            for command in commands
            if "verify_canonical_coverage.py --collect --scope app" in command
        ]
        expected_count = 1 if shard_index == "0" else 0
        assert len(python_contract_commands) == expected_count
        assert len(canonical_coverage_commands) == 0


def test_unsharded_app_test_phase_keeps_the_full_shared_suite(
    tmp_path: Path,
) -> None:
    completed, log_path = _run_stubbed_app_test_phase(
        tmp_path,
        shard_total=None,
        shard_index=None,
    )

    assert completed.returncode == 0, completed.stderr
    commands = log_path.read_text(encoding="utf-8").splitlines()
    assert sum("test-app-python-local-contract" in row for row in commands) == 1
    assert not any(
        "verify_canonical_coverage.py --collect --scope app" in row
        for row in commands
    )


def test_app_coverage_phase_executes_canonical_coverage_once(
    tmp_path: Path,
) -> None:
    completed, log_path = _run_stubbed_app_test_phase(
        tmp_path,
        phase="coverage",
        shard_total=None,
        shard_index=None,
    )

    assert completed.returncode == 0, completed.stderr
    commands = log_path.read_text(encoding="utf-8").splitlines()
    assert not any("test-app-python-local-contract" in row for row in commands)
    assert sum(
        "verify_canonical_coverage.py --collect --scope app" in row
        for row in commands
    ) == 1


def test_app_test_phase_rejects_invalid_shards_before_execution(
    tmp_path: Path,
) -> None:
    invalid_shards = (
        (None, "0"),
        ("4", None),
        ("0", "0"),
        ("not-a-number", "0"),
        ("4", "-1"),
        ("4", "not-a-number"),
        ("4", "4"),
    )

    for shard_total, shard_index in invalid_shards:
        completed, log_path = _run_stubbed_app_test_phase(
            tmp_path,
            shard_total=shard_total,
            shard_index=shard_index,
        )

        assert completed.returncode == 2
        assert (
            "app phase=tests sharding requires total>0 and 0<=index<total"
            in completed.stderr
        )
        assert "or unset both for unsharded execution" in completed.stderr
        assert not log_path.exists()


def test_delivery_pr_reuses_push_owned_app_evidence_without_merging_ranges() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )
    local_app_if = (
        "github.event_name != 'pull_request' && (github.event_name == "
        "'workflow_call' || needs.topology_regression.outputs.candidate_app == 'true')"
    )
    assert workflow.count(local_app_if) == 4
    assert "name: Detect candidate-level App scope" in workflow
    assert "git merge-base origin/main \"$HEAD_SHA\"" in workflow
    assert "--scope-receipt" in workflow
    assert "SCOPE_ARGS+=(--required-scope app)" in workflow
    assert '${SCOPE_ARGS[@]+"${SCOPE_ARGS[@]}"}' in workflow
    assert "name: Verify push-owned App evidence" in workflow
    assert "make verify-delivery-app-evidence" in workflow
    assert "job_closure_digest: ${{ steps.external.outputs.job_closure_digest }}" in workflow
    assert "if: ${{ github.event_name == 'pull_request' }}" in workflow
    assert 'if [[ "${{ github.event_name }}" != "pull_request" ]]; then' in workflow
    assert "if: ${{ github.event_name != 'pull_request' }}" in workflow
    assert "--external-phase \"app_static=$APP_STATIC_EXTERNAL\"" in workflow
    assert "--external-phase \"app_coverage=$APP_COVERAGE_EXTERNAL\"" in workflow
    assert '--candidate-job "Delivery Gate — App (L1)"' not in workflow
    concurrency = workflow[workflow.index("concurrency:") : workflow.index("\non:")]
    assert "github.event_name" in concurrency
    assert "github.ref" in concurrency
    assert "head.sha" not in concurrency


def test_delivery_gate_keeps_cross_platform_jobs_on_linux_and_visual_phases_on_controlled_macos() -> None:
    delivery = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )

    hosted_linux_jobs = (
        "common_governance",
        "topology_regression",
        "quwoquan_service",
        "search_contract_smoke",
        "quwoquan_app_static",
        "quwoquan_app_tests",
        "quwoquan_app",
        "quwoquan_data",
        "ops_portal",
        "release_evidence",
        "delivery_gate_summary",
    )
    for job_name in hosted_linux_jobs:
        job_start = delivery.index(f"  {job_name}:\n")
        next_job = re.search(
            r"^  [a-z_]+:\n", delivery[job_start + 1 :], flags=re.MULTILINE
        )
        job_end = job_start + 1 + next_job.start() if next_job else None
        job_body = delivery[job_start:job_end]
        assert "runs-on: ubuntu-latest" in job_body

    for job_name, next_job_name in (
        ("quwoquan_app_serial", "quwoquan_app_coverage"),
        ("quwoquan_app_coverage", "quwoquan_app"),
    ):
        job_start = delivery.index(f"  {job_name}:\n")
        job_end = delivery.index(f"\n  {next_job_name}:\n", job_start)
        job_body = delivery[job_start:job_end]
        assert "runs-on: [self-hosted, macOS, ARM64]" in job_body
    assert "runs-on: macos-latest" not in delivery


def test_search_smoke_builds_the_pinned_cjk_provider_before_api_tests() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )
    job_start = workflow.index("  search_contract_smoke:\n")
    job_end = workflow.index("\n  quwoquan_app_static:\n", job_start)
    job = workflow[job_start:job_end]

    build = (
        "docker build \\\n"
        "            --tag quwoquan/elasticsearch-cjk:8.13.4"
    )
    test = "go test ./services/search-service/tests/api_integration/search/search_index_view"
    assert build in job
    assert job.index(build) < job.index(test)


def test_environment_writing_jobs_stay_on_controlled_runners() -> None:
    for workflow_path in (
        ROOT / ".github/workflows/pre-release-gate.yml",
        ROOT / ".github/workflows/artifact-lifecycle.yml",
    ):
        workflow = workflow_path.read_text(encoding="utf-8")
        assert "runs-on: macos-latest" not in workflow
        assert "runs-on: [self-hosted, macOS, ARM64]" in workflow


def test_contract_metadata_bootstrap_creates_cache_parent_before_mktemp() -> None:
    script = (
        ROOT / "quwoquan_service/scripts/verify/contract_graph/verify_contract_metadata.sh"
    ).read_text(encoding="utf-8")

    mkdir_index = script.index('mkdir -p "$CONTRACT_VIEW_CACHE"')
    mktemp_index = script.index('mktemp -d "${CONTRACT_VIEW_CACHE}/verify.XXXXXX"')
    assert mkdir_index < mktemp_index


def test_ff_config_contract_uses_portable_grep() -> None:
    script = (
        ROOT / "quwoquan_ops/environments/verify/verify_ff_config_contract.sh"
    ).read_text(encoding="utf-8")

    assert 'grep -nF -- "$token" "$spec"' in script
    assert "rg -n" not in script
