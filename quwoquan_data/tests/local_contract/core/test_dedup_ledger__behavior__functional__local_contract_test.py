"""跨批去重账本并发契约（WP4 dedup 修正，local_contract）。

- mark_* 必须经文件锁互斥：多进程并发回写不丢更新（多省并行前置）。
- 幂等：重复 mark 不重复 append。
- 默认账本维度 = 全国常量（防再漂移回省级维度）。
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import multiprocessing
import os
import tempfile

_DEDUP_ROOT = Path(os.environ.get("QWQ_DEDUP_LEDGER_TEST_ROOT") or tempfile.mkdtemp(prefix="dedup_ledger_"))
os.environ["QWQ_DEDUP_LEDGER_TEST_ROOT"] = str(_DEDUP_ROOT)

from core import paths as _paths_mod  # noqa: E402
from core import dedup  # noqa: E402

TASK = "20260711--travel-homepage-dedup-ledger--cn-national--canary-001"


def _retarget_root(root: Path = _DEDUP_ROOT) -> None:
    os.environ["QWQ_DEDUP_LEDGER_TEST_ROOT"] = str(root)
    os.environ["QWQ_DATA_ROOT"] = str(root)
    os.environ["QWQ_OUTPUT_ROOT"] = str(root / "output")
    _paths_mod.DATA_ROOT = root
    _paths_mod.OUTPUT_ROOT = root / "output"
    _paths_mod.DATA_OUTPUT_ROOT = _paths_mod.OUTPUT_ROOT / "data"
    _paths_mod.DATA_EXECUTIONS_ROOT = _paths_mod.DATA_OUTPUT_ROOT / "tasks"
    _paths_mod.DATA_LOCAL_ROOT = _paths_mod.DATA_OUTPUT_ROOT / "local"
    _paths_mod.RUNTIME_ROOT = _paths_mod.DATA_EXECUTIONS_ROOT
    _paths_mod.DATA_EXECUTIONS_ROOT = _paths_mod.DATA_EXECUTIONS_ROOT


def setup_function() -> None:
    _retarget_root()


def _mark_range(bounds: tuple[int, int, str]) -> None:
    # 子进程 worker：spawn 后显式重绑到父进程同一测试根。
    start, end, root = bounds
    _retarget_root(Path(root))
    for i in range(start, end):
        dedup.mark_entity_done(TASK, f"实体{i:03d}")


def test_concurrent_marks_do_not_lose_updates() -> None:
    total, workers = 60, 4
    step = total // workers
    _retarget_root()
    bounds = [(i * step, (i + 1) * step, str(_DEDUP_ROOT)) for i in range(workers)]
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(workers) as pool:
        pool.map(_mark_range, bounds)
    completed = set(dedup.load_manifest(TASK).get("completedEntities", []))
    expected = {f"实体{i:03d}" for i in range(total)}
    missing = expected - completed
    assert not missing, f"文件锁失效丢更新: {sorted(missing)[:10]}"


def test_mark_is_idempotent_and_schema_stamped() -> None:
    dedup.mark_entity_done(TASK, "幂等实体")
    dedup.mark_entity_done(TASK, "幂等实体")
    manifest = dedup.load_manifest(TASK)
    assert manifest["completedEntities"].count("幂等实体") == 1
    assert manifest["schema"] == dedup.LEDGER_SCHEMA


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"dedup ledger tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
