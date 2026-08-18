"""One-pass immutable index for accepted professional image assets."""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from content.source.professional_image_acquisition import (
    load_professional_image_acquisition_receipt,
)

_ACCEPTED = frozenset({"research_allowed", "commercial_allowed"})


@dataclass(frozen=True, slots=True)
class AcquiredImageSpecIndex:
    _encoded_specs_by_entity: Mapping[str, tuple[str, ...]]
    entity_names: tuple[str, ...]
    accepted_asset_count: int
    _encoded_work_unit_candidates: tuple[str, ...] = ()

    def specs_for_names(self, entity_names: tuple[str, ...]) -> list[dict[str, Any]]:
        for name in dict.fromkeys(
            str(value).strip() for value in entity_names if str(value).strip()
        ):
            encoded = self._encoded_specs_by_entity.get(name, ())
            if encoded:
                return [json.loads(payload) for payload in encoded]
        return []

    @property
    def work_unit_candidates(self) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(payload) for payload in self._encoded_work_unit_candidates)


def build_acquired_image_spec_index(
    receipt_refs: list[str],
    *,
    root: Path | None = None,
    descriptors: tuple[Mapping[str, Any], ...] = (),
) -> AcquiredImageSpecIndex:
    normalized_refs = tuple(str(ref).strip() for ref in receipt_refs)
    if any(not ref for ref in normalized_refs):
        raise ValueError("professional image receipt refs must be non-empty")
    if len(normalized_refs) != len(set(normalized_refs)):
        raise ValueError("professional image receipt refs must not contain duplicates")
    descriptor_by_receipt = {
        str(row.get("receiptRef") or "").strip(): dict(row)
        for row in descriptors
    }
    if descriptors and set(descriptor_by_receipt) != set(normalized_refs):
        raise ValueError("professional image descriptors must match receipt refs")

    specs_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    entity_names: list[str] = []
    work_unit_candidates: list[dict[str, Any]] = []
    seen_content: set[str] = set()
    for receipt_ref in normalized_refs:
        receipt = load_professional_image_acquisition_receipt(receipt_ref, root=root)
        descriptor = descriptor_by_receipt.get(receipt_ref)
        if descriptor is not None and descriptor.get("receiptDigest") != receipt.get("receiptDigest"):
            raise ValueError("professional image descriptor receiptDigest drift")
        for row in receipt["assets"]:
            if not isinstance(row, Mapping) or row.get("distributionDecision") not in _ACCEPTED:
                continue
            if row.get("acquisitionStatus") != "acquired":
                raise ValueError("accepted professional image was not acquired")
            spec = row.get("planImageSpec")
            if not isinstance(spec, Mapping):
                raise TypeError("accepted professional image lacks planImageSpec")
            digest = str(row.get("contentSha256") or "").strip()
            if digest in seen_content:
                raise ValueError(f"professional image cross-receipt duplicate: {digest}")
            seen_content.add(digest)
            names = tuple(
                dict.fromkeys(
                    str(value).strip()
                    for value in (
                        row.get("entityId"),
                        *(row.get("entityAliases") or []),
                    )
                    if str(value).strip()
                )
            )
            if not names:
                raise ValueError("accepted professional image lacks entity identity")
            projected = {
                **dict(spec),
                "sourceCollectionId": (
                    f"acquisition:{receipt['manifestId']}:{row['assetId']}"
                ),
                "acquisitionReceiptRef": receipt_ref,
                "professionalAssetId": str(row["assetId"]),
                "professionalContentSha256": digest,
                "researchLane": "image",
            }
            for name in names:
                if name not in specs_by_entity:
                    entity_names.append(name)
                specs_by_entity[name].append(projected)
            if descriptor is not None:
                work_unit_candidates.append(
                    {
                        "carrier": "image",
                        "manifestRef": str(descriptor["manifestRef"]),
                        "manifestDigest": str(descriptor["manifestDigest"]),
                        "receiptRef": receipt_ref,
                        "receiptDigest": str(descriptor["receiptDigest"]),
                        "assetId": str(row["assetId"]),
                        "contentSha256": digest,
                        "sourceEntityId": names[0],
                        "sourceEntityAliases": list(names[1:]),
                    }
                )
    encoded = MappingProxyType(
        {
            name: tuple(
                json.dumps(
                    spec,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                for spec in specs
            )
            for name, specs in specs_by_entity.items()
        }
    )
    return AcquiredImageSpecIndex(
        _encoded_specs_by_entity=encoded,
        entity_names=tuple(entity_names),
        accepted_asset_count=len(seen_content),
        _encoded_work_unit_candidates=tuple(
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for row in work_unit_candidates
        ),
    )


__all__ = ["AcquiredImageSpecIndex", "build_acquired_image_spec_index"]
