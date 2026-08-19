"""One-pass immutable index for accepted professional video assets."""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from content.source.professional_video_popularity import popularity_sort_key
from content.source.professional_video_receipt import (
    ACCEPTED_DECISIONS,
    _assert_publish_grade_video,
    load_professional_video_acquisition_receipt,
)


@dataclass(frozen=True, slots=True)
class AcquiredVideoSpecIndex:
    """Immutable projection built after one fail-closed receipt/CAS verification."""

    _encoded_specs_by_entity: Mapping[str, tuple[str, ...]]
    entity_names: tuple[str, ...]
    accepted_asset_count: int
    _encoded_exclusions: tuple[str, ...] = ()
    _encoded_work_unit_candidates: tuple[str, ...] = ()

    def specs_for_entity(self, entity_id: str) -> list[dict[str, Any]]:
        encoded = self._encoded_specs_by_entity.get(str(entity_id).strip(), ())
        return [json.loads(payload) for payload in encoded]

    def specs_for_names(self, entity_names: tuple[str, ...]) -> list[dict[str, Any]]:
        """Resolve canonical name then aliases without re-reading frozen bytes."""
        for entity_name in dict.fromkeys(
            str(value).strip() for value in entity_names if str(value).strip()
        ):
            specs = self.specs_for_entity(entity_name)
            if specs:
                return specs
        return []

    @property
    def exclusions(self) -> tuple[dict[str, str], ...]:
        return tuple(json.loads(payload) for payload in self._encoded_exclusions)

    @property
    def work_unit_candidates(self) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(payload) for payload in self._encoded_work_unit_candidates)


def build_acquired_video_spec_index(
    receipt_refs: list[str],
    *,
    root: Path | None = None,
    require_popularity_ranking: bool = False,
    work_unit_bindings: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> AcquiredVideoSpecIndex:
    """Verify each frozen receipt once and index accepted assets by entity/alias."""
    normalized_refs = tuple(str(ref).strip() for ref in receipt_refs)
    if any(not ref for ref in normalized_refs):
        raise ValueError("professional video receipt refs must be non-empty")
    if len(normalized_refs) != len(set(normalized_refs)):
        raise ValueError("professional video receipt refs must not contain duplicates")

    specs_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_content_digests: set[str] = set()
    entity_names: list[str] = []
    exclusions: list[dict[str, str]] = []
    work_unit_candidates: list[dict[str, Any]] = []
    verified_asset_digests: dict[Path, str] = {}
    for receipt_ref in normalized_refs:
        receipt = load_professional_video_acquisition_receipt(
            receipt_ref,
            root=root,
            _verified_asset_digests=verified_asset_digests,
        )
        for row in receipt["assets"]:
            if row["distributionDecision"] not in ACCEPTED_DECISIONS:
                continue
            try:
                _assert_publish_grade_video(
                    row,
                    require_popularity_ranking=require_popularity_ranking,
                )
                spec = row["planVideoSpec"]
                if not isinstance(spec, Mapping):
                    raise TypeError(
                        "accepted professional video lacks planVideoSpec: "
                        f"{row['assetId']}"
                    )
            except (TypeError, ValueError) as exc:
                if require_popularity_ranking:
                    raise
                exclusions.append(
                    {
                        "assetId": str(row.get("assetId") or ""),
                        "entityId": str(row.get("entityId") or ""),
                        "code": "DATA.SOURCE.PLAN_SPEC_INVALID",
                        "reason": str(exc),
                    }
                )
                continue
            digest = str(row["contentSha256"])
            if digest in seen_content_digests:
                exclusions.append(
                    {
                        "assetId": str(row.get("assetId") or ""),
                        "entityId": str(row.get("entityId") or ""),
                        "code": "DATA.SOURCE.DUPLICATE_ASSET",
                        "reason": f"professional video cross-receipt duplicate: {digest}",
                    }
                )
                continue
            seen_content_digests.add(digest)
            binding = (
                work_unit_bindings.get((receipt_ref, str(row["assetId"])))
                if work_unit_bindings is not None
                else None
            )
            if work_unit_bindings is not None and binding is None:
                raise ValueError(
                    "accepted professional video is absent from its frozen manifest"
                )
            if binding is not None and str(binding.get("sourceEntityId") or "") != str(
                row.get("entityId") or ""
            ):
                raise ValueError("professional video manifest/receipt entity identity drift")
            frozen_names = [
                str(row.get("entityId") or "").strip(),
                *(
                    str(value).strip()
                    for value in (
                        binding.get("sourceEntityAliases")
                        if binding is not None
                        else row.get("entityAliases") or []
                    )
                    if str(value).strip()
                ),
            ]
            frozen_names = list(dict.fromkeys(name for name in frozen_names if name))
            if not frozen_names:
                raise ValueError(
                    f"accepted professional video lacks entity identity: {row['assetId']}"
                )
            for entity_name in frozen_names:
                if entity_name not in specs_by_entity:
                    entity_names.append(entity_name)
                specs_by_entity[entity_name].append(dict(spec))
            if binding is not None:
                work_unit_candidates.append(
                    {
                        "carrier": "video",
                        "manifestRef": str(binding["manifestRef"]),
                        "manifestDigest": str(binding["manifestDigest"]),
                        "receiptRef": receipt_ref,
                        "receiptDigest": str(binding["receiptDigest"]),
                        "assetId": str(row["assetId"]),
                        "contentSha256": digest,
                        "sourceEntityId": frozen_names[0],
                        "sourceEntityAliases": frozen_names[1:],
                    }
                )

    encoded = {
        entity_name: tuple(
            json.dumps(
                spec,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for spec in sorted(specs, key=popularity_sort_key)
        )
        for entity_name, specs in specs_by_entity.items()
    }
    return AcquiredVideoSpecIndex(
        _encoded_specs_by_entity=MappingProxyType(encoded),
        entity_names=tuple(entity_names),
        accepted_asset_count=len(seen_content_digests),
        _encoded_exclusions=tuple(
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for row in exclusions
        ),
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


def acquired_video_specs_for_entity(
    receipt_refs: list[str],
    *,
    entity_id: str,
    root: Path | None = None,
    require_popularity_ranking: bool = False,
) -> list[dict[str, Any]]:
    """Project playable research assets; scale callers can require real ranking."""
    return build_acquired_video_spec_index(
        receipt_refs,
        root=root,
        require_popularity_ranking=require_popularity_ranking,
    ).specs_for_entity(entity_id)


__all__ = [
    "AcquiredVideoSpecIndex",
    "acquired_video_specs_for_entity",
    "build_acquired_video_spec_index",
]
