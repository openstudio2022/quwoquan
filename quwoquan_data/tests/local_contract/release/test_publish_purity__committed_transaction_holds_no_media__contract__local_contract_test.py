"""A committed object transaction leaves zero media bytes in canonical publish.

This is the exit anchor for "canonical publish never owns the bytes it shows".
Purity gates judge a tree someone else built; this judges the producer: run one
real transaction against an empty publish root and ask what it actually landed.
The tree must come back holding documents only, while every body the object
cites is reachable in the content library under the digest that document froze.

The transaction core is exercised directly — freeze the delta, then apply it —
because that is the single place that decides which of a package's files become
canonical files, and it is the decision this anchor is about.
"""

from __future__ import annotations

import json
from pathlib import Path

from content.release.canonical.canonical_inventory import load_or_bootstrap_inventory
from content.release.canonical.object_transaction_delta import (
    apply_forward_delta,
    build_transaction_delta,
)
from core.content_library import MEDIA_KIND, library_cas_root, resolve_media_holding
from support.object_transaction_fixtures import (
    CREATOR_ID,
    OBJECT_REF,
    TAG_REF,
    TRANSACTION_ID,
    build_canonical,
    build_package,
)

# Named here rather than imported from the contract so the anchor keeps its own
# statement of what a media body is: a test that asked production for the answer
# would still pass if production narrowed it.
MEDIA_SUFFIXES = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".avif",
        ".mp4",
        ".webm",
        ".mov",
        ".m4v",
        ".mp3",
        ".m4a",
    }
)


def _frozen_package(package_root: Path) -> dict[str, object]:
    """Read the package the fixture froze into the shape the delta consumes."""

    package = json.loads(
        (package_root / "object_transaction_package.json").read_text(encoding="utf-8")
    )
    closure = package["closure"]
    return {
        "transactionId": package["transactionId"],
        "executionId": package["executionId"],
        "objectKind": package["target"]["objectKind"],
        "objectRef": package["target"]["objectRef"],
        "objectRoot": package_root / package["target"]["packageObjectRef"],
        "creatorRefs": closure["creatorRefs"],
        "tagRefs": closure["tagRefs"],
        "casRows": closure["casRefs"],
    }


def _publish_files(publish_root: Path) -> list[Path]:
    return sorted(
        path for path in publish_root.rglob("*") if path.is_file()
    )


def test_committed_transaction_leaves_no_media_bytes_in_canonical_publish(
    tmp_path: Path,
) -> None:
    publish = build_canonical(tmp_path)
    package_root = build_package(tmp_path, publish)
    run_root = tmp_path / "run"

    delta, _after_inventory = build_transaction_delta(
        publish_root=publish,
        run_root=run_root,
        package_root=package_root,
        package=_frozen_package(package_root),
        before_inventory=load_or_bootstrap_inventory(publish),
    )
    apply_forward_delta(publish_root=publish, run_root=run_root, manifest=delta)

    assert (publish / "entities" / OBJECT_REF / "manifest.json").is_file()
    assert (publish / "creators" / CREATOR_ID / "_creator.json").is_file()
    assert (publish / "tags" / TAG_REF / "_definition.json").is_file()

    bodies = [
        path
        for path in _publish_files(publish)
        if path.suffix.casefold() in MEDIA_SUFFIXES
    ]
    assert bodies == [], [path.relative_to(publish).as_posix() for path in bodies]
    assert not (publish / "media").exists()

    # The delta is the audited record of the commit, so the absence has to hold
    # there too: a body that never appears as a destination is one that no
    # replay of this transaction can put back.
    assert [
        row["destination"]
        for row in delta["entries"]
        if Path(str(row["destination"])).suffix.casefold() in MEDIA_SUFFIXES
    ] == []


def test_published_object_reaches_its_body_through_the_content_library(
    tmp_path: Path,
) -> None:
    publish = build_canonical(tmp_path)
    package_root = build_package(tmp_path, publish)
    run_root = tmp_path / "run"
    source_body = (package_root / "cas/image.jpg").read_bytes()

    delta, _after_inventory = build_transaction_delta(
        publish_root=publish,
        run_root=run_root,
        package_root=package_root,
        package=_frozen_package(package_root),
        before_inventory=load_or_bootstrap_inventory(publish),
    )
    apply_forward_delta(publish_root=publish, run_root=run_root, manifest=delta)

    manifest = json.loads(
        (publish / "entities" / OBJECT_REF / "manifest.json").read_text(encoding="utf-8")
    )
    asset = manifest["assets"][0]
    # Publish keeps the reference the consumer resolves, and only the reference.
    assert not (publish / str(asset["objectKey"])).exists()

    entry = resolve_media_holding(
        str(asset["sha256"]),
        expected_bytes=int(asset["bytes"]),
    )

    assert entry.is_relative_to(library_cas_root(MEDIA_KIND))
    assert entry.read_bytes() == source_body
