"""标签可点击态契约：标签本体只描述语义，可浏览目标由 publish index 派生。"""
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

_TMP = Path(tempfile.mkdtemp(prefix="tag_link_targets_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.io import read_json, read_ndjson, write_json  # noqa: E402
from _common.paths import PUBLISH_ROOT  # noqa: E402
from publish_ops.build_publish_lookup_indexes import build_publish_lookup_indexes  # noqa: E402


def _tag(ref: str, label: str, *, landing: bool = False) -> None:
    tag_dir = PUBLISH_ROOT / "tags" / ref
    write_json(tag_dir / "_definition.json", {
        "label": label,
        "labelEn": label,
        "description": f"{label} 语义定义",
        "createdAt": "2026-05-15T00:00:00+08:00",
        "updatedAt": "2026-05-15T00:00:00+08:00",
    })
    if landing:
        (tag_dir / "page.md").write_text(f"# {label}\n", encoding="utf-8")


def _seed_publish() -> None:
    _tag("Topic/旅行/玩法/徒步", "徒步")
    _tag("Topic/季节/秋", "秋", landing=True)
    _tag("Topic/旅行/玩法/潜水", "潜水")
    write_json(PUBLISH_ROOT / "posts" / "article" / "攻略" / "毕棚沟" / "1" / "manifest.json", {
        "entityRefs": ["/entity/地点/景区/毕棚沟"],
        "tagRefs": ["Topic/旅行/玩法/徒步"],
    })


def test_tag_link_targets_are_derived_not_tag_fields():
    _seed_publish()
    counts = build_publish_lookup_indexes()
    assert counts["tagLinkTargets"] == 3
    rows = read_ndjson(PUBLISH_ROOT / "index" / "link_targets" / "tags.ndjson")
    by_ref = {row["tagRef"]: row for row in rows}
    assert by_ref["Topic/季节/秋"]["targetKind"] == "landing"
    assert by_ref["Topic/旅行/玩法/徒步"]["targetKind"] == "search"
    assert by_ref["Topic/旅行/玩法/潜水"]["targetKind"] == "none"
    definition = read_json(PUBLISH_ROOT / "tags" / "Topic/旅行/玩法/徒步" / "_definition.json")
    assert "linkable" not in definition and "targetKind" not in definition


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"tag link target tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
