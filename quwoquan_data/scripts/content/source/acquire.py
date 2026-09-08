"""task acquire：零网络 ingest。AI 已用宿主原生能力出网检索、取证并下载来源；本命令只从本地字节
派生不可伪造的硬事实，不发起任何网络请求。

一次调用处理一个 execution 的 ingest 清单（逐 target 的本地文件 + AI 申报的来源事实）：
- page：AI 亲笔 `source.md`（首行 H1 为标题），脚本只算摘要并登记来源身份。
- image / video：读本地字节，算 sha256；申报了来源 sha1 时与字节交叉校验；探测 mime/尺寸/时长；
  图片按载体预算降采样；视频超预算或容器不在发布闭集时转码为 H.264 mp4 派生体并抽 poster；
  降采样/转码/抽帧都写进 `derivedModifications`，不再恒为空。
- `rightsStatus` 只由申报 license 字符串经开放许可白名单纯函数派生（verified / unverified / unknown），
  AI 不直接给出；水印三字段（watermarkStatus/watermarkKind/watermarkNote）由看过像素的 AI 申报并原样转录。
写入 `sources/<unit>/{meta.json,source.md,assets/}` 与对象 `1.download/source_refs.json`，媒体字节入
content library。逐 target 独立报告：单 target 失败以 typed issue 记录，不影响同批其余。
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.execution.identity import parse_execution_id, validate_execution_id
from content.execution.runtime_contract import stage_execution_context
from core.content_library import library_root_for_output, link_bytes_from_library
from core.control_types import carrier_of_target_ref
from core.image_variants import derive_budget_compliant_variant, image_dimensions
from core.media_processing_policy import MEDIA_PROCESSING_POLICY
from core.media_source_provenance import DerivedModification
from core.object_storage_budget import source_unit_asset_budget_bytes
from core.paths import execution_root, execution_source_unit_dir
from core.schema import assert_valid
from core.video_variants import (
    DERIVED_VIDEO_EXTENSION,
    derive_budget_compliant_video,
    probe_video,
    video_needs_derivative,
)
from governance.coverage.distribution import load_content_distribution_policy


def _asset_record_defaults() -> dict[str, str]:
    """采集代码无法核实的资产级常量只从 content_distribution.policy.yaml 取，不在这里另写一份。"""
    return dict(load_content_distribution_policy().asset_record_defaults)

# 单个来源文件的传输上限，不是准入判据：源体允许大于对象预算，降采样/转码要先拿到源体。
_MAX_SOURCE_BYTES = MEDIA_PROCESSING_POLICY.source_asset_max_bytes
_MAX_PUBLISHABLE_PIXELS = MEDIA_PROCESSING_POLICY.max_publishable_image_pixels
# 开放许可白名单：CC0、CC BY、CC BY-SA、公有领域（含 PDM）。命中即 rightsStatus=verified；
# 其它可读 license 记为 unverified 并把 license 原文写进 rightsIssues；读不到记 unknown。
_LICENSE_VERIFIED = re.compile(r"^(cc0|cc[ -]by(?:[ -]sa)?(?:[ -][0-9.]+)?(?:[ -][a-z]{2})?|public domain|pd(?:m|-[a-z0-9-]+)?)\b", re.I)
_LICENSE_RESTRICTIVE = re.compile(r"\b(nc|nd|fair use|copyright)\b", re.I)
_IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF8", "image/gif"),
    (b"RIFF", "image/webp"),
)


class AcquireError(ValueError):
    """来源文件不可读、字节漂移或媒体不可用。"""


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")[:60] or "source"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rights_record(short_name: str) -> tuple[str, list[str]]:
    """按申报 license 原文派生 (rightsStatus, rightsIssues)；只记录，不判否。"""
    text = str(short_name or "").strip()
    if not text:
        return "unknown", ["license not readable from source metadata"]
    if _LICENSE_VERIFIED.match(text) and not _LICENSE_RESTRICTIVE.search(text):
        return "verified", []
    return "unverified", [f"license outside open-license allowlist: {text}"]


def _platform_of(source: dict[str, Any]) -> str:
    declared = str(source.get("platform") or "").strip()
    if declared:
        return declared
    host = str(source["sourceUrl"]).split("//", 1)[-1].split("/", 1)[0]
    if host.endswith("wikimedia.org"):
        return "Wikimedia Commons"
    if host.endswith("wikipedia.org"):
        return "维基百科"
    if _is_toutiao_baike_host(host):
        return "头条百科"
    return host


def _is_toutiao_baike_host(host: str) -> bool:
    """头条百科/快懂百科：`www.baike.com` 与其子域；publish 实体 schema 的百科闭集成员 `toutiao_baike`。"""

    return host == "baike.com" or host.endswith(".baike.com")


# ── 本地读取 ──────────────────────────────────────────────────────────


def _read_local_bytes(raw_path: str, *, label: str) -> bytes:
    path = Path(raw_path).expanduser()
    if not path.is_file():
        raise AcquireError(f"DATA.ACQUIRE.LOCAL_FILE_MISSING: {label}: {raw_path}")
    body = path.read_bytes()
    if not body:
        raise AcquireError(f"DATA.ACQUIRE.LOCAL_FILE_EMPTY: {label}: {raw_path}")
    if len(body) > _MAX_SOURCE_BYTES:
        raise AcquireError(f"DATA.ACQUIRE.OVER_BYTES: {label}: {raw_path}")
    return body


def _sniff_image_mime(body: bytes, *, hint: str) -> str:
    for magic, mime in _IMAGE_MAGIC:
        if body.startswith(magic):
            if mime == "image/webp" and body[8:12] != b"WEBP":
                continue
            return mime
    guessed = mimetypes.guess_type(hint)[0] or ""
    if guessed.startswith("image/"):
        return guessed
    raise AcquireError(f"DATA.ACQUIRE.MIME_MISMATCH: {hint} is not a decodable image")


def _ingest_page(source: dict[str, Any]) -> dict[str, Any]:
    body = _read_local_bytes(str(source["sourceMarkdownPath"]), label="source.md")
    text = body.decode("utf-8", errors="strict") if b"\x00" not in body else ""
    if not text.strip():
        raise AcquireError(f"DATA.ACQUIRE.PAGE_EMPTY: {source['sourceUrl']}")
    host = str(source["sourceUrl"]).split("//", 1)[-1].split("/", 1)[0]
    host_parts = host.split(".")
    source_id = _slug("_".join(host_parts[:2]) if len(host_parts) >= 2 else host)
    if _is_toutiao_baike_host(host):
        # 与 final_surface_projection._homepage_source_kind 的 "toutiao" 判据同一个词根。
        source_id = "toutiao_baike"
    is_encyclopedia = host.endswith("wikipedia.org") or host.endswith("baike.baidu.com") or _is_toutiao_baike_host(host)
    return {
        "title": str(source["title"]).strip(),
        "sourceId": source_id,
        "sourceClass": "encyclopedia" if is_encyclopedia else "web_page",
        "platform": _platform_of(source),
        "sourceUseMode": "factual_reference_only",
        "canonicalUrl": str(source["sourceUrl"]),
        "license": str(source["license"]).strip(),
        "termsUrl": str(source["licenseUrl"]),
        "creator": str(source["creator"]).strip(),
        "text": text,
        "snapshot": body,
        "snapshotName": "snapshot.raw",
        "revisionId": int(source.get("revisionId") or 0),
    }


def _ffprobe(path: Path) -> dict[str, Any]:
    try:
        return probe_video(path)
    except ValueError as exc:
        raise AcquireError(f"DATA.ACQUIRE.VIDEO_NOT_PROBEABLE: {path.name}: {exc}") from exc


def _derivative_binding(original: bytes, derived: bytes, *, mime: str, derived_mime: str, carrier: str, extension: str) -> dict[str, Any]:
    return {
        "originalSha256": _sha256(original),
        "originalBytes": len(original),
        "originalMimeType": mime,
        "policy": "source_unit_asset_budget",
        "profile": carrier,
        "derivedSha256": _sha256(derived),
        "derivedBytes": len(derived),
        "derivedMimeType": derived_mime,
        "derivedExtension": extension,
    }


def _video_derivative(body: bytes, *, mime: str, carrier: str, title: str) -> tuple[bytes, str, dict[str, Any] | None]:
    """超预算或容器不在发布闭集的视频转成装进预算的 mp4；返回 (body, mime, derivativeBinding)。"""
    budget = source_unit_asset_budget_bytes(carrier)
    if not video_needs_derivative(mime=mime, size_bytes=len(body), budget_bytes=budget):
        return body, mime, None
    try:
        variant = derive_budget_compliant_video(
            body, budget_bytes=budget, target_bytes=MEDIA_PROCESSING_POLICY.video_derivative_target_bytes
        )
    except ValueError as exc:
        raise AcquireError(f"DATA.ACQUIRE.VIDEO_NOT_PROBEABLE: {title}: {exc}") from exc
    if variant is None:
        raise AcquireError(f"DATA.ACQUIRE.VIDEO_OVER_BUDGET: {title}")
    derived = bytes(variant["bytes"])
    derived_mime = str(variant["mimeType"])
    return derived, derived_mime, _derivative_binding(body, derived, mime=mime, derived_mime=derived_mime, carrier=carrier, extension=DERIVED_VIDEO_EXTENSION)


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


def _attribution(source: dict[str, Any], *, platform: str, collected_at: str, has_audio: bool | None, derived: list[str]) -> dict[str, Any]:
    """来源署名：只转录 AI 申报的事实与脚本实际做过的衍生修改，不编造它不知道的字段。"""
    creator = str(source["creator"]).strip()
    license_name = str(source["license"]).strip()
    license_url = str(source["licenseUrl"])
    if has_audio is None:
        audio = "no_audio"
    else:
        audio = "unverified" if has_audio else "no_audio"
    defaults = _asset_record_defaults()
    return {
        "isOriginal": False,
        "originalCreatorId": None,
        "originalCreatorName": creator,
        "originalCreatorProfileUrl": None,
        "platform": platform,
        "sourcePostUrl": str(source["sourceUrl"]),
        "originalAssetUrl": str(source["directUrl"]),
        "attributionText": f"{creator} / {platform} / {license_name}",
        "rightsBasis": f"open_license:{license_name}",
        "commercialAuthorizationStatus": defaults["commercialAuthorizationStatus"],
        # 对象级权利词汇是已冻结在 canonical 字节中的记录事实，保持既有取值。
        "publicationAdmission": "research_release",
        "authorizationProofUrl": license_url,
        "termsUrl": license_url,
        "watermarkStatus": str(source["watermarkStatus"]),
        "watermarkKind": str(source["watermarkKind"]),
        "watermarkNote": str(source.get("watermarkNote") or ""),
        "audioRightsStatus": audio,
        "modelReleaseStatus": defaults["modelReleaseStatus"],
        "propertyReleaseStatus": defaults["propertyReleaseStatus"],
        "collectedAt": collected_at,
        "takedownPolicy": defaults["takedownPolicy"],
        "derivedModifications": sorted(set(derived)),
    }


def _ingest_media(source: dict[str, Any], *, kind: str, carrier: str) -> dict[str, Any]:
    file_page = str(source["sourceUrl"])
    title = str(source.get("description") or "").strip().splitlines()[0][:80] if str(source.get("description") or "").strip() else Path(str(source["filePath"])).name
    body = _read_local_bytes(str(source["filePath"]), label=kind)
    declared_sha1 = str(source.get("sha1") or "").strip().lower()
    if declared_sha1 and hashlib.sha1(body).hexdigest() != declared_sha1:
        raise AcquireError(f"DATA.ACQUIRE.SOURCE_SHA1_DRIFT: {file_page}")
    # source unit 身份必须由下载原件决定：转码/降采样派生体的字节不保证逐次相同，
    # 若用派生体摘要定 unit id，重放会为同一 target 生成第二个 unit。
    original_sha = _sha256(body)
    derived: list[str] = []
    derivative: dict[str, Any] | None = None
    width = height = 0
    if kind == "image":
        mime = _sniff_image_mime(body, hint=str(source["filePath"]))
        dims = image_dimensions(body)
        if dims is None:
            raise AcquireError(f"DATA.ACQUIRE.MIME_MISMATCH: {file_page} is not a decodable image")
        width, height = dims
        budget = source_unit_asset_budget_bytes(carrier)
        # 入池存储体必须既装进对象字节预算、又不超过可发布像素上限：全景接片常常字节不大
        # 但栅格数亿像素，若原样入池会在 publish 截面被判否，所以两条阈值任一超出都降采样。
        if len(body) > budget or width * height > _MAX_PUBLISHABLE_PIXELS:
            variant = derive_budget_compliant_variant(body, budget_bytes=budget)
            if variant is None or len(variant["bytes"]) > budget:
                raise AcquireError(f"DATA.ACQUIRE.IMAGE_OVER_BUDGET: {file_page}")
            derived_mime = str(variant["mimeType"])
            extension = mimetypes.guess_extension(derived_mime, strict=False) or ".jpg"
            derivative = _derivative_binding(body, bytes(variant["bytes"]), mime=mime, derived_mime=derived_mime, carrier=carrier, extension=extension)
            derived.append(DerivedModification.RESIZE.value)
            if derived_mime != mime:
                derived.append(DerivedModification.FORMAT_CONVERSION.value)
            body = bytes(variant["bytes"])
            mime = derived_mime
            width, height = int(variant.get("width") or width), int(variant.get("height") or height)
    else:
        mime = mimetypes.guess_type(str(source["filePath"]))[0] or ""
        if not mime.startswith("video/"):
            with tempfile.NamedTemporaryFile(suffix=Path(str(source["filePath"])).suffix or ".bin", delete=False) as handle:
                handle.write(body)
                probe_path = Path(handle.name)
            try:
                probe = _ffprobe(probe_path)
            finally:
                probe_path.unlink(missing_ok=True)
            mime = f"video/{probe.get('container') or 'mp4'}"
        original_mime = mime
        body, mime, derivative = _video_derivative(body, mime=mime, carrier=carrier, title=file_page)
        if derivative is not None:
            derived.append(DerivedModification.FORMAT_CONVERSION.value if original_mime != mime else DerivedModification.RESIZE.value)
    license_name = str(source["license"]).strip()
    rights_status, rights_issues = _rights_record(license_name)
    collected_at = _now()
    platform = _platform_of(source)
    has_audio = bool(source.get("hasAudio")) if kind == "video" else None
    return {
        "title": title,
        "sourceId": _slug(platform.lower().replace(" ", "_")) + ("_video" if kind == "video" else ""),
        "sourceClass": "open_license_media",
        "platform": platform,
        "sourceUseMode": "licensed_adaptation",
        "canonicalUrl": file_page,
        "license": license_name,
        "termsUrl": str(source["licenseUrl"]),
        "creator": str(source["creator"]).strip(),
        "text": f"# {title}\n\n{str(source.get('description') or '')}\n\n作者：{source['creator']}\n许可：{license_name}\n来源页：{file_page}\n",
        # 媒体来源不再单独落 snapshot：字节本身就是快照，摘要记在 meta.rawSha256。
        "snapshot": None,
        "snapshotName": None,
        "revisionId": 0,
        "media": {
            "kind": kind,
            "body": body,
            "originalSha256": original_sha,
            "mime": mime,
            "directUrl": str(source["directUrl"]),
            "width": width,
            "height": height,
            "derivative": derivative,
            "collectedAt": collected_at,
            "attribution": _attribution(source, platform=platform, collected_at=collected_at, has_audio=has_audio, derived=derived),
            "description": str(source.get("description") or ""),
            "rightsStatus": rights_status,
            "rightsIssues": rights_issues,
            "watermarkStatus": str(source["watermarkStatus"]),
            "watermarkKind": str(source["watermarkKind"]),
            "watermarkNote": str(source.get("watermarkNote") or ""),
            "derivedModifications": sorted(set(derived)),
            # 访问政策只记录不判否：缺席即缺席，不补 open。
            **({"accessPolicy": str(source["accessPolicy"])} if source.get("accessPolicy") else {}),
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
    rights_status = str(media.get("rightsStatus") or "verified")
    rights_issues = list(media.get("rightsIssues") or [])
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
        "modelReleaseStatus": attribution["modelReleaseStatus"],
        "propertyReleaseStatus": attribution["propertyReleaseStatus"],
        "sourceAttribution": attribution,
        "sourceUrl": acquired["canonicalUrl"],
        "license": acquired["license"],
        "termsUrl": acquired["termsUrl"],
        # 开放许可的授权证明就是许可证正文本身；非白名单 license 仍记 termsUrl，由 rightsStatus 说明状态。
        "authorizationProof": acquired["termsUrl"],
        "rightsStatus": rights_status,
        "authorizationRequired": rights_status != "verified",
        "distributionDecision": "research_allowed",
        "rightsIssues": rights_issues,
        "relevance": relevance,
        "caption": media.get("description") or acquired["title"],
        "watermarkStatus": media["watermarkStatus"],
        "watermarkKind": media["watermarkKind"],
        "watermarkNote": media["watermarkNote"],
        "derivedModifications": list(media["derivedModifications"]),
        **({"accessPolicy": media["accessPolicy"]} if media.get("accessPolicy") else {}),
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
    # 媒体来源的原始字节就是媒体本身，不再复制一份 snapshot 进 source CAS；
    # unit 身份取下载原件的摘要，而不是可能逐次不同的派生体摘要。
    if acquired["snapshot"] is not None:
        raw_sha = _sha256(acquired["snapshot"])
    else:
        raw_sha = acquired["media"].get("originalSha256") or _sha256(acquired["media"]["body"])
    unit_id = "%s__%s" % (
        _slug(acquired["sourceId"]),
        hashlib.sha256("\n".join((execution_id, target_ref, str(source["sourceUrl"]), raw_sha)).encode("utf-8")).hexdigest()[:16],
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
    if isinstance(source.get("discoverySignals"), dict) and source["discoverySignals"]:
        # 热度/发现信号只记录不判否：原样转录，不派生任何判据。
        meta["discoverySignals"] = dict(source["discoverySignals"])
    if source.get("accessPolicy"):
        # 来源站点 robots/ToS 态度只记录：schema 已把取值限定在闭集，这里不再解释含义。
        meta["accessPolicy"] = str(source["accessPolicy"])
    assets: list[dict[str, Any]] = []
    receipt_ref = ""
    with _lock(unit.parent / f".{unit_id}.lock"):
        if unit.exists():
            existing = json.loads((unit / "meta.json").read_bytes())
            if existing.get("rawSha256") != raw_sha or existing.get("targetRef") != target_ref:
                raise AcquireError(f"DATA.ACQUIRE.CREATE_ONCE_CONFLICT: {unit_id}")
            meta = existing
            index_path = unit / "assets/index.json"
            if index_path.is_file():
                assets = list(json.loads(index_path.read_bytes()).get("assets") or [])
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
                        poster_acquired = {
                            **acquired,
                            "media": {
                                **media,
                                "attribution": {
                                    **media["attribution"],
                                    "audioRightsStatus": "no_audio",
                                    "derivedModifications": sorted(set(media["derivedModifications"]) | {DerivedModification.VIDEO_FRAME_EXTRACTION.value}),
                                },
                                "derivedModifications": sorted(set(media["derivedModifications"]) | {DerivedModification.VIDEO_FRAME_EXTRACTION.value}),
                            },
                        }
                        assets.append(_asset_row(
                            asset_id=f"{unit_id}:poster", file_name=poster_name, role="poster", body=poster_body,
                            mime="image/png", acquired=poster_acquired, relevance=str(source["relevance"]),
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
                if acquired["snapshot"] is not None:
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
        "rightsStatus": acquired["media"]["rightsStatus"] if "media" in acquired else "verified",
        "watermarkStatus": acquired["media"]["watermarkStatus"] if "media" in acquired else None,
        "assets": [row["fileName"] for row in assets],
        "sourceRef": row["sourceRef"],
    }


def _ingest_target(*, execution_id: str, target: dict[str, Any], carrier: str, plan_ref: str, plan_digest: str) -> dict[str, Any]:
    target_ref = str(target["targetRef"]).strip().strip("/")
    results: list[dict[str, Any]] = []
    for source in target["sources"]:
        kind = source["kind"]
        acquired = _ingest_page(source) if kind == "page" else _ingest_media(source, kind=kind, carrier=carrier)
        results.append(_materialize(
            execution_id=execution_id, target_ref=target_ref, source=source, acquired=acquired,
            plan_ref=plan_ref, plan_digest=plan_digest,
        ))
    return {"targetRef": target_ref, "status": "ingested", "sources": results}


def acquire(*, execution_id: str, request_path: Path) -> dict[str, Any]:
    """零网络 ingest 一个 execution 的全部 target；逐 target 独立报告。"""
    execution_id = validate_execution_id(execution_id)
    carrier = parse_execution_id(execution_id).content_type.value
    root = execution_root(execution_id)
    if not (root / "execution_manifest.json").is_file():
        raise AcquireError(f"DATA.ACQUIRE.EXECUTION_MISSING: {execution_id}")
    target_set = json.loads((root / "0.plan/target_set.json").read_bytes())
    declared_refs = set(target_set.get("targetRefs") or [])
    request = json.loads(Path(request_path).expanduser().read_bytes())
    assert_valid(request, "source", "ingest_manifest", label=str(request_path))
    if request["executionId"] != execution_id:
        raise AcquireError(f"DATA.ACQUIRE.EXECUTION_MISMATCH: manifest={request['executionId']} execution={execution_id}")
    request_bytes = _canonical(request)
    plan_digest = _sha256(request_bytes)
    plan_ref = f"sources/plans/{plan_digest.removeprefix('sha256:')}.json"
    _write_create_or_same(root / plan_ref, request_bytes)

    targets: list[dict[str, Any]] = []
    for target in request["targets"]:
        target_ref = str(target["targetRef"]).strip().strip("/")
        try:
            if carrier_of_target_ref(target_ref) != carrier:
                raise AcquireError(f"DATA.ACQUIRE.CARRIER_MISMATCH: execution={execution_id} target={target_ref}")
            if target_ref not in declared_refs:
                raise AcquireError(f"DATA.ACQUIRE.TARGET_NOT_DECLARED: {target_ref}")
            targets.append(_ingest_target(execution_id=execution_id, target=target, carrier=carrier, plan_ref=plan_ref, plan_digest=plan_digest))
        except (AcquireError, OSError, ValueError) as exc:
            message = str(exc)
            code = message.split(":", 1)[0] if message.startswith("DATA.") else "DATA.ACQUIRE.TARGET_FAILED"
            targets.append({"targetRef": target_ref, "status": "failed", "issue": {"code": code, "message": message}})
    ingested = sum(1 for row in targets if row["status"] == "ingested")
    return {"executionId": execution_id, "ingested": ingested, "failed": len(targets) - ingested, "targets": targets}


__all__ = ["AcquireError", "acquire"]
