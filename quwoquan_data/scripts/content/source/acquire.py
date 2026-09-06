"""task acquire：AI 只点名来源 URL、类型与相关性理由，脚本机械取得字节与权利硬事实。

一次调用处理一个 target 的全部来源：
- page：MediaWiki（zh.wikipedia 等）走 API 取纯文本与修订号；其它 https 页面取 HTML 转纯文本。
- image / video：Wikimedia Commons 文件页走 imageinfo API 取直链、mime、尺寸、license、作者，
  下载字节、算 sha256；图片按载体字节预算降采样；视频 ffprobe 探测并抽 poster 帧。
写入 `sources/<unit>/{meta.json,source.md,snapshot.*,assets/}` 与对象 `1.download/source_refs.json`，
媒体字节入 content library。license 不在研究白名单即 typed GATE_BLOCK。
"""
from __future__ import annotations

import fcntl
import hashlib
import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.execution.identity import parse_execution_id, validate_execution_id
from content.execution.runtime_contract import stage_execution_context
from content.source.html_text import _html_to_plain_text
from content.source.mediawiki_page import fetch_mediawiki_page_bundle_for_url, mediawiki_title_from_url
from content.source.research import network_io
from core.content_library import library_root_for_output, link_bytes_from_library
from core.control_types import carrier_of_target_ref
from core.image_variants import derive_budget_compliant_variant
from core.object_storage_budget import source_unit_asset_budget_bytes
from core.paths import execution_root, execution_source_unit_dir
from core.schema import assert_valid

_MAX_SOURCE_BYTES = 64 * 1024 * 1024
_COMMONS_HOST = "commons.wikimedia.org"
_COMMONS_TERMS = "https://commons.wikimedia.org/wiki/Commons:Licensing"
_WIKIPEDIA_LICENSE = "CC BY-SA 4.0"
_WIKIPEDIA_TERMS = "https://creativecommons.org/licenses/by-sa/4.0/"
# 研究用途 license 白名单：CC0、CC BY、CC BY-SA、公有领域（含 PDM）。NC/ND 与其它一律拒绝。
_LICENSE_ALLOWED = re.compile(r"^(cc0|cc[ -]by(?:[ -]sa)?(?:[ -][0-9.]+)?(?:[ -][a-z]{2})?|public domain|pd(?:m|-[a-z0-9-]+)?)\b", re.I)
_LICENSE_FORBIDDEN = re.compile(r"\b(nc|nd|fair use|copyright)\b", re.I)


class AcquireError(ValueError):
    """来源不可取得或权利不允许研究用途。"""


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")[:60] or "source"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_html(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", str(value or ""))).strip()


def _license_allowed(short_name: str) -> bool:
    text = str(short_name or "").strip()
    return bool(text) and bool(_LICENSE_ALLOWED.match(text)) and not _LICENSE_FORBIDDEN.search(text)


# ── 抓取 ──────────────────────────────────────────────────────────────


def _fetch_bytes(url: str) -> tuple[bytes, str]:
    response = network_io.fetch_http(url, timeout=120)
    if not response.ok or not response.body:
        raise AcquireError(f"DATA.ACQUIRE.FETCH_FAILED: {url} status={response.status_code}")
    if len(response.body) > _MAX_SOURCE_BYTES:
        raise AcquireError(f"DATA.ACQUIRE.OVER_BYTES: {url}")
    final_url = response.final_url or url
    if not final_url.startswith("https://"):
        raise AcquireError(f"DATA.ACQUIRE.NON_HTTPS_REDIRECT: {url}")
    return response.body, final_url


def _acquire_page(source: dict[str, Any]) -> dict[str, Any]:
    url = str(source["url"])
    host, title = mediawiki_title_from_url(url)
    if host and title:
        bundle = fetch_mediawiki_page_bundle_for_url(url, include_images=False)
        if bundle is None or not bundle.rendered_text:
            raise AcquireError(f"DATA.ACQUIRE.PAGE_EMPTY: {url}")
        canonical_url = f"https://{host}/wiki/{urllib.parse.quote(bundle.resolved_title.replace(' ', '_'))}"
        return {
            "title": bundle.resolved_title,
            "sourceId": _slug(host.split(".")[0] + "_" + host.split(".")[1]),
            "sourceClass": "encyclopedia",
            "platform": "维基百科" if "wikipedia" in host else host,
            "sourceUseMode": "factual_reference_only",
            "canonicalUrl": canonical_url,
            "license": _WIKIPEDIA_LICENSE,
            "termsUrl": _WIKIPEDIA_TERMS,
            "creator": f"{bundle.resolved_title} 条目贡献者",
            "text": bundle.rendered_text,
            "snapshot": bundle.raw.encode("utf-8"),
            "snapshotName": "snapshot.raw",
            "revisionId": bundle.revision_id,
        }
    body, final_url = _fetch_bytes(url)
    if b"\x00" in body:
        raise AcquireError(f"DATA.ACQUIRE.PAGE_NOT_TEXT: {url}")
    text = _html_to_plain_text(body.decode("utf-8", errors="replace"), final_url)
    if not text.strip():
        raise AcquireError(f"DATA.ACQUIRE.PAGE_EMPTY: {url}")
    parsed = urllib.parse.urlparse(final_url)
    return {
        "title": text.strip().splitlines()[0][:120],
        "sourceId": _slug(parsed.hostname or "web"),
        "sourceClass": "web_page",
        "platform": parsed.hostname or "web",
        "sourceUseMode": "factual_reference_only",
        "canonicalUrl": final_url,
        "license": "all rights reserved (factual reference only)",
        "termsUrl": final_url,
        "creator": parsed.hostname or "web",
        "text": text,
        "snapshot": body,
        "snapshotName": "snapshot.raw",
        "revisionId": 0,
    }


def _commons_file_title(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if (parsed.hostname or "") != _COMMONS_HOST or "/wiki/" not in parsed.path:
        raise AcquireError(f"DATA.ACQUIRE.NOT_COMMONS_FILE_PAGE: {url}")
    title = urllib.parse.unquote(parsed.path.split("/wiki/", 1)[1].split("#", 1)[0])
    if not title.startswith("File:"):
        raise AcquireError(f"DATA.ACQUIRE.NOT_COMMONS_FILE_PAGE: {url}")
    return title


def _commons_imageinfo(title: str) -> dict[str, Any]:
    payload = network_io.wiki_api(
        _COMMONS_HOST,
        {
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|mime|size|sha1|extmetadata|user",
            "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|ImageDescription|Credit|DateTimeOriginal|Attribution",
            "format": "json",
            "redirects": 1,
        },
    )
    pages = ((payload.get("query") or {}).get("pages") or {}) if isinstance(payload, dict) else {}
    page = next((row for row in pages.values() if isinstance(row, dict)), None)
    info = (page or {}).get("imageinfo") if page else None
    if not info or not isinstance(info, list) or not isinstance(info[0], dict):
        raise AcquireError(f"DATA.ACQUIRE.COMMONS_IMAGEINFO_MISSING: {title}")
    row = info[0]
    meta = {key: _strip_html((value or {}).get("value")) for key, value in (row.get("extmetadata") or {}).items()}
    # Commons 对 CC0/PD 常给出 http:// 的许可证链接；creativecommons.org 全站支持 https，统一为 https。
    if meta.get("LicenseUrl", "").startswith("http://"):
        meta["LicenseUrl"] = "https://" + meta["LicenseUrl"][len("http://"):]
    return {
        "directUrl": str(row.get("url") or ""),
        "mime": str(row.get("mime") or ""),
        "size": int(row.get("size") or 0),
        "sha1": str(row.get("sha1") or ""),
        "width": int(row.get("width") or 0),
        "height": int(row.get("height") or 0),
        "user": str(row.get("user") or ""),
        "licenseShortName": meta.get("LicenseShortName", ""),
        "licenseUrl": meta.get("LicenseUrl", ""),
        "artist": meta.get("Artist", "") or meta.get("Attribution", "") or str(row.get("user") or ""),
        "description": meta.get("ImageDescription", ""),
        "credit": meta.get("Credit", ""),
        "dateTimeOriginal": meta.get("DateTimeOriginal", ""),
    }


def _ffprobe(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AcquireError(f"DATA.ACQUIRE.VIDEO_NOT_PROBEABLE: {path.name}")
    probe = json.loads(proc.stdout or "{}")
    video = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise AcquireError(f"DATA.ACQUIRE.VIDEO_NO_STREAM: {path.name}")
    duration = float((probe.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        raise AcquireError(f"DATA.ACQUIRE.VIDEO_NO_DURATION: {path.name}")
    return {
        "durationMs": int(duration * 1000),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "codec": str(video.get("codec_name") or ""),
        "container": str((probe.get("format") or {}).get("format_name") or ""),
        "hasAudio": any(s.get("codec_type") == "audio" for s in probe.get("streams", [])),
    }


def _extract_poster(video_path: Path, poster_path: Path, *, duration_ms: int) -> None:
    seek = min(1.0, max(0.0, duration_ms / 1000 / 2))
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{seek:.2f}", "-i", str(video_path), "-frames:v", "1", str(poster_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not poster_path.is_file() or poster_path.stat().st_size == 0:
        raise AcquireError(f"DATA.ACQUIRE.POSTER_EXTRACT_FAILED: {video_path.name}")


def _commons_attribution(info: dict[str, Any], *, file_page: str, collected_at: str) -> dict[str, Any]:
    creator = info["artist"] or info["user"] or "Wikimedia Commons contributor"
    return {
        "isOriginal": False,
        "originalCreatorId": None,
        "originalCreatorName": creator,
        "originalCreatorProfileUrl": None,
        "platform": "Wikimedia Commons",
        "sourcePostUrl": file_page,
        "originalAssetUrl": info["directUrl"],
        "attributionText": f"{creator} / Wikimedia Commons / {info['licenseShortName']}",
        "rightsBasis": f"open_license:{info['licenseShortName']}",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "authorizationProofUrl": info["licenseUrl"] or _COMMONS_TERMS,
        "termsUrl": info["licenseUrl"] or _COMMONS_TERMS,
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": collected_at,
        "takedownPolicy": "remove_on_rights_holder_request",
        "derivedModifications": [],
    }


def _acquire_media(source: dict[str, Any], *, kind: str, carrier: str) -> dict[str, Any]:
    file_page = str(source["url"])
    title = _commons_file_title(file_page)
    info = _commons_imageinfo(title)
    if not _license_allowed(info["licenseShortName"]):
        raise AcquireError(
            f"DATA.ACQUIRE.LICENSE_NOT_ALLOWED: {title} license={info['licenseShortName'] or 'unknown'}"
        )
    if not info["directUrl"].startswith("https://"):
        raise AcquireError(f"DATA.ACQUIRE.COMMONS_DIRECT_URL_MISSING: {title}")
    expected_prefix = "image/" if kind == "image" else "video/"
    if not info["mime"].startswith(expected_prefix):
        raise AcquireError(f"DATA.ACQUIRE.MIME_MISMATCH: {title} kind={kind} mime={info['mime']}")
    body, _final = _fetch_bytes(info["directUrl"])
    if hashlib.sha1(body).hexdigest() != info["sha1"]:
        raise AcquireError(f"DATA.ACQUIRE.COMMONS_SHA1_DRIFT: {title}")
    original_sha256 = _sha256(body)
    original_bytes = len(body)
    mime = info["mime"]
    derivative: dict[str, Any] | None = None
    if kind == "image":
        budget = source_unit_asset_budget_bytes(carrier)
        if len(body) > budget:
            variant = derive_budget_compliant_variant(body, budget_bytes=budget)
            if variant is None or len(variant["bytes"]) > budget:
                raise AcquireError(f"DATA.ACQUIRE.IMAGE_OVER_BUDGET: {title}")
            derivative = {
                "originalSha256": original_sha256,
                "originalBytes": original_bytes,
                "originalMimeType": mime,
                "policy": "source_unit_asset_budget",
                "profile": carrier,
                "derivedSha256": _sha256(bytes(variant["bytes"])),
                "derivedBytes": len(variant["bytes"]),
                "derivedMimeType": str(variant["mimeType"]),
                "derivedExtension": mimetypes.guess_extension(str(variant["mimeType"]), strict=False) or ".jpg",
            }
            body = bytes(variant["bytes"])
            mime = str(variant["mimeType"])
    collected_at = _now()
    return {
        "title": title.removeprefix("File:"),
        "sourceId": "wikimedia_commons" if kind == "image" else "wikimedia_commons_video",
        "sourceClass": "open_license_media",
        "platform": "Wikimedia Commons",
        "sourceUseMode": "licensed_adaptation",
        "canonicalUrl": file_page,
        "license": info["licenseShortName"],
        "termsUrl": info["licenseUrl"] or _COMMONS_TERMS,
        "creator": info["artist"] or info["user"] or "Wikimedia Commons contributor",
        "text": f"# {title}\n\n{info['description'] or ''}\n\n作者：{info['artist'] or info['user']}\n许可：{info['licenseShortName']}\n来源页：{file_page}\n",
        "snapshot": body,
        "snapshotName": "snapshot.bin",
        "revisionId": 0,
        "media": {
            "kind": kind,
            "body": body,
            "mime": mime,
            "directUrl": info["directUrl"],
            "width": info["width"],
            "height": info["height"],
            "derivative": derivative,
            "collectedAt": collected_at,
            "attribution": _commons_attribution(info, file_page=file_page, collected_at=collected_at),
            "description": info["description"],
        },
    }


# ── 写入 ──────────────────────────────────────────────────────────────


def _lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _write_create_or_same(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise AcquireError(f"DATA.ACQUIRE.CREATE_ONCE_CONFLICT: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _asset_row(
    *,
    asset_id: str,
    file_name: str,
    role: str,
    body: bytes,
    mime: str,
    acquired: dict[str, Any],
    relevance: str,
    receipt_ref: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    media = acquired["media"]
    attribution = media["attribution"]
    return {
        "sourceAssetId": asset_id,
        "fileName": file_name,
        "assetRole": role,
        "mimeType": mime,
        "bytes": len(body),
        "sha256": _sha256(body),
        "contentSha256": _sha256(body),
        "acquisitionReceiptRef": receipt_ref,
        "professionalAssetId": asset_id,
        "creator": acquired["creator"],
        "platform": acquired["platform"],
        "collectionPageUrl": acquired["canonicalUrl"],
        "originalAssetUrl": media["directUrl"],
        "capturedAt": media["collectedAt"],
        "licenseSnapshot": acquired["license"],
        "usageScope": "editorial",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "sourceAttribution": attribution,
        "sourceUrl": acquired["canonicalUrl"],
        "license": acquired["license"],
        "termsUrl": acquired["termsUrl"],
        # 开放许可的授权证明就是许可证正文本身。
        "authorizationProof": acquired["termsUrl"],
        "rightsStatus": "verified",
        "authorizationRequired": False,
        "distributionDecision": "research_allowed",
        "rightsIssues": [],
        "relevance": relevance,
        "caption": media.get("description") or acquired["title"],
        **(extra or {}),
    }


def _materialize(
    *,
    execution_id: str,
    target_ref: str,
    source: dict[str, Any],
    acquired: dict[str, Any],
    plan_ref: str,
    plan_digest: str,
) -> dict[str, Any]:
    root = execution_root(execution_id)
    output_root = root.parents[2]
    library_root = library_root_for_output(output_root)
    carrier = carrier_of_target_ref(target_ref)
    candidate_digest = _sha256(_canonical(source))
    raw_sha = _sha256(acquired["snapshot"])
    unit_id = "%s__%s" % (
        _slug(acquired["sourceId"]),
        hashlib.sha256("\n".join((execution_id, target_ref, str(source["url"]), raw_sha)).encode("utf-8")).hexdigest()[:16],
    )
    unit = execution_source_unit_dir(execution_id, unit_id)
    source_md = acquired["text"] if acquired["text"].startswith("# ") else f"# {acquired['title']}\n\n{acquired['text']}\n"
    if not source_md.endswith("\n"):
        source_md += "\n"
    source_sha = _sha256(source_md.encode("utf-8"))
    meta: dict[str, Any] = {
        "schema": "quwoquan_data.atomic_source_unit",
        "stage": "1.download",
        **stage_execution_context(execution_id),
        "sourceUnitId": unit_id,
        "sourcePlanRef": plan_ref,
        "sourcePlanDigest": plan_digest,
        "chosenCandidateDigest": candidate_digest,
        "sourceId": acquired["sourceId"],
        "targetRef": target_ref,
        "carrier": carrier,
        "title": acquired["title"],
        "sourceClass": acquired["sourceClass"],
        "sourceUseMode": acquired["sourceUseMode"],
        "purpose": str(source["relevance"]),
        "rightsClue": f"{acquired['license']} · {acquired['termsUrl']}",
        "canonicalUrl": acquired["canonicalUrl"],
        "fetchedAt": _now(),
        "rawSha256": raw_sha,
        "sourceMarkdownSha256": source_sha,
    }
    assets: list[dict[str, Any]] = []
    receipt_ref = ""
    with _lock(unit.parent / f".{unit_id}.lock"):
        if unit.exists():
            existing = json.loads((unit / "meta.json").read_bytes())
            if existing.get("rawSha256") != raw_sha or existing.get("targetRef") != target_ref:
                raise AcquireError(f"DATA.ACQUIRE.CREATE_ONCE_CONFLICT: {unit_id}")
            meta = existing
        else:
            unit.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(tempfile.mkdtemp(prefix=f".{unit_id}.", dir=unit.parent))
            try:
                (temporary / "assets").mkdir()
                if "media" in acquired:
                    media = acquired["media"]
                    receipt_ref = f"receipts/{unit_id}.json"
                    safe = _slug(Path(acquired["title"]).stem)[:40]
                    suffix = mimetypes.guess_extension(media["mime"], strict=False) or (".jpg" if media["kind"] == "image" else ".webm")
                    if suffix == ".jpe":
                        suffix = ".jpg"
                    file_name = f"001_{safe}{suffix}"
                    asset_path = temporary / "assets" / file_name
                    link_bytes_from_library(media["body"], asset_path, kind="media", library_root=library_root)
                    extra: dict[str, Any] = {"width": media["width"], "height": media["height"]}
                    if media["derivative"]:
                        extra["derivativeBinding"] = media["derivative"]
                    acquisition: dict[str, Any] = {
                        "receiptRef": receipt_ref,
                        "assetId": unit_id,
                        "assetRef": f"assets/{file_name}",
                        "contentSha256": _sha256(media["body"]),
                        "bytes": len(media["body"]),
                        "mimeType": media["mime"],
                    }
                    if media["derivative"]:
                        acquisition["derivativeBinding"] = media["derivative"]
                    if media["kind"] == "video":
                        probe = _ffprobe(asset_path)
                        extra.update({k: probe[k] for k in ("durationMs", "codec", "container")})
                        extra["width"], extra["height"] = probe["width"], probe["height"]
                        poster_name = f"002_{safe}_poster.png"
                        poster_path = temporary / "assets" / poster_name
                        _extract_poster(asset_path, poster_path, duration_ms=probe["durationMs"])
                        poster_body = poster_path.read_bytes()
                        link_bytes_from_library(poster_body, poster_path, kind="media", library_root=library_root)
                        acquisition["posterAssetRef"] = f"assets/{poster_name}"
                        acquisition["posterContentSha256"] = _sha256(poster_body)
                        assets.append(_asset_row(
                            asset_id=f"{unit_id}:video", file_name=file_name, role="video", body=media["body"],
                            mime=media["mime"], acquired=acquired, relevance=str(source["relevance"]),
                            receipt_ref=receipt_ref, extra=extra,
                        ))
                        assets.append(_asset_row(
                            asset_id=f"{unit_id}:poster", file_name=poster_name, role="poster", body=poster_body,
                            mime="image/png", acquired=acquired, relevance=str(source["relevance"]),
                            receipt_ref=receipt_ref,
                            extra={"derivedFromSourceAssetId": f"{unit_id}:video", "derivation": "first_frame"},
                        ))
                    else:
                        assets.append(_asset_row(
                            asset_id=unit_id, file_name=file_name, role="image", body=media["body"],
                            mime=media["mime"], acquired=acquired, relevance=str(source["relevance"]),
                            receipt_ref=receipt_ref, extra=extra,
                        ))
                    meta["acquisition"] = acquisition
                    receipt = {
                        "schema": "quwoquan_data.acquire_receipt",
                        "executionId": execution_id,
                        "targetRef": target_ref,
                        "sourceUnitId": unit_id,
                        "filePage": acquired["canonicalUrl"],
                        "directUrl": media["directUrl"],
                        "license": acquired["license"],
                        "termsUrl": acquired["termsUrl"],
                        "creator": acquired["creator"],
                        "mimeType": media["mime"],
                        "collectedAt": media["collectedAt"],
                        "assets": [{k: row[k] for k in ("sourceAssetId", "fileName", "assetRole", "sha256", "bytes", "mimeType")} for row in assets],
                    }
                    _write_create_or_same(unit.parent / receipt_ref, _canonical(receipt))
                link_bytes_from_library(acquired["snapshot"], temporary / acquired["snapshotName"], kind="source", library_root=library_root)
                (temporary / "source.md").write_text(source_md, encoding="utf-8")
                (temporary / "assets/index.json").write_bytes(_canonical({"assets": assets}))
                assert_valid(meta, "source", "atomic_source_unit_meta", label=unit_id)
                (temporary / "meta.json").write_bytes(_canonical(meta))
                os.rename(temporary, unit)
                temporary = None
            finally:
                if temporary is not None:
                    shutil.rmtree(temporary, ignore_errors=True)

    object_dir = root / target_ref
    refs_path = object_dir / "1.download/source_refs.json"
    row = {
        "sourceUnitId": unit_id,
        "sourceRef": (unit / "source.md").relative_to(root).as_posix(),
        "metaRef": (unit / "meta.json").relative_to(root).as_posix(),
        "sourcePlanRef": plan_ref,
        "sourcePlanDigest": plan_digest,
        "chosenCandidateDigest": candidate_digest,
        "sourceId": acquired["sourceId"],
        "sourceClass": acquired["sourceClass"],
        "targetRefs": [target_ref],
    }
    with _lock(refs_path.with_suffix(".lock")):
        existing = json.loads(refs_path.read_bytes()) if refs_path.is_file() else {
            "schema": "quwoquan_data.object_source_refs",
            "executionId": execution_id,
            "objectRef": target_ref,
            "sources": [],
        }
        rows = [value for value in existing.get("sources", []) if isinstance(value, dict)]
        if any(value.get("sourceUnitId") == unit_id and value != row for value in rows):
            raise AcquireError(f"DATA.ACQUIRE.SOURCE_REFS_CONFLICT: {unit_id}")
        if row not in rows:
            rows.append(row)
        payload = {**existing, "sources": sorted(rows, key=lambda value: str(value.get("sourceUnitId") or ""))}
        assert_valid(payload, "source", "object_source_refs", label=str(refs_path))
        refs_path.parent.mkdir(parents=True, exist_ok=True)
        refs_path.write_bytes(_canonical(payload))
    return {
        "sourceUnitId": unit_id,
        "kind": source["kind"],
        "title": acquired["title"],
        "license": acquired["license"],
        "assets": [row["fileName"] for row in assets],
        "sourceRef": row["sourceRef"],
    }


def acquire(*, execution_id: str, target_ref: str, request_path: Path) -> dict[str, Any]:
    execution_id = validate_execution_id(execution_id)
    target_ref = str(target_ref).strip().strip("/")
    carrier = carrier_of_target_ref(target_ref)
    if parse_execution_id(execution_id).content_type.value != carrier:
        raise AcquireError(f"DATA.ACQUIRE.CARRIER_MISMATCH: execution={execution_id} target={target_ref}")
    root = execution_root(execution_id)
    if not (root / "execution_manifest.json").is_file():
        raise AcquireError(f"DATA.ACQUIRE.EXECUTION_MISSING: {execution_id}")
    target_set = json.loads((root / "0.plan/target_set.json").read_bytes())
    if target_ref not in (target_set.get("targetRefs") or []):
        raise AcquireError(f"DATA.ACQUIRE.TARGET_NOT_DECLARED: {target_ref}")
    request = json.loads(Path(request_path).expanduser().read_bytes())
    assert_valid(request, "source", "acquire_request", label=str(request_path))
    request_bytes = _canonical(request)
    plan_digest = _sha256(request_bytes)
    plan_ref = f"sources/plans/{plan_digest.removeprefix('sha256:')}.json"
    _write_create_or_same(root / plan_ref, request_bytes)

    results: list[dict[str, Any]] = []
    for source in request["sources"]:
        kind = source["kind"]
        acquired = _acquire_page(source) if kind == "page" else _acquire_media(source, kind=kind, carrier=carrier)
        results.append(_materialize(
            execution_id=execution_id, target_ref=target_ref, source=source, acquired=acquired,
            plan_ref=plan_ref, plan_digest=plan_digest,
        ))
    return {"executionId": execution_id, "targetRef": target_ref, "sources": results}


__all__ = ["AcquireError", "acquire"]
