"""download 默认零源 bug 回归：预置 source_plan(含 body) → handle_download 产出 ≥1 source.md。

裸 GET 对 .invalid 域必失败，走 source_frontmatter(body) 离线兜底，不依赖联网。
覆盖两种 source_plan 形态：顶层 sources / envelope payload.sources。
可直接运行 python3 quwoquan_data/tests/download/test_download_source_plan.py
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

import argparse
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="dl_srcplan_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.io import write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    STAGE_DOWNLOAD,
    batch_inputs_dir,
    ensure_batch_layout,
)
from _common.source_unit import iter_source_units, resolve_entity_object_dir  # noqa: E402
from download.handler import handle_download  # noqa: E402
from download.source_inputs import curated_sources_for_entity  # noqa: E402

_TASK = "旅行/地域/四川省/景区/景区全覆盖"
_BATCH = "test_batch"
_EID = "稻城亚丁"
_BODY_MARK = "离线兜底正文：亚丁三神山与牛奶海"


def _doc(top_level: bool, source_count: int = 1) -> dict:
    entries = [
        {
            "source_id": "s1",
            "platform": "baike",
            "url": "https://daocheng.invalid/guide",
            "body": _BODY_MARK,
        },
        {
            "source_id": "s2",
            "platform": "mafengwo",
            "url": "https://daocheng.invalid/travelogue",
            "body": "离线兜底正文：亚丁徒步与避坑。",
        },
        {
            "source_id": "s3",
            "platform": "官网",
            "url": "https://daocheng.invalid/official",
            "body": "离线兜底正文：亚丁官方开放与预约信息。",
        },
    ][:source_count]
    return {"sources": entries} if top_level else {
        "schemaVersion": "quwoquan_data.stage_envelope", "ref": _EID,
        "payload": {"entityId": _EID, "sources": entries},
    }


def _seed_object_plan(top_level: bool, source_count: int = 1) -> None:
    """对象优先：source_plan 落实体对象 1.download/source_plan.json。"""
    ensure_batch_layout(_TASK, _BATCH, "download")
    obj = resolve_entity_object_dir(_TASK, _BATCH, _EID, etype_hint="景区")
    write_json(obj / STAGE_DOWNLOAD / "source_plan.json", _doc(top_level, source_count))


def test_curated_reads_object_plan_top_level_and_envelope():
    _seed_object_plan(top_level=True)
    assert len(curated_sources_for_entity(_TASK, _BATCH, _EID, "景区")) == 1
    _seed_object_plan(top_level=False)
    got = curated_sources_for_entity(_TASK, _BATCH, _EID, "景区")
    assert len(got) == 1 and got[0]["url"].endswith("/guide")


def test_curated_ignores_legacy_layout_only():
    # 旧 stage-first source_plan 不再作为读取真相源。
    legacy_batch = "legacy_only_batch"
    ensure_batch_layout(_TASK, legacy_batch, "download")
    inputs_dir = batch_inputs_dir(_TASK, legacy_batch, "download", "source_plan")
    inputs_dir.mkdir(parents=True, exist_ok=True)
    write_json(inputs_dir / f"{_EID}.json", _doc(top_level=True))
    got = curated_sources_for_entity(_TASK, legacy_batch, _EID, "景区")
    assert got == []


def test_handle_download_produces_source_unit_from_preset_plan():
    # 对象同构新布局：来源写成 entities/{domain}/{type}/{name}/1.download/sources/01.s1/。
    _seed_object_plan(top_level=True, source_count=3)
    args = argparse.Namespace(task=_TASK, batch=_BATCH, entity_ids=_EID, entity_type="景区")
    handle_download(args)
    obj = resolve_entity_object_dir(_TASK, _BATCH, _EID, etype_hint="景区")
    units = iter_source_units(obj)
    assert units, f"no source unit under {obj}"
    assert [unit.name for unit in units] == ["01.s1", "02.s2", "03.s3"], units
    src_md = units[0] / "source.md"
    assert src_md.is_file(), f"missing {src_md}"
    assert (units[0] / "meta.json").is_file()
    assert _BODY_MARK in src_md.read_text(encoding="utf-8")
    # 不再产生对象级散落 images/
    assert not (obj / "images").exists()


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"download source_plan tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
