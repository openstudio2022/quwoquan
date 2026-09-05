"""A missing acquisition body is either a finished collection or damage.

Acquisition receipts outlive their bodies: once an object adopts a body it holds
the rights evidence itself and the content library owns the bytes, so the staged
copy becomes reclaimable. That makes "the file is not there" ambiguous, and these
tests pin the three states apart — every body present, every body reclaimed, and
the mixed shape that no collection can produce.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from content.source.acquisition_body_state import (
    ReclaimedBody,
    assert_unit_reclamation_is_total,
)
from content.source.professional_image_receipt_validation import _resolved_cas_asset

_LABEL = "unit under test"


def _row(digest: str) -> dict[str, object]:
    return {
        "assetId": "asset-001",
        "contentSha256": f"sha256:{digest}",
        "assetRef": f"cas/sha256/{digest[:2]}/{digest}.jpg",
        "bytes": 1,
        "mimeType": "image/jpeg",
        "width": 1,
        "height": 1,
    }


def _digest(marker: str) -> str:
    return hashlib.sha256(marker.encode()).hexdigest()


def test_a_fully_present_unit_is_not_reclaimed() -> None:
    assert_unit_reclamation_is_total(
        [Path("a.jpg"), Path("b.jpg")],
        label=_LABEL,
    )


def test_a_fully_reclaimed_unit_is_accepted_as_a_tombstone() -> None:
    assert_unit_reclamation_is_total(
        [ReclaimedBody(asset_ref="a.jpg"), ReclaimedBody(asset_ref="b.jpg")],
        label=_LABEL,
    )


def test_a_partially_reclaimed_unit_is_corruption() -> None:
    """No collection produces a mixed unit, so it must stay fail-closed."""

    with pytest.raises(ValueError, match="partially reclaimed") as caught:
        assert_unit_reclamation_is_total(
            [Path("present.jpg"), ReclaimedBody(asset_ref="gone.jpg")],
            label=_LABEL,
        )
    # The failure has to name what is missing, not just report a count.
    assert "gone.jpg" in str(caught.value)
    assert "present.jpg" in str(caught.value)


def test_a_reclaimed_body_is_distinguishable_from_a_never_acquired_one() -> None:
    """Absence and failure must not collapse onto one value.

    ``None`` means the asset was never acquired, which is a failure for an
    accepted asset. A reclaimed body was acquired, adopted, then released, and it
    carries the ref that identifies it.
    """

    reclaimed = ReclaimedBody(asset_ref="cas/sha256/ab/abcd.jpg")
    assert reclaimed is not None
    assert not isinstance(reclaimed, Path)
    assert reclaimed.asset_ref == "cas/sha256/ab/abcd.jpg"


def test_strict_readers_still_refuse_a_missing_body(tmp_path: Path) -> None:
    digest = _digest("strict")
    with pytest.raises(ValueError, match="CAS asset is missing"):
        _resolved_cas_asset(
            _row(digest),
            resolved_root=tmp_path,
            min_image_bytes=1,
            max_image_bytes=10_000_000,
            require_bodies=True,
        )


def test_lenient_readers_report_a_missing_body_as_reclaimed(tmp_path: Path) -> None:
    digest = _digest("lenient")
    body = _resolved_cas_asset(
        _row(digest),
        resolved_root=tmp_path,
        min_image_bytes=1,
        max_image_bytes=10_000_000,
        require_bodies=False,
    )
    assert body == ReclaimedBody(asset_ref=f"cas/sha256/{digest[:2]}/{digest}.jpg")


def test_a_symlinked_body_is_invalid_even_for_lenient_readers(tmp_path: Path) -> None:
    """The collector only unlinks bodies in place, so a symlink is never its work."""

    digest = _digest("symlink")
    relative = Path(f"cas/sha256/{digest[:2]}/{digest}.jpg")
    target = tmp_path / "elsewhere.jpg"
    target.write_bytes(b"x")
    link = tmp_path / relative
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)

    with pytest.raises(ValueError, match="CAS asset is invalid"):
        _resolved_cas_asset(
            _row(digest),
            resolved_root=tmp_path,
            min_image_bytes=1,
            max_image_bytes=10_000_000,
            require_bodies=False,
        )
