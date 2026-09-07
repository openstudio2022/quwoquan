"""Project reviewed six-step artifacts into execution-local final surfaces.

投影输入只有：`0.plan/target_set.json` 的 target、`1.download/source_refs.json` 与 source unit、
author 产物（page.md / draft.article.md / image_work.json / video_script.json）与 review 结论。
author 产物的 frontmatter / 字段直接声明 title、tagRefs、creatorProfileId 与选用资产；没有 compose 文件。
"""
from __future__ import annotations

import hashlib
import json
import re
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
from content.release.canonical.media_rights_projection import (
    asset_rights_fields,
    object_rights_rollup,
)
from content.release.canonical.post_transaction_assets import source_assets
from content.source.research.homepage_article_source_attribution import (
    encyclopedia_source_attribution,
)
from core.content_library import reference_existing_file
from core.control_types import AUTHOR_ARTIFACT_BY_CARRIER
from core.schema import assert_valid
from governance.creators.assignment import creator_from_payload

_DEFAULT_CREATOR = {
    "homepage": "qwq_creator_geo_editor_001",
    "article": "qwq_creator_travel_blogger_001",
    "image": "qwq_creator_landscape_photographer_001",
    "video": "qwq_creator_travel_blogger_001",
}
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """读取 Markdown 顶部 YAML frontmatter；只支持 key: scalar 与 key: [a, b] 两种形态。"""

    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    result: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.startswith((" ", "\t", "#")):
            continue
        key, _sep, raw = line.partition(":")
        value = raw.strip()
        if value.startswith("[") and value.endswith("]"):
            result[key.strip()] = [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
        else:
            result[key.strip()] = value.strip("'\"")
    return result


def _resolve_asset_ref(raw: str, index: Mapping[str, Mapping[str, Any]], *, label: str) -> str:
    """接受 fileName / assets/<fileName> / 完整 sources 路径，归一为 execution 相对资产路径。"""

    value = str(raw or "").strip().strip("/")
    if value in index:
        return value
    tail = value.removeprefix("assets/")
    matches = [ref for ref in index if ref.endswith(f"/assets/{tail}")]
    if len(matches) != 1:
        raise ObjectTransactionError(f"{label} asset ref 无法唯一解析：{raw!r}")
    return matches[0]


def _author_intent(
    *,
    object_dir: Path,
    carrier: str,
    target: Mapping[str, Any],
    source_rows: Sequence[Mapping[str, Any]],
    asset_index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """从 author 产物直接读出发布意图，替代已删除的 compose 文件。"""

    draft_path = _regular(object_dir / "4.draft" / AUTHOR_ARTIFACT_BY_CARRIER[carrier], label=f"{carrier} draft")
    intent: dict[str, Any] = {
        "vertical": "travel",
        "publishLayout": carrier,
        "selectedSourceRefs": [str(row["sourceRef"]) for row in source_rows],
        "assets": [],
    }
    if draft_path.suffix == ".json":
        document = _read_json(draft_path)
        intent["title"] = str(document.get("title") or target.get("publishTitle") or target.get("name") or "")
        intent["caption"] = str(document.get("caption") or "")
        intent["tagRefs"] = [str(value) for value in document.get("tagRefs") or []]
        intent["creatorProfileRef"] = str(document.get("creatorProfileId") or _DEFAULT_CREATOR[carrier])
        if carrier == "image":
            refs = [_resolve_asset_ref(str(value), asset_index, label="image_work.assetRefs") for value in document.get("assetRefs") or []]
            intent["assets"] = [{"assetRef": ref, "caption": intent["caption"]} for ref in refs]
        else:
            explicit = str(document.get("sourceVideoAssetRef") or "").strip()
            videos = [ref for ref, row in asset_index.items() if str(row.get("assetRole") or "") == "video"]
            video_ref = _resolve_asset_ref(explicit, asset_index, label="video_script.sourceVideoAssetRef") if explicit else (videos[0] if len(videos) == 1 else "")
            if not video_ref:
                raise ObjectTransactionError("video author artifact must select exactly one source video")
            intent["sourceVideo"] = {"assetRef": video_ref}
        intent["draft"] = document
        return intent
    text = draft_path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text)
    heading = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("# ")), "")
    intent["title"] = str(frontmatter.get("title") or heading or target.get("publishTitle") or target.get("name") or "")
    tag_refs = frontmatter.get("tagRefs")
    intent["tagRefs"] = [str(value) for value in tag_refs] if isinstance(tag_refs, list) else []
    intent["creatorProfileRef"] = str(frontmatter.get("creatorProfileId") or _DEFAULT_CREATOR[carrier])
    seen: list[str] = []
    for raw in _MARKDOWN_IMAGE_RE.findall(text):
        if raw.startswith(("http://", "https://")):
            raise ObjectTransactionError("正文只允许引用本对象 assets/ 内的已取得图片，不得外链")
        ref = _resolve_asset_ref(raw, asset_index, label=f"{carrier} 正文图片")
        if ref not in seen:
            seen.append(ref)
    intent["assets"] = [{"assetRef": ref, "caption": ""} for ref in seen]
    intent["draft"] = {"title": intent["title"]}
    return intent


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


def _homepage_source_kind(raw: Mapping[str, Any]) -> tuple[str, str, str]:
    identity = " ".join(
        (
            str(raw.get("sourceId") or ""),
            str(raw.get("sourceKind") or ""),
            str((raw.get("meta") or {}).get("sourceClass") or ""),
        )
    ).lower()
    if "wikipedia" in identity:
        return "wikipedia", "wikipedia_api", "encyclopedia-primary"
    if "baidu" in identity:
        return "baidu_baike", "baidu_baike_html", "encyclopedia-primary"
    if "toutiao" in identity:
        return "toutiao_baike", "toutiao_baike_html", "encyclopedia-primary"
    if any(marker in identity for marker in ("media", "image", "commons")):
        return "image_collection", "image_collection_download", "image-collection-attribution"
    # 非百科的公开网页也可作事实参考；catalog 以 web_page 登记，不阻断。
    return "web_page", "html_text", ""


def _source_catalog(
    rows: Sequence[Mapping[str, Any]], *, entity_name: str
) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    for raw in rows:
        meta = raw.get("meta") if isinstance(raw.get("meta"), Mapping) else {}
        url = str(raw.get("sourceUrl") or "").strip()
        mode = str(raw.get("sourceUseMode") or "").strip()
        source_kind, extractor, policy_revision = _homepage_source_kind(raw)
        if (
            not url.startswith("https://")
            or mode not in {"licensed_adaptation", "factual_reference_only"}
        ):
            raise ObjectTransactionError(
                "homepage source catalog lacks canonical source facts"
            )
        source_ref = str(raw.get("sourceRef") or "")
        unit_id = Path(source_ref).parts[1]
        row = {
            "schema": "quwoquan_data.object_source_evidence",
            "sourceUnitId": unit_id,
            "entityName": entity_name,
            "sourceKind": source_kind,
            "extractor": extractor,
            "canonicalUrl": url,
            "sourceUrl": url,
            "title": str(meta.get("title") or entity_name),
            "fetchedAt": str(raw.get("fetchedAt") or ""),
            "snapshotHash": str(meta.get("rawSha256") or raw.get("digest") or ""),
            "policyRevision": policy_revision,
            "sourceUseMode": mode,
            "evidenceRef": f"evidence/sources/{unit_id}/meta.json",
        }
        sources.append(row)
    primaries = [
        row for row in sources if row["policyRevision"] == "encyclopedia-primary"
    ] or [row for row in sources if row["sourceKind"] not in {"image_collection"}] or sources
    catalog = {
        "schema": "quwoquan_data.object_source_catalog",
        "policyRevision": "encyclopedia-primary" if primaries[0]["policyRevision"] == "encyclopedia-primary" else "factual-reference",
        "primaryEvidenceRef": primaries[0]["evidenceRef"],
        "primarySource": primaries[0],
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
    encyclopedia = [
        raw
        for raw in rows
        if any(
            marker in " ".join(
                str(raw.get(key) or "")
                for key in ("sourceId", "sourceRef", "sourceKind")
            ).lower()
            for marker in ("wikipedia", "baidu", "toutiao")
        )
    ]
    primary = encyclopedia[0] if encyclopedia else rows[0]
    source_url = str(primary.get("sourceUrl") or "")
    source_identity = " ".join(
        str(primary.get(key) or "")
        for key in ("sourceId", "sourceRef", "sourceKind")
    ).lower()
    for marker, source_kind in (
        ("wikipedia", "wikipedia"),
        ("baidu", "baidu_baike"),
        ("toutiao", "toutiao_baike"),
    ):
        if marker in source_identity:
            return encyclopedia_source_attribution(
                source_kind=source_kind,
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
    rights = object_rights_rollup(assets, carrier)
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
        **{k: rights[k] for k in ("watermarkStatus", "watermarkKind", "audioRightsStatus")},
        "modelReleaseStatus": str(first.get("modelReleaseStatus") or "not_required"),
        "propertyReleaseStatus": str(first.get("propertyReleaseStatus") or "unverified"),
        "collectedAt": collected_at,
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
        "derivedModifications": rights["derivedModifications"],
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
            execution_root / "_shared/receipts/002-4.draft.json",
            label="author receipt",
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
            publishMediaMode="illustrated" if assets else "text_only",
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
    if not streams:
        raise ObjectTransactionError("selected source video has no video stream")
    stream = streams[0]
    facts = {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "codec": str(stream.get("codec_name") or ""),
        "pixelFormat": str(stream.get("pix_fmt") or ""),
        "container": str(fmt.get("format_name") or "").split(",")[-1],
        "durationMs": round(float(fmt.get("duration") or 0) * 1000),
    }
    # 唯一硬门：可探测且有时长；其余探测字段缺失只作为事实缺省，不阻断。
    if facts["durationMs"] <= 0:
        raise ObjectTransactionError("selected source video has no playable duration")
    return {key: value for key, value in facts.items() if value}


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
    if carrier in {"article", "image"}:
        return [
            str(raw.get("sourceAssetRef") or raw.get("assetRef") or "").strip()
            for raw in compose.get("assets") or []
            if isinstance(raw, Mapping)
        ]
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
        "sourceRef": (Path(source_ref).parent.parent / "source.md").as_posix(),
        "creator": creator,
        "platform": str(source.get("platform") or "")
        or urlparse(source_url).netloc,
        "collectionPageUrl": source_url,
        "originalAssetUrl": str(source.get("originalAssetUrl") or source_url),
        "license": license_name,
        "termsUrl": str(source.get("termsUrl") or ""),
        "authorizationProof": str(source.get("authorizationProof") or ""),
        "usageScope": str(source.get("usageScope") or "app_publish"),
        "modelReleaseStatus": str(source.get("modelReleaseStatus") or "not_required"),
        "propertyReleaseStatus": str(source.get("propertyReleaseStatus") or "unverified"),
        "distributionDecision": str(source.get("distributionDecision") or ""),
        "rightsAuditStatus": rights_status,
        "rightsAuditIssues": [
            str(value) for value in source.get("rightsIssues") or source.get("rightsAuditIssues") or [] if str(value)
        ],
        "sha256": digest,
        "objectKey": (
            f"media/objects/sha256/{digest_hex[:2]}/{digest_hex[2:4]}/"
            f"{digest_hex}.{suffix}"
        ),
        "mimeType": str(source.get("mimeType") or "application/octet-stream"),
        "sourceCollectionId": str(
            source.get("sourceCollectionId") or source.get("professionalAssetId") or Path(source_ref).parts[1]
        ),
        **asset_rights_fields(source, kind),
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
    if carrier == "article" and not refs:
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
    binding_captions = {
        str(raw.get("sourceAssetRef") or raw.get("assetRef") or "").strip(): str(
            raw.get("caption") or raw.get("captionIntent") or ""
        ).strip()
        for raw in compose.get("assets") or []
        if isinstance(raw, Mapping)
    }
    caption = str(draft.get("caption") or compose.get("title") or "")
    assets: list[dict[str, Any]] = []
    files: dict[Path, bytes | Path] = {}
    for ref in refs:
        row, destination, source_path = _asset_projection(
            execution_root=execution_root,
            source_ref=ref,
            source=index[ref],
            caption=binding_captions.get(ref) or caption,
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
    if carrier == "article" and assets:
        # 首图作封面，其余为正文图；配图数量不设门。
        assets[0]["role"] = "cover"
        for row in assets[1:]:
            row["role"] = "detail"
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
    creator = _creator_fields(compose, carrier="homepage")
    attribution = _text_attribution(source_rows, creator)
    name = str(target.get("name") or "")
    homepage_compose = {"assets": list(compose.get("assets") or []), "title": name}
    assets, media = _project_assets(
        execution_root=execution_root,
        object_dir=object_dir,
        carrier="homepage",
        compose=homepage_compose,
        draft={},
    ) if homepage_compose["assets"] else ([], {})
    for asset in assets:
        asset["fileName"] = Path(str(asset["fileName"])).name
    entity_ref = "/entity/" + target_ref.removeprefix("entities/")
    domain, type_name = str(target.get("entityType") or "").split("/", 1)
    region = str(target.get("region") or "").strip("/")
    if not region:
        # geoTagRef 是 publish/entity schema 的必填单值主归属；缺 region 的目标不得投影成实体。
        raise ObjectTransactionError(f"homepage target {target_ref} lacks region for geoTagRef")
    geo_tag_ref = f"Topic/地理/行政区/{region}"
    catalog = _source_catalog(source_rows, entity_name=name)
    hidden = {"schema", "sourceUnitId", "evidenceRef"}
    entity = {
        "label": name,
        "domain": domain,
        "type": type_name,
        "executionId": execution_root.name,
        "entityRef": entity_ref,
        "sourceRefs": [str(row["sourceRef"]) for row in source_rows],
        "sourceUrls": [str(row["sourceUrl"]) for row in source_rows],
        "primarySource": {k: v for k, v in catalog["primarySource"].items() if k not in hidden},
        "sourceAttribution": attribution,
        "tagRefs": sorted({*_target_tag_refs(target), *(str(v) for v in compose.get("tagRefs") or []), geo_tag_ref}),
        "geoTagRef": geo_tag_ref,
        **creator,
    }
    # 与下游 homepage 导入器同一判据（百科闭集 + encyclopedia-primary）在 publish 截面 fail-closed。
    assert_valid(entity, "publish", "entity", label=f"homepage entity {entity_ref}")
    manifest = {
        "vertical": "travel",
        "sourceAttribution": attribution,
        "assets": assets,
        "contentType": "homepage",
        "publishMediaMode": "not_applicable" if assets else "text_only",
    }
    return {
        Path("page.md"): page_path,
        Path("_entity.json"): _json_bytes(entity),
        Path("manifest.json"): _json_bytes(manifest),
        Path("evidence/source_catalog.json"): _json_bytes(catalog),
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
    draft_path = object_dir / "4.draft" / AUTHOR_ARTIFACT_BY_CARRIER[carrier]
    draft = dict(compose.get("draft") or {})
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
                reference_existing_file(expected, target)
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
    """Create or exact-replay one final surface after review approval."""
    source_rows = _source_rows(execution_root, object_dir)
    # 只看本对象 source unit 的资产（与 seal 的 _object_source_assets 同作用域），避免同名净化文件跨对象撞名。
    unit_prefixes = tuple(f"{row['sourceRef'].rsplit('/', 1)[0]}/assets/" for row in source_rows)
    execution_assets = source_assets_by_ref(execution_root) if carrier == "homepage" else source_assets(execution_root)
    asset_index = {ref: row for ref, row in execution_assets.items() if ref.startswith(unit_prefixes)}
    compose = _author_intent(
        object_dir=object_dir,
        carrier=carrier,
        target=target,
        source_rows=source_rows,
        asset_index=asset_index,
    )
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
