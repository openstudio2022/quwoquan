"""A release holds media by reference; integrity is library reachability.

Locks the two separable closures a release carries. ``objects_merkle`` must stay
insensitive to media so two releases that decided the same objects stay
comparable, and ``media_holdings_digest`` must bind the holdings so a substituted
body cannot pass. ``verify_release_holdings`` must fail closed when the library
can no longer honour a recorded holding, which is the check that replaces
"the payload bytes are present" once bodies are owned once by the library.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from core.content_library import library_cas_path, link_from_library  # noqa: E402
from core.release_layout import (  # noqa: E402
    media_holdings_digest,
    objects_merkle,
    payload_file,
    release_holdings,
    verify_release_holdings,
)


def _release_with_media(root: Path, *, bodies: dict[str, bytes]) -> None:
    objects = payload_file(root, "objects")
    objects.mkdir(parents=True, exist_ok=True)
    (objects / "post.json").write_text('{"ref": "post-1"}', encoding="utf-8")
    staging = root.parent / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    for name, body in bodies.items():
        source = staging / name
        source.write_bytes(body)
        link_from_library(source, payload_file(root, f"media/{name}"), kind="media")


def test_objects_merkle_ignores_media_so_closures_stay_comparable(tmp_path: Path) -> None:
    first = tmp_path / "releases" / "r1"
    second = tmp_path / "releases" / "r2"
    _release_with_media(first, bodies={"a.jpg": b"cover-a"})
    _release_with_media(second, bodies={"a.jpg": b"cover-a", "b.jpg": b"cover-b"})

    assert objects_merkle(first) == objects_merkle(second)
    assert media_holdings_digest(first) != media_holdings_digest(second)


def test_holdings_record_the_library_address_of_every_media_body(tmp_path: Path) -> None:
    release = tmp_path / "releases" / "r1"
    _release_with_media(release, bodies={"a.jpg": b"cover-a"})

    holdings = release_holdings(release)
    assert [path for path, _digest, _size in holdings] == ["a.jpg"]
    _path, digest, size = holdings[0]
    assert size == len(b"cover-a")
    # The digest is simultaneously the content identity and the library address.
    assert library_cas_path("media", digest).is_file()
    assert verify_release_holdings(release) == ()


def test_media_holdings_digest_rejects_a_substituted_body(tmp_path: Path) -> None:
    release = tmp_path / "releases" / "r1"
    _release_with_media(release, bodies={"a.jpg": b"cover-a"})
    frozen = media_holdings_digest(release)

    held = payload_file(release, "media/a.jpg")
    held.unlink()
    substitute = tmp_path / "substitute.jpg"
    substitute.write_bytes(b"cover-tampered")
    link_from_library(substitute, held, kind="media")

    assert media_holdings_digest(release) != frozen


def test_verify_release_holdings_fails_closed_when_the_library_drops_an_entry(
    tmp_path: Path,
) -> None:
    release = tmp_path / "releases" / "r1"
    _release_with_media(release, bodies={"a.jpg": b"cover-a"})
    _path, digest, _size = release_holdings(release)[0]

    entry = library_cas_path("media", digest)
    entry.unlink()

    issues = verify_release_holdings(release)
    assert len(issues) == 1
    assert "not reachable in the content library" in issues[0]
    assert digest in issues[0]


def test_a_release_reference_and_its_library_entry_are_one_body(tmp_path: Path) -> None:
    release = tmp_path / "releases" / "r1"
    _release_with_media(release, bodies={"a.jpg": b"cover-a"})
    _path, digest, _size = release_holdings(release)[0]

    held = payload_file(release, "media/a.jpg")
    entry = library_cas_path("media", digest)
    assert held.stat().st_ino == entry.stat().st_ino
    # Referenced bodies are immutable: a holding cannot be edited in place.
    with pytest.raises(PermissionError):
        held.write_bytes(b"cover-tampered")
