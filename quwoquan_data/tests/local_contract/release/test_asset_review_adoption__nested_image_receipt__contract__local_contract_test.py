from __future__ import annotations

import pytest

from content.release.canonical.asset_review_adoption import _professional_identity
from content.release.canonical.object_transaction_contract import ObjectTransactionError


_SHA = "sha256:" + "a" * 64


def _image(receipt_ref: str) -> dict[str, str]:
    return {
        "acquisitionReceiptRef": receipt_ref,
        "professionalAssetId": "openverse:asset:one",
        "professionalContentSha256": _SHA,
    }


def test_image_receipt_accepts_safe_source_acquisition_nested_ref() -> None:
    receipt_ref = (
        "openverse-smoke/preparations/professional-image/receipts/"
        + "b" * 64
        + ".json"
    )

    assert _professional_identity(
        _image(receipt_ref), (), asset_kind="image"
    ) == (receipt_ref, "openverse:asset:one", _SHA)


@pytest.mark.parametrize(
    "receipt_ref",
    (
        "/tmp/receipts/receipt.json",
        "openverse-smoke/../receipts/receipt.json",
        "openverse-smoke/reviews/receipt.json",
    ),
)
def test_image_receipt_rejects_unsafe_or_wrong_nested_ref(receipt_ref: str) -> None:
    with pytest.raises(ObjectTransactionError, match="non-canonical"):
        _professional_identity(_image(receipt_ref), (), asset_kind="image")


def test_video_receipt_stays_single_canonical_receipts_segment() -> None:
    raw = {
        "professionalAcquisitionReceiptRef": (
            "provider/preparations/video/receipts/receipt.json"
        ),
        "professionalAssetId": "video-one",
        "professionalContentSha256": _SHA,
    }

    with pytest.raises(ObjectTransactionError, match="non-canonical"):
        _professional_identity(raw, (), asset_kind="video")
