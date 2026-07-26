"""全局 execution 序号分配契约测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="execution_sequence_"))

sys.path.insert(0, str(SCRIPTS_ROOT))

from content.execution.runtime_state import load_execution_runtime_state, write_execution_runtime_state  # noqa: E402
from content.execution.contracts import ExecutionRuntimeState  # noqa: E402
from core.asset_sequence import allocate_execution_sequence, read_latest_execution_sequence  # noqa: E402
from core.paths import execution_sequence_path  # noqa: E402
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402

EXECUTION_ID = "20260711--travel-homepage-coverage--test-region-b--pilot-001"


def test_allocate_execution_sequence_is_monotonic():
    first = allocate_execution_sequence()
    second = allocate_execution_sequence()
    assert second == first + 1
    assert read_latest_execution_sequence() == second
    assert execution_sequence_path().is_file()


def test_write_execution_runtime_state_reuses_execution_sequence():
    build_execution_fixture(EXECUTION_ID)
    write_execution_runtime_state(EXECUTION_ID, command="execution")
    manifest = load_execution_runtime_state(EXECUTION_ID)
    assert isinstance(manifest, ExecutionRuntimeState)
    seq = manifest.execution_sequence
    write_execution_runtime_state(EXECUTION_ID, command="source")
    manifest2 = load_execution_runtime_state(EXECUTION_ID)
    assert manifest2 is not None
    assert manifest2.execution_sequence == seq
    assert manifest2.command_chain == ("execution", "source")


def test_write_execution_runtime_state_rejects_retired_workspace_names():
    build_execution_fixture(EXECUTION_ID)
    with pytest.raises(ValueError, match="unsupported execution workspace"):
        write_execution_runtime_state(EXECUTION_ID, command="_invalid_workspace_")


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"execution sequence tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
