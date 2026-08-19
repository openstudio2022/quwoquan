# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-007
"""The collector keeps running after it reclaims an acquisition body.

Reclaiming staged bodies is the point of the acquisition lifecycle, so the very
next collection pass reads receipts whose bodies are gone. If the inventory
treated that as a missing reference, collection would break precisely because an
earlier collection succeeded. These tests pin the surviving distinction: a
reclaimed body is recorded as an absence, while a symlink in its place is still
damage.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from content.release.canonical import garbage_collection_inventory as inventory
from content.release.canonical.garbage_collection_reference_graph import ReferenceGraph
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)

_ACQUISITION = "data/local/workspace/source-acquisition"
_RECEIPT = "preparations/receipts/unit.json"
# A staged body is content addressed, so the path has to agree with the bytes for
# a present body to survive the inventory's own CAS check.
_BODY_BYTES = b"body"
_BODY_DIGEST = hashlib.sha256(_BODY_BYTES).hexdigest()
_BODY = f"cas/sha256/{_BODY_DIGEST[:2]}/{_BODY_DIGEST}.jpg"


def _tree(tmp_path: Path) -> tuple[ReferenceGraph, Path]:
    output_root = tmp_path / "output"
    receipt = output_root / _ACQUISITION / _RECEIPT
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"schema": "x"}), encoding="utf-8")
    graph = ReferenceGraph(
        output_root=output_root,
        publish_root=tmp_path / "publish",
        tasks={},
    )
    return graph, output_root


@pytest.fixture
def admitting_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for a loader that admitted a fully reclaimed unit.

    The loader's own three-state judgement is covered separately; here it is held
    fixed so the inventory's handling of the absent body is what gets measured.
    """

    def _loader(_ref: str, *, root: Path, require_bodies: bool) -> dict[str, Any]:
        assert require_bodies is False, (
            "the collector must admit reclaimed units rather than demand bodies"
        )
        return {"assets": [{"assetRef": _BODY}]}

    monkeypatch.setattr(
        inventory,
        "load_professional_image_acquisition_receipt",
        _loader,
    )


def test_a_reclaimed_body_is_recorded_as_an_absence(
    tmp_path: Path,
    admitting_loader: None,
) -> None:
    graph, _ = _tree(tmp_path)

    inventory.register_acquisition_inventory(graph, scan_value=lambda *a, **k: None)

    absent = [
        ref for ref, kind in graph.nodes.items() if kind == "absent_acquisition_body"
    ]
    assert absent == [f"{_ACQUISITION}/{_BODY}"], (
        "the receipt's claim on a reclaimed body must stay visible in the graph"
    )


def test_a_symlink_in_place_of_a_body_is_still_damage(
    tmp_path: Path,
    admitting_loader: None,
) -> None:
    """The collector only unlinks bodies, so a symlink is never its outcome.

    The acquisition walk rejects symlinks before it reaches the per-body check,
    which is why admitting reclaimed units does not widen the door for them.
    """

    graph, output_root = _tree(tmp_path)
    blob = output_root / _ACQUISITION / _BODY
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.symlink_to(tmp_path / "elsewhere.jpg")

    with pytest.raises(ObjectTransactionError, match="symlink"):
        inventory.register_acquisition_inventory(
            graph,
            scan_value=lambda *a, **k: None,
        )


def test_a_present_body_is_still_registered_as_a_collectable_artifact(
    tmp_path: Path,
    admitting_loader: None,
) -> None:
    graph, output_root = _tree(tmp_path)
    blob = output_root / _ACQUISITION / _BODY
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(_BODY_BYTES)

    inventory.register_acquisition_inventory(graph, scan_value=lambda *a, **k: None)

    assert graph.nodes.get(f"{_ACQUISITION}/{_BODY}") == "acquisition_cas"
