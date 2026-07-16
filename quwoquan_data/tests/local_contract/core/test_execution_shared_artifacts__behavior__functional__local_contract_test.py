"""Execution 共享运行状态与 source catalog 归位到 `_shared`。"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os
import tempfile

_TMP = Path(tempfile.mkdtemp(prefix="batch_shared_"))

sys.path.insert(0, str(SCRIPTS_ROOT))

from content.execution.runtime_state import write_execution_runtime_state, write_source_catalog  # noqa: E402
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402
from core.io import read_json  # noqa: E402
from core.paths import (  # noqa: E402
    execution_runtime_state_path,
    execution_root,
    execution_source_catalog_path,
)

_TASK = "20260711--travel-homepage-shared--cn-sichuan--canary-001"
_BATCH = _TASK
_IDENTITY: dict[str, object] = {}


def setup_function() -> None:
    global _IDENTITY
    _IDENTITY = build_execution_fixture(
        _TASK,
        targets=[{"name": "稻城亚丁", "entityType": "地点/景区"}],
    )


def test_execution_runtime_state_is_object_first_and_idempotent():
    p1 = write_execution_runtime_state(_TASK, command="execution")
    assert p1 == execution_runtime_state_path(_TASK)
    assert p1.parent == execution_root(_TASK) / "_shared"
    m = read_json(p1)
    assert m["executionId"] == _TASK
    assert m["targetSetSha256"] == _IDENTITY["targetSetSha256"]
    assert isinstance(m["executionSequence"], int) and m["executionSequence"] > 0
    assert m["commandChain"] == ["execution"]
    created = m["createdAt"]
    seq = m["executionSequence"]
    # 幂等：再次写不重复命令、不丢 createdAt、追加新命令
    write_execution_runtime_state(_TASK, command="execution")
    write_execution_runtime_state(_TASK, command="source")
    m2 = read_json(p1)
    assert m2["createdAt"] == created
    assert m2["executionSequence"] == seq
    assert m2["commandChain"] == ["execution", "source"]
    assert "coverageTargets" not in m2
    assert "env" not in m2 and "contentType" not in m2


def test_source_catalog_projected_to_shared():
    p = write_source_catalog(_TASK)
    assert p == execution_source_catalog_path(_TASK)
    # 落 _shared 下
    assert p.parent.name == "_shared"
    assert p.parent.parent == execution_root(_TASK)
    cat = read_json(p)
    assert cat["source"].endswith("source_catalog.yaml")
    assert isinstance(cat["sourceKinds"], list) and cat["sourceKinds"], cat
    sample = cat["sourceKinds"][0]
    assert "kind" in sample and "label" in sample, sample


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        setup_function()
        fn()
        print(f"PASS {fn.__name__}")
    print(f"batch shared artifacts tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
