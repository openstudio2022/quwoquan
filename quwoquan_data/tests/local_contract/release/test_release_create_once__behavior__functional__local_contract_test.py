from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import content.release.canonical.assemble as assemble  # noqa: E402


def _json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_release_is_create_once_and_contains_only_compact_review_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    batch = tmp_path / ".qwq_output/data/tasks/20260711--travel-article-release--test--canary-001"
    post = batch / "posts/article/a"
    _json(post / "manifest.json", {"contentType": "article", "ref": "article/a"})
    (post / "article.md").write_text("# final\n", encoding="utf-8")
    _json(post / "5.review/attestation.json", {"decision": "approved"})
    _json(post / "5.review/evidence_index.json", {"refs": ["runtime/evidence/a"]})
    _json(post / "5.review/reviewer_result.json", {"verdict": "passed"})
    (post / "5.review/prompt.md").write_text("process prompt", encoding="utf-8")

    release_parent = tmp_path / "release"
    monkeypatch.setattr(assemble, "release_root", lambda release_id: release_parent / release_id)
    monkeypatch.setattr(assemble, "execution_root", lambda *_args: batch)
    monkeypatch.setattr(assemble, "collect_execution_entity_objects", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(assemble, "_execution_is_homepage_only", lambda _execution_id: False)

    release = assemble.assemble_release("20260711--travel-article-release--test--canary-001", "release-1")
    released_post = release / "posts/article/a"
    assert (released_post / "article.md").is_file()
    assert (released_post / "attestation.json").is_file()
    assert (released_post / "evidence_index.json").is_file()
    assert not (released_post / "5.review").exists()
    assert not (released_post / "reviewer_result.json").exists()
    assert not (released_post / "prompt.md").exists()

    with pytest.raises(FileExistsError, match="create-once"):
        assemble.assemble_release("20260711--travel-article-release--test--canary-001", "release-1")
