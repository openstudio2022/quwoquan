#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = (
    ROOT / "quwoquan_service/services/content-service/contracts"
)

post_fields = (CONTRACT_ROOT / "content/post/fields.yaml").read_text()
media_asset_fields = (
    CONTRACT_ROOT / "media/media_asset/fields.yaml"
).read_text()
post_service = (CONTRACT_ROOT / "content/post/operations.yaml").read_text()
original_access_service = (
    CONTRACT_ROOT / "media/media_original_access_fact/operations.yaml"
).read_text()

required_post_fields = (
    "mediaUrls",
    "mediaItems",
    "coverUrl",
    "thumbnailUrl",
    "videoUrl",
)
required_media_asset_fields = (
    "objectKey",
    "sha256",
    "accessPolicy",
    "processingStatus",
)
missing = [
    f"post.{name}"
    for name in required_post_fields
    if f"name: {name}" not in post_fields
]
missing.extend(
    f"media_asset.{name}"
    for name in required_media_asset_fields
    if f"name: {name}" not in media_asset_fields
)
if "SubmitPostPublication" not in post_service:
    missing.append("SubmitPostPublication")
if "RequestOriginalImageAccess" not in original_access_service:
    missing.append("RequestOriginalImageAccess")
if missing:
    print("[media-delivery-registry] FAIL missing: " + ", ".join(missing))
    sys.exit(2)
print("[media-delivery-registry] OK")
