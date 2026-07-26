"""Homepage publication must not turn coverage classifications into facts."""
from __future__ import annotations

import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.homepage.homepage import _homepage_tag_refs  # noqa: E402


def test_homepage_tags_keep_declared_kind_and_reject_unevidenced_coverage_facets() -> None:
    tags = _homepage_tag_refs(
        "地点",
        "景区",
        "测试实体甲",
        {
            "geoTagRef": "Topic/地理/行政区/中国/test-region-a/舟山市/普陀区",
            "typeTagRefs": [
                "Entity/地点/景区/5A景区",
                "Entity/地点/宗教场所",
            ],
            "tagRefs": ["Entity/地点/景区/5A景区"],
        },
    )

    assert "Entity/地点/景区" in tags
    assert "Topic/地理/行政区/中国/test-region-a/舟山市/普陀区" in tags
    assert "Entity/地点/景区/5A景区" not in tags
    assert "Entity/地点/宗教场所" not in tags
