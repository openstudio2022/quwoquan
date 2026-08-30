"""Validation and projection helpers for supported-API image preparation."""
from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.parse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid
from core.source_attribution import derived_modifications_value

from content.source.professional_safety_evidence import file_sha256
from content.source.professional_image_openverse_contract import (
    openverse_metadata,
    openverse_source_attribution,
)

_LICENSE_DENY = ("noncommercial", "non-commercial", "no derivatives", "fair use")


def _journal_digest(value: Mapping[str, Any]) -> str:
    body = (
        json.dumps(
            dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _canonical_document_digest(value: Mapping[str, Any]) -> str:
    return _journal_digest(value)


def load_document(path: Path, *, group: str, name: str) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise TypeError(f"{name} must be an object")
    assert_valid(payload, group, name, label=name)
    return payload


def verify_metadata_catalog(
    catalog: Mapping[str, Any], *, digest: Any,
) -> None:
    stable = {
        key: value
        for key, value in catalog.items()
        if key not in {"schema", "catalogId", "catalogDigest"}
    }
    if catalog.get("catalogDigest") != digest(stable):
        raise ValueError("metadata catalog digest drift")
    if catalog.get("catalogId") != (
        "professional-image-supported-api-metadata-"
        + str(catalog["catalogDigest"])[7:23]
    ):
        raise ValueError("metadata catalog identity drift")
    ids = [str(row["candidateId"]) for row in catalog["candidates"]]
    sources = [
        (str(row["sourcePageUrl"]), str(row["originalAssetUrl"]))
        for row in catalog["candidates"]
    ]
    if (
        len(ids) != len(set(ids))
        or len(sources) != len(set(sources))
        or int(catalog["candidateCount"]) != len(ids)
        or int(catalog["candidateCount"]) != int(catalog["targetCandidateCount"])
        or int(catalog["completedQueryCount"]) > int(catalog["queryCount"])
    ):
        raise ValueError("metadata candidate identity/count drift")


def verify_plan(
    plan: Mapping[str, Any], catalog: Mapping[str, Any], *, digest: Any,
) -> dict[str, Mapping[str, Any]]:
    stable = {
        key: plan[key]
        for key in (
            "catalogRef", "catalogDigest", "dimensions", "candidateCount",
            "providerCandidateCounts", "candidates",
        )
    }
    if plan.get("planDigest") != digest(stable):
        raise ValueError("discovery plan digest drift")
    if (
        catalog.get("discoveryPlanId") != plan.get("planId")
        or catalog.get("discoveryPlanDigest") != plan.get("planDigest")
    ):
        raise ValueError("metadata catalog discovery plan binding drift")
    candidates = {str(row["candidateId"]): row for row in plan["candidates"]}
    for row in catalog["candidates"]:
        planned = candidates.get(str(row["discoveryCandidateId"]))
        observed_entity_id = str(
            row.get("observedEntityId") or row.get("entityId") or ""
        )
        if (
            not isinstance(planned, Mapping)
            or planned.get("provider") != row.get("provider")
            # 发现计划保留请求时使用的目录别名，metadata catalog 同时记录
            # canonical entity identity。按 observed request 绑定可保留精确
            # query provenance，同时仍允许别名归一到 canonical identity。
            or str(planned.get("entity") or "") != observed_entity_id
            or "supported_api" not in planned.get("acquisitionPaths", [])
        ):
            raise ValueError(
                f"metadata candidate is not bound to plan: {row['candidateId']}"
            )
    return candidates


def verify_fresh_metadata(
    candidate: Mapping[str, Any], meta: Mapping[str, Any]
) -> None:
    """Reject provider metadata drift between discovery and original preparation."""
    expected = {
        "sourcePageUrl": str(meta["sourcePageUrl"]),
        "originalAssetUrl": str(meta["originalAssetUrl"]),
        "creator": str(meta["creator"]),
        "license": str(meta["license"]),
        "licenseVersion": str(meta["licenseVersion"]),
        "attributionText": str(meta["attributionText"]),
        "termsUrl": str(meta["termsUrl"]),
        "width": int(meta["width"]),
        "height": int(meta["height"]),
    }
    if candidate.get("provider") == "openverse":
        expected.update(
            {
                "providerAssetId": str(meta["providerAssetId"]),
                "upstreamProvider": str(meta["upstreamProvider"]),
            }
        )
    drift = [key for key, value in expected.items() if candidate.get(key) != value]
    if drift:
        raise ValueError(
            "supported API metadata changed after discovery: "
            + ", ".join(sorted(drift))
        )


def commons_request_url(file_title: str) -> str:
    query = urllib.parse.urlencode(
        {
            "action": "query", "format": "json", "formatversion": "2",
            "prop": "imageinfo", "iiprop": "url|size|extmetadata",
            "titles": file_title,
        }
    )
    return "https://commons.wikimedia.org/w/api.php?" + query


def _strip_html(value: object) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html.unescape(str(value or ""))).split())


def commons_metadata(
    response: Mapping[str, Any], *, expected_title: str,
) -> dict[str, Any]:
    pages = ((response.get("query") or {}).get("pages") or [])
    matches = [
        row for row in pages
        if isinstance(row, Mapping) and str(row.get("title") or "") == expected_title
    ]
    if len(matches) != 1:
        raise ValueError(f"Commons API did not return exact file: {expected_title}")
    info_rows = matches[0].get("imageinfo") or []
    if len(info_rows) != 1 or not isinstance(info_rows[0], Mapping):
        raise ValueError("Commons imageinfo is missing or ambiguous")
    info = info_rows[0]
    metadata = info.get("extmetadata") or {}
    if not isinstance(metadata, Mapping):
        raise TypeError("Commons extmetadata is missing")

    def meta(name: str) -> str:
        raw = metadata.get(name) or {}
        return _strip_html(raw.get("value") if isinstance(raw, Mapping) else "")

    result = {
        "sourcePageUrl": str(info.get("descriptionurl") or "").strip(),
        "originalAssetUrl": str(info.get("url") or "").strip(),
        "creator": meta("Artist") or meta("Credit"),
        "license": meta("LicenseShortName"),
        "termsUrl": meta("LicenseUrl"),
        "description": meta("ImageDescription"),
        "width": int(info.get("width") or 0),
        "height": int(info.get("height") or 0),
    }
    if (
        not result["sourcePageUrl"].startswith("https://commons.wikimedia.org/")
        or not result["originalAssetUrl"].startswith("https://upload.wikimedia.org/")
        or not result["creator"]
        or not result["license"]
        or not result["termsUrl"].startswith("https://")
        or any(marker in result["license"].casefold() for marker in _LICENSE_DENY)
    ):
        raise ValueError("Commons provenance/license metadata is incomplete")
    version = re.search(r"\b\d+(?:\.\d+)+\b", result["license"])
    if version is None:
        version = re.search(r"\b\d+(?:\.\d+)+\b", result["termsUrl"])
    if version is None:
        raise ValueError("Commons license version is missing")
    result["licenseVersion"] = version.group(0)
    result["attributionText"] = (
        f"{result['creator']} · Wikimedia Commons · {result['license']}"
    )
    return result


def source_attribution(
    meta: Mapping[str, Any], *, observed_at: str, platform: str = "Wikimedia Commons",
) -> dict[str, Any]:
    if platform == "Openverse":
        return openverse_source_attribution(meta, observed_at=observed_at)
    creator = str(meta["creator"])
    license_name = str(meta["license"])
    return {
        "isOriginal": False,
        "originalCreatorName": creator,
        "platform": "Wikimedia Commons",
        "sourcePostUrl": str(meta["sourcePageUrl"]),
        "originalAssetUrl": str(meta["originalAssetUrl"]),
        "attributionText": f"{creator} · Wikimedia Commons · {license_name}",
        "rightsBasis": license_name,
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "authorizationProofUrl": str(meta["sourcePageUrl"]),
        "termsUrl": str(meta["termsUrl"]),
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "unverified",
        "collectedAt": observed_at,
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
        # 采集把 provider 原图逐字节存入 CAS，没有任何衍生修改。
        "derivedModifications": derived_modifications_value(),
    }


def supported_api_detail(
    candidate: Mapping[str, Any], response: Mapping[str, Any]
) -> dict[str, Any]:
    if candidate.get("provider") == "openverse":
        meta = openverse_metadata(response)
        if meta["providerAssetId"] != candidate.get("providerAssetId"):
            raise ValueError("Openverse detail returned another asset id")
        return meta
    return commons_metadata(response, expected_title=str(candidate["fileTitle"]))


def load_reviewer_results(
    refs: Sequence[str], *, root: Path, catalog: Mapping[str, Any], digest: Any,
    execution_source_identity: Mapping[str, Any] | None = None,
    source_review_identity: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Load only validated host-source-review/v1 results for new source writes."""
    del catalog, digest, execution_source_identity
    from content.source.host_source_review import read_host_source_review_result

    results: dict[str, dict[str, Any]] = {}
    resolved_root = root.resolve()
    for ref in refs:
        relative = Path(str(ref or ""))
        path = (resolved_root / relative).resolve()
        if (
            relative.is_absolute() or ".." in relative.parts
            or resolved_root not in path.parents or not path.is_file() or path.is_symlink()
        ):
            raise ValueError("reviewer evidence ref is unsafe or missing")
        raw = read_json(path)
        if not isinstance(raw, Mapping) or raw.get("schema") != "quwoquan_data.host_source_review_result":
            raise ValueError("new image source review requires host-source-review/v1 result")
        result = read_host_source_review_result(
            evidence_root=resolved_root,
            request_ref=str(raw.get("requestRef") or ""),
            result_ref=relative.as_posix(),
        )
        asset = result["assetBinding"]
        if asset.get("assetKind") != "image":
            raise ValueError("image source review result assetKind drift")
        if source_review_identity is not None and any(
            result["sourceIdentity"].get(key) != source_review_identity.get(key)
            for key in (
                "sourceRevision", "sourceDigest", "entityCatalogDigest",
                "executionBundleDigest", "handoffDigest",
            )
        ):
            raise ValueError("source reviewer identity differs from handoff")
        candidate_id = str(asset["assetId"])
        if candidate_id in results:
            raise ValueError(f"duplicate reviewer result: {candidate_id}")
        results[candidate_id] = {
            "candidateId": candidate_id,
            "contentSha256": str(asset["contentSha256"]),
            "judgment": dict(result["verdict"]),
            "reviewedAt": str(result["reviewedAt"]),
            "runId": str(result["actor"]["auditRunId"]),
            "evidenceRef": relative.as_posix(),
            "evidencePath": path,
            "sourceIdentity": dict(result["sourceIdentity"]),
            "requestDigest": str(result["requestDigest"]),
            "resultDigest": str(result["resultDigest"]),
            "actor": dict(result["actor"]),
        }
    return results


def review_accepted(judgment: Mapping[str, Any]) -> bool:
    return (
        judgment.get("status") == "passed"
        and judgment.get("qualityStatus") == "passed"
        and judgment.get("entityMatch") == "matched"
        and judgment.get("privacyRisk") == "none"
        and judgment.get("minorRisk") == "none"
        and judgment.get("maliciousMediaRisk") == "none"
        and judgment.get("watermarkStatus") == "absent"
    )


__all__ = [
    "commons_metadata", "commons_request_url", "load_document",
    "load_reviewer_results", "review_accepted", "source_attribution",
    "supported_api_detail", "verify_fresh_metadata", "verify_metadata_catalog",
    "verify_plan",
]
