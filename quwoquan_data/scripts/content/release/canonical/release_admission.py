"""Project one immutable release's governed asset and carrier admission."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)
from governance.coverage.distribution import (
    DistributionDecision,
    RightsStatus,
    project_asset_admission,
)

_CARRIERS = ("homepage", "article", "image", "video")


def _content_review_approved(root: Path) -> bool:
    path = root / "content_review.json"
    if not path.is_file():
        return False
    review = _read_json(path)
    return bool(
        review.get("schema") == "quwoquan_data.content_review"
        and review.get("decision") == "approved"
    )

def _object_rows(
    objects_root: Path,
    desired: Mapping[str, list[str]],
    *,
    output_root: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for kind in ("entities", "posts"):
        for ref in desired[kind]:
            root = objects_root / kind / ref
            # manifest.json is the release-control document for both object
            # kinds. _entity.json is a consumer projection and must not be
            # required merely to classify the carrier.
            manifest = _read_json(root / "manifest.json")
            carrier = (
                "homepage"
                if kind == "entities"
                else str(manifest.get("contentType") or "").strip()
            )
            if carrier not in _CARRIERS:
                raise ObjectTransactionError(
                    f"release object carrier is invalid: {kind}/{ref}:{carrier}"
                )
            rights_path = root / "rights.json"
            rights = (
                _read_json(rights_path) if rights_path.is_file() else {"assets": []}
            )
            raw_assets = rights.get("assets")
            if not isinstance(raw_assets, list):
                raise ObjectTransactionError(
                    f"release object rights assets must be an array: {kind}/{ref}"
                )
            object_ref = f"{kind}/{ref}"
            assets: list[dict[str, Any]] = []
            for raw in raw_assets:
                if not isinstance(raw, Mapping):
                    raise ObjectTransactionError(
                        f"release rights asset must be an object: {object_ref}"
                    )
                try:
                    projected = project_asset_admission(raw, object_ref=object_ref)
                    assets.append(projected)
                except (TypeError, ValueError) as exc:
                    raise ObjectTransactionError(str(exc)) from exc
            rows.append(
                {
                    "objectRef": object_ref,
                    "carrier": carrier,
                    "manifest": manifest,
                    "assets": assets,
                    "contentReviewApproved": _content_review_approved(root),
                }
            )
    return rows


def _article_media_mode(row: Mapping[str, Any]) -> str:
    """Validate final article media facts without semantic-stage helpers."""
    object_ref = str(row["objectRef"])
    manifest = row["manifest"]
    raw_assets = manifest.get("assets")
    if not isinstance(raw_assets, list) or any(
        not isinstance(asset, Mapping) for asset in raw_assets
    ):
        raise ObjectTransactionError(
            f"{object_ref}: article manifest assets must be an array of objects"
        )
    assets = [asset for asset in raw_assets if isinstance(asset, Mapping)]
    asset_ids = [str(asset.get("assetId") or "").strip() for asset in assets]
    if any(not asset_id for asset_id in asset_ids) or len(asset_ids) != len(
        set(asset_ids)
    ):
        raise ObjectTransactionError(
            f"{object_ref}: article manifest assetIds must be unique and non-empty"
        )
    mode = str(manifest.get("publishMediaMode") or "").strip()
    if mode == "text_only":
        if assets:
            raise ObjectTransactionError(
                f"{object_ref}: text_only article carries assets"
            )
        return mode
    covers = [
        asset for asset in assets if str(asset.get("role") or "").strip() == "cover"
    ]
    bodies = [asset for asset in assets if asset not in covers]
    if (
        len(covers) != 1
        or not bodies
        or any(str(asset.get("kind") or "image").strip() != "image" for asset in assets)
        or any(not str(asset.get("sourceRef") or "").strip() for asset in assets)
    ):
        raise ObjectTransactionError(
            f"{object_ref}: illustrated article must bind one cover and body assets"
        )
    return "illustrated"


def _article_media_coverage(
    objects: list[dict[str, Any]],
) -> dict[str, int | float]:
    articles = [row for row in objects if row["carrier"] == "article"]
    illustrated = 0
    for row in articles:
        if _article_media_mode(row) == "illustrated":
            illustrated += 1
    total = len(articles)
    text_only = total - illustrated
    illustrated_rate = round(illustrated / total, 6) if total else 1.0
    text_only_rate = round(text_only / total, 6) if total else 0.0
    return {
        "articleCount": total,
        "illustratedCount": illustrated,
        "textOnlyCount": text_only,
        "illustratedRate": illustrated_rate,
        "textOnlyRate": text_only_rate,
    }


def _object_media_is_admissible(row: Mapping[str, Any]) -> bool:
    """Validate the selected object's media/rights closure before counting it.

    ``rights.json`` describes distribution admission; it is not proof that the
    object manifest actually exposes the corresponding media.  In particular,
    ``all([])`` must never turn an empty homepage/image/video into an accepted
    object.  The manifest and rights asset IDs therefore form one exact set.
    """

    object_ref = str(row["objectRef"])
    carrier = str(row["carrier"])
    manifest = row["manifest"]
    raw_manifest_assets = manifest.get("assets")
    if not isinstance(raw_manifest_assets, list):
        raise ObjectTransactionError(
            f"release object manifest assets must be an array: {object_ref}"
        )
    manifest_assets: list[Mapping[str, Any]] = []
    manifest_asset_ids: list[str] = []
    for raw in raw_manifest_assets:
        if not isinstance(raw, Mapping):
            raise ObjectTransactionError(
                f"release manifest asset must be an object: {object_ref}"
            )
        asset_id = str(raw.get("assetId") or "").strip()
        if not asset_id:
            raise ObjectTransactionError(
                f"release manifest assetId is missing: {object_ref}"
            )
        manifest_assets.append(raw)
        manifest_asset_ids.append(asset_id)
    if len(manifest_asset_ids) != len(set(manifest_asset_ids)):
        raise ObjectTransactionError(
            f"release manifest asset IDs must be unique: {object_ref}"
        )
    rights_asset_ids = [str(asset["assetId"]) for asset in row["assets"]]
    if set(manifest_asset_ids) != set(rights_asset_ids):
        raise ObjectTransactionError(
            f"release object manifest/rights asset closure drift: {object_ref}"
        )

    if carrier == "article":
        text_only = str(manifest.get("publishMediaMode") or "").strip() == "text_only"
        return not manifest_assets if text_only else bool(manifest_assets)
    if carrier == "homepage":
        text_only = str(manifest.get("publishMediaMode") or "").strip() == "text_only"
        return not manifest_assets if text_only else any(
            str(asset.get("kind") or "image").strip() == "image"
            for asset in manifest_assets
        )
    if carrier == "image":
        return any(
            str(asset.get("kind") or "image").strip() == "image"
            for asset in manifest_assets
        )
    if carrier == "video":
        by_id = {
            str(asset.get("assetId") or "").strip(): asset for asset in manifest_assets
        }
        for asset in manifest_assets:
            if str(asset.get("kind") or "").strip() != "video":
                continue
            mime_type = str(asset.get("mimeType") or "").strip().lower()
            sha256 = str(asset.get("sha256") or "").strip()
            poster = by_id.get(str(asset.get("posterAssetId") or "").strip())
            if (
                mime_type.startswith("video/")
                and sha256.startswith("sha256:")
                and bool(row.get("contentReviewApproved"))
                and isinstance(poster, Mapping)
                and str(poster.get("kind") or "").strip() == "image"
                and str(poster.get("role") or "").strip() == "cover"
            ):
                return True
        return False
    return False


def build_release_asset_admission(
    *,
    release_id: str,
    objects_root: Path,
    desired: Mapping[str, list[str]],
    release_class: str,
    output_root: Path | None = None,
) -> dict[str, Any]:
    if output_root is None:
        from core import paths as core_paths

        output_root = core_paths.OUTPUT_ROOT
    release_mode = str(release_class or "").strip()
    if release_mode not in {"research", "commercial"}:
        raise ObjectTransactionError(f"DATA.RELEASE.CLASS_INVALID: {release_mode!r}")
    objects = _object_rows(objects_root, desired, output_root=output_root)
    assets = [asset for row in objects for asset in row["assets"]]
    asset_ids = [str(asset["assetId"]) for asset in assets]
    if any(not asset_id for asset_id in asset_ids) or len(asset_ids) != len(
        set(asset_ids)
    ):
        raise ObjectTransactionError(
            "release asset IDs must be globally unique and non-empty"
        )
    if any(asset["generated"] for asset in assets):
        generated = [asset["assetId"] for asset in assets if asset["generated"]]
        raise ObjectTransactionError(
            "generated image/video assets are disabled by current policy: "
            + ", ".join(generated[:10])
        )
    blocked_assets = [
        asset
        for asset in assets
        if asset["distributionDecision"] == DistributionDecision.BLOCKED.value
    ]
    if blocked_assets:
        raise ObjectTransactionError(
            "release contains blocked assets: "
            + ", ".join(str(asset["assetId"]) for asset in blocked_assets[:10])
        )
    if release_mode == "commercial":
        noncommercial = [
            asset
            for asset in assets
            if asset["distributionDecision"]
            != DistributionDecision.COMMERCIAL_ALLOWED.value
        ]
        if noncommercial:
            raise ObjectTransactionError(
                "commercial release contains non-commercial assets: "
                + ", ".join(str(asset["assetId"]) for asset in noncommercial[:10])
            )
    article_coverage = _article_media_coverage(objects)
    rights_counts = Counter(str(asset["rightsStatus"]) for asset in assets)
    carrier_counts: list[dict[str, Any]] = []
    research_total = 0
    commercial_total = 0
    for carrier in _CARRIERS:
        carrier_objects = [row for row in objects if row["carrier"] == carrier]
        media_admission = {
            str(row["objectRef"]): _object_media_is_admissible(row)
            for row in carrier_objects
        }
        missing_media = [
            object_ref
            for object_ref, accepted in media_admission.items()
            if not accepted
        ]
        if missing_media:
            raise ObjectTransactionError(
                f"{carrier} required media closure GATE_BLOCK: "
                + ", ".join(missing_media[:10])
            )
        research_accepted = sum(
            media_admission[str(row["objectRef"])]
            and all(
                asset["distributionDecision"]
                in {
                    DistributionDecision.RESEARCH_ALLOWED.value,
                    DistributionDecision.COMMERCIAL_ALLOWED.value,
                }
                for asset in row["assets"]
            )
            for row in carrier_objects
        )
        commercial_accepted = sum(
            media_admission[str(row["objectRef"])]
            and all(
                asset["distributionDecision"]
                == DistributionDecision.COMMERCIAL_ALLOWED.value
                for asset in row["assets"]
            )
            for row in carrier_objects
        )
        research_total += research_accepted
        commercial_total += commercial_accepted
        carrier_counts.append(
            {
                "carrier": carrier,
                "objectCount": len(carrier_objects),
                "assetCount": sum(len(row["assets"]) for row in carrier_objects),
                "researchAcceptedCount": research_accepted,
                "commercialAcceptedCount": commercial_accepted,
            }
        )
    by_provider: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for asset in assets:
        provider = str(asset["platform"])
        display_name = provider
        by_provider[(display_name, provider)].append(asset)
    source_counts: list[dict[str, Any]] = []
    for (display_name, provider), rows in sorted(by_provider.items()):
        provider_rights = Counter(str(row["rightsStatus"]) for row in rows)
        accepted_count = sum(
            row["distributionDecision"] != DistributionDecision.BLOCKED.value
            for row in rows
        )
        # These counts describe the immutable release closure. Discovery-stage
        # rejections remain in source-unit funnel receipts and are never guessed.
        source_counts.append(
            {
                "displayName": display_name,
                "provider": provider,
                "plannedAssetCount": len(rows),
                "discoveredAssetCount": len(rows),
                "downloadedAssetCount": len(rows),
                "acceptedAssetCount": accepted_count,
                "rejectedAssetCount": len(rows) - accepted_count,
                "verifiedAssetCount": provider_rights[RightsStatus.VERIFIED.value],
                "unverifiedAssetCount": provider_rights[RightsStatus.UNVERIFIED.value],
                "restrictedAssetCount": provider_rights[RightsStatus.RESTRICTED.value],
                "unknownAssetCount": provider_rights[RightsStatus.UNKNOWN.value],
            }
        )
    authorization_required_ids = sorted(
        str(asset["assetId"]) for asset in assets if asset["authorizationRequired"]
    )
    return {
        "schema": "quwoquan_data.release_asset_admission",
        "releaseId": release_id,
        "releaseClass": release_mode,
        "productLifecycleState": release_mode,
        "containsUnverifiedAssets": bool(authorization_required_ids),
        "rightsStatusCounts": {
            status.value: rights_counts[status.value] for status in RightsStatus
        },
        "authorizationRequiredAssetIds": authorization_required_ids,
        "researchAcceptedCount": research_total,
        "commercialAcceptedCount": commercial_total,
        "carrierCounts": carrier_counts,
        "articleMediaCoverage": article_coverage,
        "sourceAssetCounts": source_counts,
        "assets": sorted(
            assets, key=lambda row: (str(row["objectRef"]), str(row["assetId"]))
        ),
    }


__all__ = ["build_release_asset_admission"]
