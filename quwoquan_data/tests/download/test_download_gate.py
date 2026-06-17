"""download gate 契约测试（对象优先）。"""
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

sys.path.insert(0, str(SCRIPTS_ROOT))

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

from _common.paths import batch_entity_object_dir, batch_root, ensure_task_layout  # noqa: E402
from _common.io import write_json  # noqa: E402
from _common.source_unit import write_source_unit  # noqa: E402
from download.gate import gate_download  # noqa: E402

TASK = "旅行/地域/四川省/景区/景区全覆盖"


def _attach_image(unit_dir: Path, name: str) -> None:
    assets = unit_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    image = assets / f"{name}.jpg"
    image.write_bytes(b"fake-image")
    write_json(
        assets / "index.json",
        {
            "assets": [
                {
                    "fileName": image.name,
                    "sourceAssetId": name,
                    "sha256": f"sha256:{name}",
                    "license": "CC-BY-4.0",
                    "credit": "fixture",
                    "sourceUrl": "https://example.com/image.jpg",
                    "termsUrl": "https://example.com/terms",
                    "usageScope": "commercial_editorial",
                }
            ]
        },
    )


def test_gate_download_passes_object_first_sources():
    batch = "download_gate_pass"
    ensure_task_layout(TASK)
    entity_dir = batch_entity_object_dir(TASK, batch, "地点", "景区", "峨眉山")
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="overview_baike",
        source_md="# 峨眉山\n\n概述",
        quality={"sourceId": "overview_baike", "quality": "B-fact", "score": 5},
        platform="baike",
        source_category="overview_baike",
        url="https://example.com/1",
        title="峨眉山（百科）",
        target_ref="/entity/地点/景区/峨眉山",
    )
    _attach_image(entity_dir / "1.download/sources/01.overview_baike", "emei_1")
    write_source_unit(
        entity_dir,
        ordinal=2,
        source_id="travel_notes",
        source_md="# 峨眉山\n\n游记",
        quality={"sourceId": "travel_notes", "quality": "A-story", "score": 8},
        platform="travelogue",
        source_category="travelogue",
        url="https://example.com/2",
        title="峨眉山（游记）",
        target_ref="/entity/地点/景区/峨眉山",
    )
    _attach_image(entity_dir / "1.download/sources/02.travel_notes", "emei_2")
    issues = gate_download(TASK, batch)
    assert issues == [], issues
    assert (batch_root(TASK, batch) / "entities").is_dir()


def test_gate_download_blocks_single_source_unit():
    batch = "download_gate_block"
    ensure_task_layout(TASK)
    entity_dir = batch_entity_object_dir(TASK, batch, "地点", "景区", "乐山大佛")
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="overview_baike",
        source_md="# 乐山大佛\n\n概述",
        quality={"sourceId": "overview_baike", "quality": "B-fact", "score": 5},
        platform="baike",
        source_category="overview_baike",
        url="https://example.com/3",
        title="乐山大佛（百科）",
        target_ref="/entity/地点/景区/乐山大佛",
    )
    issues = gate_download(TASK, batch)
    assert any("only 1 sources" in issue for issue in issues), issues


def test_gate_download_blocks_reject_only_units():
    batch = "download_gate_reject_only"
    ensure_task_layout(TASK)
    entity_dir = batch_entity_object_dir(TASK, batch, "地点", "景区", "九寨沟")
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="probe_1",
        source_md="---\nretained: false\n---\n\nmanual_source_plan_note: 探针页\n",
        quality={"sourceId": "probe_1", "quality": "Reject", "score": 0},
        platform="mafengwo",
        source_category="travelogue",
        url="https://example.com/r1",
        title="探针页1",
        target_ref="/entity/地点/景区/九寨沟",
    )
    write_source_unit(
        entity_dir,
        ordinal=2,
        source_id="probe_2",
        source_md="---\nretained: false\n---\n\nmanual_source_plan_note: 探针页\n",
        quality={"sourceId": "probe_2", "quality": "Reject", "score": 0},
        platform="ctrip",
        source_category="travelogue",
        url="https://example.com/r2",
        title="探针页2",
        target_ref="/entity/地点/景区/九寨沟",
    )
    issues = gate_download(TASK, batch)
    assert any("retained sources" in issue for issue in issues), issues


def test_gate_download_includes_failed_stage_gate_sidecars():
    batch = "download_gate_stage_sidecar"
    ensure_task_layout(TASK)
    entity_dir = batch_entity_object_dir(TASK, batch, "地点", "景区", "三苏祠")
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="overview_baike",
        source_md="# 三苏祠\n\n概述",
        quality={"sourceId": "overview_baike", "quality": "B-fact", "score": 5},
        platform="baike",
        source_category="overview_baike",
        url="https://example.com/1",
        title="三苏祠（百科）",
        target_ref="/entity/地点/景区/三苏祠",
    )
    _attach_image(entity_dir / "1.download/sources/01.overview_baike", "sansuci_1")
    write_source_unit(
        entity_dir,
        ordinal=2,
        source_id="travel_notes",
        source_md="# 三苏祠\n\n游记",
        quality={"sourceId": "travel_notes", "quality": "A-story", "score": 8},
        platform="travelogue",
        source_category="travelogue",
        url="https://example.com/2",
        title="三苏祠（游记）",
        target_ref="/entity/地点/景区/三苏祠",
    )
    _attach_image(entity_dir / "1.download/sources/02.travel_notes", "sansuci_2")
    report_dir = batch_root(TASK, batch) / "task_download" / "results" / "image_fetch_gate"
    report_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        report_dir / "三苏祠.json",
        {
            "payload": {
                "ref": "三苏祠",
                "passed": False,
                "issues": ["imageCount: 三苏祠 仅下到 1 张合格图（要求 ≥2）"],
            }
        },
    )

    issues = gate_download(TASK, batch)
    assert any("imageCount" in issue for issue in issues), issues


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]:
        fn()
        print(f"PASS {fn.__name__}")
    print("download gate tests passed")
