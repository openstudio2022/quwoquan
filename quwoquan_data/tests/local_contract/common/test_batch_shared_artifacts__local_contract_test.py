"""M2 对象优先：批次级公共信息上提（batch_manifest + _shared/source_catalog）。

规格 §2.2/§4/§14：任务/批次级公共信息抽到 batch 根，不在对象目录重复；
受控来源类目从 committed 唯一真相源投影到 _shared，供对象目录只读引用。
可直接运行 python3 quwoquan_data/tests/local_contract/common/test_batch_shared_artifacts__local_contract_test.py
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

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="batch_shared_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.batch_manifest import write_batch_manifest, write_source_catalog  # noqa: E402
from _common.io import read_json  # noqa: E402
from _common.paths import (  # noqa: E402
    batch_manifest_path,
    batch_root,
    batch_source_catalog_path,
)

_TASK = "旅行/地域/四川省/景区/景区全覆盖"
_BATCH = "shared_b1"


def test_batch_manifest_is_object_first_and_idempotent():
    targets = [{"name": "稻城亚丁", "entityType": "地点/景区"}]
    p1 = write_batch_manifest(_TASK, _BATCH, coverage_targets=targets, command="task_run")
    assert p1 == batch_manifest_path(_TASK, _BATCH)
    # batch 根下，不在对象目录
    assert p1.parent == batch_root(_TASK, _BATCH)
    m = read_json(p1)
    assert m["layout"] == "object-first"
    assert m["taskId"] == _TASK and m["batchId"] == _BATCH
    assert isinstance(m["globalBatchSeq"], int) and m["globalBatchSeq"] > 0
    assert m["coverageTargets"] == [{"name": "稻城亚丁", "entityType": "地点/景区"}]
    assert m["commandChain"] == ["task_run"]
    created = m["createdAt"]
    seq = m["globalBatchSeq"]
    # 幂等：再次写不重复命令、不丢 createdAt、追加新命令
    write_batch_manifest(_TASK, _BATCH, command="task_run")
    write_batch_manifest(_TASK, _BATCH, command="download")
    m2 = read_json(p1)
    assert m2["createdAt"] == created
    assert m2["globalBatchSeq"] == seq
    assert m2["commandChain"] == ["task_run", "download"]
    # 已有 coverageTargets 不被空覆盖
    assert m2["coverageTargets"] == [{"name": "稻城亚丁", "entityType": "地点/景区"}]


def test_source_catalog_projected_to_shared():
    p = write_source_catalog(_TASK, _BATCH)
    assert p == batch_source_catalog_path(_TASK, _BATCH)
    # 落 _shared 下
    assert p.parent.name == "_shared"
    assert p.parent.parent == batch_root(_TASK, _BATCH)
    cat = read_json(p)
    assert cat["source"].endswith("source_catalog.yaml")
    assert isinstance(cat["sourceKinds"], list) and cat["sourceKinds"], cat
    sample = cat["sourceKinds"][0]
    assert "kind" in sample and "label" in sample, sample


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"batch shared artifacts tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
