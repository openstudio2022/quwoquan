# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-007
"""Acquisition bodies are reclaimable; acquisition evidence is not.

Acquisition used to be retained as one indivisible population, so the fetched
bodies could never be collected and the acquisition tree grew without bound. The
two populations have opposite rules: a receipt or manifest is the irreplaceable
record of what was fetched under which rights, while a fetched body is a staging
copy of bytes the content library owns once an object adopts them. These tests
pin that split so neither side can quietly drift back into the other.
"""

from __future__ import annotations

from content.release.canonical.garbage_collection_reference_graph import (
    _is_reclaimable_ref,
)

_ACQUISITION = "data/local/workspace/source-acquisition"


def test_fetched_bodies_are_reclaimable() -> None:
    assert _is_reclaimable_ref(f"{_ACQUISITION}/video/cas/abcd.mp4")
    assert _is_reclaimable_ref(f"{_ACQUISITION}/homepage-article-source-ready/m100/x.jpg")
    assert _is_reclaimable_ref(f"{_ACQUISITION}/candidates/pool/body.webp")


def test_acquisition_documents_are_never_reclaimable() -> None:
    """Losing one of these is real corruption, not a completed collection."""

    assert not _is_reclaimable_ref(f"{_ACQUISITION}/video/receipts/r.json")
    assert not _is_reclaimable_ref(f"{_ACQUISITION}/manifests/m.json")
    assert not _is_reclaimable_ref(f"{_ACQUISITION}/video/manifests/nested/m.json")
    # Evidence is a record too, even though it sits under neither well-known
    # segment; the split is document versus body, not directory name.
    assert not _is_reclaimable_ref(f"{_ACQUISITION}/evidence/missing.json")
    assert not _is_reclaimable_ref(f"{_ACQUISITION}/candidates/plan.json")


def test_cache_root_keeps_its_existing_reclaimable_semantics() -> None:
    assert _is_reclaimable_ref("data/local/cache/content-campaign-workspaces/w/x.bin")
    assert _is_reclaimable_ref("data/local/cache/reliabletask-observer-binaries/o")


def test_governed_trees_outside_the_reclaimable_roots_stay_fatal() -> None:
    """A missing task or release reference is still corruption."""

    assert not _is_reclaimable_ref("data/tasks/some-execution/object/manifest.json")
    assert not _is_reclaimable_ref("data/releases/some-release/payload/release.json")
    assert not _is_reclaimable_ref("data/local/workspace/object-transactions/t/x.json")
