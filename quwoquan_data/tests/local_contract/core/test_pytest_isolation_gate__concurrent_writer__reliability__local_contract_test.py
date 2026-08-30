# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
"""落盘隔离门的三级判定合约。

FAIL 只由测试进程自证的强证据触发（隔离 env/paths 常量逃逸、仓内 publish
diff）；真实输出根 diff 在隔离自证完好时降级 WARNING——文件系统快照无法
区分写入者，并行数据任务运行期的写入不得把测试判红。
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import conftest as isolation_gate


def _isolated_env(root: Path) -> dict[str, str]:
    return {
        "QWQ_DATA_ROOT": str(root),
        "QWQ_OUTPUT_ROOT": str(root / "output"),
        "QWQ_PUBLISH_ROOT": str(root / "publish"),
        "QWQ_CARRIED_MEDIA_ROOT": str(root / "carried-media"),
    }


def _paths_module(root: Path) -> SimpleNamespace:
    """替身必须与 ``core.paths`` 的暴露面同构。

    随体媒体根按调用解析而非模块常量，因此这里也必须是 callable——把它做成
    属性会让隔离自证在替身上取到与生产不同的形态。
    """
    return SimpleNamespace(
        DATA_ROOT=root,
        OUTPUT_ROOT=root / "output",
        PUBLISH_ROOT=root / "publish",
        carried_media_root=lambda: root / "carried-media",
    )


def _apply_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_intact_isolation_reports_no_breach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _isolated_env(tmp_path)
    _apply_env(monkeypatch, env)
    assert isolation_gate._isolation_breach_evidence(_paths_module(tmp_path), env) == []


def test_escaped_paths_constant_is_a_breach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _isolated_env(tmp_path)
    _apply_env(monkeypatch, env)
    escaped = _paths_module(tmp_path)
    escaped.OUTPUT_ROOT = Path("/") / "real-output-root"
    breaches = isolation_gate._isolation_breach_evidence(escaped, env)
    assert any("OUTPUT_ROOT escaped" in item for item in breaches), breaches


def test_escaped_carried_media_root_is_a_breach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """随体媒体根写的是受版本控制的仓内目录，逃逸即污染真仓库。"""
    env = _isolated_env(tmp_path)
    _apply_env(monkeypatch, env)
    escaped = _paths_module(tmp_path)
    escaped.carried_media_root = lambda: Path("/") / "real-repo" / "golden_media"
    breaches = isolation_gate._isolation_breach_evidence(escaped, env)
    assert any("carried media root escaped" in item for item in breaches), breaches


def test_drifted_env_declaration_is_a_breach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _isolated_env(tmp_path)
    _apply_env(monkeypatch, env)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", "/somewhere-else")
    breaches = isolation_gate._isolation_breach_evidence(_paths_module(tmp_path), env)
    assert any("QWQ_OUTPUT_ROOT drifted" in item for item in breaches), breaches


class _FakeConfig(SimpleNamespace):
    pass


def _run_unconfigure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    breaches: list[str],
    output_diff: bool,
    publish_diff: bool,
    carried_diff: bool = False,
) -> list[str]:
    """驱动 pytest_unconfigure 的三级编排；返回打印的 WARNING 行。"""
    env = _isolated_env(tmp_path)
    _apply_env(monkeypatch, env)
    monkeypatch.delenv("QWQ_PYTEST_ALLOW_ENV_ROOTS", raising=False)
    monkeypatch.setattr(
        isolation_gate,
        "_isolation_breach_evidence",
        lambda *_args: list(breaches),
    )
    baseline_files: dict[str, tuple[int, int]] = {}
    changed_files = {"parallel-task/artifact.json": (1, 1)} if output_diff else {}
    publish_files = {"leaked.json": (1, 1)} if publish_diff else {}
    carried_files = {"leaked.webp": (1, 1)} if carried_diff else {}

    def fake_snapshot(root: Path) -> dict[str, tuple[int, int]]:
        if root.name == "publish":
            return publish_files
        if root.name == "golden_media":
            return carried_files
        return changed_files

    monkeypatch.setattr(isolation_gate, "_snapshot_files", fake_snapshot)
    config = _FakeConfig(
        _qwq_output_baseline={
            str(root): dict(baseline_files)
            for root in isolation_gate._REAL_DATA_OUTPUT_ROOTS
        },
        _qwq_publish_baseline={},
        _qwq_carried_media_baseline={},
    )
    printed: list[str] = []
    monkeypatch.setattr(
        "builtins.print", lambda *args, **_kwargs: printed.append(" ".join(map(str, args)))
    )
    isolation_gate.pytest_unconfigure(config)
    return printed


def test_output_root_diff_with_intact_isolation_is_a_warning_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    printed = _run_unconfigure(
        monkeypatch, tmp_path, breaches=[], output_diff=True, publish_diff=False
    )
    assert any("WARNING" in line and "并行数据任务" in line for line in printed), printed


def test_output_root_diff_with_breached_isolation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(RuntimeError, match="isolation breach"):
        _run_unconfigure(
            monkeypatch,
            tmp_path,
            breaches=["core.paths.OUTPUT_ROOT escaped the isolated root: /real"],
            output_diff=True,
            publish_diff=False,
        )


def test_repo_publish_diff_always_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(RuntimeError, match="publish"):
        _run_unconfigure(
            monkeypatch, tmp_path, breaches=[], output_diff=False, publish_diff=True
        )


def test_carried_media_diff_always_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """随体媒体根与 publish 同级：字节留在仓内就会被当成生产资产提交。"""
    with pytest.raises(RuntimeError, match="golden_media"):
        _run_unconfigure(
            monkeypatch,
            tmp_path,
            breaches=[],
            output_diff=False,
            publish_diff=False,
            carried_diff=True,
        )
