"""P0 契约：项目内 gitignored sandbox 根 + gate release 根隔离。

固化「输出漂移到用户 HOME（~/qwq_scale_verify）」复盘后的不变量：
- 默认 sandbox 根落在仓库内 `.qwq_sandbox/`（已 gitignore），不在用户 HOME；
- 把 QWQ_DATA_ROOT 指向 sandbox 时，runtime/publish/release 跟随 sandbox，
  而 schema / 服务侧 contracts 仍跟代码走（不漂移）；
- sandbox 的 release 根与 gate 默认 release 根（quwoquan_data/release）物理隔离，
  保证 `verify --scope current` 不被 sandbox 实验产物污染。
"""
from __future__ import annotations

import importlib
from pathlib import Path

from _common import paths as paths_mod


def test_default_sandbox_root_is_in_repo_and_gitignored():
    sandbox = paths_mod.default_sandbox_root()
    assert sandbox == paths_mod.DEFAULT_SANDBOX_ROOT
    # 落在仓库根下，且名为 .qwq_sandbox（不是用户 HOME 下的散落 scratch 根）。
    assert sandbox.parent == paths_mod.REPO_ROOT
    assert sandbox.name == ".qwq_sandbox"
    # 不得是历史的 ~/qwq_scale_verify（仓库本身可能在 HOME 下，故只排除该旧路径）。
    assert sandbox != Path.home() / "qwq_scale_verify"

    gitignore = (paths_mod.REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".qwq_sandbox/" in gitignore


def test_no_runner_defaults_to_home_scale_verify():
    runners = paths_mod.REPO_ROOT / "agent_ops" / "runners"
    offenders = [
        str(p.relative_to(paths_mod.REPO_ROOT))
        for p in runners.glob("*.sh")
        if "qwq_scale_verify" in p.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"runner scripts must not default to ~/qwq_scale_verify: {offenders}"


def _reload_paths_with_root(monkeypatch, sandbox: Path):
    monkeypatch.setenv("QWQ_DATA_ROOT", str(sandbox))
    monkeypatch.delenv("QWQ_RUNTIME_ROOT", raising=False)
    monkeypatch.delenv("QWQ_PUBLISH_ROOT", raising=False)
    monkeypatch.delenv("QWQ_RELEASE_ROOT", raising=False)
    monkeypatch.delenv("QWQ_SCHEMA_ROOT", raising=False)
    monkeypatch.delenv("QWQ_SERVICE_CONTRACTS_METADATA_ROOT", raising=False)
    return importlib.reload(paths_mod)


def test_sandbox_root_isolates_release_but_keeps_contracts_on_repo(tmp_path, monkeypatch):
    sandbox = tmp_path / ".qwq_sandbox"
    try:
        reloaded = _reload_paths_with_root(monkeypatch, sandbox)
        # runtime/publish/release 跟随 sandbox 根。
        assert reloaded.RUNTIME_ROOT == sandbox / "runtime"
        assert reloaded.PUBLISH_ROOT == sandbox / "publish"
        assert reloaded.RELEASE_ROOT == sandbox / "release"
        # schema 与服务侧 contracts 跟代码走（不随 sandbox 漂移）。
        assert reloaded.SCHEMA_ROOT == reloaded._REPO_DATA_ROOT / "schema"
        assert reloaded.SERVICE_CONTRACTS_METADATA_ROOT == (
            reloaded.REPO_ROOT / "quwoquan_service" / "contracts" / "metadata"
        )
        # gate 默认 release 根（仓库内）与 sandbox release 根物理隔离。
        gate_release_root = reloaded._REPO_DATA_ROOT / "release"
        assert reloaded.RELEASE_ROOT != gate_release_root
        assert sandbox not in gate_release_root.parents
    finally:
        # 还原默认 paths（移除 env 后重载），避免污染同进程其它用例。
        monkeypatch.delenv("QWQ_DATA_ROOT", raising=False)
        importlib.reload(paths_mod)
