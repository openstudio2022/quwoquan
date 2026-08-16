"""Discover governed Wikimedia Commons metadata without downloading originals."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.image_safety import watermark_prone_source_reason
from core.io import read_json
from core.paths import SOURCE_ACQUISITION_ROOT
from core.schema import assert_valid

from content.execution.controller.execute.pre_acquisition_handoff import (
    guard_acquisition_source_identity,
    load_pre_acquisition_handoff,
)
from content.source.professional_image_openverse_contract import (
    openverse_metadata,
    openverse_search_url,
)
from content.source.professional_image_supported_api_contract import commons_metadata
from content.source.professional_image_supported_api_metadata_entities import (
    load_entity_bindings,
    resolve_entity,
)
from content.source.professional_image_transport import fetch_public_json
from content.source.professional_safety_evidence import file_sha256

_EXTRACTED_DEPENDENCIES = (file_sha256,)

METADATA_DISCOVERY_ROOT = (
    SOURCE_ACQUISITION_ROOT / "professional-image-supported-api-metadata"
)
SOURCE_POOL_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"
METADATA_INVALID = "DATA.SOURCE.SUPPORTED_API_METADATA_INVALID"
RATE_LIMITED = "DATA.SOURCE.SUPPORTED_API_RATE_LIMITED"
PROVIDER_UNAVAILABLE = "DATA.SOURCE.SUPPORTED_API_UNAVAILABLE"


class ProfessionalImageSupportedApiMetadataError(RuntimeError):
    """Typed metadata discovery failure with an optional resumable checkpoint."""

    def __init__(self, code: str, detail: str, *, receipt_ref: str = "") -> None:
        self.code = code
        self.receipt_ref = receipt_ref
        super().__init__(f"{code}: {detail}")


def _digest(value: object) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _write_once(path: Path, body: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
            raise ProfessionalImageSupportedApiMetadataError(
                METADATA_INVALID, f"create-once collision: {path}"
            ) from None
        return path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    return _write_once(path, body)


def _safe_ref(path: Path, root: Path) -> str:
    resolved = path.resolve()
    base = root.resolve()
    if resolved == base or base not in resolved.parents:
        raise ProfessionalImageSupportedApiMetadataError(
            METADATA_INVALID, f"metadata evidence escapes output root: {path}"
        )
    return resolved.relative_to(base).as_posix()


def _load_plan(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise TypeError("professional image discovery plan must be an object")
    assert_valid(
        payload,
        "source",
        "professional_image_discovery_plan",
        label="professional image discovery plan",
    )
    stable = {
        key: payload[key]
        for key in (
            "catalogRef",
            "catalogDigest",
            "dimensions",
            "candidateCount",
            "providerCandidateCounts",
            "candidates",
        )
    }
    if payload["planDigest"] != _digest(stable):
        raise ValueError("professional image discovery plan digest drift")
    return payload


def _supported_queries(
    plan: Mapping[str, Any],
    entity_index: dict[str, dict[str, Any]],
    *,
    limit: int,
    providers: Sequence[str],
) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    for row in plan["candidates"]:
        provider = str(row["provider"])
        if provider not in providers:
            continue
        if "supported_api" not in row["acquisitionPaths"]:
            raise ValueError("Commons discovery candidate lacks supported_api")
        entity = resolve_entity(row["entity"], index=entity_index)
        stable = {
            "discoveryPlanDigest": plan["planDigest"],
            "discoveryCandidateId": row["candidateId"],
            "entityId": entity["entityId"],
            "queryText": row["queryText"],
        }
        query_id = (
            f"{'commons' if provider == 'wikimedia_commons' else 'openverse'}-query-"
            + _digest(stable)[7:23]
        )
        request_url = (
            "https://commons.wikimedia.org/w/api.php?"
            + urllib.parse.urlencode(
                {
                    "action": "query",
                    "format": "json",
                    "formatversion": "2",
                    "generator": "search",
                    "gsrsearch": row["queryText"],
                    "gsrnamespace": "6",
                    "gsrlimit": str(limit),
                    "prop": "imageinfo",
                    "iiprop": "url|size|extmetadata",
                }
            )
            if provider == "wikimedia_commons"
            else openverse_search_url(str(row["queryText"]), page_size=limit)
        )
        queries.append(
            {
                **stable,
                **entity,
                "provider": provider,
                "queryId": query_id,
                "requestUrl": request_url,
            }
        )
    if not queries or len({row["queryId"] for row in queries}) != len(queries):
        raise ValueError("Commons discovery queries are empty or not unique")
    return queries


def _transport_evidence(
    fetched: Mapping[str, Any],
    *,
    body: bytes,
) -> dict[str, Any]:
    evidence = fetched.get("transportEvidence")
    if not isinstance(evidence, dict):
        raise TypeError("supported API fetch lacks HTTPS transport evidence")
    assert_valid(
        evidence,
        "source",
        "professional_image_https_transport_evidence",
        label="professional image metadata HTTPS transport evidence",
    )
    if evidence["responseSha256"] != ("sha256:" + hashlib.sha256(body).hexdigest()):
        raise ValueError("supported API HTTPS transport evidence bytes drift")
    return evidence


def _response_bytes(
    fetched: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any], dict[str, Any]]:
    body = fetched.get("bytes")
    payload = fetched.get("payload")
    if not isinstance(body, bytes) or not body or not isinstance(payload, dict):
        raise ValueError("Commons API fetch result lacks exact JSON bytes")
    decoded = json.loads(body.decode("utf-8"))
    if decoded != payload:
        raise ValueError("Commons API bytes/payload binding drift")
    return body, payload, _transport_evidence(fetched, body=body)


def _load_response(
    path: Path,
    transport_path: Path,
) -> tuple[bytes, dict[str, Any], dict[str, Any]]:
    body = path.read_bytes()
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Commons API response must be an object")
    evidence = read_json(transport_path)
    if not isinstance(evidence, dict):
        raise TypeError("supported API HTTPS transport evidence must be an object")
    assert_valid(
        evidence,
        "source",
        "professional_image_https_transport_evidence",
        label="professional image metadata HTTPS transport evidence",
    )
    if evidence["responseSha256"] != ("sha256:" + hashlib.sha256(body).hexdigest()):
        raise ValueError("supported API HTTPS transport evidence bytes drift")
    return body, payload, evidence


def _candidate(
    page: Mapping[str, Any], *, query: Mapping[str, Any], response_sha: str
) -> dict[str, Any]:
    title = str(page.get("title") or "").strip()
    if not title.startswith("File:"):
        raise ValueError("Commons search result is not a File page")
    page_id = page.get("pageid")
    if isinstance(page_id, bool) or not isinstance(page_id, int) or page_id < 1:
        raise ValueError("Commons search result lacks pageId")
    meta = commons_metadata({"query": {"pages": [dict(page)]}}, expected_title=title)
    block_reason = watermark_prone_source_reason([title, *meta.values()])
    if block_reason:
        raise ProfessionalImageSupportedApiMetadataError(
            "DATA.SOURCE.WATERMARK_BLOCKED", block_reason
        )
    identity = {
        "sourcePageUrl": meta["sourcePageUrl"],
        "originalAssetUrl": meta["originalAssetUrl"],
    }
    caption = str(meta.get("description") or "").strip() or title.removeprefix("File:")
    return {
        "candidateId": "wikimedia_commons:commons:" + _digest(identity)[7:23],
        "queryId": query["queryId"],
        "discoveryCandidateId": query["discoveryCandidateId"],
        "provider": "wikimedia_commons",
        "entityId": query["entityId"],
        "observedEntityId": query["observedEntityId"],
        "entityAliases": query["entityAliases"],
        "providerAssetId": str(page_id),
        "upstreamProvider": "wikimedia_commons",
        "fileTitle": title,
        "pageId": page_id,
        "caption": caption,
        "relevance": "semantic entity relevance review pending for: "
        + query["queryText"],
        "sourcePageUrl": meta["sourcePageUrl"],
        "originalAssetUrl": meta["originalAssetUrl"],
        "creator": meta["creator"],
        "license": meta["license"],
        "licenseVersion": meta["licenseVersion"],
        "attributionText": meta["attributionText"],
        "termsUrl": meta["termsUrl"],
        "width": meta["width"],
        "height": meta["height"],
        "apiRequestUrl": query["requestUrl"],
        "apiResponseSha256": response_sha,
    }


def _openverse_candidate(
    row: Mapping[str, Any], *, query: Mapping[str, Any], response_sha: str
) -> dict[str, Any]:
    meta = openverse_metadata(row)
    block_reason = watermark_prone_source_reason(
        [meta["title"], meta["attributionText"], meta["sourcePageUrl"]]
    )
    if block_reason:
        raise ProfessionalImageSupportedApiMetadataError(
            "DATA.SOURCE.WATERMARK_BLOCKED", block_reason
        )
    identity = {
        "providerAssetId": meta["providerAssetId"],
        "sourcePageUrl": meta["sourcePageUrl"],
        "originalAssetUrl": meta["originalAssetUrl"],
    }
    return {
        "candidateId": "openverse:asset:" + _digest(identity)[7:23],
        "queryId": query["queryId"],
        "discoveryCandidateId": query["discoveryCandidateId"],
        "provider": "openverse",
        "entityId": query["entityId"],
        "observedEntityId": query["observedEntityId"],
        "entityAliases": query["entityAliases"],
        "providerAssetId": meta["providerAssetId"],
        "upstreamProvider": meta["upstreamProvider"],
        "fileTitle": meta["title"],
        "pageId": 0,
        "caption": meta["title"],
        "relevance": "semantic entity relevance review pending for: "
        + query["queryText"],
        "sourcePageUrl": meta["sourcePageUrl"],
        "originalAssetUrl": meta["originalAssetUrl"],
        "creator": meta["creator"],
        "license": meta["license"],
        "licenseVersion": meta["licenseVersion"],
        "attributionText": meta["attributionText"],
        "termsUrl": meta["termsUrl"],
        "width": meta["width"],
        "height": meta["height"],
        "apiRequestUrl": query["requestUrl"],
        "apiResponseSha256": response_sha,
    }


def _project_response(
    payload: Mapping[str, Any], *, query: Mapping[str, Any], response_sha: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if query["provider"] == "openverse":
        raw_pages = payload.get("results")
    else:
        raw_query = payload.get("query")
        # MediaWiki 搜索无命中时会合法省略 ``query``（例如受治理地点尚未
        # 收录在 Commons）。这是已完成的零候选查询，不是畸形的 provider
        # 元数据；外层 receipt 必须保留 shortfall 以便重试或替换来源。
        raw_pages = (
            []
            if raw_query is None
            else (raw_query.get("pages") if isinstance(raw_query, Mapping) else None)
        )
    if not isinstance(raw_pages, list):
        raise TypeError("Commons search response lacks query.pages")
    pages = sorted(
        (row for row in raw_pages if isinstance(row, Mapping)),
        key=lambda row: (
            int(row.get("pageid") or 0),
            str(row.get("id") or ""),
            str(row.get("title") or ""),
        ),
    )
    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for page in pages:
        title = str(page.get("title") or "unknown supported API asset").strip()
        try:
            candidates.append(
                _openverse_candidate(page, query=query, response_sha=response_sha)
                if query["provider"] == "openverse"
                else _candidate(page, query=query, response_sha=response_sha)
            )
        except ProfessionalImageSupportedApiMetadataError as exc:
            exclusions.append(
                {
                    "queryId": query["queryId"],
                    "fileTitle": title,
                    "failureCode": exc.code,
                    "detail": str(exc).split(": ", 1)[-1][:240],
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            exclusions.append(
                {
                    "queryId": query["queryId"],
                    "fileTitle": title,
                    "failureCode": METADATA_INVALID,
                    "detail": str(exc)[:240] or "invalid Commons metadata",
                }
            )
    return candidates, exclusions


def _failure(query_id: str, exc: Exception) -> dict[str, Any]:
    status = int(getattr(exc, "code", 0) or 0)
    if status == 429:
        code, retryable = RATE_LIMITED, True
    elif status >= 500 or isinstance(exc, (OSError, TimeoutError)):
        code, retryable = PROVIDER_UNAVAILABLE, True
    else:
        code, retryable = METADATA_INVALID, False
    label = "Openverse" if query_id.startswith("openverse-") else "Commons"
    detail = f"{label} metadata request failed ({status or type(exc).__name__})"
    return {
        "queryId": query_id,
        "failureCode": code,
        "retryable": retryable,
        "detail": detail,
    }


def _write_catalog(
    root: Path,
    *,
    stable: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    catalog_digest = _digest(stable)
    catalog = {
        "schema": "quwoquan_data.professional_image_supported_api_metadata_catalog",
        "catalogId": "professional-image-supported-api-metadata-"
        + catalog_digest[7:23],
        "catalogDigest": catalog_digest,
        **stable,
    }
    assert_valid(
        catalog,
        "source",
        "professional_image_supported_api_metadata_catalog",
        label="professional image supported API metadata catalog",
    )
    path = root / "catalog.json"
    _write_json(path, catalog)
    return catalog, path


def _write_receipt(
    root: Path,
    *,
    output_root: Path,
    stable: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    receipt_digest = _digest(stable)
    receipt = {
        "schema": "quwoquan_data.professional_image_supported_api_metadata_discovery_receipt",
        "discoveryId": root.name,
        "receiptDigest": receipt_digest,
        **stable,
    }
    assert_valid(
        receipt,
        "source",
        "professional_image_supported_api_metadata_discovery_receipt",
        label="professional image supported API metadata discovery receipt",
    )
    path = root / "receipts" / f"{stable['status']}-{receipt_digest[7:23]}.json"
    _write_json(path, receipt)
    return receipt, path


def discover_supported_api_metadata(
    *,
    handoff_ref: Path,
    discovery_plan_path: Path,
    entity_catalog_path: Path,
    candidate_target: int,
    results_per_query: int = 50,
    providers: Sequence[str] = ("wikimedia_commons", "openverse"),
    output_root: Path = METADATA_DISCOVERY_ROOT,
    physical_evidence_root: Path = SOURCE_ACQUISITION_ROOT,
    api_fetcher: Callable[[str], Mapping[str, Any]] = fetch_public_json,
    handoff_loader: Callable[[Path], Mapping[str, Any]] = load_pre_acquisition_handoff,
    identity_guard: Callable[
        ..., Mapping[str, Any]
    ] = guard_acquisition_source_identity,
    entity_loader: Callable[
        [Path], tuple[str, str, dict[str, dict[str, Any]]]
    ] = load_entity_bindings,
    clock: Callable[[], str] = _now,
) -> tuple[dict[str, Any], Path, Path | None]:
    from content.source.professional_image_supported_api_metadata_discovery import (
        discover_supported_api_metadata as _discover,
    )

    return _discover(
        handoff_ref=handoff_ref,
        discovery_plan_path=discovery_plan_path,
        entity_catalog_path=entity_catalog_path,
        candidate_target=candidate_target,
        results_per_query=results_per_query,
        providers=providers,
        output_root=output_root,
        physical_evidence_root=physical_evidence_root,
        api_fetcher=api_fetcher,
        handoff_loader=handoff_loader,
        identity_guard=identity_guard,
        entity_loader=entity_loader,
        clock=clock,
    )


__all__ = [
    "METADATA_DISCOVERY_ROOT",
    "METADATA_INVALID",
    "RATE_LIMITED",
    "SOURCE_POOL_SHORTFALL",
    "ProfessionalImageSupportedApiMetadataError",
    "discover_supported_api_metadata",
]
