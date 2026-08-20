"""Canonical media bodies must be owned by the content library, not by the tree.

A delta blob lives in the transaction run root, which the collector reclaims once
the run closes. If the canonical tree took a media body from that blob, reclaiming
the run would leave the tree holding the only copy of every body it publishes, and
the library would never accumulate the bytes it is supposed to own. These tests pin
the ownership split: media bodies are admitted into the library and addressed from
the object's own JSON by digest, while canonical documents stay owned by the tree.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.object_transaction_delta import apply_forward_delta
from core.content_library import MEDIA_KIND, admit_library_entry, library_cas_path

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


def test_a_media_destination_is_refused_because_the_tree_never_owns_a_body(
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

    with pytest.raises(ObjectTransactionError, match="outside canonical roots"):
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

    assert not (publish_root / destination).exists()
    assert list(publish_root.iterdir()) == []


def test_reclaiming_the_run_root_leaves_the_library_owning_the_body(
    tmp_path: Path,
) -> None:
    """The whole point of admission: the body outlives its transaction run."""

    run_root = tmp_path / "run"
    run_root.mkdir()

    hex_digest = hashlib.sha256(_MEDIA_BODY).hexdigest()
    blob_ref = _stage_blob(run_root, _MEDIA_BODY)
    blob = run_root / blob_ref
    admit_library_entry(blob, kind=MEDIA_KIND, sha256=hex_digest)

    blob.unlink()

    entry = library_cas_path(MEDIA_KIND, hex_digest)
    assert entry.is_file(), "library entry must survive reclamation of the run root"
    assert entry.read_bytes() == _MEDIA_BODY


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
