"""Project reviewed hard-cut artifacts into execution-local final surfaces."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from content.release.canonical.entity_transaction_sources import source_assets_by_ref
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_file,
    _read_json,
    _safe_rel,
)
from content.release.canonical.post_transaction_assets import source_assets
from content.source.research.homepage_article_source_attribution import (
    encyclopedia_source_attribution,
)
from core.schema import assert_valid
from governance.creators.assignment import creator_from_payload


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _regular(path: Path, *, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ObjectTransactionError(f"publish final projection missing {label}")
    return path


def _source_rows(execution_root: Path, object_dir: Path) -> list[dict[str, Any]]:
    source_refs = _read_json(
        _regular(object_dir / "1.download/source_refs.json", label="source_refs")
    )
    raw_rows = source_refs.get("sources") if isinstance(source_refs, Mapping) else None
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ObjectTransactionError(
            "publish final projection requires non-empty source_refs"
        )
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, Mapping):
            raise ObjectTransactionError(f"source_refs.sources[{index}] must be object")
        source_ref = _safe_rel(
            str(raw.get("sourceRef") or ""), label="sourceRef"
        ).as_posix()
        meta_ref = _safe_rel(
            str(raw.get("metaRef") or ""), label="metaRef"
        ).as_posix()
        source_path = _regular(execution_root / source_ref, label=source_ref)
        meta = _read_json(_regular(execution_root / meta_ref, label=meta_ref))
        rows.append(
            {
                "sourceId": str(raw.get("sourceId") or meta.get("sourceId") or ""),
                "sourceRef": source_ref,
                "sourceUrl": str(
                    raw.get("sourceUrl")
                    or meta.get("canonicalUrl")
                    or meta.get("url")
                    or ""
                ).strip(),
                "sourceUseMode": str(meta.get("sourceUseMode") or "").strip(),
                "sourceKind": str(
                    meta.get("sourceKind")
                    or meta.get("sourceClass")
                    or raw.get("sourceClass")
                    or ""
                ).strip(),
                "fetchedAt": str(meta.get("fetchedAt") or "").strip(),
                "sourceAttribution": meta.get("sourceAttribution"),
                "meta": meta,
                "digest": _digest_file(source_path),
            }
        )
    return rows


def _source_catalog(
    rows: Sequence[Mapping[str, Any]], *, entity_name: str
) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    for raw in rows:
        meta = raw.get("meta") if isinstance(raw.get("meta"), Mapping) else {}
        url = str(raw.get("sourceUrl") or "").strip()
        mode = str(raw.get("sourceUseMode") or "").strip()
        source_id = str(raw.get("sourceId") or "").strip()
        identity = " ".join((source_id, str(raw.get("sourceKind") or ""))).lower()
        source_kind = (
            "wikipedia"
            if "wikipedia" in identity
            else "baidu_baike"
            if "baidu" in identity
            else "toutiao_baike"
            if "toutiao" in identity
            else ""
        )
        if (
            not url.startswith("https://")
            or mode not in {"licensed_adaptation", "factual_reference_only"}
            or not source_kind
        ):
            raise ObjectTransactionError(
                "homepage source catalog lacks canonical encyclopedia facts"
            )
        source_ref = str(raw.get("sourceRef") or "")
        unit_id = Path(source_ref).parts[1]
        row = {
            "schema": "quwoquan_data.object_source_evidence",
            "sourceUnitId": unit_id,
            "entityName": entity_name,
            "sourceKind": source_kind,
            "extractor": {
                "wikipedia": "wikipedia_api",
                "baidu_baike": "baidu_baike_html",
                "toutiao_baike": "toutiao_baike_html",
            }[source_kind],
            "canonicalUrl": url,
            "sourceUrl": url,
            "title": str(meta.get("title") or entity_name),
            "fetchedAt": str(raw.get("fetchedAt") or ""),
            "snapshotHash": str(meta.get("rawSha256") or raw.get("digest") or ""),
            "policyRevision": "encyclopedia-primary",
            "sourceUseMode": mode,
            "evidenceRef": f"evidence/sources/{unit_id}/meta.json",
        }
        sources.append(row)
    if not sources:
        raise ObjectTransactionError("homepage source catalog requires sources")
    catalog = {
        "schema": "quwoquan_data.object_source_catalog",
        "policyRevision": "encyclopedia-primary",
        "primaryEvidenceRef": sources[0]["evidenceRef"],
        "primarySource": sources[0],
        "sources": sources,
    }
    assert_valid(catalog, "publish", "source_catalog", label="homepage source catalog")
    return catalog

def _creator_fields(compose: Mapping[str, Any], *, carrier: str) -> dict[str, Any]:
    profile_ref = str(compose.get("creatorProfileRef") or "").strip()
    fields = creator_from_payload({"creatorProfileId": profile_ref}) if profile_ref else {}
    if not fields:
        raise ObjectTransactionError(
            f"{carrier} compose lacks resolvable creatorProfileRef"
        )
    return fields


def _text_attribution(
    rows: Sequence[Mapping[str, Any]], creator: Mapping[str, Any]
) -> dict[str, Any]:
    explicit = [raw.get("sourceAttribution") for raw in rows if raw.get("sourceAttribution")]
    if explicit:
        identities = {_json_bytes(value) for value in explicit}
        if len(identities) != 1:
            raise ObjectTransactionError("selected sourceAttribution values drift")
        return dict(explicit[0])
    primary = rows[0]
    source_url = str(primary.get("sourceUrl") or "")
    source_identity = " ".join(
        str(primary.get(key) or "")
        for key in ("sourceId", "sourceRef", "sourceKind")
    ).lower()
    if "wikipedia" in source_identity:
        return encyclopedia_source_attribution(
            source_kind="wikipedia",
            source_url=source_url,
            captured_at=str(primary.get("fetchedAt") or ""),
        )
    collected_at = str(primary.get("fetchedAt") or "").strip()
    author_id = str(creator.get("authorId") or "").strip()
    if not source_url.startswith("https://") or not collected_at or not author_id:
        raise ObjectTransactionError(
            "selected sources cannot mechanically project text attribution"
        )
    return {
        "isOriginal": True,
        "originalCreatorId": author_id,
        "originalCreatorName": author_id,
        "originalCreatorProfileUrl": None,
        "platform": "趣我圈",
        "sourcePostUrl": source_url,
        "originalAssetUrl": source_url,
        "attributionText": "原创表达；事实来源见 source catalog。",
        "rightsBasis": "original_expression_with_factual_reference_only",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "authorizationProofUrl": None,
        "termsUrl": None,
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": collected_at,
        "takedownPolicy": "remove_or_correct_on_verified_rights_or_source_dispute",
        "derivedModifications": [],
    }


def _media_attribution(
    assets: Sequence[Mapping[str, Any]], *, carrier: str, collected_at: str
) -> dict[str, Any]:
    if not assets:
        raise ObjectTransactionError(f"{carrier} attribution requires selected assets")
    first = assets[0]
    creator = str(first.get("creator") or "").strip()
    source_url = str(first.get("collectionPageUrl") or "").strip()
    terms_url = str(first.get("termsUrl") or "").strip()
    proof = str(first.get("authorizationProof") or "").strip()
    license_name = str(first.get("license") or "").strip()
    if not all((creator, source_url.startswith("https://"), license_name)):
        raise ObjectTransactionError(
            f"{carrier} selected assets lack attribution hard facts"
        )
    all_commercial = carrier != "video" and all(
        raw.get("distributionDecision") == "commercial_allowed"
        and raw.get("rightsAuditStatus") == "verified"
        and str(raw.get("authorizationProof") or "").startswith("https://")
        and str(raw.get("termsUrl") or "").startswith("https://")
        for raw in assets
    )
    platform = str(first.get("platform") or "").strip() or urlparse(source_url).netloc
    return {
        "isOriginal": False,
        "originalCreatorId": None,
        "originalCreatorName": creator,
        "originalCreatorProfileUrl": None,
        "platform": platform,
        "sourcePostUrl": source_url,
        "originalAssetUrl": str(first.get("originalAssetUrl") or source_url),
        "attributionText": f"{creator} · {platform} · {license_name}",
        "rightsBasis": license_name,
        "commercialAuthorizationStatus": "verified" if all_commercial else "unverified",
        "publicationAdmission": "research_release",
        "authorizationProofUrl": proof or None,
        "termsUrl": terms_url or None,
        "watermarkStatus": "absent",
        "audioRightsStatus": "unverified" if carrier == "video" else "no_audio",
        "modelReleaseStatus": str(first.get("modelReleaseStatus") or "not_required"),
        "propertyReleaseStatus": str(first.get("propertyReleaseStatus") or "unverified"),
        "collectedAt": collected_at,
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
        "derivedModifications": [],
    }


def _target_entity_ref(target: Mapping[str, Any]) -> str:
    entity_type = str(target.get("entityType") or "").strip().strip("/")
    name = str(target.get("name") or "").strip()
    if len(entity_type.split("/")) != 2 or not name:
        raise ObjectTransactionError("target entity identity is incomplete")
    return f"/entity/{entity_type}/{name}"


def _target_tag_refs(target: Mapping[str, Any]) -> list[str]:
    refs = {f"Entity/{str(target.get('entityType') or '').strip('/')}"}
    region = str(target.get("region") or "").strip().strip("/")
    if region:
        refs.add(f"Topic/地理/行政区/{region}")
    return sorted(ref for ref in refs if ref != "Entity/")


def _content_id(execution_id: str, target_ref: str) -> str:
    digest = hashlib.sha256(f"{execution_id}|{target_ref}".encode()).hexdigest()
    return "qwq_data_" + digest[:24]


def _created_at(rows: Sequence[Mapping[str, Any]]) -> str:
    values = sorted(
        str(row.get("fetchedAt") or "").strip()
        for row in rows
        if row.get("fetchedAt")
    )
    if not values:
        raise ObjectTransactionError("selected sources lack deterministic fetchedAt")
    return values[-1]


def _author_model(execution_root: Path) -> str | None:
    receipt = _read_json(
        _regular(
            execution_root / "_shared/receipts/006-4.draft.json",
            label="sequence-006 receipt",
        )
    )
    invocation = receipt.get("actor", {}).get("invocation", {})
    value = str(invocation.get("model") or "").strip()
    return value or None


def _post_manifest(
    *,
    execution_root: Path,
    target_ref: str,
    target: Mapping[str, Any],
    compose: Mapping[str, Any],
    carrier: str,
    source_rows: Sequence[Mapping[str, Any]],
    assets: list[dict[str, Any]],
    draft: Mapping[str, Any],
) -> dict[str, Any]:
    created_at = _created_at(source_rows)
    creator = _creator_fields(compose, carrier=carrier)
    attribution = (
        _text_attribution(source_rows, creator)
        if carrier == "article"
        else _media_attribution(assets, carrier=carrier, collected_at=created_at)
    )
    manifest: dict[str, Any] = {
        "schema": "quwoquan_data.post_manifest",
        "contentId": _content_id(execution_root.name, target_ref),
        "version": 1,
        "vertical": str(compose.get("vertical") or "travel"),
        "topicId": target_ref.removeprefix("posts/"),
        "contentType": carrier,
        "contentIdentity": "work",
        "title": str(draft.get("title") or compose.get("title") or target.get("publishTitle") or ""),
        "entityRefs": [_target_entity_ref(target)],
        "tagRefs": sorted(
            {str(value) for value in compose.get("tagRefs") or [] if str(value)}
        ),
        **creator,
        "sourceUrls": [str(row["sourceUrl"]) for row in source_rows],
        "sourceAttribution": attribution,
        "assets": assets,
        "carrier": carrier,
        "generator": "agent",
        "generatorModel": _author_model(execution_root),
        "citedSourceRefs": [
            str(value) for value in compose.get("selectedSourceRefs") or []
        ],
        "reviewDecision": "approved",
        "publishLayout": str(compose.get("publishLayout") or carrier),
        "publishAngle": str(target.get("publishAngle") or ""),
        "publishTitle": str(target.get("publishTitle") or compose.get("title") or ""),
        "publishSeq": int(target.get("publishSeq") or 1),
        "createdAt": created_at,
        "updatedAt": created_at,
        "executionId": execution_root.name,
    }
    if compose.get("writingIntent"):
        manifest["writingIntent"] = compose["writingIntent"]
    if carrier == "article":
        manifest.update(
            publishMediaMode="text_only",
            markdownDialect="qwq-rich-md",
            articleRenderProfile={
                "template": "guide",
                "fontPreset": "clean",
                "layoutPolicy": {
                    "wrapDowngrade": "compactWidthToFullWidth",
                    "galleryDowngrade": "singleColumn",
                },
            },
        )
    elif carrier == "image":
        first = assets[0]
        manifest.update(
            caption=str(draft.get("caption") or ""),
            sourceCollectionId=str(first.get("sourceCollectionId") or ""),
            creator=str(first.get("creator") or ""),
            collectionPageUrl=str(first.get("collectionPageUrl") or ""),
            license=str(first.get("license") or ""),
            termsUrl=str(first.get("termsUrl") or ""),
            authorizationProof=str(first.get("authorizationProof") or ""),
            rightsAuditStatus=str(first.get("rightsAuditStatus") or ""),
            rightsAuditIssues=sorted(
                {
                    str(issue)
                    for asset in assets
                    for issue in asset.get("rightsAuditIssues") or []
                    if str(issue)
                }
            ),
        )
    else:
        manifest.update(
            caption=str(draft.get("caption") or ""),
            videoBindings=[
                {"assetId": asset["assetId"], "role": "shortVideo"}
                for asset in assets
                if asset.get("kind") == "video"
            ],
        )
    assert_valid(
        manifest,
        "content",
        "post_manifest",
        label=f"publish final projection {target_ref}",
    )
    return manifest


def _probe_video(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name,pix_fmt",
            "-show_entries", "format=format_name,duration", "-of", "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise ObjectTransactionError("selected source video is not mechanically probeable")
    payload = json.loads(completed.stdout)
    streams = payload.get("streams") or []
    fmt = payload.get("format") or {}
    if len(streams) != 1:
        raise ObjectTransactionError("selected source video must have one primary stream")
    stream = streams[0]
    facts = {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "codec": str(stream.get("codec_name") or ""),
        "pixelFormat": str(stream.get("pix_fmt") or ""),
        "container": str(fmt.get("format_name") or "").split(",")[-1],
        "durationMs": round(float(fmt.get("duration") or 0) * 1000),
    }
    if any(not facts[key] for key in facts):
        raise ObjectTransactionError("selected source video probe is incomplete")
    return facts


def _source_unit_meta(execution_root: Path, source_ref: str) -> dict[str, Any]:
    unit_ref = Path(source_ref).parent.parent
    return _read_json(_regular(execution_root / unit_ref / "meta.json", label="source meta"))


def _video_poster_ref(
    *, execution_root: Path, video_ref: str, explicit_ref: str
) -> str:
    meta = _source_unit_meta(execution_root, video_ref)
    acquisition = meta.get("acquisition")
    recorded_relative = (
        str(acquisition.get("posterAssetRef") or "").strip()
        if isinstance(acquisition, Mapping)
        else ""
    )
    recorded = (
        (Path(video_ref).parent.parent / recorded_relative).as_posix()
        if recorded_relative
        else ""
    )
    if explicit_ref and recorded and explicit_ref != recorded:
        raise ObjectTransactionError("selected source video poster binding drift")
    poster_ref = explicit_ref or recorded
    if not poster_ref:
        raise ObjectTransactionError("selected source video lacks exact poster binding")
    return poster_ref


def _selected_asset_refs(
    carrier: str,
    compose: Mapping[str, Any],
    draft: Mapping[str, Any],
    *,
    execution_root: Path,
) -> list[str]:
    if carrier == "article":
        rows = compose.get("assets") or []
        refs = [
            str(raw.get("sourceAssetRef") or raw.get("assetRef") or "").strip()
            for raw in rows
            if isinstance(raw, Mapping)
        ]
        if refs:
            raise ObjectTransactionError(
                "fresh article final projection supports text_only only"
            )
        return []
    if carrier == "image":
        values = draft.get("assetRefs")
        return [str(value).strip() for value in values or []]
    if carrier == "video":
        source_video = compose.get("sourceVideo")
        if isinstance(source_video, Mapping):
            video_ref = str(
                source_video.get("assetRef")
                or source_video.get("sourceAssetRef")
                or ""
            ).strip()
            explicit_poster = str(
                source_video.get("posterAssetRef")
                or compose.get("posterAssetRef")
                or ""
            ).strip()
        else:
            selected = [
                str(raw.get("assetRef") or raw.get("sourceAssetRef") or "").strip()
                for raw in compose.get("assets") or []
                if isinstance(raw, Mapping)
                and str(raw.get("assetRole") or "").strip() == "video"
            ]
            if len(selected) != 1:
                raise ObjectTransactionError(
                    "video compose assets must select one source video"
                )
            video_ref, explicit_poster = selected[0], ""
        if not video_ref:
            raise ObjectTransactionError("video compose source video assetRef is missing")
        return [
            video_ref,
            _video_poster_ref(
                execution_root=execution_root,
                video_ref=video_ref,
                explicit_ref=explicit_poster,
            ),
        ]
    return [
        str(raw.get("sourceAssetRef") or raw.get("assetRef") or "").strip()
        for raw in compose.get("assets") or []
        if isinstance(raw, Mapping)
    ]


def _source_creator(execution_root: Path, source_ref: str, source: Mapping[str, Any]) -> str:
    creator = str(source.get("creator") or source.get("credit") or "").strip()
    if creator:
        return creator
    clue = str(_source_unit_meta(execution_root, source_ref).get("rightsClue") or "")
    if clue.startswith("作者 ") and "，" in clue:
        return clue.removeprefix("作者 ").split("，", 1)[0].strip()
    return ""


def _asset_projection(
    *,
    execution_root: Path,
    source_ref: str,
    source: Mapping[str, Any],
    caption: str,
) -> tuple[dict[str, Any], Path, Path]:
    source_path = _regular(execution_root / source_ref, label=source_ref)
    destination = Path("assets") / source_path.name
    asset_role = str(source.get("assetRole") or "").strip()
    kind = "video" if asset_role == "video" else "image"
    creator = _source_creator(execution_root, source_ref, source)
    source_url = str(
        source.get("collectionPageUrl")
        or source.get("sourceUrl")
        or source.get("url")
        or ""
    ).strip()
    license_name = str(source.get("license") or "").strip()
    if not creator or not source_url.startswith("https://") or not license_name:
        raise ObjectTransactionError(
            f"selected source asset lacks creator/source/license hard facts: {source_ref}"
        )
    rights_status = str(
        source.get("rightsStatus") or source.get("rightsAuditStatus") or ""
    ).strip()
    digest = _digest_file(source_path)
    digest_hex = digest.removeprefix("sha256:")
    suffix = source_path.suffix.lower().lstrip(".") or "bin"
    row: dict[str, Any] = {
        "assetId": str(source.get("sourceAssetId") or source_path.stem),
        "fileName": destination.as_posix(),
        "caption": caption,
        "kind": kind,
        "role": (
            "embedded"
            if kind == "video"
            else "cover"
            if asset_role == "poster"
            else "detail"
        ),
        "sourceAssetId": str(source.get("sourceAssetId") or ""),
        "creator": creator,
        "platform": str(source.get("platform") or "")
        or urlparse(source_url).netloc,
        "collectionPageUrl": source_url,
        "originalAssetUrl": str(source.get("originalAssetUrl") or source_url),
        "license": license_name,
        "termsUrl": str(source.get("termsUrl") or ""),
        "authorizationProof": str(source.get("authorizationProof") or ""),
        "usageScope": str(source.get("usageScope") or "app_publish"),
        "modelReleaseStatus": str(
            source.get("modelReleaseStatus") or "not_required"
        ),
        "propertyReleaseStatus": str(
            source.get("propertyReleaseStatus") or "unverified"
        ),
        "distributionDecision": str(source.get("distributionDecision") or ""),
        "rightsAuditStatus": (
            "verified" if rights_status == "verified" else rights_status
        ),
        "rightsAuditIssues": [
            str(value)
            for value in source.get("rightsIssues")
            or source.get("rightsAuditIssues")
            or []
            if str(value)
        ],
        "sha256": digest,
        "objectKey": (
            f"media/objects/sha256/{digest_hex[:2]}/{digest_hex[2:4]}/"
            f"{digest_hex}.{suffix}"
        ),
        "mimeType": str(source.get("mimeType") or "application/octet-stream"),
        "sourceCollectionId": str(
            source.get("sourceCollectionId")
            or source.get("professionalAssetId")
            or Path(source_ref).parts[1]
        ),
    }
    if kind == "video":
        row["sourceAssetRefs"] = [source_ref]
    else:
        row["sourceAssetRef"] = source_ref
    return (
        {key: value for key, value in row.items() if value not in ("", None)},
        destination,
        source_path,
    )


def _bind_video_surface(
    *,
    refs: Sequence[str],
    index: Mapping[str, Mapping[str, Any]],
    assets: list[dict[str, Any]],
    files: dict[Path, bytes | Path],
) -> None:
    by_kind = {asset["kind"]: asset for asset in assets}
    video = by_kind["video"]
    poster = by_kind["image"]
    source_video_path = files[Path(video["fileName"])]
    if not isinstance(source_video_path, Path):
        raise ObjectTransactionError("selected source video path is invalid")
    receipt_refs = sorted(
        {
            str(index[ref].get("acquisitionReceiptRef") or "").strip()
            for ref in refs
        }
    )
    if "" in receipt_refs:
        raise ObjectTransactionError(
            "selected source video or poster lacks acquisitionReceiptRef"
        )
    video.update(
        _probe_video(source_video_path),
        posterAssetId=poster["assetId"],
        posterFileName=poster["fileName"],
        posterSha256=poster["sha256"],
        rightsRefs=receipt_refs,
    )


def _project_assets(
    *,
    execution_root: Path,
    object_dir: Path,
    carrier: str,
    compose: Mapping[str, Any],
    draft: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[Path, bytes | Path]]:
    index = (
        source_assets_by_ref(execution_root)
        if carrier == "homepage"
        else source_assets(execution_root)
    )
    refs = _selected_asset_refs(
        carrier, compose, draft, execution_root=execution_root
    )
    if carrier == "article":
        return [], {}
    if not refs or any(not ref for ref in refs) or len(refs) != len(set(refs)):
        raise ObjectTransactionError(
            f"{carrier} final projection requires unique selected assets"
        )
    missing = [ref for ref in refs if ref not in index]
    if missing:
        raise ObjectTransactionError(
            "selected source assets are missing: " + ", ".join(missing)
        )
    if carrier == "video":
        roles = sorted(str(index[ref].get("assetRole") or "") for ref in refs)
        if roles != ["poster", "video"]:
            raise ObjectTransactionError(
                "video final projection requires exact video+poster assets"
            )
    caption = str(draft.get("caption") or compose.get("title") or "")
    assets: list[dict[str, Any]] = []
    files: dict[Path, bytes | Path] = {}
    for ref in refs:
        row, destination, source_path = _asset_projection(
            execution_root=execution_root,
            source_ref=ref,
            source=index[ref],
            caption=caption,
        )
        if destination in files and files[destination] != source_path:
            raise ObjectTransactionError(
                f"selected assets collide at {destination.as_posix()}"
            )
        files[destination] = source_path
        assets.append(row)
    if carrier == "video":
        _bind_video_surface(
            refs=refs, index=index, assets=assets, files=files
        )
    return assets, files

def _homepage_surface(
    *,
    execution_root: Path,
    object_dir: Path,
    target_ref: str,
    target: Mapping[str, Any],
    compose: Mapping[str, Any],
    source_rows: Sequence[Mapping[str, Any]],
) -> dict[Path, bytes | Path]:
    page_path = _regular(object_dir / "4.draft/page.md", label="homepage draft")
    creator = _creator_fields(
        {"creatorProfileRef": "qwq_creator_geo_editor_001"}, carrier="homepage"
    )
    attribution = _text_attribution(source_rows, creator)
    payload = compose.get("payload") if isinstance(compose.get("payload"), Mapping) else {}
    homepage_compose = {
        "assets": payload.get("imagePlaceholderBindings") or [],
        "title": str(target.get("name") or ""),
    }
    assets, media = _project_assets(
        execution_root=execution_root,
        object_dir=object_dir,
        carrier="homepage",
        compose=homepage_compose,
        draft={},
    ) if homepage_compose["assets"] else ([], {})
    entity_ref = "/entity/" + target_ref.removeprefix("entities/")
    domain, type_name = str(target.get("entityType") or "").split("/", 1)
    tag_refs = _target_tag_refs(target)
    entity = {
        "label": str(target.get("name") or ""),
        "domain": domain,
        "type": type_name,
        "executionId": execution_root.name,
        "entityRef": entity_ref,
        "sourceRefs": [str(row["sourceRef"]) for row in source_rows],
        "sourceUrls": [str(row["sourceUrl"]) for row in source_rows],
        "primarySource": {
            "sourceKind": str(source_rows[0].get("sourceKind") or ""),
            "sourceUrl": str(source_rows[0].get("sourceUrl") or ""),
            "fetchedAt": str(source_rows[0].get("fetchedAt") or ""),
        },
        "sourceAttribution": attribution,
        "tagRefs": tag_refs,
        **creator,
    }
    manifest = {
        "vertical": "travel",
        "sourceAttribution": attribution,
        "assets": assets,
        "contentType": "article",
        "publishMediaMode": "text_only",
    }
    return {
        Path("page.md"): page_path,
        Path("_entity.json"): _json_bytes(entity),
        Path("manifest.json"): _json_bytes(manifest),
        Path("evidence/source_catalog.json"): _json_bytes(
            _source_catalog(source_rows, entity_name=str(target.get("name") or ""))
        ),
        **media,
    }


def _post_surface(
    *,
    execution_root: Path,
    object_dir: Path,
    target_ref: str,
    target: Mapping[str, Any],
    carrier: str,
    compose: Mapping[str, Any],
    source_rows: Sequence[Mapping[str, Any]],
) -> dict[Path, bytes | Path]:
    draft_path = object_dir / "4.draft" / {
        "article": "draft.article.md",
        "image": "image_work.json",
        "video": "video_script.json",
    }[carrier]
    draft = (
        {}
        if carrier == "article"
        else _read_json(_regular(draft_path, label=f"{carrier} draft"))
    )
    assets, media = _project_assets(
        execution_root=execution_root,
        object_dir=object_dir,
        carrier=carrier,
        compose=compose,
        draft=draft,
    )
    manifest = _post_manifest(
        execution_root=execution_root,
        target_ref=target_ref,
        target=target,
        compose=compose,
        carrier=carrier,
        source_rows=source_rows,
        assets=assets,
        draft=draft,
    )
    surface: dict[Path, bytes | Path] = {
        Path("manifest.json"): _json_bytes(manifest),
        **media,
    }
    if carrier == "article":
        surface[Path("article.md")] = _regular(draft_path, label="article draft")
    return surface


def _same_content(path: Path, expected: bytes | Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    if isinstance(expected, bytes):
        return path.read_bytes() == expected
    return path.stat().st_size == expected.stat().st_size and _digest_file(path) == _digest_file(expected)


def _write_create_once(
    object_dir: Path, surface: Mapping[Path, bytes | Path]
) -> bool:
    conflicts = [
        relative.as_posix()
        for relative, expected in surface.items()
        if (object_dir / relative).exists()
        and not _same_content(object_dir / relative, expected)
    ]
    if conflicts:
        raise ObjectTransactionError(
            "publish final surface drift: " + ", ".join(sorted(conflicts))
        )
    missing = [
        (relative, expected)
        for relative, expected in surface.items()
        if not (object_dir / relative).exists()
    ]
    if not missing:
        return True
    temporary = Path(tempfile.mkdtemp(prefix=".publish-final-", dir=object_dir))
    try:
        for relative, expected in missing:
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(expected, bytes):
                target.write_bytes(expected)
            else:
                shutil.copy2(expected, target)
        for relative, expected in missing:
            target = object_dir / relative
            if target.exists():
                if not _same_content(target, expected):
                    raise ObjectTransactionError(
                        f"publish final surface concurrent drift: {relative.as_posix()}"
                    )
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            (temporary / relative).replace(target)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return False


def project_publish_final_surface(
    *,
    execution_root: Path,
    object_dir: Path,
    target_ref: str,
    target: Mapping[str, Any],
    carrier: str,
) -> dict[str, Any]:
    """Create or exact-replay one final surface after sequence-007 approval."""
    compose_name = (
        "entity_page_input.json" if carrier == "homepage" else "writing_pack.json"
    )
    compose = _read_json(
        _regular(object_dir / "3.compose" / compose_name, label="compose input")
    )
    source_rows = _source_rows(execution_root, object_dir)
    if carrier == "homepage":
        surface = _homepage_surface(
            execution_root=execution_root,
            object_dir=object_dir,
            target_ref=target_ref,
            target=target,
            compose=compose,
            source_rows=source_rows,
        )
    else:
        surface = _post_surface(
            execution_root=execution_root,
            object_dir=object_dir,
            target_ref=target_ref,
            target=target,
            carrier=carrier,
            compose=compose,
            source_rows=source_rows,
        )
    replayed = _write_create_once(object_dir, surface)
    manifest = _read_json(
        _regular(object_dir / "manifest.json", label="final manifest")
    )
    return {
        "manifest": manifest,
        "finalFiles": sorted(relative.as_posix() for relative in surface),
        "replayed": replayed,
    }


__all__ = ["project_publish_final_surface"]
