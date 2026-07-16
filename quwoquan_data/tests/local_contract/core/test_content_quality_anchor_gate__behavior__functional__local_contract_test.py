"""内容质量门中的对象锚点归一契约测试。"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from verify.verify_content_quality import _normalized_entity_ref_issues  # noqa: E402


def test_normalized_entity_refs_matches_canonicalized_publish_refs():
    manifest = {
        "entityRefs": ["/entity/地点/景区/九寨沟", "/entity/地点/景区/黄龙"],
        "normalizedEntityRefs": ["entity:景区:九寨沟", "entity:景区:黄龙"],
    }
    issues = _normalized_entity_ref_issues(Path("manifest.json"), manifest)
    assert issues == [], issues


def test_normalized_entity_refs_rejects_runtime_legacy_formats():
    manifest = {
        "entityRefs": ["/entity/地点/景区/九寨沟"],
        "normalizedEntityRefs": ["sight/homepage_sight_jiuzhaigou"],
    }
    issues = _normalized_entity_ref_issues(Path("manifest.json"), manifest)
    assert any("must equal canonicalized entityRefs" in issue for issue in issues), issues
    assert any("must use canonical entity:* format" in issue for issue in issues), issues


def test_normalized_entity_refs_must_be_array():
    manifest = {
        "entityRefs": ["/entity/地点/景区/九寨沟"],
        "normalizedEntityRefs": "entity:景区:九寨沟",
    }
    issues = _normalized_entity_ref_issues(Path("manifest.json"), manifest)
    assert any("normalizedEntityRefs must be an array" in issue for issue in issues), issues


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"content quality anchor gate tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
