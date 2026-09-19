from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
sys.path.insert(0, str(DATA_ROOT / "scripts"))

from content.release.canonical.integrity import _entity_homepage_issues


def test_release_integrity_rejects_invalid_entity_page_input_at_read_boundary(tmp_path) -> None:
    publish = tmp_path / "publish"
    entity = publish / "entities/landmark/p0001/example/1"
    entity.mkdir(parents=True)
    (entity / "manifest.json").write_text("{}", encoding="utf-8")

    runtime = tmp_path / "runtime"
    compose = runtime / "entities/landmark/p0001/example/1/3.compose"
    compose.mkdir(parents=True)
    (compose / "entity_page_input.json").write_text("{}", encoding="utf-8")

    issues = _entity_homepage_issues(publish, runtime)
    assert len(issues) == 1
    assert "invalid entity_page_input" in issues[0]
    assert "缺 required 字段 'schema'" in issues[0]
