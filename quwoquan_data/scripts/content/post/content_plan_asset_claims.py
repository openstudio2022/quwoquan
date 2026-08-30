"""Within-execution asset ownership checks for content-plan validation."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ContentPlanAssetClaims:
    """Track one-work ownership for physical assets and source collections."""

    issues: list[str]
    asset_owners: dict[str, str] = field(default_factory=dict)
    asset_sha_owners: dict[str, str] = field(default_factory=dict)
    collection_owners: dict[str, str] = field(default_factory=dict)

    def claim_asset(self, owner_ref: str, asset_ref: str) -> None:
        if not asset_ref:
            return
        previous = self.asset_owners.get(asset_ref)
        if previous and previous != owner_ref:
            self.issues.append(
                f"item[{owner_ref}]: sourceAssetRef {asset_ref!r} reused by {previous}; "
                "same execution requires one source image asset per work"
            )
        self.asset_owners.setdefault(asset_ref, owner_ref)

    def claim_asset_sha(self, owner_ref: str, asset_sha: str) -> None:
        asset_sha = asset_sha.removeprefix("sha256:").strip().lower()
        if not asset_sha:
            return
        previous = self.asset_sha_owners.get(asset_sha)
        if previous and previous != owner_ref:
            self.issues.append(
                f"item[{owner_ref}]: image sha256 {asset_sha[:16]!r} reused by {previous}; "
                "same execution requires one physical source image per work"
            )
        self.asset_sha_owners.setdefault(asset_sha, owner_ref)

    def claim_collection(self, owner_ref: str, collection_id: str) -> None:
        if not collection_id:
            return
        previous = self.collection_owners.get(collection_id)
        if previous and previous != owner_ref:
            self.issues.append(
                f"item[{owner_ref}]: sourceCollectionId {collection_id!r} reused by {previous}; "
                "same execution requires one image collection per work"
            )
        self.collection_owners.setdefault(collection_id, owner_ref)
