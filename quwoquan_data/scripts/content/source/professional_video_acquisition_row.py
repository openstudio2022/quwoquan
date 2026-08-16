"""Empty acquisition-row projection for governed videos."""

from __future__ import annotations

from pathlib import Path

from content.source.professional_video_acquisition import (
    AcquisitionStatus,
    Any,
    DistributionDecision,
    Mapping,
    RightsStatus,
    initial_popularity_signals,
    redact_sensitive_video_url,
)


def _empty_row(item: Mapping[str, Any], *, rights: RightsStatus) -> dict[str, Any]:
    row = {
        **{
            key: item[key]
            for key in (
                "assetId",
                "entityId",
                "observedEntityId",
                "provider",
                "platform",
                "displayName",
                "sourceKind",
                "acquisitionPath",
                "sourceUrl",
                "assetUrl",
                "manualFile",
                "apiEvidence",
                "accessEvidence",
                "title",
                "relevance",
                "creator",
                "capturedAt",
                "license",
                "termsUrl",
                "authorizationProof",
                "rightsIssues",
                "modelReleaseStatus",
                "propertyReleaseStatus",
                "safetyReview",
            )
        },
        "acquisitionStatus": AcquisitionStatus.BLOCKED.value,
        "rightsStatus": rights.value,
        "authorizationRequired": rights is not RightsStatus.VERIFIED
        or not str(item["authorizationProof"]).strip(),
        "distributionDecision": DistributionDecision.BLOCKED.value,
        "contentSha256": "",
        "assetRef": "",
        "bytes": 0,
        "mediaProbe": None,
        "duplicateOf": "",
        "failureCode": "",
        "failure": "",
        "popularitySignals": initial_popularity_signals(
            dict(item["popularitySignals"])
        ),
        "planVideoSpec": None,
        "popularCandidateId": str(item.get("popularCandidateId") or ""),
        "popularCatalogRef": str(item.get("popularCatalogRef") or ""),
        "popularCatalogDigest": str(item.get("popularCatalogDigest") or ""),
        "popularCatalogFileSha256": str(item.get("popularCatalogFileSha256") or ""),
    }
    for field in (
        "sourceUrl",
        "assetUrl",
        "apiEvidence",
        "termsUrl",
        "authorizationProof",
    ):
        row[field] = redact_sensitive_video_url(str(row[field]))
    return row


def _receipt_source_identity_header(path: Path) -> tuple[str, str, str]:
    from content.source.professional_video_acquisition import (
        Mapping,
        read_json,
    )

    """Read only the immutable identity header before current-schema validation.

    Historical receipts from another source identity are not candidates for
    deduplication and may predate the current receipt body schema.  A malformed
    header still fails closed because its identity cannot be proven foreign.
    """
    document = read_json(path)
    if not isinstance(document, Mapping):
        raise TypeError(
            f"professional video acquisition receipt header must be an object: {path}"
        )
    if document.get("schema") != "quwoquan_data.professional_video_acquisition_receipt":
        raise ValueError(
            f"professional video acquisition receipt header schema is invalid: {path}"
        )
    values: list[str] = []
    for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest"):
        value = document.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "professional video acquisition receipt identity header is invalid: "
                f"{path} field={field}"
            )
        values.append(value)
    return values[0], values[1], values[2]


def _prior_content_index(
    output_root: Path,
    *,
    current_receipt: Path,
    source_identity: tuple[str, str, str],
) -> dict[str, str]:
    from content.source.professional_video_acquisition import (
        load_professional_video_acquisition_receipt,
    )

    index: dict[str, str] = {}
    receipts = output_root / "receipts"
    if not receipts.is_dir():
        return index
    for path in sorted(receipts.glob("*.json")):
        if path.resolve() == current_receipt.resolve():
            continue
        ref = path.relative_to(output_root).as_posix()
        if _receipt_source_identity_header(path) != source_identity:
            continue
        receipt = load_professional_video_acquisition_receipt(ref, root=output_root)
        for row in receipt["assets"]:
            digest = str(row.get("contentSha256") or "")
            if row.get("acquisitionStatus") == "acquired" and digest:
                index.setdefault(digest, f"{ref}#{row['assetId']}")
    return index
