"""content_plan 证据准入门 contract test：source_screen=reject 来源不得进入 content_plan。

可直接运行：python3 quwoquan_data/tests/common/test_content_plan_source_reject.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = tempfile.mkdtemp(prefix="qwq_content_plan_test_")
os.environ["QWQ_RUNTIME_ROOT"] = _TMP

from _common import content_plan as cp  # noqa: E402
from _common.io import write_json  # noqa: E402
from _common.paths import batch_content_plan_packet_path, batch_results_dir  # noqa: E402

TASK = "旅行/地域/四川省/景区/景区精选"
BATCH = "test_batch_reject"


def _seed():
    reject_dir = batch_results_dir(TASK, BATCH, "download", "source_screen")
    write_json(reject_dir / "reject1.json", {"sourceId": "reject1", "decision": "reject"})
    write_json(reject_dir / "keep1.json", {"sourceId": "keep1", "decision": "retain"})
    packet = {
        "schemaVersion": cp.CONTENT_PLAN_SCHEMA,
        "items": [
            {
                "ref": "x",
                "kind": "entity",
                "title": "样例",
                "entityRefs": ["e1"],
                "evidenceRefs": ["1.download/sources/reject1.md"],
                "rationale": "r",
                "writingIntent": "planning_consultation",
                "baseSourceRef": "1.download/sources/reject1.md",
            }
        ],
    }
    write_json(batch_content_plan_packet_path(TASK, BATCH), packet)


def test_reject_source_ids_collects_only_rejects():
    _seed()
    rejects = cp.reject_source_ids(TASK, BATCH)
    assert rejects == {"reject1"}


def test_content_plan_blocks_rejected_source():
    _seed()
    issues = cp.validate_content_plan(TASK, BATCH, {})
    assert any("cites rejected source" in i and "reject1" in i for i in issues), issues


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"content_plan source-reject tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
