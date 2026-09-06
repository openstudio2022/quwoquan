"""Data local-contract selection remains available outside source promotion.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#req-003
"""

from __future__ import annotations

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

SHARD_CLI = ROOT / "quwoquan_ops" / "gate" / "delivery_gate_data_shard.py"
GATE_REPO = ROOT / "quwoquan_ops" / "gate" / "gate_repo.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "delivery-gate.yml"
RELEASE_QUALIFICATION = ROOT / ".github" / "workflows" / "release-qualification.yml"


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


def test_source_promotion_excludes_data_execution() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert set(workflow[True]) == {"pull_request", "push"}
    assert set(workflow["jobs"]) == {
        "promotion_verify",
        "main_source_seal",
        "system_backsync",
    }
    source = WORKFLOW.read_text(encoding="utf-8")
    for token in (
        "quwoquan_data",
        "delivery_gate_data_shard.py",
        "GATE_DATA_PHASE",
        "DATA_TEST_TOTAL_SHARDS",
        "gate_repo.sh --scope data",
    ):
        assert token not in source


def test_release_qualification_owns_heavy_factories() -> None:
    workflow = yaml.safe_load(RELEASE_QUALIFICATION.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert jobs["service_factory"]["uses"] == "./.github/workflows/service_pipeline.yml"
    assert jobs["app_factory"]["uses"] == "./.github/workflows/app_pipeline.yml"
    assert jobs["materialize_candidate"]["needs"] == [
        "allocate_build_number",
        "service_factory",
        "app_factory",
    ]


def test_every_test_file_lands_in_exactly_one_shard() -> None:
    full = shard.local_contract_test_files(ROOT)
    assert full
    selected = [
        path
        for index in range(4)
        for path in shard.sharded_test_files(ROOT, 4, index)
    ]
    assert sorted(selected) == full
    assert len(selected) == len(set(selected))


def test_shard_membership_is_stable_across_calls() -> None:
    assert shard.sharded_test_files(ROOT, 4, 0) == shard.sharded_test_files(ROOT, 4, 0)


def test_a_test_file_added_later_still_lands_in_a_shard() -> None:
    newcomer = (
        "quwoquan_data/tests/local_contract/execution/"
        "test_not_yet_written__contract__local_contract_test.py"
    )
    assert shard.shard_of(newcomer, 4) in range(4)


def test_single_shard_selects_the_whole_set() -> None:
    assert shard.sharded_test_files(ROOT, 1, 0) == shard.local_contract_test_files(ROOT)


def test_shard_discovery_covers_every_test_file_on_disk() -> None:
    on_disk = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "quwoquan_data" / "tests" / "local_contract").rglob("*.py")
    )
    assert shard.local_contract_test_files(ROOT) == on_disk


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
    assert result.returncode == 2
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
    scope: str, phase: str
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


def test_partial_selector_stdout_with_nonzero_status_never_reaches_pytest(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    script = (
        "set -euo pipefail\n"
        f"ROOT={shlex.quote(str(repository))}\n"
        "python3() {\n"
        '  if [[ "$*" == *delivery_gate_data_shard.py* ]]; then\n'
        "    printf '%s\n' 'quwoquan_data/tests/local_contract/partial_test.py'\n"
        "    return 17\n"
        "  fi\n"
        "  printf 'unexpected pytest execution\n' >&2\n"
        "  return 99\n"
        "}\n"
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
    assert result.returncode == 17
    assert "data shard selector failed (exit=17)" in result.stderr
    assert "unexpected pytest execution" not in result.stderr


def test_every_data_implementation_directory_is_reachable_from_commit_gate() -> None:
    scripts_root = ROOT / "quwoquan_data" / "scripts"
    implementation_dirs = sorted(
        path.relative_to(ROOT).as_posix() + "/"
        for path in list(scripts_root.iterdir())
        + list((scripts_root / "content").iterdir())
        if path.is_dir() and path.name != "__pycache__" and path.name != "content"
    )
    for directory in implementation_dirs:
        selected, deferred = cgs.select_pytest_paths([directory + "probe.py"])
        assert selected or deferred


def test_crosscutting_data_changes_remain_explicitly_deferred() -> None:
    for prefix in cgs.DATA_CROSSCUTTING_PREFIXES:
        probe = prefix if prefix.endswith(".py") else prefix + "probe.py"
        _, deferred = cgs.select_pytest_paths([probe])
        assert cgs.DATA_LOCAL_CONTRACT_ROOT in deferred


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
    plan = cgs.build_plan(changed, cgs.DEFAULT_FLUTTER_CAP)
    selected = plan["pytest_paths"]
    deferred = [path for path in plan["deferred_to_ci"] if path.endswith(".py")]
    assert plan["estimated_pytest_seconds"] <= plan["pytest_budget_seconds"]
    assert sorted(selected + deferred) == changed
