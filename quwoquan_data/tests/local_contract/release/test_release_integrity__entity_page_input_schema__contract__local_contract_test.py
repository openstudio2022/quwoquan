# spec_ref: specs/feature-tree/discovery-content/spec.md#dom-001
"""Release integrity validates entity_page_input before reading its payload."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.integrity import _entity_homepage_issues


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _entity_roots(tmp_path: Path) -> tuple[Path, Path, str]:
    root = tmp_path / "publish"
    runtime = tmp_path / "runtime"
    entity_rel = "entities/地点/景区/p0001/样例/1"
    _write_json(root / entity_rel / "manifest.json", {})
    _write_json(
        runtime / entity_rel / "2.quality" / "quality_analysis.json",
        {"baseDraft": {"sourceRef": "sources/primary/source.md"}},
    )
    return root, runtime, entity_rel


@pytest.mark.parametrize(
    "document",
    [
        {},
        {
            "stage": "3.compose",
            "executionId": "execution-1",
            "step": "entity_page",
            "ref": "entities/地点/景区/p0001/样例/1",
            "qualityRef": "2.quality/quality_analysis.json",
            "qualityDigest": "sha256:" + "0" * 64,
            "selectedSourceUrls": ["https://example.com/source"],
            "selectedSourceRefs": ["sources/other/source.md"],
            "payload": {"baseDraft": {"sourceRef": "sources/other/source.md"}},
        },
    ],
    ids=["empty-object", "missing-schema"],
)
def test_invalid_entity_page_input_fails_closed_before_payload_semantics(
    tmp_path: Path,
    document: dict,
) -> None:
    root, runtime, entity_rel = _entity_roots(tmp_path)
    _write_json(runtime / entity_rel / "3.compose" / "entity_page_input.json", document)

    issues = _entity_homepage_issues(root, runtime)

    assert len(issues) == 1, issues
    assert "invalid entity_page_input" in issues[0]
    assert "quality base draft differs from compose base draft" not in issues[0]


def test_valid_entity_page_input_continues_into_existing_semantic_checks(
    tmp_path: Path,
) -> None:
    root, runtime, entity_rel = _entity_roots(tmp_path)
    _write_json(
        runtime / entity_rel / "3.compose" / "entity_page_input.json",
        {
            "schema": "quwoquan_data.entity_page_input",
            "stage": "3.compose",
            "executionId": "execution-1",
            "step": "entity_page",
            "ref": entity_rel,
            "qualityRef": "2.quality/quality_analysis.json",
            "qualityDigest": "sha256:" + "0" * 64,
            "selectedSourceUrls": ["https://example.com/source"],
            "selectedSourceRefs": ["sources/primary/source.md"],
            "payload": {
                "name": "样例",
                "entityRef": entity_rel,
                "baseDraft": {},
                "draftPage": "4.draft/page.md",
                "minChars": 1,
                "minSectionChars": 1,
            },
        },
    )

    issues = _entity_homepage_issues(root, runtime)

    assert all("invalid entity_page_input" not in issue for issue in issues)
    assert any("homepage primary authority source" in issue for issue in issues), issues
