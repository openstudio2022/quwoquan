"""Materialize the object-local homepage source catalog and rights evidence."""
from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.article_package import sha256_file
from core.io import read_json, write_json
from core.paths import execution_root
def _materialize_homepage_source_catalog(
    execution_id: str,
    obj: Path,
    base: Mapping[str, Any],
    *,
    fallback_title: str,
) -> tuple[dict[str, Any], list[str], str, str]:
    """把主底稿来源闭包进对象 evidence，并返回公开投影与 catalog digest。"""
    from core.public_source_url import normalize_public_source_url
    from core.schema import assert_valid
    from core.baike_source_contract import source_identity_matches_contract

    source_ref = str(base.get("primaryEvidenceRef") or base.get("sourceRef") or "").strip()
    if not source_ref:
        raise ValueError("homepage primaryEvidenceRef is empty")
    source_path = execution_root(execution_id) / source_ref
    unit_dir = source_path.parent
    meta_path = unit_dir / "meta.json"
    if not source_path.is_file() or not meta_path.is_file():
        raise ValueError(f"homepage source evidence is not closed: {source_ref}")
    meta = read_json(meta_path)
    source_kind = str(meta.get("sourceKind") or "")
    extractor = str(meta.get("extractor") or "")
    policy_revision = str(meta.get("policyRevision") or "")
    source_url = normalize_public_source_url(
        str(meta.get("canonicalUrl") or meta.get("finalUrl") or meta.get("url") or ""),
        source_kind=source_kind,
    )
    source_unit_id = str(meta.get("sourceUnitId") or unit_dir.name)
    if not source_identity_matches_contract(
        source_kind=source_kind,
        url=source_url,
        extractor=extractor,
        policy_revision=policy_revision,
    ):
        raise ValueError(
            "homepage primaryEvidenceRef must resolve to explicit encyclopedia-primary-v2 identity"
        )
    if (
        not source_unit_id.strip()
        or source_unit_id in {".", ".."}
        or "/" in source_unit_id
        or "\\" in source_unit_id
    ):
        raise ValueError("sourceUnitId is not a safe evidence directory name")
    evidence_dir = obj / "evidence" / "sources" / source_unit_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    compact_meta = {
        "schemaVersion": "quwoquan_data.object_source_evidence/1",
        "sourceUnitId": source_unit_id,
        "entityName": str(meta.get("entityName") or fallback_title),
        "sourceKind": source_kind,
        "extractor": extractor,
        "canonicalUrl": source_url,
        "sourceUrl": source_url,
        "title": str(meta.get("title") or fallback_title),
        "fetchedAt": str(meta.get("fetchedAt") or ""),
        "snapshotHash": str(meta.get("snapshotHash") or meta.get("cleanSha256") or ""),
        "policyRevision": policy_revision,
        "sourceUseMode": str(meta.get("sourceUseMode") or "factual_reference_only"),
    }
    write_json(evidence_dir / "meta.json", compact_meta)
    clean_source = unit_dir / "source.clean.md"
    shutil.copy2(clean_source if clean_source.is_file() else source_path, evidence_dir / "source.clean.md")
    write_json(
        evidence_dir / "rights.json",
        {
            "sourceUseMode": compact_meta["sourceUseMode"],
            "license": str(meta.get("license") or ""),
            "rightsMode": str(meta.get("rightsMode") or compact_meta["sourceUseMode"]),
        },
    )
    evidence_ref = f"evidence/sources/{source_unit_id}/meta.json"
    catalog_source = {**compact_meta, "evidenceRef": evidence_ref}
    catalog = {
        "schemaVersion": "quwoquan_data.object_source_catalog/1",
        "policyRevision": "encyclopedia-primary-v2",
        "primaryEvidenceRef": evidence_ref,
        "primarySource": catalog_source,
        "sources": [catalog_source],
    }
    catalog_path = obj / "evidence" / "source_catalog.json"
    assert_valid(catalog, "publish", "source_catalog", label=f"source_catalog:{fallback_title}")
    write_json(catalog_path, catalog)
    public_primary = {
        key: compact_meta[key]
        for key in (
            "entityName",
            "sourceKind",
            "extractor",
            "canonicalUrl",
            "sourceUrl",
            "title",
            "fetchedAt",
            "snapshotHash",
            "policyRevision",
            "sourceUseMode",
        )
    }
    return public_primary, [source_url], evidence_ref, sha256_file(catalog_path)
