# spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/spec.md#req-002
"""Post safety 重依赖不得污染 canonical stackctl 的加载边界。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
STACKCTL = ROOT / "quwoquan_ops/cli/stackctl.py"


def _run_without_heavy_dependencies(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    blocker = tmp_path / "sitecustomize.py"
    blocker.write_text(
        """import builtins\n"
        "real_import = builtins.__import__\n"
        "def guarded(name, *args, **kwargs):\n"
        "    if name == 'pydantic' or name.startswith('pydantic.') or name == 'pymongo' or name.startswith('pymongo.'):\n"
        "        raise ModuleNotFoundError(name)\n"
        "    return real_import(name, *args, **kwargs)\n"
        "builtins.__import__ = guarded\n""",
        encoding="utf-8",
    )
    return subprocess.run(
        [sys.executable, str(STACKCTL), *arguments], cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, capture_output=True, timeout=30, check=False,
    )


def test_standard_and_post_safety_help_load_without_heavy_dependencies(tmp_path: Path) -> None:
    for arguments in (("--help",), ("post-safety-runtime", "--help")):
        result = _run_without_heavy_dependencies(tmp_path, *arguments)
        assert result.returncode == 0, result.stderr
        assert "Traceback" not in result.stderr


def test_inspect_and_verify_parsers_load_without_heavy_dependencies(tmp_path: Path) -> None:
    for arguments in (("inspect", "--help"), ("verify", "--help")):
        result = _run_without_heavy_dependencies(tmp_path, *arguments)
        assert result.returncode == 0, result.stderr
        assert "Traceback" not in result.stderr


def test_post_safety_execution_returns_typed_dependency_blocker(tmp_path: Path) -> None:
    script = """
import json
from argparse import Namespace
from quwoquan_ops.cli.commands.post_safety_runtime import command_post_safety_runtime
value = command_post_safety_runtime(Namespace(action='plan', target='alpha-local', plan_ref='', confirm_post_safety_runtime=False, report_dir='', command='post-safety-runtime'))
print(json.dumps(value, sort_keys=True))
"""
    blocker = tmp_path / "sitecustomize.py"
    blocker.write_text(
        "import builtins\nr=builtins.__import__\ndef f(n,*a,**k):\n"
        " if n=='pydantic' or n.startswith('pydantic.') or n=='pymongo' or n.startswith('pymongo.'): raise ModuleNotFoundError(n)\n"
        " return r(n,*a,**k)\nbuiltins.__import__=f\n",
        encoding="utf-8",
    )
    result = subprocess.run([sys.executable, "-c", script], cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["exitCode"] == 2
    assert payload["blockerKind"] == "post_safety_runtime_dependency_unavailable"
    assert "make prepare-test-python" in payload["summary"]
    assert "Traceback" not in result.stderr


def test_post_safety_execution_blocks_when_only_pymongo_is_missing(tmp_path: Path) -> None:
    blocker = tmp_path / "sitecustomize.py"
    blocker.write_text(
        "import builtins\nr=builtins.__import__\ndef f(n,*a,**k):\n"
        " if n=='pymongo' or n.startswith('pymongo.'): raise ModuleNotFoundError(n)\n"
        " return r(n,*a,**k)\nbuiltins.__import__=f\n", encoding="utf-8")
    script = """
import json
from argparse import Namespace
from quwoquan_ops.cli.commands.post_safety_runtime import command_post_safety_runtime
print(json.dumps(command_post_safety_runtime(Namespace(action='verify', target='alpha-local', plan_ref='', confirm_post_safety_runtime=False, report_dir='', command='post-safety-runtime'))))
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, capture_output=True, timeout=30, check=False)
    assert result.returncode == 0 and "Traceback" not in result.stderr
    assert json.loads(result.stdout)["blockerKind"] == "post_safety_runtime_dependency_unavailable"
