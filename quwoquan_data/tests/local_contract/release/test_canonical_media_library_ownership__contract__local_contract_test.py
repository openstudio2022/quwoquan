"""Canonical media bodies must be owned by the content library, not by the tree.

A delta blob lives in the transaction run root, which the collector reclaims once
the run closes. If the canonical tree linked a media body straight from that blob,
reclaiming the run would leave the tree holding the only copy of every body it
publishes, and the library would never accumulate the bytes it is supposed to own.
These tests pin the ownership split: media bodies are admitted into the library and
referenced from it, while canonical documents stay owned by the tree itself.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from content.release.canonical.object_transaction_delta import apply_forward_delta
from core.content_library import MEDIA_KIND, library_cas_path

_MEDIA_BODY = b"\xff\xd8\xff\xe0canonical-media-body-under-test"
_DOCUMENT_BODY = b'{"schema":"quwoquan_data.entity_object"}'


def _digest(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _stage_blob(run_root: Path, body: bytes) -> str:
    """Write one body into the transaction blob CAS and return its blobRef."""

    hex_digest = hashlib.sha256(body).hexdigest()
    ref = Path("delta/blobs/sha256") / hex_digest[:2] / hex_digest
    target = run_root / ref
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    return ref.as_posix()


def _manifest(entries: list[dict[str, object]]) -> dict[str, object]:
    return {"targetPrefix": "entities/", "entries": entries}


def test_media_body_is_admitted_into_the_library_and_referenced_from_it(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    run_root = tmp_path / "run"
    publish_root.mkdir()
    run_root.mkdir()

    hex_digest = hashlib.sha256(_MEDIA_BODY).hexdigest()
    destination = (
        f"media/objects/sha256/{hex_digest[:2]}/{hex_digest[2:4]}/{hex_digest}.jpg"
    )
    blob_ref = _stage_blob(run_root, _MEDIA_BODY)

    apply_forward_delta(
        publish_root=publish_root,
        run_root=run_root,
        manifest=_manifest(
            [
                {
                    "destination": destination,
                    "operation": "create",
                    "blobRef": blob_ref,
                    "sha256": _digest(_MEDIA_BODY),
                    "bytes": len(_MEDIA_BODY),
                }
            ]
        ),
    )

    published = publish_root / destination
    entry = library_cas_path(MEDIA_KIND, hex_digest, suffix=".jpg")
    assert published.is_file(), "canonical media destination must exist"
    assert entry.is_file(), "media body must be admitted into the content library"
    assert published.read_bytes() == _MEDIA_BODY
    assert os.stat(published).st_ino == os.stat(entry).st_ino, (
        "canonical media must reference the library entry rather than own a "
        "second copy of the bytes"
    )


def test_reclaiming_the_run_root_leaves_the_library_owning_the_body(
    tmp_path: Path,
) -> None:
    """The whole point of admission: the body outlives its transaction run."""

    publish_root = tmp_path / "publish"
    run_root = tmp_path / "run"
    publish_root.mkdir()
    run_root.mkdir()

    hex_digest = hashlib.sha256(_MEDIA_BODY).hexdigest()
    destination = (
        f"media/objects/sha256/{hex_digest[:2]}/{hex_digest[2:4]}/{hex_digest}.jpg"
    )
    blob_ref = _stage_blob(run_root, _MEDIA_BODY)
    apply_forward_delta(
        publish_root=publish_root,
        run_root=run_root,
        manifest=_manifest(
            [
                {
                    "destination": destination,
                    "operation": "create",
                    "blobRef": blob_ref,
                    "sha256": _digest(_MEDIA_BODY),
                    "bytes": len(_MEDIA_BODY),
                }
            ]
        ),
    )

    blob = run_root / blob_ref
    blob.unlink()

    entry = library_cas_path(MEDIA_KIND, hex_digest, suffix=".jpg")
    assert entry.is_file(), "library entry must survive reclamation of the run root"
    assert (publish_root / destination).read_bytes() == _MEDIA_BODY


def test_canonical_documents_stay_outside_the_media_library(tmp_path: Path) -> None:
    publish_root = tmp_path / "publish"
    run_root = tmp_path / "run"
    publish_root.mkdir()
    run_root.mkdir()

    destination = "entities/地点/景区/测试/manifest.json"
    blob_ref = _stage_blob(run_root, _DOCUMENT_BODY)

    apply_forward_delta(
        publish_root=publish_root,
        run_root=run_root,
        manifest=_manifest(
            [
                {
                    "destination": destination,
                    "operation": "create",
                    "blobRef": blob_ref,
                    "sha256": _digest(_DOCUMENT_BODY),
                    "bytes": len(_DOCUMENT_BODY),
                }
            ]
        ),
    )

    published = publish_root / destination
    hex_digest = hashlib.sha256(_DOCUMENT_BODY).hexdigest()
    assert published.read_bytes() == _DOCUMENT_BODY
    assert not library_cas_path(MEDIA_KIND, hex_digest, suffix=".json").exists(), (
        "documents are the tree's own content and must not be addressed through "
        "the media library"
    )
