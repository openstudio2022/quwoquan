"""Build and promote approved post objects through the canonical transaction."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.asset_review_adoption import (
    adopt_independent_asset_review,
)
from content.release.canonical.content_pool_record import (
    append_pool_record,
    build_canonical_pool_record,
    build_content_pool_fields,
)
from content.release.canonical.creator_projection import (
    project_creator_object,
)
from content.release.canonical.image_identity import (
    canonical_asset_manifest_row,
)
from content.release.canonical.object_source_identity import (
    freeze_execution_source_identity,
)
from content.release.canonical.object_transaction_contract import (
    EXPECTED_OBJECT_SCHEMAS,
    LAYOUT_SCHEMA,
    PACKAGE_SCHEMA,
    ObjectTransactionError,
    _closure_digest,
    _digest_file,
    _execution_id,
    _read_json,
    _review_binding,
    _safe_id,
    _safe_rel,
    _tree_digest,
    _write_json,
)
from content.release.canonical.post_asset_identity import (
    freeze_canonical_video_poster_identities,
)
from content.release.canonical.post_transaction_assets import (
    asset_sources as _asset_sources,
)
from content.release.canonical.post_transaction_assets import (
    source_assets as _source_assets,
)
from content.release.canonical.post_transaction_media import (
    copy_post_surface as _copy_post_surface,
)
from content.release.canonical.post_transaction_media import (
    media_dimensions as _media_dimensions,
)
from content.release.canonical.post_transaction_media import (
    post_asset_path as _post_asset_path,
)
from content.release.canonical.post_transaction_sources import (
    asset_source_use_mode as _asset_source_use_mode,
)
from content.release.canonical.post_transaction_sources import https_source as _https
from content.release.canonical.post_transaction_sources import (
    source_catalog as _source_catalog,
)
from core.control_types import SourcePolicyRevision
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, now_iso
from core.schema import assert_valid
from core.source_digest import (
    ExecutionBundleIdentity,
    SourceDefinitionSnapshot,
    SourceDigestError,
)
from core.tree_integrity import tree_integrity_stats
from governance.coverage.license import (
    RightsAuditStatus,
    parse_rights_audit_status,
    rights_proof_required,
)

_EXTRACTED_DEPENDENCIES = (
    EXPECTED_OBJECT_SCHEMAS,
    LAYOUT_SCHEMA,
    PACKAGE_SCHEMA,
    ExecutionBundleIdentity,
    RightsAuditStatus,
    SourceDefinitionSnapshot,
    SourceDigestError,
    SourcePolicyRevision,
    _asset_source_use_mode,
    _asset_sources,
    _closure_digest,
    _copy_post_surface,
    _digest_file,
    _execution_id,
    _https,
    _media_dimensions,
    _post_asset_path,
    _read_json,
    _review_binding,
    _safe_rel,
    _source_assets,
    _source_catalog,
    _tree_digest,
    _write_json,
    adopt_independent_asset_review,
    append_pool_record,
    assert_valid,
    build_canonical_pool_record,
    build_content_pool_fields,
    canonical_asset_manifest_row,
    freeze_canonical_video_poster_identities,
    freeze_execution_source_identity,
    hashlib,
    json,
    now_iso,
    os,
    parse_rights_audit_status,
    project_creator_object,
    rights_proof_required,
    shutil,
    tempfile,
    tree_integrity_stats,
)


def _creator_ref(manifest: Mapping[str, Any]) -> str:
    ref = str(manifest.get("creatorProfileId") or "").strip()
    if not ref:
        raise ObjectTransactionError("post manifest 缺 creatorProfileId")
    return _safe_id(ref, label="creatorProfileId")


def build_post_object_transaction_package(
    *,
    execution_root: Path,
    object_ref: str,
    transaction_id: str,
    package_root: Path,
    pool_delivery_intent: Mapping[str, Any],
) -> dict[str, Any]:
    from content.release.canonical.post_transaction_builder import (
        build_post_object_transaction_package as implementation,
    )

    return implementation(
        execution_root=execution_root,
        object_ref=object_ref,
        transaction_id=transaction_id,
        package_root=package_root,
        pool_delivery_intent=pool_delivery_intent,
        output_root=OUTPUT_ROOT,
        publish_root=PUBLISH_ROOT,
    )


__all__ = ["build_post_object_transaction_package"]
