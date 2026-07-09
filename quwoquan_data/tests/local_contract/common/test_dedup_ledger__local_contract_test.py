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

os.environ.setdefault("QWQ_DATA_ROOT", tempfile.mkdtemp(prefix="dedup_ledger_"))

from _common import dedup  # noqa: E402

TASK = "旅行/地域/中国/景区/去重账本_gwt"


def _mark_range(bounds: tuple[int, int]) -> None:
    # 子进程 worker：继承 QWQ_DATA_ROOT，与父进程写同一账本。
    start, end = bounds
    for i in range(start, end):
        dedup.mark_entity_done(TASK, f"实体{i:03d}")


def test_concurrent_marks_do_not_lose_updates() -> None:
    total, workers = 60, 4
    step = total // workers
    bounds = [(i * step, (i + 1) * step) for i in range(workers)]
    ctx = multiprocessing.get_context("fork")
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
    assert manifest["schemaVersion"] == dedup.LEDGER_SCHEMA


def test_default_source_task_is_national_constant() -> None:
    from task.target_selection import DEFAULT_SOURCE_TASK_ID

    assert DEFAULT_SOURCE_TASK_ID == "旅行/地域/中国/景区/景区全覆盖"
    assert "四川" not in DEFAULT_SOURCE_TASK_ID


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"dedup ledger tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
