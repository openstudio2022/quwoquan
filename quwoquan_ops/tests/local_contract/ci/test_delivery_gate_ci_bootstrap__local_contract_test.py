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
    push_ref_name: str = "",
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
        "PUSH_REF_NAME": push_ref_name,
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
    assert 'go install "github.com/rhysd/actionlint/cmd/actionlint@v$ACTIONLINT_VERSION"' in workflow
    assert "actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830" in workflow
    assert "actionlint-${{ runner.os }}-${{ runner.arch }}-v1.7.7" in workflow
    assert "timeout 180s env GOBIN=" in workflow
    assert "awk 'NR == 1 {print; exit}'" in workflow


def test_common_governance_is_one_exact_sha_bounded_job() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    jobs = _workflow_jobs()

    assert list(jobs).count("common_governance") == 1
    common = _job_body(workflow, "common_governance")
    assert "timeout-minutes: 15" in common
    assert "inputs.checkout_ref || github.sha" in common
    assert "git rev-parse HEAD" in common
    assert "git status --porcelain" in common
    assert common.count("verify_git_branch_policy.py") == 1
    assert common.count("verify_github_supply_chain.py") == 1
    assert "github.com/rhysd/actionlint/cmd/actionlint@v$ACTIONLINT_VERSION" in common
    assert "steps.workflow_impact.outputs.workflow_required == 'true'" in common
    assert "state=NOT_REQUIRED" in common
    assert "base_sha=$BASE_SHA head_sha=$HEAD_SHA" in common
    assert "steps.actionlint_cache.outputs.cache-hit != 'true'" in common
    assert "Validate optional LocalReadiness verifier wiring" in common
    assert "quwoquan_ops/policies/local_readiness_contract.yaml" in common
    assert "quwoquan_ops/cli/local_readiness.py" in common
    assert 'python3 "$VERIFIER" verify --help' in common
    assert "LocalReadiness contract exists without its canonical verifier" in common
    assert "bash quwoquan_ops/gate/gate_repo.sh" not in common
    assert "GATE_SKIP" not in workflow
    topology = _job_body(workflow, "topology_regression")
    assert "needs: common_governance" not in topology
    assert "verify_git_branch_policy.py" not in topology
    assert "verify_github_supply_chain.py" not in topology


def test_common_and_topology_start_independently_but_both_gate_summary() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    topology = _job_body(workflow, "topology_regression")
    summary = _job_body(workflow, "delivery_gate_summary")

    assert "needs: common_governance" not in topology
    assert "- common_governance" in summary
    assert "- topology_regression" in summary
    assert 'expect_success "common_governance"' in summary
    assert 'expect_success "topology_regression"' in summary
    assert '--dag-branch "common_governance${RELEASE_BRANCH_SUFFIX}"' in summary
    assert '--dag-branch "topology;' in summary
    assert 'RELEASE_BRANCH_SUFFIX=";release_evidence"' in summary
    assert '--dag-layer "release_evidence"' not in summary


def test_data_jobs_are_unconditional_complete_delivery_closure() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    data = _job_body(workflow, "quwoquan_data")
    shards = _job_body(workflow, "quwoquan_data_tests")

    data_if = "if: ${{ needs.topology_regression.outputs.data == 'true' }}"
    assert data_if not in data
    assert data_if not in shards
    assert "GATE_DATA_PHASE: verify" in data
    assert "GATE_DATA_PHASE: local_contract" in shards
    assert 'DATA_TEST_TOTAL_SHARDS: "4"' in shards
    assert "shard_index: [0, 1, 2, 3]" in shards
    assert 'if [[ "$DATA_IMPACTED" == "true" ]]; then' not in workflow
    assert '--local-required data' in workflow
    assert '--local-required data_tests' in workflow
    assert '--require-count "data=1"' in workflow
    assert '--require-count "data_tests=4"' in workflow
    assert 'FANOUT=(data data_tests)' in workflow
    assert 'expect_success "quwoquan_data" "${DATA}"' in workflow
    assert 'expect_success "quwoquan_data_tests" "${DATA_TESTS}"' in workflow
    assert 'expect_typed_pending_or_skipped "quwoquan_data"' not in workflow
    assert 'expect_typed_pending_or_skipped "quwoquan_data_tests"' not in workflow


def test_pull_request_reruns_service_closure_and_defers_app_to_push_evidence() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    pr_exclusion = "github.event_name != 'pull_request'"

    # G1：service impacted 的 exact merge candidate 必须在 PR merge ref 上重跑
    # Service closure，required scope 不得以 skipped 计绿。
    service_if = "if: ${{ needs.topology_regression.outputs.service == 'true' }}"
    for job_name in ("quwoquan_service", "quwoquan_service_packaging"):
        body = _job_body(workflow, job_name)
        assert pr_exclusion not in body
        assert service_if in body
    coverage_body = _job_body(workflow, "quwoquan_service_coverage")
    assert pr_exclusion not in coverage_body
    assert "outputs.coverage_service == 'true'" in coverage_body
    for job_name in (
        "quwoquan_service",
        "quwoquan_service_packaging",
        "quwoquan_service_coverage",
    ):
        assert f'expect_typed_pending_or_skipped "{job_name}"' in workflow
    assert 'SERVICE_IMPACTED: ${{ needs.topology_regression.outputs.service }}' in workflow
    # App 重活由 lane/dev1.0 push 生产 exact head 证据，PR 上由 quwoquan_app 核验
    # push 证据（缺失即 GATE_BLOCK），不重跑也不以 skipped 计绿。
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


def test_delivery_gate_fetches_history_for_frozen_knowledge_assets() -> None:
    jobs = _workflow_jobs()
    expected_repository_gate_jobs = {
        "quwoquan_service",
        "quwoquan_service_packaging",
        "quwoquan_service_coverage",
        "quwoquan_app_static",
        "quwoquan_app_tests",
        "quwoquan_app_serial",
        "quwoquan_app_coverage",
        "quwoquan_data",
        "quwoquan_data_tests",
        "ops_portal",
    }
    repository_gate_jobs = {
        job_name: job
        for job_name, job in jobs.items()
        if any(
            "bash quwoquan_ops/gate/gate_repo.sh" in str(step.get("run", ""))
            for step in job.get("steps", [])
        )
    }

    assert set(repository_gate_jobs) == expected_repository_gate_jobs
    for job_name, job in repository_gate_jobs.items():
        checkouts = [
            step
            for step in job.get("steps", [])
            if str(step.get("uses", "")).startswith("actions/checkout@")
        ]
        assert len(checkouts) == 1, job_name
        # gate_repo 的全局前置检查会从冻结提交读取 S0 knowledge assets；浅克隆
        # 无法执行 `git show <frozen_sha>:<path>`，会让所有 scope 共因失败。
        assert (checkouts[0].get("with") or {}).get("fetch-depth") == 0, (
            f"{job_name} 必须检出完整历史，供 frozen knowledge assets 校验读取"
        )


def test_hosted_gate_jobs_prepare_tesseract_before_repository_gate() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )
    expected = (
        "quwoquan_app_static",
        "quwoquan_app_tests",
        "quwoquan_data",
        "quwoquan_data_tests",
        "ops_portal",
    )
    install = "bash quwoquan_ops/ci/run_bounded_apt_install.sh tesseract-ocr"
    for job_name in expected:
        job = _job_body(workflow, job_name)
        assert job.count(install) == 1, job_name
        assert job.index(install) < job.index("bash quwoquan_ops/gate/gate_repo.sh")

    app_tests = _job_body(workflow, "quwoquan_app_tests")
    install_step = app_tests[
        app_tests.index("Install repository test native dependencies") :
        app_tests.index("Gate (quwoquan_app tests shard)")
    ]
    assert "matrix.shard_index" not in install_step


def test_hosted_non_app_repository_gates_prepare_pinned_dart_for_codegen_checks() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )
    for job_name in ("quwoquan_data", "quwoquan_data_tests", "ops_portal"):
        job = _job_body(workflow, job_name)
        assert job.count("Resolve repository-pinned Flutter SDK for repository gate") == 1, job_name
        assert job.count("Install verified Flutter SDK for repository gate") == 1, job_name
        assert job.index("python3 quwoquan_ops/ci/setup_flutter_sdk.py install") < job.index(
            "bash quwoquan_ops/gate/gate_repo.sh"
        ), job_name


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


def test_delivery_uses_literal_absolute_output_root_for_flutter_identity() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )

    assert "QWQ_OUTPUT_ROOT: ${{ github.workspace }}/.qwq_output" in workflow
    assert "QWQ_OUTPUT_ROOT: .qwq_output" not in workflow


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
    assert "run_bounded_apt_install.sh" not in packaging
    prepare_index = packaging.index("id: strict_inputs")
    gate_index = packaging.index("Gate (quwoquan_service packaging)")
    assert prepare_index < gate_index
    assert "actions/setup-java@c1e323688fd81a25caa38c78aa6df2d33d3e20d9" in packaging
    assert "quwoquan_app/.flutter-version" in packaging
    assert "python3 quwoquan_ops/ci/setup_flutter_sdk.py resolve" in packaging
    assert "python3 quwoquan_ops/ci/setup_flutter_sdk.py install" in packaging
    assert "subosito/flutter-action@" not in packaging
    assert "prepare_app_pipeline_inputs.py" in packaging
    assert "--build-product-id android-nonprod-apk" in packaging
    assert '--environment "${{ matrix.packaging_env }}"' in packaging
    assert '--target "${{ matrix.packaging_env }}-local"' in packaging
    assert '--expected-source-git-sha "$EXPECTED_SOURCE"' in packaging
    assert (
        '--work-root "$RUNNER_TEMP/delivery-packaging-inputs-'
        '${{ github.run_id }}-${{ github.run_attempt }}-${{ matrix.packaging_env }}"'
        in packaging
    )
    assert (
        "QWQ_OUTPUT_ROOT: ${{ steps.strict_inputs.outputs.qwq_output_root }}"
        in packaging
    )
    assert (
        "QWQ_COCOAPODS_EXECUTABLE: "
        "${{ steps.strict_inputs.outputs.cocoapods_executable }}"
        in packaging
    )
    assert "app-dependency-sync/cache" not in packaging
    assert "ln -s" not in packaging
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
    assert '--require-count "service=1" --require-count "service_packaging=3"' in workflow
    assert 'if [[ "$SERVICE_COVERAGE_IMPACTED" == "true" ]]' in workflow
    assert '--require-count "service_coverage=1"' in workflow
    assert "--local-required service --local-required service_packaging" in workflow
    assert "ARGS+=(--local-required service_coverage)" in workflow
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
        pr_head_sha=base_sha,
        event_sha=head_sha,
    )
    assert pull_request.returncode == 0, pull_request.stderr
    pull_request_output = (tmp_path / "github-output").read_text(encoding="utf-8")
    assert f"candidate_sha={head_sha}" in pull_request_output
    assert f"candidate_sha={base_sha}" not in pull_request_output

    push = _run_delivery_change_range(
        tmp_path,
        event_name="push",
        push_before_sha=base_sha,
        event_sha=head_sha,
    )
    assert push.returncode == 0, push.stderr

    for invalid_before, ref_name in (("", ""), ("0" * 40, ""), ("0" * 40, "dev1.0")):
        blocked_push = _run_delivery_change_range(
            tmp_path,
            event_name="push",
            push_before_sha=invalid_before,
            push_ref_name=ref_name,
            event_sha=head_sha,
        )
        assert blocked_push.returncode == 2
        assert "push requires an exact non-zero before SHA" in blocked_push.stdout

    # lane 分支首推没有旧 tip；变更区间必须锚定到 dev1.0 merge-base 而不是放弃 exact。
    lane_bootstrap = _run_delivery_change_range(
        tmp_path,
        event_name="push",
        push_before_sha="0" * 40,
        push_ref_name="lane/small-fix",
        event_sha=head_sha,
    )
    assert lane_bootstrap.returncode == 0, lane_bootstrap.stdout + lane_bootstrap.stderr
    expected_lane_base = subprocess.run(
        ("git", "merge-base", "origin/dev1.0", head_sha),
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()
    lane_output = (tmp_path / "github-output").read_text(encoding="utf-8")
    assert f"base_sha={expected_lane_base}" in lane_output
    assert f"candidate_sha={head_sha}" in lane_output


def test_pull_request_jobs_checkout_and_diff_the_exact_merge_candidate() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")

    exact_checkout = "${{ inputs.checkout_ref || github.sha }}"
    # pull_request 的 github.sha 是 GitHub synthetic merge candidate；PR head
    # 只允许用于核验 lane push-owned App evidence。
    document = yaml.safe_load(workflow)
    checkouts = [
        (job_name, (step.get("with") or {}).get("ref"))
        for job_name, job in document["jobs"].items()
        for step in job.get("steps") or []
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert checkouts, "Delivery Gate 必须有 checkout 步骤"
    drifted = [job_name for job_name, ref in checkouts if ref != exact_checkout]
    assert not drifted, f"这些 job 的 checkout 没钉到事件 merge candidate：{drifted}"
    assert "PR_BASE_SHA: ${{ github.event.pull_request.base.sha || '' }}" in workflow
    assert 'REQUESTED_CANDIDATE_SHA="$DISPATCH_SHA"' in workflow
    assert "PUSH_BEFORE_SHA: ${{ github.event.before || '' }}" in workflow
    assert "HEAD_SHA: ${{ inputs.head_sha || github.sha }}" in workflow
    assert (
        '--source-git-sha "${{ inputs.source_git_sha || github.sha }}"'
    ) in workflow
    assert workflow.count("github.event.pull_request.head.sha") == 1
    assert "verify-delivery-app-evidence" in workflow


def test_delivery_and_promotion_gates_defer_edges_to_canonical_evaluator() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    pre_release = (ROOT / ".github/workflows/pre-release-gate.yml").read_text(encoding="utf-8")
    app_matrix = (
        ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml"
    ).read_text(encoding="utf-8")
    policy = (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_text(encoding="utf-8")

    assert "pull_request:\n    branches:" not in workflow
    assert "pull_request:\n    branches:" not in pre_release
    assert "\n  push:\n    branches: [dev1.0, 'lane/**']\n" in workflow
    assert "\n  push:\n    branches: [dev1.0]\n" in pre_release
    assert "\n  push:\n    branches: [dev1.0]\n" in app_matrix
    assert "PR_BASE_SHA: ${{ github.event.pull_request.base.sha || '' }}" in workflow
    assert "PUSH_BEFORE_SHA: ${{ github.event.before || '' }}" in workflow

    # Delivery 与设备矩阵仍拥有各自 required check 的 canonical admission。
    for source in (workflow, app_matrix):
        assert "Enforce canonical repository branch admission" in source
        assert "python3 quwoquan_ops/gate/verify_git_branch_policy.py" in source
    assert "Admit direct dev1.0 integration push" not in app_matrix

    # pr_light 不重复 pre-push/上游的 branch-policy-only job；它保留自己独有的
    # changed-candidate 安全边界与 canonical impact plan。
    assert "Enforce canonical repository branch admission" not in pre_release
    assert "verify_git_branch_policy.py" not in pre_release
    assert "Pre-Release — Branch Policy" not in pre_release
    assert "Pre-Release — PR Light Governance" in pre_release
    assert "Verify changed secret, PII and generated boundaries" in pre_release
    assert "Generate canonical PR-light impact plan" in pre_release
    assert "--validate-impact-plan" in pre_release
    assert "Verify fast CI governance contracts" not in pre_release
    for duplicate in (
        "test_detect_ci_impacted_scopes__local_contract_test.py",
        "test_github_actions_timing__local_contract_test.py",
        "test_ci_timing_summary__canonical__local_contract_test.py",
    ):
        assert duplicate not in pre_release

    # promotion 合法边没有丢失：single authority policy 仍声明 dev1.0 -> main，
    # 并把三条 required check 绑定到各自 workflow；pr_light 只不重复执行 evaluator。
    assert "- head: dev1.0\n    base: main" in policy
    assert "name: 03. Delivery Gate" in policy
    assert "workflow: .github/workflows/delivery-gate.yml" in policy
    assert "name: 04. Pre-Release Gate" in policy
    assert "workflow: .github/workflows/pre-release-gate.yml" in policy
    assert "name: 05. App Env Device Matrix" in policy
    assert "workflow: .github/workflows/app-env-device-matrix-self-hosted.yml" in policy


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

    assert "Install repository test native dependencies" in job
    assert "if: ${{ matrix.shard_index == 0 }}" not in job
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
        "max(common_governance, topology_regression + "
        "max(quwoquan_service, quwoquan_service_packaging, "
        "quwoquan_service_coverage, search_contract_smoke, "
        "quwoquan_app_static, quwoquan_app_tests, quwoquan_app_serial, "
        "quwoquan_app_coverage, quwoquan_data, quwoquan_data_tests, "
        "ops_portal)); Data verify and all Data test shards run on every Delivery; "
        "pull_request "
        "sources quwoquan_app_* from verified push evidence while calendar "
        "still ends at its own verifier completion; produce_release_evidence "
        "appends release_evidence after both parallel branches converge"
    )
    assert delivery["timingPolicy"] == "telemetry_advisory"
    assert set(delivery["phaseBudgetsSeconds"]) >= {
        "quwoquan_app_static",
        "quwoquan_app_tests",
        "quwoquan_app_serial",
        "quwoquan_app_coverage",
    }
