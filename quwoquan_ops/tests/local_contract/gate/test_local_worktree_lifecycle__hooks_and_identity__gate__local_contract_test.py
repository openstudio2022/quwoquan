# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-003.t3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-003.t4
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-004.t1
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-004.t2
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-004.t3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-004.t4
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-004.t5
"""本地工作副本生命周期治理的行为级 local_contract（hooks 与身份组）。

由 Python 1000 行硬顶从主套件按职责拆出；完整保留 hooks 安装自检、
lane 身份、策略与物理布局测试，授权和滞留提醒组仍在原套件。
"""

from __future__ import annotations

from collections.abc import Iterator
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
# 按目录加进 sys.path，而不是 `from quwoquan_ops.hooks import ...`：后者把 quwoquan_ops
# 当成真包导入，会在源码树留下 __pycache__，而仓库要求源码树缓存为零。
extra = ROOT / "quwoquan_ops/cli/lib"
if str(extra) not in sys.path:
    sys.path.insert(0, str(extra))

import local_worktree_inventory as inventory  # noqa: E402
from quwoquan_ops.cli import lane_worktree_commands  # noqa: E402

INSTALL_SCRIPT = ROOT / "quwoquan_ops/hooks/run_install_hooks.sh"
GATE_SCRIPT = ROOT / "quwoquan_ops/gate/verify_local_worktree_lifecycle.py"
ALLOWED = frozenset({"dev1.0", "main", "lane/product-mainline", "lane/data-engineering", "lane/engineering", "lane/ops", "lane/small-fix", "lane/refactor"})


@pytest.fixture(scope="module")
def policy() -> inventory.WorktreePolicy:
    return inventory.load_policy()


def _run_git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


# --- GWT-003 hooks 安装自检 ------------------------------------------------


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "dev1.0", str(path)], check=True, capture_output=True)


def test_gwt_003_t1_detects_missing_hooks_path(tmp_path: Path, policy) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / policy.hooks_path).mkdir(parents=True)

    assert inventory.hooks_installed(root=repo, policy=policy) is False


def test_gwt_003_t2_accepts_only_in_repo_hooks_path(tmp_path: Path, policy) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / policy.hooks_path).mkdir(parents=True)

    subprocess.run(["git", "config", "core.hooksPath", policy.hooks_path], cwd=repo, check=True)
    assert inventory.hooks_installed(root=repo, policy=policy) is True

    outside = tmp_path / "outside-hooks"
    outside.mkdir()
    subprocess.run(["git", "config", "core.hooksPath", str(outside)], cwd=repo, check=True)
    assert inventory.hooks_installed(root=repo, policy=policy) is False, "仓外 hook 目录不算已安装"


def test_gwt_003_t3_install_entrypoint_resolves_repo_root(tmp_path: Path, policy) -> None:
    """安装入口的路径解析回归。

    这里曾经写成 `/../../..`，多退一级落到仓库外的父目录，`git config` 静默失败，
    core.hooksPath 长期未设置，pre-commit 与 pre-push 从未生效。
    """
    repo = tmp_path / "nested" / "repo"
    _init_repo(repo)
    hook_dir = repo / policy.hooks_path
    hook_dir.mkdir(parents=True)
    for name in ("pre-commit", "pre-push", "post-commit"):
        shutil.copy(ROOT / policy.hooks_path / name, hook_dir / name)
    shutil.copy(INSTALL_SCRIPT, hook_dir / INSTALL_SCRIPT.name)

    completed = subprocess.run(
        ["bash", str(hook_dir / INSTALL_SCRIPT.name)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    readback = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"], cwd=repo, capture_output=True, text=True, check=True
    )
    assert readback.stdout.strip() == policy.hooks_path
    # 幂等：重复安装不改变结果，也不报错。
    assert subprocess.run(
        ["bash", str(hook_dir / INSTALL_SCRIPT.name)],
        capture_output=True,
        check=False,
    ).returncode == 0


def test_gwt_003_t4_install_refuses_outside_git_toplevel(tmp_path: Path, policy) -> None:
    """非 git 顶层目录下必须 fail-closed，而不是把配置写去别处后声称成功。"""
    plain = tmp_path / "plain"
    hook_dir = plain / policy.hooks_path
    hook_dir.mkdir(parents=True)
    for name in ("pre-commit", "pre-push", "post-commit"):
        shutil.copy(ROOT / policy.hooks_path / name, hook_dir / name)
    shutil.copy(INSTALL_SCRIPT, hook_dir / INSTALL_SCRIPT.name)

    completed = subprocess.run(
        ["bash", str(hook_dir / INSTALL_SCRIPT.name)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert completed.returncode == 2
    assert "not the git toplevel" in completed.stderr


def test_gate_entrypoint_is_executable_and_reports_typed_codes() -> None:
    """门禁本身必须可被 gate 链执行，且失败身份用稳定错误码表达。"""
    completed = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert completed.returncode in (0, 2)
    payload = json.loads(completed.stdout)
    assert "issues" in payload and "summary" in payload
    for issue in payload["issues"]:
        assert issue.startswith("OPS.WORKTREE."), issue


# --- GWT-004 lane 身份与策略布局 ------------------------------------------


def _linked(
    path: str,
    branch: str,
    *,
    probe_error: str = "",
    head: str = "same",
    clean: bool = True,
    dirty: int = 0,
) -> inventory.WorkCopy:
    return inventory.WorkCopy(
        path=path,
        kind="linked_worktree",
        branch=branch,
        ahead=0,
        dirty=dirty,
        stashes=0,
        oldest_unmerged_epoch=None,
        probe_error=probe_error,
        head=head,
        clean=clean,
    )


def test_inventory_list_failure_is_typed_fail_closed(monkeypatch, policy) -> None:
    monkeypatch.setattr(inventory, "_git", lambda *_args: (2, "authority down"))
    with pytest.raises(inventory.InventoryError) as caught:
        inventory.discover_work_copies(root=ROOT, policy=policy)
    assert caught.value.code == inventory.INVENTORY_UNAVAILABLE


def _canonical_path(policy, branch: str) -> str:
    if branch == policy.integration_branch:
        return str(ROOT.parent / policy.integration_directory)
    return str(ROOT.parent / dict(policy.lane_worktree_directories)[branch])


def _integration(policy, *, head: str = "same", clean: bool = True, dirty: int = 0):
    return _linked(
        _canonical_path(policy, policy.integration_branch),
        policy.integration_branch,
        head=head,
        clean=clean,
        dirty=dirty,
    )


def test_porcelain_parser_preserves_bare_record_without_branch() -> None:
    parsed = inventory.parse_worktree_list(
        "worktree /tmp/project/quwoquan.git\nbare\n\n"
        "worktree /tmp/project/engineering\nHEAD abc\n"
        "branch refs/heads/lane/engineering\n"
    )
    assert parsed == [
        inventory.WorktreeListEntry(
            path="/tmp/project/quwoquan.git", branch="", bare=True
        ),
        inventory.WorktreeListEntry(
            path="/tmp/project/engineering", branch="lane/engineering", bare=False
        ),
    ]


def test_discovery_validates_bare_hub_without_probing_it(tmp_path, policy, monkeypatch) -> None:
    project = tmp_path / "quwoquan"
    hub = project / policy.bare_hub_directory
    integration = project / policy.integration_directory
    hub.mkdir(parents=True)
    integration.mkdir()
    porcelain = (
        f"worktree {hub}\nbare\n\n"
        f"worktree {integration}\nHEAD {'a' * 40}\n"
        f"branch refs/heads/{policy.integration_branch}\n"
    )
    actual_git = inventory._git

    def fake_git(cwd, *args):
        if args == ("worktree", "list", "--porcelain"):
            return 0, porcelain
        return actual_git(cwd, *args)

    probed: list[Path] = []

    def fake_probe(path, **kwargs):
        probed.append(path)
        return _linked(str(path), kwargs["branch"])

    monkeypatch.setattr(inventory, "_git", fake_git)
    monkeypatch.setattr(inventory, "probe_work_copy", fake_probe)
    monkeypatch.setattr(inventory, "_scan_for_clones", lambda *_args: [])
    copies = inventory.discover_work_copies(root=integration, policy=policy)
    assert probed == [integration.resolve()]
    assert all(copy.path != str(hub) for copy in copies)


@pytest.fixture
def hook_env_temp_path() -> Iterator[Path]:
    """在仓外系统临时目录创建并清理跨仓 Git 环境回归夹具。"""
    system_temp_root = Path("/tmp").resolve()
    assert system_temp_root.is_dir()
    with tempfile.TemporaryDirectory(
        prefix="qwq-hook-env-regression-", dir=system_temp_root
    ) as temp_dir:
        path = Path(temp_dir).resolve()
        assert not path.is_relative_to(ROOT.resolve())
        yield path


def test_discovery_ignores_hook_repository_environment_and_preserves_copy_facts(
    hook_env_temp_path: Path, policy, monkeypatch
) -> None:
    project = hook_env_temp_path / "project"
    hub = project / policy.bare_hub_directory
    integration = project / policy.integration_directory
    lane = project / dict(policy.lane_worktree_directories)["lane/engineering"]
    hub.parent.mkdir(parents=True)
    _run_git(hub.parent, "init", "--bare", "-q", str(hub))
    _run_git(hub, "worktree", "add", "-q", "-b", policy.integration_branch, str(integration))
    (integration / "seed.txt").write_text("seed\n", encoding="utf-8")
    _run_git(integration, "add", "seed.txt")
    _run_git(integration, "commit", "-qm", "seed")
    _run_git(
        hub,
        "worktree",
        "add",
        "-q",
        "-b",
        "lane/engineering",
        str(lane),
        policy.integration_branch,
    )
    (lane / "ahead.txt").write_text("ahead\n", encoding="utf-8")
    _run_git(lane, "add", "ahead.txt")
    _run_git(lane, "commit", "-qm", "ahead")
    (lane / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    test_policy = inventory.WorktreePolicy(
        **{
            **vars(policy),
            "project_root": str(project),
            "discovery_roots": (str(project),),
        }
    )
    monkeypatch.setenv("GIT_DIR", str(hub / "worktrees" / lane.name))
    monkeypatch.setenv("GIT_WORK_TREE", str(lane))

    copies = inventory.discover_work_copies(root=integration, policy=test_policy)
    by_branch = {copy.branch: copy for copy in copies}
    assert set(by_branch) == {policy.integration_branch, "lane/engineering"}
    assert all(copy.path != str(hub.resolve()) for copy in copies), "bare hub is authority, not a copy"
    assert all(copy.probe_error == "" for copy in copies)
    assert by_branch[policy.integration_branch].dirty == 0
    assert by_branch[policy.integration_branch].ahead == 0
    assert by_branch["lane/engineering"].dirty == 1
    assert by_branch["lane/engineering"].ahead == 1


@pytest.mark.parametrize(
    "copies_factory, fragment",
    [
        (lambda policy: [_integration(policy), _linked("/tmp/detached", "")], "detached"),
        (lambda policy: [_integration(policy), _linked("/tmp/main", "main")], "not integration or a fixed lane"),
        (
            lambda policy: [
                _integration(policy),
                _linked(_canonical_path(policy, "lane/ops"), "lane/ops", probe_error="status failed"),
            ],
            "probe failed",
        ),
        (
            lambda policy: [
                _integration(policy),
                _linked(_canonical_path(policy, "lane/ops"), "lane/ops"),
                _linked("/tmp/ops-copy", "lane/ops"),
            ],
            "duplicate lane binding",
        ),
        (
            lambda policy: [
                _integration(policy),
                _linked("/tmp/same", "lane/ops"),
                _linked("/tmp/same", "lane/refactor"),
            ],
            "duplicate worktree path",
        ),
        (
            lambda policy: [
                _integration(policy),
                _linked("/tmp/wrong-ops", "lane/ops"),
            ],
            "lane path mismatch",
        ),
    ],
)
def test_discovered_linked_identity_failures_block(policy, copies_factory, fragment) -> None:
    issues = inventory.validate_worktree_identity(copies_factory(policy), policy)
    assert any(fragment in issue for issue in issues), issues


def test_integration_is_unique_clean_and_bound_to_integration_directory(policy) -> None:
    assert inventory.validate_worktree_identity([_integration(policy)], policy) == []
    dirty = inventory.validate_worktree_identity(
        [_integration(policy, clean=False, dirty=1)], policy
    )
    assert any("integration worktree is not clean" in issue for issue in dirty)
    missing = inventory.validate_worktree_identity([], policy)
    assert any("integration worktree must appear exactly once" in issue for issue in missing)


def test_require_all_lanes_checks_clean_and_canonical_head(monkeypatch, policy) -> None:
    lanes = sorted(branch for branch in policy.allowed_local_branches if branch.startswith("lane/"))
    copies = [
        _integration(policy),
        *[_linked(_canonical_path(policy, branch), branch) for branch in lanes],
    ]
    monkeypatch.setattr(inventory, "_integration_ref", lambda _root, _policy: "origin/dev1.0")
    monkeypatch.setattr(inventory, "_git", lambda *_args: (0, "same"))
    assert inventory.validate_worktree_identity(
        copies, policy, require_all_lanes=True, repo_root=ROOT
    ) == []

    dirty = list(copies)
    dirty[1] = _linked(dirty[1].path, dirty[1].branch, clean=False, dirty=1)
    dirty[2] = _linked(dirty[2].path, dirty[2].branch, head="other")
    issues = inventory.validate_worktree_identity(
        dirty, policy, require_all_lanes=True, repo_root=ROOT
    )
    assert any("lane worktree is not clean" in issue for issue in issues)
    assert any("lane HEAD differs from origin/dev1.0" in issue for issue in issues)

    integration_drift = list(copies)
    integration_drift[0] = _integration(policy, head="other")
    issues = inventory.validate_worktree_identity(
        integration_drift, policy, require_all_lanes=True, repo_root=ROOT
    )
    assert any("integration HEAD differs from origin/dev1.0" in issue for issue in issues)

    missing = inventory.validate_worktree_identity(
        copies[:-1], policy, require_all_lanes=True, repo_root=ROOT
    )
    assert any("require-all-lanes mismatch" in issue for issue in missing)


@pytest.mark.parametrize(
    ("policy_mutator", "branch_mutator"),
    [
        (lambda raw: raw + b"unknown_field: true\n", lambda raw: raw),
        (
            lambda raw: raw.replace(
                b"authorization_env_var: QWQ_WORKTREE_AUTHZ\n",
                b"authorization_env_var: QWQ_WORKTREE_AUTHZ\n"
                b"authorization_env_var: OTHER\n",
            ),
            lambda raw: raw,
        ),
        (lambda raw: raw, lambda raw: raw + b"unknown_field: true\n"),
        (
            lambda raw: raw,
            lambda raw: raw.replace(
                b"integration_branch: dev1.0\n",
                b"integration_branch: dev1.0\nintegration_branch: main\n",
            ),
        ),
        (
            lambda raw: raw,
            lambda raw: raw.replace(
                b"production_workflow: .github/workflows/deploy-prod-auto.yml\n",
                b"",
            ),
        ),
        (
            lambda raw: raw,
            lambda raw: raw.replace(
                b"  mainHeadDenied: true\n",
                b"  mainHeadDenied: false\n",
                1,
            ),
        ),
    ],
)
def test_policy_loader_rejects_unknown_duplicate_and_incomplete_contracts(
    tmp_path: Path, policy_mutator, branch_mutator,
) -> None:
    policy_path = tmp_path / "worktree_policy.yaml"
    branch_path = tmp_path / "branch_policy.yaml"
    policy_path.write_bytes(
        policy_mutator(
            (ROOT / "quwoquan_ops/policies/worktree_policy.yaml").read_bytes()
        )
    )
    branch_path.write_bytes(
        branch_mutator(
            (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_bytes()
        )
    )

    with pytest.raises(inventory.PolicyError):
        inventory.load_policy(
            policy_path=policy_path,
            branch_policy_path=branch_path,
        )


def test_policy_declares_fixed_project_hub_integration_and_lane_directories(policy) -> None:
    assert policy.schema_version == 2
    assert policy.project_root == "{repo_parent}"
    assert policy.bare_hub_directory == "quwoquan.git"
    assert (policy.integration_directory, policy.integration_branch) == ("integration", "dev1.0")
    source = (ROOT / "quwoquan_ops/policies/worktree_policy.yaml").read_text(encoding="utf-8")
    assert "lane_worktree_directory_rule: branch_suffix" in source
    assert "lane/engineering:" not in source, "分支闭集不得复制到物理布局策略"
    assert dict(policy.lane_worktree_directories) == {
        branch: branch.removeprefix("lane/")
        for branch in ALLOWED
        if branch.startswith("lane/")
    }


def test_lane_command_targets_render_without_mutation_and_derive_policy(policy) -> None:
    bootstrap = lane_worktree_commands.render("bootstrap")
    resync = lane_worktree_commands.render("resync")
    assert len(bootstrap) == len(resync) == 6
    for branch, directory in policy.lane_worktree_directories:
        assert any(branch in command and f"/{directory}" in command for command in bootstrap)
        assert any(f"/{directory}" in command and "merge --ff-only dev1.0" in command for command in resync)
    source = (ROOT / "quwoquan_ops/cli/lane_worktree_commands.py").read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "os.system" not in source


def test_lane_ownership_schema_is_closed_and_uses_branch_policy_lanes(policy) -> None:
    lanes = frozenset(branch for branch in ALLOWED if branch.startswith("lane/"))
    rules = inventory.load_lane_ownership(allowed_lanes=lanes)
    assert inventory.ownership_owner("quwoquan_ops/gate/verify_root_layout.py", rules) == "lane/engineering"
    assert inventory.ownership_owner("quwoquan_app/run.sh", rules) == "lane/engineering"
    assert inventory.ownership_owner("quwoquan_app/scripts/device/supervise_app_launch.py", rules) == "lane/engineering"
    assert inventory.ownership_owner("quwoquan_ops/cli/lib/app_readiness_facts.py", rules) == "lane/engineering"
    assert inventory.ownership_owner("quwoquan_ops/cli/lib/environment_acceptance_fact.py", rules) == "lane/engineering"
    assert inventory.ownership_owner("quwoquan_ops/cli/lib/deployment_candidate_manifest/manifest.py", rules) == "lane/engineering"
    assert inventory.ownership_owner("quwoquan_ops/cli/commands/deploy_rollout.py", rules) == "lane/engineering"
    assert inventory.ownership_owner("quwoquan_ops/cli/prod/hosted_release_ledger.py", rules) == "lane/engineering"
    assert inventory.ownership_owner("quwoquan_ops/cli/stackctl.py", rules) == "lane/ops"
    assert inventory.ownership_owner("quwoquan_ops/cli/commands/health.py", rules) == "lane/ops"
    assert inventory.ownership_owner("quwoquan_ops/cli/prod/render_prod_plane_stack.py", rules) == "lane/ops"
    assert inventory.ownership_owner("quwoquan_ops/observability/prometheus.yml", rules) == "lane/ops"
    assert inventory.ownership_owner("quwoquan_ops/environments/prod/environment.yaml", rules) == "lane/ops"
    assert inventory.ownership_owner("quwoquan_app/lib/main.dart", rules) == "lane/product-mainline"
    assert inventory.ownership_owner("quwoquan_ops/policies/branch_policy.yaml", rules) == "lane/engineering"
    assert inventory.ownership_owner("quwoquan_ops/policies/app_build_projection_policy.json", rules) == "lane/ops"


def test_policy_install_command_matches_real_entrypoint(policy) -> None:
    """策略里的安装命令与真实入口不得漂移——两处字面量是这类治理最容易烂掉的地方。"""
    assert policy.install_command.endswith(str(INSTALL_SCRIPT.relative_to(ROOT)))
    assert INSTALL_SCRIPT.is_file()
    assert (ROOT / policy.hooks_path).is_dir()
