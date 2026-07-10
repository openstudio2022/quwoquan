"""输出根隔离契约（数据输出规范）。

固化统一输出目录规范的核心不变量：
- 默认输出根 `QWQ_OUTPUT_ROOT=<repo>/.qwq_output/`：工程目录内、gitignore 隔离，
  不在用户 HOME / /tmp；
- data/local/runtime/release/输出侧 artifacts 全部从 OUTPUT_ROOT 推导；publish 保持仓内受版本控制；
- 显式覆盖 QWQ_DATA_ROOT（测试隔离根）时输出根跟随其隔离，schema/contracts 仍跟代码走；
- 批次树按 data/local/runtime/{phase}/{contentType}/{supplyMode}/ 三级主键落位，
  一批次唯一 phase、唯一 contentType、唯一 supplyMode；
- 历史平铺 runtime/batches/ 与 `.qwq_sandbox` 不再作为 reader fallback。
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from _common import paths as paths_mod

_PYTEST_ENV_BASELINE = {
    key: os.environ.get(key)
    for key in (
        "QWQ_DATA_ROOT",
        "QWQ_PUBLISH_ROOT",
        "QWQ_RELEASE_ROOT",
        "QWQ_SCHEMA_ROOT",
        "QWQ_OUTPUT_ARTIFACTS_ROOT",
        "QWQ_SERVICE_CONTRACTS_METADATA_ROOT",
        "QWQ_RUNTIME_ROOT",
        "QWQ_OUTPUT_ROOT",
    )
}


def test_pytest_session_runs_on_isolated_tempfile_root():
    """单元/合约测试落盘隔离契约：conftest 导入守卫必须已注入隔离根。

    pytest 进程内（未显式 opt-out 时）：
    - `QWQ_DATA_ROOT` 指向 tempfile 临时根，绝不指向仓内数据根或真实输出根；
    - 真实输出根声明（QWQ_OUTPUT_ROOT）已被清除，测试不可能跟随其落盘。
    """
    import os

    assert os.environ.get("QWQ_PYTEST_ALLOW_ENV_ROOTS") != "1"
    declared = os.environ.get("QWQ_DATA_ROOT", "")
    assert declared, "conftest 必须注入隔离 QWQ_DATA_ROOT"
    declared_path = Path(declared).resolve()
    assert declared_path != paths_mod._REPO_DATA_ROOT.resolve()
    assert not str(declared_path).startswith(str(paths_mod.default_output_root().resolve()))
    assert os.environ.get("QWQ_OUTPUT_ROOT") in (None, "") or Path(
        os.environ["QWQ_OUTPUT_ROOT"]
    ).resolve() != paths_mod.default_output_root().resolve()
    assert os.environ.get("QWQ_CURSOR_STARTUP_PROBE_CACHE_TTL_SECONDS") == "0"


def test_default_output_root_is_in_repo_and_gitignored():
    output_root = paths_mod.default_output_root()
    # 落在仓库根下，且名为 .qwq_output（不是 HOME / /tmp 下的散落 scratch 根）。
    assert output_root.parent == paths_mod.REPO_ROOT
    assert output_root.name == ".qwq_output"
    assert output_root != Path.home() / "qwq_scale_verify"

    gitignore = (paths_mod.REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".qwq_output/" in gitignore


def test_no_runner_defaults_to_home_scale_verify():
    runners = paths_mod.REPO_ROOT / "quwoquan_ops" / "runners"
    offenders = [
        str(p.relative_to(paths_mod.REPO_ROOT))
        for p in runners.glob("*.sh")
        if "qwq_scale_verify" in p.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"runner scripts must not default to ~/qwq_scale_verify: {offenders}"


def _reload_paths(monkeypatch, **env: str):
    for key in (
        "QWQ_DATA_ROOT",
        "QWQ_OUTPUT_ROOT",
        "QWQ_RUNTIME_ROOT",
        "QWQ_PUBLISH_ROOT",
        "QWQ_RELEASE_ROOT",
        "QWQ_SCHEMA_ROOT",
        "QWQ_OUTPUT_ARTIFACTS_ROOT",
        "QWQ_SERVICE_CONTRACTS_METADATA_ROOT",
        "QWQ_BATCH_PHASE",
        "QWQ_BATCH_CONTENT_TYPE",
        "QWQ_BATCH_SUPPLY_MODE",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(paths_mod)


@pytest.fixture()
def restore_paths(monkeypatch):
    yield
    # 必须先 undo，再显式恢复 pytest 会话隔离根并 reload：否则验证默认根的
    # 用例可能把 paths 常量短暂重置到真实仓内 publish，污染同 session 后续测试。
    monkeypatch.undo()
    for key, value in _PYTEST_ENV_BASELINE.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    importlib.reload(paths_mod)


def test_output_root_drives_runtime_release_artifacts_but_not_publish(
    tmp_path, monkeypatch, restore_paths
):
    output_root = tmp_path / ".qwq_output"
    reloaded = _reload_paths(monkeypatch, QWQ_OUTPUT_ROOT=str(output_root))
    # data/local/runtime、data/release、data/runs 摘要索引全部从输出根推导。
    assert reloaded.RUNTIME_ROOT == output_root / "data" / "local" / "runtime"
    assert reloaded.RELEASE_ROOT == output_root / "data" / "release"
    assert reloaded.OUTPUT_ARTIFACTS_ROOT == output_root / "data" / "runs"
    # publish 是唯一入库生成输出：默认仓内受版本控制，不随输出根出仓。
    assert reloaded.PUBLISH_ROOT == reloaded._REPO_DATA_ROOT / "publish"
    # schema / 服务侧 contracts 跟代码走。
    assert reloaded.SCHEMA_ROOT == reloaded._REPO_DATA_ROOT / "schema"
    assert reloaded.SERVICE_CONTRACTS_METADATA_ROOT == (
        reloaded.REPO_ROOT / "quwoquan_service" / "contracts" / "metadata"
    )


def test_isolated_data_root_keeps_full_isolation_semantics(
    tmp_path, monkeypatch, restore_paths
):
    isolated = tmp_path / "isolated_root"
    reloaded = _reload_paths(monkeypatch, QWQ_DATA_ROOT=str(isolated))
    # 测试隔离根：data/local/runtime、publish、data/release 全部跟随隔离根。
    assert reloaded.RUNTIME_ROOT == isolated / "data" / "local" / "runtime"
    assert reloaded.PUBLISH_ROOT == isolated / "publish"
    assert reloaded.RELEASE_ROOT == isolated / "data" / "release"
    # schema 契约仍跟代码走。
    assert reloaded.SCHEMA_ROOT == reloaded._REPO_DATA_ROOT / "schema"
    # gate 默认 release 根（仓库内）与隔离 release 根物理隔离。
    gate_release_root = reloaded._REPO_DATA_ROOT / "data" / "release"
    assert reloaded.RELEASE_ROOT != gate_release_root


def test_batch_root_layers_phase_content_type_supply_mode(
    tmp_path, monkeypatch, restore_paths
):
    reloaded = _reload_paths(
        monkeypatch,
        QWQ_DATA_ROOT=str(tmp_path / "root"),
        QWQ_BATCH_PHASE="operations",
        QWQ_BATCH_CONTENT_TYPE="homepage",
        QWQ_BATCH_SUPPLY_MODE="site_primary",
    )
    root = reloaded.batch_root("旅行/网站/示例", "b0001")
    rel = root.relative_to(reloaded.RUNTIME_ROOT)
    assert rel.parts[:3] == ("operations", "homepage", "site_primary")
    assert rel.parts[3].endswith("__b0001")


def test_batch_axis_env_rejects_unknown_values(tmp_path, monkeypatch, restore_paths):
    reloaded = _reload_paths(
        monkeypatch,
        QWQ_DATA_ROOT=str(tmp_path / "root"),
        QWQ_BATCH_CONTENT_TYPE="mixed",
    )
    with pytest.raises(ValueError):
        reloaded.batch_content_type()


def test_batch_root_ignores_legacy_flat_layout(tmp_path, monkeypatch, restore_paths):
    reloaded = _reload_paths(monkeypatch, QWQ_DATA_ROOT=str(tmp_path / "root"))
    task_id = "旅行/网站/legacy示例"
    name = reloaded.batch_dir_name(task_id, "b9999")
    legacy_dir = reloaded.RUNTIME_ROOT / "batches" / name
    legacy_dir.mkdir(parents=True)
    # 已存在的 legacy 平铺批次不再被 reader 解析；缺失 canonical 批次按当前声明落位。
    resolved = reloaded.batch_root(task_id, "b9999")
    assert resolved != legacy_dir
    rel = resolved.relative_to(reloaded.RUNTIME_ROOT)
    assert rel.parts[:3] == ("e2e", "article", "site_primary")
    assert rel.parts[3] == name
