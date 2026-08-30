"""Canonical publish carries documents; a media body there is a purity failure.

Publish used to own the bytes it showed, under a `media/objects/sha256/**` root,
so purity only had to police the shape of that root. It owns none of them now —
the content library does, and a canonical document reaches a body by the digest
it records. What purity has to answer is therefore no longer "is this body
content-addressed" but "why is a body here at all", and both shapes of that
question are asked below: a `media` root, and a body nested inside a root
publish legitimately owns.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from verify.verify_publish_purity import publish_purity_issues  # noqa: E402


def _write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def test_publish_refuses_a_media_root(tmp_path: Path):
    body = b"cover-bytes"
    digest = hashlib.sha256(body).hexdigest()
    _write(
        tmp_path / "media/objects/sha256" / digest[:2] / digest[2:4] / f"{digest}.jpg",
        body,
    )

    issues = publish_purity_issues(tmp_path)

    # Content-addressing does not earn a body a place in the versioned tree: the
    # store it belongs to is the library, so the root itself is what is refused.
    assert any("publish root only permits" in issue for issue in issues)
    assert any("creators, entities, posts, tags" in issue for issue in issues)


def test_publish_refuses_a_media_body_nested_under_a_canonical_root(tmp_path: Path):
    _write(tmp_path / "posts/image/摄影/作品/1/assets/cover.jpg", b"cover-bytes")

    issues = publish_purity_issues(tmp_path)

    # `posts/` is a root publish owns, so only judging the whole path catches a
    # body that hides inside an object surface.
    assert any(
        "publish carries documents only" in issue for issue in issues
    ), issues


def test_publish_accepts_a_document_only_tree(tmp_path: Path):
    entity = tmp_path / "entities/地点/景区/真实地点"
    _write(entity / "_entity.json", json.dumps({"label": "真实地点"}).encode("utf-8"))
    _write(entity / "page.md", "# 真实地点\n".encode("utf-8"))

    assert publish_purity_issues(tmp_path) == []


def test_publish_post_requires_explicit_work_identity(tmp_path: Path):
    manifest = tmp_path / "posts" / "article" / "攻略" / "西湖" / "1" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"contentType":"article","assets":[]}', encoding="utf-8")

    issues = publish_purity_issues(tmp_path)

    assert any("post_content_identity_invalid" in issue for issue in issues)
