"""全局批次号分配契约测试。"""
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
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="global_batch_seq_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.batch_manifest import load_batch_manifest, write_batch_manifest  # noqa: E402
from _common.global_batch_seq import allocate_global_batch_seq, read_latest_global_batch_seq  # noqa: E402
from _common.paths import global_batch_seq_path  # noqa: E402

TASK = "旅行/地域/四川省/景区/景区全覆盖"


def test_allocate_global_batch_seq_is_monotonic():
    first = allocate_global_batch_seq()
    second = allocate_global_batch_seq()
    assert second == first + 1
    assert read_latest_global_batch_seq() == second
    assert global_batch_seq_path().is_file()


def test_write_batch_manifest_reuses_global_batch_seq():
    batch = "gbs_manifest"
    write_batch_manifest(TASK, batch, command="task_run")
    manifest = load_batch_manifest(TASK, batch)
    seq = int(manifest["globalBatchSeq"])
    write_batch_manifest(TASK, batch, command="download")
    manifest2 = load_batch_manifest(TASK, batch)
    assert int(manifest2["globalBatchSeq"]) == seq
    assert manifest2["commandChain"] == ["task_run", "download"]


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"global batch seq tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
