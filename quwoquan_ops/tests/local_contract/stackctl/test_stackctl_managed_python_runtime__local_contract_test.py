# spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/spec.md#req-002
"""stackctl 的 Ops-owned Python cache 与 mutation 前置合同。"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from quwoquan_ops.cli.commands import managed_python


ROOT = Path(__file__).resolve().parents[4]
STACKCTL = ROOT / "quwoquan_ops/cli/stackctl.py"
OPS_ONLY_REQUIREMENTS = {"jsonschema", "pydantic", "psycopg", "redis", "docker", "pymongo"}


def _requirement_names(path: Path) -> set[str]:
    return {
        line.split("[", 1)[0].split("==", 1)[0].strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_data_requirements_exclude_ops_runtime_modules() -> None:
    data = _requirement_names(ROOT / "quwoquan_data/requirements.txt")
    ops = _requirement_names(ROOT / "quwoquan_ops/requirements.txt")

    assert not (data & OPS_ONLY_REQUIREMENTS)
    assert OPS_ONLY_REQUIREMENTS <= ops


def test_prepare_test_python_names_distinct_data_and_ops_caches() -> None:
    source = (ROOT / "quwoquan_ops/cli/prepare_test_python.py").read_text(encoding="utf-8")
    assert '"data": prepare_data_runtime_cache()' in source
    assert '"ops": prepare_ops_runtime_cache()' in source
    assert managed_python.ops_venv_dir().name == "quwoquan-ops"


def test_stackctl_reexec_overwrites_ambient_spoof(monkeypatch, tmp_path: Path) -> None:
    expected = tmp_path / "quwoquan-ops/bin/python"
    expected.parent.mkdir(parents=True)
    expected.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    expected.chmod(0o755)
    captured: dict[str, object] = {}
    monkeypatch.setattr(managed_python, "ops_venv_python", lambda: expected)
    monkeypatch.setattr(managed_python, "preflight_ops_python", lambda python: (True, []))
    monkeypatch.setattr(
        managed_python.os,
        "execve",
        lambda executable, argv, environment: captured.update(
            executable=executable, argv=argv, environment=environment
        ),
    )
    monkeypatch.setenv("QWQ_STACKCTL_PYTHON", "/ambient/spoof")
    monkeypatch.delenv(managed_python.OPS_BOOTSTRAP_ENV, raising=False)

    managed_python.ensure_managed_stackctl_runtime([str(STACKCTL), "up", "--target", "gamma-local"])

    assert captured["executable"] == str(expected)
    environment = captured["environment"]
    assert isinstance(environment, dict)
    assert environment["QWQ_STACKCTL_PYTHON"] == str(expected)
    assert environment[managed_python.OPS_BOOTSTRAP_ENV] == "1"


def test_stackctl_reexec_loop_is_typed(monkeypatch, tmp_path: Path) -> None:
    expected = tmp_path / "quwoquan-ops/bin/python"
    expected.parent.mkdir(parents=True)
    expected.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    expected.chmod(0o755)
    monkeypatch.setattr(managed_python, "ops_venv_python", lambda: expected)
    monkeypatch.setenv(managed_python.OPS_BOOTSTRAP_ENV, "1")

    with pytest.raises(RuntimeError, match="STACKCTL_MANAGED_PYTHON_REEXEC_LOOP"):
        managed_python.ensure_managed_stackctl_runtime([str(STACKCTL), "up"])


def test_missing_ops_cache_blocks_before_stackctl_command_graph_and_startup(tmp_path: Path) -> None:
    cache_root = tmp_path / "empty-cache"
    ambient = tmp_path / "ambient-python"
    ambient.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    ambient.chmod(0o755)
    result = subprocess.run(
        [sys.executable, str(STACKCTL), "up", "--target", "gamma-local"],
        cwd=ROOT,
        env={
            **os.environ,
            "QWQ_PYTHON_CACHE_ROOT": str(cache_root),
            "QWQ_STACKCTL_PYTHON": str(ambient),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 2
    assert "STACKCTL_MANAGED_PYTHON_UNAVAILABLE" in result.stderr
    assert "start_local_gamma_mirror.sh" not in result.stdout + result.stderr


def test_generated_dto_and_modules_are_preflighted_before_command_imports() -> None:
    stackctl = STACKCTL.read_text(encoding="utf-8")
    bootstrap = stackctl.index("ensure_managed_stackctl_runtime(sys.argv)")
    first_command_import = stackctl.index("from quwoquan_ops.cli.lib.common import")
    source = Path(managed_python.__file__).read_text(encoding="utf-8")

    assert bootstrap < first_command_import
    assert "PostSafetyDeploymentStartupMaterial.model_json_schema()" in source
    for module in managed_python.OPS_REQUIRED_MODULES:
        assert f"import {module}" in managed_python._preflight_code()
