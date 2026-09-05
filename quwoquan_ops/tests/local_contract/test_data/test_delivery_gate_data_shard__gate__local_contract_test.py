# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-024.t5
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-024.t6
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-024.t7
"""data `local_contract` 段进入 Delivery Gate 的本地契约。

在此之前 Delivery Gate 的 data 段只跑 `cli.py verify all` 的静态门，519 个
`local_contract` 测试在 CI 零覆盖；commit gate 则按影响面选一部分，两套判据谁都不
覆盖全域。纳入的做法是分片，而分片本身有三条会让「全绿」变成假象的失效方式，本
测试逐条钉住：

1. **分片漏测试**：写死的分片清单外的新文件落在所有片之外，每片都判它不属于自己，
   于是四片全绿而它一次没跑。摘要取模让每个文件必然落进恰好一片。
2. **分片不进阻断链**：分片 job 存在但不被聚合 job 依赖或不被 `expect_success`
   检查时，红片不会阻断 Delivery Gate。
3. **片数两处漂移**：job matrix 的片数与传给 gate 的 `DATA_TEST_TOTAL_SHARDS`、
   以及 timing 的 `--require-count` 是三处独立字面量，任一处改了另两处不会被发现。

commit gate 一侧钉的是另一件事：它的 15 分钟硬顶跑不完 21 分钟的全量，横切实现面
的影响面就是全域，因此必须显式登记 deferred，而不是选 80 条冒充覆盖。
"""

from __future__ import annotations

import copy
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import commit_gate_select as cgs
from quwoquan_ops.gate import delivery_gate_data_shard as shard
from quwoquan_ops.gate.local_dependency_purity.shell_commands import (
    ShellCommandParseError,
    reachable_shell_array_tokens,
    reachable_shell_command_tokens,
)
from quwoquan_ops.tests.support.delivery_gate_data_trigger_support import (
    DATA_TESTS_JOB,
    DATA_TRIGGER_SCOPE,
    assert_data_jobs_trigger_scoped,
    assert_summary_contract,
    run_summary,
)

SHARD_CLI = ROOT / "quwoquan_ops" / "gate" / "delivery_gate_data_shard.py"
GATE_REPO = ROOT / "quwoquan_ops" / "gate" / "gate_repo.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "delivery-gate.yml"
EXPECTED_SHARD_INDICES = (0, 1, 2, 3)
EXPECTED_SHARD_ENVIRONMENT = {
    "GATE_DATA_PHASE": "local_contract",
    "DATA_TEST_TOTAL_SHARDS": str(len(EXPECTED_SHARD_INDICES)),
    "DATA_TEST_SHARD_INDEX": "${{ matrix.shard_index }}",
}


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def data_tests_job(workflow: dict) -> dict:
    jobs = workflow["jobs"]
    assert DATA_TESTS_JOB in jobs, (
        "Delivery Gate 缺 data local_contract 分片 job——data 段回到只跑静态门的整体排除态"
    )
    return jobs[DATA_TESTS_JOB]


@pytest.fixture(scope="module")
def declared_shard_indices(data_tests_job: dict) -> tuple[int, ...]:
    return _declared_shard_indices(data_tests_job)


@pytest.fixture(scope="module")
def declared_shard_total(declared_shard_indices: tuple[int, ...]) -> int:
    return len(declared_shard_indices)


def _declared_shard_indices(job: dict) -> tuple[int, ...]:
    raw_indices = job["strategy"]["matrix"]["shard_index"]
    assert isinstance(raw_indices, list) and raw_indices, (
        "data local_contract matrix 必须声明非空 shard_index 列表"
    )
    assert all(type(index) is int for index in raw_indices), (
        "data local_contract matrix shard_index 必须是整数，bool/string 不得替代"
    )
    expected = list(EXPECTED_SHARD_INDICES)
    assert raw_indices == expected and len(set(raw_indices)) == len(raw_indices), (
        "data local_contract matrix shard_index 必须精确等于 canonical 四片"
    )
    return tuple(raw_indices)


def _shard_step(job: dict, *, shard_total: int) -> dict:
    assert job.get("continue-on-error") in (None, False), (
        "data local_contract job 不得吞掉分片失败"
    )
    assert job["strategy"] == {
        "fail-fast": False,
        "matrix": {"shard_index": list(EXPECTED_SHARD_INDICES)},
    }, "data local_contract strategy 必须精确绑定 canonical 四片 matrix"
    steps = [
        step
        for step in job["steps"]
        if step.get("env", {}).get("GATE_DATA_PHASE") == "local_contract"
    ]
    assert len(steps) == 1, "分片 job 必须有且只有一个 local_contract phase 步骤"
    step = steps[0]
    assert set(step) == {"name", "env", "run"}, (
        "data local_contract step 只允许 name/env/run，禁止 if/shell/continue-on-error 绕过"
    )
    assert type(step.get("run")) is str and step["run"] == (
        "bash quwoquan_ops/gate/gate_repo.sh --scope data"
    ), "data local_contract step 必须精确调用 canonical gate_repo data scope"
    environment = step["env"]
    assert shard_total == len(EXPECTED_SHARD_INDICES)
    assert environment == EXPECTED_SHARD_ENVIRONMENT, (
        "data local_contract env 必须精确绑定 phase/total/index，禁止测试选择污染"
    )
    return step


def _assert_executable_command(run: str, expected_prefix: tuple[str, ...]) -> None:
    matches = reachable_shell_command_tokens(run, command_prefix=expected_prefix)
    assert len(matches) == 1, (
        f"workflow 必须真实执行 {' '.join(expected_prefix)}，注释/heredoc/未调用函数不算"
    )


def _assert_token_sequence(tokens: tuple[str, ...], expected: tuple[str, ...]) -> None:
    assert any(
        tokens[index : index + len(expected)] == expected
        for index in range(len(tokens) - len(expected) + 1)
    ), f"workflow canonical ARGS 缺 {' '.join(expected)}"


def _run_shard_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SHARD_CLI), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )


def _run_gate_repo(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(GATE_REPO), "--scope", "data"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(ROOT), **env},
    )


def _gate_shell_function(name: str) -> str:
    lines = GATE_REPO.read_text(encoding="utf-8").splitlines()
    start = lines.index(f"{name}() {{")
    end = next(index for index in range(start + 1, len(lines)) if lines[index] == "}")
    return "\n".join(lines[start : end + 1])


def _run_data_phase_validation(
    *, scope: str, phase: str, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    script = (
        "set -u\n"
        f"scope={shlex.quote(scope)}\n"
        f"data_phase={shlex.quote(phase)}\n"
        f"{_gate_shell_function('validate_data_phase_configuration')}\n"
        "validate_data_phase_configuration\n"
    )
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", **env},
    )


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_partial_selector_stdout_with_nonzero_status_never_reaches_pytest(
    tmp_path: Path,
    cleanup_fails: bool,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    cleanup_stub = "rm() { return 23; }" if cleanup_fails else ""
    script = (
        "set -euo pipefail\n"
        f"ROOT={shlex.quote(str(repository))}\n"
        "python3() {\n"
        '  if [[ "$*" == *delivery_gate_data_shard.py* ]]; then\n'
        "    printf '%s\\n' 'quwoquan_data/tests/local_contract/partial_test.py'\n"
        "    return 17\n"
        "  fi\n"
        "  printf 'unexpected pytest execution\\n' >&2\n"
        "  return 99\n"
        "}\n"
        f"{cleanup_stub}\n"
        f"{_gate_shell_function('run_data_local_contract')}\n"
        "run_data_local_contract\n"
    )

    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )

    assert result.returncode == 17, result.stdout + result.stderr
    assert "data shard selector failed (exit=17)" in result.stderr
    assert "data local_contract files=" not in result.stdout
    assert "unexpected pytest execution" not in result.stderr
    managed = (
        repository / ".qwq_output/env/repo/local/repo-gate/process/data-shard-selector"
    )
    if cleanup_fails:
        assert "preserving selector exit=17" in result.stderr
        assert list(managed.iterdir())
    else:
        assert list(managed.iterdir()) == []


def test_every_test_file_lands_in_exactly_one_shard(
    declared_shard_indices: tuple[int, ...],
) -> None:
    full = shard.local_contract_test_files(ROOT)
    assert full, "data local_contract 测试全集不应为空"

    shard_total = len(declared_shard_indices)
    shards = [
        shard.sharded_test_files(ROOT, shard_total, index)
        for index in declared_shard_indices
    ]
    union: list[str] = []
    for selected in shards:
        union.extend(selected)

    assert sorted(union) == full, "四片并集必须等于全集"
    assert len(union) == len(set(union)), "同一文件不得出现在两片里"


def test_shard_membership_is_stable_across_calls(
    declared_shard_indices: tuple[int, ...],
) -> None:
    shard_total = len(declared_shard_indices)
    selected_index = declared_shard_indices[0]
    first = shard.sharded_test_files(ROOT, shard_total, selected_index)
    second = shard.sharded_test_files(ROOT, shard_total, selected_index)
    assert first == second


def test_a_test_file_added_later_still_lands_in_a_shard(
    declared_shard_indices: tuple[int, ...],
) -> None:
    # 分片判据只读路径，因此这里不必真建文件：新文件的落片结果与它是否在磁盘上无关。
    newcomer = (
        "quwoquan_data/tests/local_contract/execution/"
        "test_not_yet_written__contract__local_contract_test.py"
    )
    shard_total = len(declared_shard_indices)
    assert shard.shard_of(newcomer, shard_total) in declared_shard_indices


def test_single_shard_selects_the_whole_set() -> None:
    assert shard.sharded_test_files(ROOT, 1, 0) == shard.local_contract_test_files(ROOT)


def test_shard_discovery_covers_every_test_file_on_disk() -> None:
    on_disk = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "quwoquan_data" / "tests" / "local_contract").rglob("*.py")
    )
    assert shard.local_contract_test_files(ROOT) == on_disk, (
        "发现面与磁盘上的 .py 不一致——命名不符合 *_local_contract_test.py 的测试会被静默跳过"
    )


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        (("--total-shards", "0"), "--total-shards 必须 >= 1"),
        (("--total-shards", "4", "--shard-index", "4"), "--shard-index 必须落在"),
        (("--total-shards", "4", "--shard-index", "-1"), "--shard-index 必须落在"),
        (("--total-shards", "100000", "--shard-index", "99999"), "为空"),
    ],
)
def test_out_of_range_sharding_is_refused(args: tuple[str, ...], reason: str) -> None:
    result = _run_shard_cli(*args)
    assert result.returncode == 2, result.stdout
    assert reason in result.stderr


def test_data_phase_is_a_closed_set_scoped_to_the_data_gate() -> None:
    bogus = _run_gate_repo({"GATE_DATA_PHASE": "bogus"})
    assert bogus.returncode == 2
    assert "invalid GATE_DATA_PHASE=bogus" in bogus.stdout + bogus.stderr

    mismatched = subprocess.run(
        ["bash", str(GATE_REPO), "--scope", "app"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
        env={
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(ROOT),
            "GATE_DATA_PHASE": "verify",
        },
    )
    assert mismatched.returncode == 2
    assert "only valid with --scope data" in mismatched.stdout + mismatched.stderr


@pytest.mark.parametrize(
    "env",
    [
        {"DATA_TEST_TOTAL_SHARDS": "4"},
        {"DATA_TEST_SHARD_INDEX": "0"},
    ],
)
def test_half_declared_sharding_is_refused(env: dict[str, str]) -> None:
    result = _run_gate_repo({"GATE_DATA_PHASE": "local_contract", **env})
    assert result.returncode == 2
    assert "must be provided together" in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("scope", "phase"),
    (("all", "all"), ("app", "all"), ("data", "verify"), ("data", "all")),
)
def test_shard_environment_is_only_valid_for_data_local_contract(
    scope: str,
    phase: str,
) -> None:
    result = _run_data_phase_validation(
        scope=scope,
        phase=phase,
        env={"DATA_TEST_TOTAL_SHARDS": "4", "DATA_TEST_SHARD_INDEX": "0"},
    )

    assert result.returncode == 2
    assert "only valid with --scope data and GATE_DATA_PHASE=local_contract" in (
        result.stdout + result.stderr
    )


def test_unsharded_aggregate_data_configuration_remains_valid() -> None:
    result = _run_data_phase_validation(scope="all", phase="all", env={})
    assert result.returncode == 0, result.stdout + result.stderr


def test_delivery_gate_runs_the_declared_shard_count(
    data_tests_job: dict,
    declared_shard_indices: tuple[int, ...],
) -> None:
    shard_total = len(declared_shard_indices)
    _shard_step(data_tests_job, shard_total=shard_total)
    assert data_tests_job.get("if") == DATA_TRIGGER_SCOPE
    assert data_tests_job["strategy"]["fail-fast"] is False


def test_duplicate_or_noncontinuous_matrix_indices_are_rejected(
    data_tests_job: dict,
) -> None:
    mutated = copy.deepcopy(data_tests_job)
    mutated["strategy"]["matrix"]["shard_index"] = [0, 0, 2, 3]

    with pytest.raises(AssertionError, match="精确等于 canonical 四片"):
        _declared_shard_indices(mutated)


def test_single_shard_matrix_cannot_redefine_the_canonical_total(
    data_tests_job: dict,
) -> None:
    mutated = copy.deepcopy(data_tests_job)
    mutated["strategy"]["matrix"]["shard_index"] = [0]

    with pytest.raises(AssertionError, match="精确等于 canonical 四片"):
        _declared_shard_indices(mutated)


def test_boolean_run_cannot_impersonate_the_canonical_gate_command(
    data_tests_job: dict,
    declared_shard_total: int,
) -> None:
    mutated = copy.deepcopy(data_tests_job)
    step = next(
        candidate
        for candidate in mutated["steps"]
        if candidate.get("env", {}).get("GATE_DATA_PHASE") == "local_contract"
    )
    step["run"] = yaml.safe_load("run: true")["run"]

    with pytest.raises(AssertionError, match="精确调用 canonical gate_repo"):
        _shard_step(mutated, shard_total=declared_shard_total)


@pytest.mark.parametrize(
    ("location", "key", "value"),
    (
        ("job", "continue-on-error", True),
        ("step", "if", "false"),
        ("step", "continue-on-error", True),
        ("step", "shell", "bash {0}"),
    ),
)
def test_shard_job_rejects_execution_bypass_controls(
    data_tests_job: dict,
    declared_shard_total: int,
    location: str,
    key: str,
    value: object,
) -> None:
    mutated = copy.deepcopy(data_tests_job)
    if location == "job":
        mutated[key] = value
    else:
        step = next(
            candidate
            for candidate in mutated["steps"]
            if candidate.get("env", {}).get("GATE_DATA_PHASE") == "local_contract"
        )
        step[key] = value

    with pytest.raises(AssertionError):
        _shard_step(mutated, shard_total=declared_shard_total)


def test_shard_step_rejects_test_selection_environment_pollution(
    data_tests_job: dict,
    declared_shard_total: int,
) -> None:
    mutated = copy.deepcopy(data_tests_job)
    step = next(
        candidate
        for candidate in mutated["steps"]
        if candidate.get("env", {}).get("GATE_DATA_PHASE") == "local_contract"
    )
    step["env"]["PYTEST_ADDOPTS"] = "--ignore=quwoquan_data/tests/local_contract"

    with pytest.raises(AssertionError, match="测试选择污染"):
        _shard_step(mutated, shard_total=declared_shard_total)


def test_data_static_gate_no_longer_carries_the_test_phase(workflow: dict) -> None:
    steps = workflow["jobs"]["quwoquan_data"]["steps"]
    phases = {
        step.get("env", {}).get("GATE_DATA_PHASE")
        for step in steps
        if "GATE_DATA_PHASE" in step.get("env", {})
    }
    assert phases == {"verify"}, (
        "静态门 job 必须只跑 verify phase；跑 all 会让同一批测试在两个 job 里重复执行"
    )


def test_a_red_shard_blocks_the_delivery_gate(workflow: dict) -> None:
    summary = workflow["jobs"]["delivery_gate_summary"]
    assert DATA_TESTS_JOB in summary["needs"]

    block_steps = [
        step
        for step in summary["steps"]
        if "DATA_TESTS" in step.get("env", {})
        and f"needs.{DATA_TESTS_JOB}.result" in str(step["env"]["DATA_TESTS"])
    ]
    assert block_steps, "汇总步骤必须读取分片 job 的结果"
    red_shard = run_summary(summary, event_name="pull_request", data_tests="failure", repo_root=ROOT)
    assert red_shard.returncode == 1
    assert "quwoquan_data_tests expected success, got failure" in red_shard.stdout


@pytest.mark.parametrize("produce_release_evidence", (False, True))
def test_pr_release_always_require_data_producers_and_consumers(
    workflow: dict,
    produce_release_evidence: bool,
) -> None:
    data_impacted = False
    assert data_impacted is False
    assert_data_jobs_trigger_scoped(workflow)
    assert_summary_contract(workflow["jobs"]["delivery_gate_summary"], repo_root=ROOT)
    if produce_release_evidence:
        evidence = workflow["jobs"]["release_evidence"]
        assert DATA_TESTS_JOB in evidence["needs"]
        aggregate = next(
            step
            for step in evidence["steps"]
            if step.get("name") == "Aggregate exact three-layer test results"
        )
        arguments = reachable_shell_array_tokens(
            aggregate["run"],
            array_name="ARGS",
            consumer_prefix=(
                "python3",
                "quwoquan_ops/ci/render_delivery_release_evidence.py",
            ),
        )
        _assert_token_sequence(arguments, ("--local-required", "data"))
        _assert_token_sequence(arguments, ("--local-required", "data_tests"))


@pytest.mark.parametrize("decoy_kind", ("comment", "heredoc"))
def test_summary_rejects_non_executable_shard_blocker_text(
    workflow: dict,
    decoy_kind: str,
) -> None:
    summary = workflow["jobs"]["delivery_gate_summary"]
    step = next(
        candidate
        for candidate in summary["steps"]
        if "DATA_TESTS" in candidate.get("env", {})
    )
    executable = (
        'expect_success "quwoquan_data_tests" "${DATA_TESTS}" '
        '"PR/release Delivery 必须执行 Data tests"'
    )
    replacement = (
        f"# {executable}"
        if decoy_kind == "comment"
        else f"cat <<'DATA_TESTS_DECOY'\n{executable}\nDATA_TESTS_DECOY"
    )
    mutated = step["run"].replace(executable, replacement, 1)

    with pytest.raises(AssertionError, match="必须真实执行"):
        _assert_executable_command(
            mutated,
            ("expect_success", DATA_TESTS_JOB, "${DATA_TESTS}"),
        )


def test_summary_shard_blocker_is_bound_to_trigger_aware_workflow_step(
    workflow: dict,
) -> None:
    summary = workflow["jobs"]["delivery_gate_summary"]
    assert_summary_contract(summary, repo_root=ROOT)


@pytest.mark.parametrize(
    ("location", "key", "value"),
    (
        ("job", "if", "false"),
        ("job", "continue-on-error", True),
        ("step", "if", "false"),
        ("step", "continue-on-error", True),
        ("env", "DATA_TESTS", "success"),
    ),
)
def test_summary_shard_blocker_rejects_workflow_bypass_mutations(
    workflow: dict,
    location: str,
    key: str,
    value: object,
) -> None:
    summary = copy.deepcopy(workflow["jobs"]["delivery_gate_summary"])
    step = next(
        candidate
        for candidate in summary["steps"]
        if "DATA_TESTS" in candidate.get("env", {})
    )
    target = (
        summary if location == "job" else step["env"] if location == "env" else step
    )
    target[key] = value

    with pytest.raises(AssertionError):
        assert_summary_contract(summary, repo_root=ROOT)


@pytest.mark.parametrize(
    "replacement",
    (
        'unused() { expect_success "quwoquan_data_tests" "${DATA_TESTS}"; }',
        'exit 0\nexpect_success "quwoquan_data_tests" "${DATA_TESTS}"',
        'false && expect_success "quwoquan_data_tests" "${DATA_TESTS}"',
        'true || expect_success "quwoquan_data_tests" "${DATA_TESTS}"',
        '(expect_success "quwoquan_data_tests" "${DATA_TESTS}")',
        'expect_success "quwoquan_data_tests" "${DATA_TESTS}" | tee /tmp/result',
        'expect_success "quwoquan_data_tests" "${DATA_TESTS}" & wait',
    ),
)
def test_summary_rejects_unreachable_shard_blocker_command(
    workflow: dict,
    replacement: str,
) -> None:
    summary = copy.deepcopy(workflow["jobs"]["delivery_gate_summary"])
    step = next(
        candidate
        for candidate in summary["steps"]
        if "DATA_TESTS" in candidate.get("env", {})
    )
    executable = (
        'expect_success "quwoquan_data_tests" "${DATA_TESTS}" '
        '"PR/release Delivery 必须执行 Data tests"'
    )
    step["run"] = step["run"].replace(executable, replacement, 1)

    with pytest.raises(AssertionError):
        assert_summary_contract(summary, repo_root=ROOT)


def test_summary_rejects_blocker_after_guaranteed_static_exit(workflow: dict) -> None:
    summary = copy.deepcopy(workflow["jobs"]["delivery_gate_summary"])
    step = next(
        candidate
        for candidate in summary["steps"]
        if "DATA_TESTS" in candidate.get("env", {})
    )
    executable = (
        'expect_success "quwoquan_data_tests" "${DATA_TESTS}" '
        '"PR/release Delivery 必须执行 Data tests"'
    )
    step["run"] = step["run"].replace(
        executable,
        "if true; then exit 0; fi\n" + executable,
        1,
    )

    with pytest.raises(AssertionError):
        assert_summary_contract(summary, repo_root=ROOT)


@pytest.mark.parametrize(
    "mutation",
    (
        "subshell",
        "control",
        "terminal",
        "short_circuit_and",
        "short_circuit_or",
    ),
)
def test_timing_rejects_nonpersistent_or_unreachable_array_write(
    workflow: dict,
    mutation: str,
) -> None:
    timing = next(
        step
        for step in workflow["jobs"]["delivery_gate_summary"]["steps"]
        if step.get("id") == "job_timing"
    )
    required_line = '  --require-count "data_tests=4"\n'
    write = 'ARGS+=(--require-count "data_tests=4")'
    replacements = {
        "subshell": f"({write})",
        "control": f"if true; then {write}; fi",
        "terminal": f"exit 0\n{write}",
        "short_circuit_and": f"false && {write}",
        "short_circuit_or": f"true || {write}",
    }
    mutated = (
        timing["run"]
        .replace(required_line, "", 1)
        .replace(
            'python3 quwoquan_ops/ci/github_actions_timing.py "${ARGS[@]}"',
            replacements[mutation]
            + '\npython3 quwoquan_ops/ci/github_actions_timing.py "${ARGS[@]}"',
            1,
        )
    )

    if mutation == "terminal":
        with pytest.raises(ShellCommandParseError):
            reachable_shell_array_tokens(
                mutated,
                array_name="ARGS",
                consumer_prefix=(
                    "python3",
                    "quwoquan_ops/ci/github_actions_timing.py",
                ),
            )
        return
    arguments = reachable_shell_array_tokens(
        mutated,
        array_name="ARGS",
        consumer_prefix=("python3", "quwoquan_ops/ci/github_actions_timing.py"),
    )
    assert "data_tests=4" not in arguments


def test_false_or_static_array_write_is_reachable_and_persistent(
    workflow: dict,
) -> None:
    timing = next(
        step
        for step in workflow["jobs"]["delivery_gate_summary"]["steps"]
        if step.get("id") == "job_timing"
    )
    mutated = (
        timing["run"]
        .replace('  --require-count "data_tests=4"\n', "", 1)
        .replace(
            'python3 quwoquan_ops/ci/github_actions_timing.py "${ARGS[@]}"',
            'false || ARGS+=(--require-count "data_tests=4")\n'
            'python3 quwoquan_ops/ci/github_actions_timing.py "${ARGS[@]}"',
            1,
        )
    )

    arguments = reachable_shell_array_tokens(
        mutated,
        array_name="ARGS",
        consumer_prefix=("python3", "quwoquan_ops/ci/github_actions_timing.py"),
    )

    _assert_token_sequence(arguments, ("--require-count", "data_tests=4"))


def test_summary_rejects_shell_override(workflow: dict) -> None:
    summary = copy.deepcopy(workflow["jobs"]["delivery_gate_summary"])
    step = next(
        candidate
        for candidate in summary["steps"]
        if "DATA_TESTS" in candidate.get("env", {})
    )
    step["shell"] = "bash --noprofile --norc -o errexit {0}"

    with pytest.raises(AssertionError):
        assert_summary_contract(summary, repo_root=ROOT)


def test_required_shard_count_matches_the_matrix(
    workflow: dict, declared_shard_total: int
) -> None:
    summary = workflow["jobs"]["delivery_gate_summary"]
    timing = [step for step in summary["steps"] if step.get("id") == "job_timing"]
    assert timing, "汇总 job 必须有 job_timing 步骤"
    run = timing[0]["run"]
    arguments = reachable_shell_array_tokens(
        run,
        array_name="ARGS",
        consumer_prefix=("python3", "quwoquan_ops/ci/github_actions_timing.py"),
    )
    expected = (
        'if [[ "$RELEASE_CALL" == "true" || "$EVENT_NAME" != push ]]; then\n'
        f'  ARGS+=(--require-count "data=1" --require-count "data_tests={declared_shard_total}")\n'
        '  FANOUT+=(data data_tests)\n'
        'fi'
    )
    assert run.count(expected) == 1, (
        "Data 四片计时必须只在 PR/release fanout 分支写入 canonical ARGS"
    )
    _assert_token_sequence(
        arguments, ("--phase-prefix", "data_tests=Delivery Gate — Data Tests Shard ")
    )


def test_timing_rejects_commented_required_shard_count(
    workflow: dict,
) -> None:
    timing = next(
        step
        for step in workflow["jobs"]["delivery_gate_summary"]["steps"]
        if step.get("id") == "job_timing"
    )
    mutated = timing["run"].replace(
        '  --require-count "data_tests=4"\n',
        '  # --require-count "data_tests=4"\n',
        1,
    )
    arguments = reachable_shell_array_tokens(
        mutated,
        array_name="ARGS",
        consumer_prefix=("python3", "quwoquan_ops/ci/github_actions_timing.py"),
    )

    with pytest.raises(AssertionError, match="canonical ARGS"):
        _assert_token_sequence(arguments, ("--require-count", "data_tests=4"))


def test_timing_rejects_required_shard_count_written_after_consumer(
    workflow: dict,
) -> None:
    timing = next(
        step
        for step in workflow["jobs"]["delivery_gate_summary"]["steps"]
        if step.get("id") == "job_timing"
    )
    mutated = (
        timing["run"]
        .replace(
            '  --require-count "data_tests=4"\n',
            "",
            1,
        )
        .replace(
            'python3 quwoquan_ops/ci/github_actions_timing.py "${ARGS[@]}"',
            'python3 quwoquan_ops/ci/github_actions_timing.py "${ARGS[@]}"\n'
            'ARGS+=(--require-count "data_tests=4")',
            1,
        )
    )
    arguments = reachable_shell_array_tokens(
        mutated,
        array_name="ARGS",
        consumer_prefix=("python3", "quwoquan_ops/ci/github_actions_timing.py"),
    )

    with pytest.raises(AssertionError, match="canonical ARGS"):
        _assert_token_sequence(arguments, ("--require-count", "data_tests=4"))


def test_release_evidence_requires_the_shards(workflow: dict) -> None:
    evidence = workflow["jobs"]["release_evidence"]
    assert DATA_TESTS_JOB in evidence["needs"]
    aggregate = [
        step
        for step in evidence["steps"]
        if step.get("name") == "Aggregate exact three-layer test results"
    ]
    assert aggregate, "候选证据 job 必须有三层测试聚合步骤"
    run = aggregate[0]["run"]
    arguments = reachable_shell_array_tokens(
        run,
        array_name="ARGS",
        consumer_prefix=(
            "python3",
            "quwoquan_ops/ci/render_delivery_release_evidence.py",
        ),
    )
    _assert_token_sequence(arguments, ("--job-result", "data_tests=$DATA_TESTS_RESULT"))
    _assert_token_sequence(arguments, ("--local-required", "data_tests"))


def test_release_evidence_rejects_heredoc_job_result_decoy(workflow: dict) -> None:
    evidence = workflow["jobs"]["release_evidence"]
    aggregate = next(
        step
        for step in evidence["steps"]
        if step.get("name") == "Aggregate exact three-layer test results"
    )
    mutated = aggregate["run"].replace(
        '  --job-result "data_tests=$DATA_TESTS_RESULT"\n',
        "cat <<'DATA_TESTS_RESULT_DECOY'\n"
        '  --job-result "data_tests=$DATA_TESTS_RESULT"\n'
        "DATA_TESTS_RESULT_DECOY\n",
        1,
    )
    arguments = reachable_shell_array_tokens(
        mutated,
        array_name="ARGS",
        consumer_prefix=(
            "python3",
            "quwoquan_ops/ci/render_delivery_release_evidence.py",
        ),
    )

    with pytest.raises(AssertionError, match="canonical ARGS"):
        _assert_token_sequence(
            arguments, ("--job-result", "data_tests=$DATA_TESTS_RESULT")
        )


def test_release_evidence_rejects_job_result_written_after_consumer(
    workflow: dict,
) -> None:
    evidence = workflow["jobs"]["release_evidence"]
    aggregate = next(
        step
        for step in evidence["steps"]
        if step.get("name") == "Aggregate exact three-layer test results"
    )
    consumer = (
        'python3 quwoquan_ops/ci/render_delivery_release_evidence.py "${ARGS[@]}"'
    )
    mutated = (
        aggregate["run"]
        .replace(
            '  --job-result "data_tests=$DATA_TESTS_RESULT"\n',
            "",
            1,
        )
        .replace(
            consumer,
            consumer + '\nARGS+=(--job-result "data_tests=$DATA_TESTS_RESULT")',
            1,
        )
    )
    arguments = reachable_shell_array_tokens(
        mutated,
        array_name="ARGS",
        consumer_prefix=(
            "python3",
            "quwoquan_ops/ci/render_delivery_release_evidence.py",
        ),
    )

    with pytest.raises(AssertionError, match="canonical ARGS"):
        _assert_token_sequence(
            arguments, ("--job-result", "data_tests=$DATA_TESTS_RESULT")
        )


def test_every_data_implementation_directory_is_reachable_from_commit_gate() -> None:
    scripts_root = ROOT / "quwoquan_data" / "scripts"
    implementation_dirs = sorted(
        path.relative_to(ROOT).as_posix() + "/"
        for path in list(scripts_root.iterdir())
        + list((scripts_root / "content").iterdir())
        if path.is_dir() and path.name != "__pycache__" and path.name != "content"
    )
    for directory in implementation_dirs:
        probe = directory + "probe.py"
        selected, deferred = cgs.select_pytest_paths([probe])
        assert selected or deferred, (
            f"{directory} 的改动既不选本地测试也不登记 deferred——这一面在两套门禁里都零覆盖"
        )


def test_crosscutting_data_changes_defer_the_whole_domain() -> None:
    for prefix in cgs.DATA_CROSSCUTTING_PREFIXES:
        probe = prefix if prefix.endswith(".py") else prefix + "probe.py"
        _, deferred = cgs.select_pytest_paths([probe])
        assert cgs.DATA_LOCAL_CONTRACT_ROOT in deferred, (
            f"{prefix} 的影响面是全域，必须显式交给 Delivery Gate 分片"
        )


@pytest.mark.parametrize("retired_owner", ("homepage", "post"))
def test_retired_content_owner_paths_have_no_stale_commit_gate_mapping(
    retired_owner: str,
) -> None:
    selected, deferred = cgs.select_pytest_paths(
        [f"quwoquan_data/scripts/content/{retired_owner}/probe.py"]
    )
    assert selected == []
    assert deferred == []


def test_over_budget_selection_is_deferred_rather_than_dropped() -> None:
    changed = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "quwoquan_ops" / "tests" / "local_contract").rglob(
            "*_local_contract_test.py"
        )
    )
    assert len(changed) > cgs.PYTEST_CAP, "本判据需要超过防御上限的在场测试文件才有意义"

    plan = cgs.build_plan(changed, cgs.DEFAULT_FLUTTER_CAP)
    selected = plan["pytest_paths"]
    deferred = [path for path in plan["deferred_to_ci"] if path.endswith(".py")]
    assert plan["estimated_pytest_seconds"] <= plan["pytest_budget_seconds"]
    assert len(selected) < cgs.PYTEST_CAP
    assert any(
        item["reason"] == "estimated_duration_budget"
        for item in plan["pytest_target_estimates"]
    )
    assert sorted(selected + deferred) == changed
