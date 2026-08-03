"""Project one immutable release's governed asset and carrier admission."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)
from governance.coverage.distribution import (
    ContentDistributionPolicy,
    DistributionDecision,
    ProductLifecycleState,
    RightsStatus,
    project_asset_admission,
)


_CARRIERS = ("homepage", "article", "image", "video")


def _object_rows(objects_root: Path, desired: Mapping[str, list[str]]) -> list[dict[str, Any]]:
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
            rights = _read_json(rights_path) if rights_path.is_file() else {"assets": []}
            raw_assets = rights.get("assets")
            if not isinstance(raw_assets, list):
                raise ObjectTransactionError(f"release object rights assets must be an array: {kind}/{ref}")
            object_ref = f"{kind}/{ref}"
            assets: list[dict[str, Any]] = []
            for raw in raw_assets:
                if not isinstance(raw, Mapping):
                    raise ObjectTransactionError(f"release rights asset must be an object: {object_ref}")
                try:
                    assets.append(project_asset_admission(raw, object_ref=object_ref))
                except (TypeError, ValueError) as exc:
                    raise ObjectTransactionError(str(exc)) from exc
            rows.append(
                {
                    "objectRef": object_ref,
                    "carrier": carrier,
                    "manifest": manifest,
                    "assets": assets,
                }
            )
    return rows


def _article_media_coverage(
    objects: list[dict[str, Any]],
    *,
    policy: ContentDistributionPolicy,
) -> dict[str, int | float]:
    articles = [row for row in objects if row["carrier"] == "article"]
    illustrated = 0
    malformed: list[str] = []
    for row in articles:
        manifest = row["manifest"]
        assets = [item for item in (manifest.get("assets") or []) if isinstance(item, Mapping)]
        image_assets = [
            item
            for item in assets
            if str(item.get("kind") or "image").strip() == "image"
        ]
        roles = {str(item.get("role") or "").strip() for item in image_assets}
        bindings = [
            item for item in (manifest.get("imageBindings") or []) if isinstance(item, Mapping)
        ]
        source_unit_refs = {
            str(item.get("sourceUnitRef") or item.get("sourceRef") or "").strip()
            for item in image_assets
        }
        has_cover = "cover" in roles
        has_body = bool(roles.intersection({"detail", "embedded"}) or len(bindings) >= 2)
        has_one_source_unit = len(source_unit_refs) == 1 and "" not in source_unit_refs
        if has_cover and has_body and len(image_assets) >= 2 and has_one_source_unit:
            illustrated += 1
        elif image_assets or str(manifest.get("publishMediaMode") or "") != "text_only":
            malformed.append(str(row["objectRef"]))
    if malformed:
        raise ObjectTransactionError(
            "article must bind same-source cover and body images: " + ", ".join(malformed[:10])
        )
    total = len(articles)
    text_only = total - illustrated
    illustrated_rate = round(illustrated / total, 6) if total else 1.0
    text_only_rate = round(text_only / total, 6) if total else 0.0
    if total and (
        illustrated_rate < policy.minimum_illustrated_rate
        or text_only_rate > policy.maximum_text_only_rate
    ):
        raise ObjectTransactionError(
            "article media coverage GATE_BLOCK: "
            f"illustrated={illustrated}/{total} ({illustrated_rate:.3f}) "
            f"textOnly={text_only}/{total} ({text_only_rate:.3f})"
        )
    return {
        "articleCount": total,
        "illustratedCount": illustrated,
        "textOnlyCount": text_only,
        "illustratedRate": illustrated_rate,
        "textOnlyRate": text_only_rate,
    }


def _creator_assets(
    objects_root: Path,
    desired: Mapping[str, list[str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for creator_ref in desired["creators"]:
        root = objects_root / "creators" / creator_ref / "rights_snapshots"
        for snapshot_path in sorted(root.glob("*.json")):
            snapshot = _read_json(snapshot_path)
            rights = snapshot.get("commercialRights")
            if not isinstance(rights, Mapping):
                raise ObjectTransactionError(
                    f"creator/{creator_ref}: avatar rights snapshot lacks commercialRights"
                )
            try:
                rows.append(
                    project_asset_admission(
                        rights,
                        object_ref=f"creators/{creator_ref}",
                    )
                )
            except (TypeError, ValueError) as exc:
                raise ObjectTransactionError(str(exc)) from exc
    return rows


def build_release_asset_admission(
    *,
    release_id: str,
    objects_root: Path,
    desired: Mapping[str, list[str]],
    policy: ContentDistributionPolicy,
) -> dict[str, Any]:
    objects = _object_rows(objects_root, desired)
    assets = [asset for row in objects for asset in row["assets"]]
    assets.extend(_creator_assets(objects_root, desired))
    asset_ids = [str(asset["assetId"]) for asset in assets]
    if any(not asset_id for asset_id in asset_ids) or len(asset_ids) != len(set(asset_ids)):
        raise ObjectTransactionError("release asset IDs must be globally unique and non-empty")
    if any(asset["generated"] for asset in assets):
        generated = [asset["assetId"] for asset in assets if asset["generated"]]
        raise ObjectTransactionError(
            "generated image/video assets are disabled by current policy: "
            + ", ".join(generated[:10])
        )
    blocked_assets = [
        asset for asset in assets if asset["distributionDecision"] == DistributionDecision.BLOCKED.value
    ]
    if blocked_assets:
        raise ObjectTransactionError(
            "release contains blocked assets: "
            + ", ".join(str(asset["assetId"]) for asset in blocked_assets[:10])
        )
    if policy.product_lifecycle_state is ProductLifecycleState.COMMERCIAL:
        noncommercial = [
            asset
            for asset in assets
            if asset["distributionDecision"] != DistributionDecision.COMMERCIAL_ALLOWED.value
        ]
        if noncommercial:
            raise ObjectTransactionError(
                "commercial release contains non-commercial assets: "
                + ", ".join(str(asset["assetId"]) for asset in noncommercial[:10])
            )
    article_coverage = _article_media_coverage(objects, policy=policy)
    rights_counts = Counter(str(asset["rightsStatus"]) for asset in assets)
    carrier_counts: list[dict[str, Any]] = []
    research_total = 0
    commercial_total = 0
    for carrier in _CARRIERS:
        carrier_objects = [row for row in objects if row["carrier"] == carrier]
        research_accepted = sum(
            all(
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
            bool(row["assets"])
            and all(
                asset["distributionDecision"] == DistributionDecision.COMMERCIAL_ALLOWED.value
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
        "releaseClass": policy.release_class.value,
        "productLifecycleState": policy.product_lifecycle_state.value,
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
        "assets": sorted(assets, key=lambda row: (str(row["objectRef"]), str(row["assetId"]))),
    }


__all__ = ["build_release_asset_admission"]
