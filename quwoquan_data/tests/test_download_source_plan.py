"""download 默认零源 bug 回归：预置 source_plan(含 body) → handle_download 产出 ≥1 source.md。

裸 GET 对 .invalid 域必失败，走 source_frontmatter(body) 离线兜底，不依赖联网。
覆盖两种 source_plan 形态：顶层 sources / envelope payload.sources。
可直接运行 python3 quwoquan_data/tests/test_download_source_plan.py
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="dl_srcplan_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _common.io import write_json  # noqa: E402
from _common.paths import batch_command_root, batch_inputs_dir, ensure_batch_layout  # noqa: E402
from download.handler import handle_download  # noqa: E402
from download.source_inputs import curated_sources_for_entity  # noqa: E402

_TASK = "旅行/地域/四川省/景区/景区全覆盖"
_BATCH = "test_batch"
_EID = "稻城亚丁"
_BODY_MARK = "离线兜底正文：亚丁三神山与牛奶海"


def _seed_plan(top_level: bool) -> None:
    ensure_batch_layout(_TASK, _BATCH, "download")
    inputs_dir = batch_inputs_dir(_TASK, _BATCH, "download", "source_plan")
    inputs_dir.mkdir(parents=True, exist_ok=True)
    entry = {"source_id": "s1", "platform": "web",
             "url": "https://daocheng.invalid/guide", "body": _BODY_MARK}
    doc = {"sources": [entry]} if top_level else {
        "schemaVersion": "quwoquan_data.stage_envelope", "ref": _EID,
        "payload": {"entityId": _EID, "sources": [entry]},
    }
    write_json(inputs_dir / f"{_EID}.json", doc)


def test_curated_reads_top_level_and_envelope():
    _seed_plan(top_level=True)
    assert len(curated_sources_for_entity(_TASK, _BATCH, _EID)) == 1
    _seed_plan(top_level=False)
    got = curated_sources_for_entity(_TASK, _BATCH, _EID)
    assert len(got) == 1 and got[0]["url"].endswith("/guide")


def test_handle_download_produces_source_md_from_preset_plan():
    _seed_plan(top_level=True)
    args = argparse.Namespace(task=_TASK, batch=_BATCH, entity_ids=_EID)
    handle_download(args)
    dl_root = batch_command_root(_TASK, _BATCH, "download")
    src_md = dl_root / "sources" / _EID / "s1" / "source.md"
    assert src_md.is_file(), f"missing {src_md}"
    assert _BODY_MARK in src_md.read_text(encoding="utf-8")


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"download source_plan tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
