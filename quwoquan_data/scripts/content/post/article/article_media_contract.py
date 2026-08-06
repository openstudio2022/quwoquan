"""Single-source cover/body media closure for materialized articles."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.asset_placement import place_assets_in_markdown, referenced_asset_ids
from core.io import read_json, write_json
from core.paths import execution_root

ARTICLE_SOURCE_ASSET_RECEIPT_REF = "5.review/article_source_asset_receipt.json"
ARTICLE_MEDIA_CLOSURE_SCHEMA = "quwoquan_data.article_media_closure"
_RIGHTS_STATUSES = ("verified", "unverified", "restricted", "unknown")
_CLOSURE_FIELDS = frozenset(
    {
        "schema",
        "mode",
        "sourceRef",
        "sourceUnitRef",
        "assetCount",
        "coverAssetId",
        "bodyAssetIds",
        "sourceAssetReceiptRef",
        "sourceAssetReceiptDigest",
        "sourceAssetCounts",
    }
)
_SOURCE_COUNT_FIELDS = frozenset(
    {
        "displayName",
        "provider",
        "plannedAssetCount",
        "discoveredAssetCount",
        "downloadedAssetCount",
        "acceptedAssetCount",
        "rejectedAssetCount",
        "verifiedAssetCount",
        "unverifiedAssetCount",
        "restrictedAssetCount",
        "unknownAssetCount",
    }
)


def _nonnegative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _source_unit_ref(source_ref: str) -> str:
    normalized = str(source_ref or "").replace("\\", "/").strip()
    if not normalized.endswith("/source.md"):
        return ""
    return normalized.rsplit("/", 1)[0]


def _execution_relative_source_ref(execution_id: str, source_ref: str) -> str:
    """Normalize a known execution-root ref before reading source-unit evidence."""
    normalized = str(source_ref or "").replace("\\", "/").strip()
    root = execution_root(execution_id).resolve()
    execution_name = root.name
    for prefix in (
        f".qwq_output/data/tasks/{execution_name}/",
        f"data/tasks/{execution_name}/",
        f"tasks/{execution_name}/",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    marker = f"/tasks/{execution_name}/"
    if marker in normalized:
        normalized = normalized.split(marker, 1)[1]

    candidate = Path(normalized)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError("article baseSourceRef escapes execution root") from exc
    return normalized.lstrip("./")


def _source_unit_dir(execution_id: str, source_ref: str) -> Path:
    normalized_ref = _execution_relative_source_ref(execution_id, source_ref)
    source_unit_ref = _source_unit_ref(normalized_ref)
    if not source_unit_ref:
        raise ValueError(
            f"article baseSourceRef must be a relative source.md ref: {source_ref!r}"
        )
    root = execution_root(execution_id).resolve()
    source_path = (root / normalized_ref).resolve()
    try:
        source_path.relative_to(root)
    except ValueError as exc:
        raise ValueError("article baseSourceRef escapes execution root") from exc
    if not source_path.is_file():
        raise ValueError(f"article baseSourceRef is not readable: {normalized_ref}")
    return source_path.parent


def article_source_asset_counts(
    execution_id: str, source_ref: str
) -> dict[str, Any]:
    """Read one source unit's exact acquisition funnel and rights distribution."""
    unit = _source_unit_dir(execution_id, source_ref)
    meta = read_json(unit / "meta.json")
    index = read_json(unit / "assets" / "index.json")
    if not isinstance(meta, Mapping) or not isinstance(index, Mapping):
        raise TypeError(f"article source unit metadata is invalid: {unit}")
    assets = [row for row in (index.get("assets") or []) if isinstance(row, Mapping)]
    funnel = (
        meta.get("assetFunnel")
        if isinstance(meta.get("assetFunnel"), Mapping)
        else {}
    )
    declared_accepted = _nonnegative_int(
        meta.get("assetCount")
        if meta.get("assetCount") is not None
        else funnel.get("keptCount")
    )
    accepted = declared_accepted if declared_accepted else len(assets)
    if accepted != len(assets):
        raise ValueError(
            "article source unit assetCount/index drift: "
            f"declared={accepted} indexed={len(assets)}"
        )
    discovered = max(_nonnegative_int(funnel.get("candidateCount")), accepted)
    planned = max(_nonnegative_int(funnel.get("plannedAssetCount")), discovered)
    failures = (
        funnel.get("fetchFailures")
        if isinstance(funnel.get("fetchFailures"), list)
        else []
    )
    downloaded = max(accepted, discovered - len(failures))
    rights = Counter(
        status if status in _RIGHTS_STATUSES else "unknown"
        for status in (
            str(row.get("rightsAuditStatus") or "unknown").strip() for row in assets
        )
    )
    return {
        "displayName": str(
            meta.get("title") or meta.get("entityName") or unit.name
        ),
        "provider": str(meta.get("platform") or meta.get("sourceKind") or "unknown"),
        "plannedAssetCount": planned,
        "discoveredAssetCount": discovered,
        "downloadedAssetCount": downloaded,
        "acceptedAssetCount": accepted,
        "rejectedAssetCount": max(0, discovered - accepted),
        **{f"{status}AssetCount": rights[status] for status in _RIGHTS_STATUSES},
    }


def article_media_contract_issues(
    compose_payload: Mapping[str, Any], base_source_ref: str
) -> list[str]:
    """Require text-only or exactly one same-source illustrated closure."""
    if str(compose_payload.get("carrier") or "article") == "image":
        return []
    issues: list[str] = []
    source_ref = str(base_source_ref or "").replace("\\", "/").strip()
    source_unit_ref = _source_unit_ref(source_ref)
    if not source_unit_ref:
        issues.append("article media closure requires one baseSourceRef ending in source.md")
    assets = [
        row
        for row in (compose_payload.get("assets") or [])
        if isinstance(row, Mapping)
    ]
    text_only = (
        str(compose_payload.get("publishMediaMode") or "").strip() == "text_only"
    )
    if text_only:
        if assets:
            issues.append("text_only article must not retain image assets")
        return issues
    if len(assets) < 2:
        issues.append("illustrated article requires a cover and at least one body image")
    asset_ids = [str(row.get("assetId") or "").strip() for row in assets]
    if any(not asset_id for asset_id in asset_ids) or len(asset_ids) != len(set(asset_ids)):
        issues.append("article media assetIds must be unique and non-empty")
    covers = [
        row for row in assets if str(row.get("role") or "").strip() == "cover"
    ]
    if len(covers) != 1:
        issues.append("illustrated article requires exactly one role=cover asset")
    body_assets = [row for row in assets if row not in covers]
    if not body_assets:
        issues.append("illustrated article requires at least one non-cover body image")
    for asset in assets:
        asset_id = str(asset.get("assetId") or asset.get("fileName") or "?")
        asset_source_ref = str(asset.get("sourceRef") or "").replace("\\", "/").strip()
        source_asset_ref = (
            str(asset.get("sourceAssetRef") or "").replace("\\", "/").strip()
        )
        if asset_source_ref != source_ref:
            issues.append(
                f"article asset {asset_id} sourceRef must equal baseSourceRef"
            )
        if not source_unit_ref or not source_asset_ref.startswith(
            source_unit_ref + "/assets/"
        ):
            issues.append(
                f"article asset {asset_id} sourceAssetRef must belong to base source unit"
            )
    return issues


def _build_receipt(
    execution_id: str,
    *,
    object_ref: str,
    source_ref: str,
    assets: Sequence[Mapping[str, Any]],
    mode: str,
) -> dict[str, Any]:
    rows = [row for row in assets if isinstance(row, Mapping)]
    cover_ids = [
        str(row.get("assetId") or "").strip()
        for row in rows
        if str(row.get("role") or "") == "cover"
    ]
    body_ids = [
        str(row.get("assetId") or "").strip()
        for row in rows
        if str(row.get("role") or "") != "cover"
        and str(row.get("assetId") or "").strip()
    ]
    stable = {
        "schema": "quwoquan_data.article_source_asset_receipt",
        "executionId": execution_id,
        "objectRef": object_ref,
        "mode": mode,
        "sourceRef": source_ref,
        "sourceUnitRef": _source_unit_ref(source_ref),
        "assetCount": len(rows),
        "coverAssetId": cover_ids[0] if len(cover_ids) == 1 else "",
        "bodyAssetIds": body_ids,
        "usagePositions": [
            {
                "assetId": str(row.get("assetId") or ""),
                "position": (
                    "cover_frontmatter"
                    if str(row.get("role") or "") == "cover"
                    else "body_figure"
                ),
            }
            for row in rows
        ],
        "sourceAssetCounts": [
            article_source_asset_counts(execution_id, source_ref)
        ],
    }
    return {**stable, "receiptDigest": _digest(stable)}


def _closure_from_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": ARTICLE_MEDIA_CLOSURE_SCHEMA,
        "mode": receipt["mode"],
        "sourceRef": receipt["sourceRef"],
        "sourceUnitRef": receipt["sourceUnitRef"],
        "assetCount": receipt["assetCount"],
        "coverAssetId": receipt["coverAssetId"],
        "bodyAssetIds": receipt["bodyAssetIds"],
        "sourceAssetReceiptRef": ARTICLE_SOURCE_ASSET_RECEIPT_REF,
        "sourceAssetReceiptDigest": receipt["receiptDigest"],
        "sourceAssetCounts": receipt["sourceAssetCounts"],
    }


def read_article_media_closure(
    manifest: Mapping[str, Any], *, object_dir: Path | None = None
) -> Mapping[str, Any]:
    """Return the sole batch/release read API; reject inferred or partial closure."""
    profile = manifest.get("articleRenderProfile")
    closure = profile.get("mediaClosure") if isinstance(profile, Mapping) else None
    if not isinstance(closure, Mapping) or set(closure) != _CLOSURE_FIELDS:
        raise ValueError("article manifest mediaClosure is missing or incomplete")
    mode = str(closure.get("mode") or "")
    asset_count = closure.get("assetCount")
    body_ids = closure.get("bodyAssetIds")
    counts = closure.get("sourceAssetCounts")
    count_row = counts[0] if isinstance(counts, list) and len(counts) == 1 else None
    if (
        closure.get("schema") != ARTICLE_MEDIA_CLOSURE_SCHEMA
        or mode not in {"illustrated", "text_only"}
        or not isinstance(asset_count, int)
        or isinstance(asset_count, bool)
        or asset_count < 0
        or not isinstance(body_ids, list)
        or not isinstance(counts, list)
        or len(counts) != 1
        or not isinstance(count_row, Mapping)
        or set(count_row) != _SOURCE_COUNT_FIELDS
        or not str(closure.get("sourceRef") or "").endswith("/source.md")
        or not str(closure.get("sourceUnitRef") or "")
        or closure.get("sourceAssetReceiptRef") != ARTICLE_SOURCE_ASSET_RECEIPT_REF
        or not str(closure.get("sourceAssetReceiptDigest") or "").startswith(
            "sha256:"
        )
    ):
        raise ValueError("article manifest mediaClosure fields are invalid")
    if mode == "illustrated" and (
        asset_count < 2
        or not str(closure.get("coverAssetId") or "")
        or not body_ids
    ):
        raise ValueError("illustrated article mediaClosure lacks cover/body assets")
    if mode == "text_only" and (
        asset_count != 0
        or str(closure.get("coverAssetId") or "")
        or body_ids
    ):
        raise ValueError("text_only article mediaClosure contains image assets")
    if object_dir is not None:
        receipt_path = object_dir / ARTICLE_SOURCE_ASSET_RECEIPT_REF
        try:
            receipt = read_json(receipt_path)
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError("article source asset receipt is unreadable") from exc
        if not isinstance(receipt, Mapping):
            raise ValueError("article source asset receipt must be an object")
        stable = {key: value for key, value in receipt.items() if key != "receiptDigest"}
        if receipt.get("receiptDigest") != _digest(stable):
            raise ValueError("article source asset receipt digest drift")
        expected = _closure_from_receipt(receipt)
        if dict(closure) != expected:
            raise ValueError("article manifest mediaClosure/receipt drift")
        manifest_assets = [
            row for row in (manifest.get("assets") or []) if isinstance(row, Mapping)
        ]
        manifest_asset_ids = [
            str(row.get("assetId") or "").strip() for row in manifest_assets
        ]
        expected_asset_ids = [
            value
            for value in [
                str(closure.get("coverAssetId") or ""),
                *[str(value) for value in body_ids],
            ]
            if value
        ]
        if manifest_asset_ids != expected_asset_ids:
            raise ValueError("article manifest assets/mediaClosure drift")
        if any(
            str(row.get("sourceRef") or "") != closure.get("sourceRef")
            for row in manifest_assets
        ):
            raise ValueError("article manifest asset sourceRef/mediaClosure drift")
    return closure


def materialize_article_media(
    execution_id: str,
    ref: str,
    article_md: str,
    compose_payload: dict[str, Any],
) -> tuple[str, list[str]]:
    """Inject body figures and persist the object-local source receipt."""
    from content.post import object_index as content_object

    base_source_ref = str(
        compose_payload.get("baseSourceRef")
        or next(iter(compose_payload.get("citedSourceRefs") or []), "")
    ).strip()
    issues = article_media_contract_issues(compose_payload, base_source_ref)
    if issues:
        raise RuntimeError(f"{ref}: " + "; ".join(issues))
    assets = [
        row
        for row in (compose_payload.get("assets") or [])
        if isinstance(row, Mapping)
    ]
    text_only = (
        str(compose_payload.get("publishMediaMode") or "").strip() == "text_only"
    )
    mode = "text_only" if text_only else "illustrated"
    actions: list[str] = []
    if not text_only:
        body_assets = [
            row for row in assets if str(row.get("role") or "") != "cover"
        ]
        placed = place_assets_in_markdown(
            article_md, body_assets, cover_first=False
        )
        if placed != article_md:
            actions.append("article_body_media_injected")
        article_md = placed
        referenced = referenced_asset_ids(article_md)
        missing = [
            str(row.get("assetId") or "")
            for row in body_assets
            if str(row.get("assetId") or "") not in referenced
        ]
        if missing:
            raise RuntimeError(
                f"{ref}: article body image placement incomplete: {missing}"
            )
    receipt = _build_receipt(
        execution_id,
        object_ref=ref,
        source_ref=base_source_ref,
        assets=assets,
        mode=mode,
    )
    object_dir = content_object.content_object_dir(execution_id, ref)
    write_json(object_dir / ARTICLE_SOURCE_ASSET_RECEIPT_REF, receipt)
    profile = compose_payload.get("articleRenderProfile")
    render_profile = dict(profile) if isinstance(profile, Mapping) else {}
    render_profile["mediaClosure"] = _closure_from_receipt(receipt)
    compose_payload["articleRenderProfile"] = render_profile
    read_article_media_closure({"articleRenderProfile": render_profile})
    actions.append("article_media_receipt_written")
    row = receipt["sourceAssetCounts"][0]
    print(
        "[article] Source assets: "
        f"displayName={row['displayName']} provider={row['provider']} "
        f"assets={row['acceptedAssetCount']} planned={row['plannedAssetCount']} "
        f"discovered={row['discoveredAssetCount']} downloaded={row['downloadedAssetCount']} "
        f"accepted={row['acceptedAssetCount']} rejected={row['rejectedAssetCount']} "
        f"verified={row['verifiedAssetCount']} unverified={row['unverifiedAssetCount']} "
        f"restricted={row['restrictedAssetCount']} unknown={row['unknownAssetCount']}",
        flush=True,
    )
    return article_md, actions


__all__ = [
    "ARTICLE_MEDIA_CLOSURE_SCHEMA",
    "ARTICLE_SOURCE_ASSET_RECEIPT_REF",
    "article_media_contract_issues",
    "article_source_asset_counts",
    "materialize_article_media",
    "read_article_media_closure",
]
