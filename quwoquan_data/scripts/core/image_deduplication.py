"""Perceptual deduplication and batch image-safety helpers."""
from __future__ import annotations
import hashlib
import io
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Sequence

if TYPE_CHECKING:
    from core.image_safety import ImageVerdict
try:
    from PIL import Image  # type: ignore
    import imagehash  # type: ignore
except Exception:
    Image = None
    imagehash = None

def _near_duplicate_threshold(value: int | None) -> int:
    if value is not None:
        return value
    from core.image_safety import NEAR_DUP_HAMMING

    return NEAR_DUP_HAMMING


def _hash_backend_available() -> bool:
    from core.image_safety import _HASH_OK

    return _HASH_OK


def _avg_hash(path: Path):
    if not _hash_backend_available():
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as im:
                return imagehash.phash(im.convert("RGB"))
    except (Image.DecompressionBombWarning, Image.DecompressionBombError, OSError, ValueError):
        return None

def is_near_duplicate(
    path_a: str | Path,
    path_b: str | Path,
    *,
    threshold: int | None = None,
) -> bool:
    ha = _avg_hash(Path(path_a))
    hb = _avg_hash(Path(path_b))
    if ha is None or hb is None:
        return False
    return bool((ha - hb) <= _near_duplicate_threshold(threshold))

def _avg_hash_bytes(data: bytes):
    if not _hash_backend_available() or not data:
        return None
    import io

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as im:
                return imagehash.phash(im.convert("RGB"))
    except (Image.DecompressionBombWarning, Image.DecompressionBombError, OSError, ValueError):
        return None

def dedupe_image_payloads(
    payloads: Sequence[dict], *, threshold: int | None = None
) -> tuple[list[dict], list[int]]:
    """对内存图片字节按感知哈希去重（下载落盘前），保留先出现者。

    每项需含 "bytes"。返回 (保留项, 被判重复的原索引列表)。
    哈希后端缺失时退化为按 sha256/字节恒等去重，绝不放水成「全保留」。
    """
    resolved_threshold = _near_duplicate_threshold(threshold)
    kept: list[dict] = []
    kept_hashes: list = []
    seen_sha: set[str] = set()
    dup_indices: list[int] = []
    for idx, payload in enumerate(payloads):
        data = payload.get("bytes") if isinstance(payload, dict) else None
        if not data:
            continue
        sha = payload.get("sha256") or hashlib.sha256(data).hexdigest()
        if sha in seen_sha:
            dup_indices.append(idx)
            continue
        h = _avg_hash_bytes(data)
        if h is not None and any((h - kh) <= resolved_threshold for kh in kept_hashes):
            dup_indices.append(idx)
            continue
        seen_sha.add(sha)
        if h is not None:
            kept_hashes.append(h)
        kept.append(payload)
    return kept, dup_indices

def dedupe_images(paths: Sequence[str | Path], *, threshold: int | None = None) -> list[Path]:
    """按感知哈希去重，保留先出现者。哈希后端缺失时退化为按解析路径去重。"""
    resolved_threshold = _near_duplicate_threshold(threshold)
    kept: list[Path] = []
    kept_hashes: list = []
    seen_resolved: set[str] = set()
    for raw in paths:
        p = Path(raw)
        key = str(p.resolve())
        if key in seen_resolved:
            continue
        seen_resolved.add(key)
        h = _avg_hash(p)
        if h is None:
            kept.append(p)
            continue
        if any((h - kh) <= resolved_threshold for kh in kept_hashes):
            continue
        kept.append(p)
        kept_hashes.append(h)
    return kept

def assess_images(paths: Iterable[str | Path]) -> list[ImageVerdict]:
    from core.image_safety import assess_image

    return [assess_image(p) for p in paths]

def assess_asset_sources(assets: Sequence[dict]) -> dict:
    """对一组 asset 记录（含 sourcePath）做图片体检并聚合。

    返回：{verdicts:[...], unsafe:[...], needsReview:[...], textHeavy:[...],
            duplicateGroups:[[idx...]], backends:{...}, summary:{...}}。
    near-dup 以 sourcePath 的感知哈希在集合内两两比较。
    """
    from core.image_safety import (
        NEAR_DUP_HAMMING,
        STATUS_NEEDS_REVIEW,
        STATUS_UNSAFE,
        assess_image,
        backend_status,
    )

    verdicts: list[dict] = []
    paths: list[Path] = []
    unsafe: list[str] = []
    needs_review: list[str] = []
    text_heavy: list[str] = []
    for asset in assets:
        source = asset.get("sourcePath") if isinstance(asset, dict) else None
        asset_id = str(asset.get("assetId") or asset.get("fileName") or "") if isinstance(asset, dict) else ""
        if not source:
            needs_review.append(asset_id or "<no-source>")
            verdicts.append({"assetId": asset_id, "status": STATUS_NEEDS_REVIEW, "reasons": ["asset_missing_sourcePath"]})
            paths.append(Path("/nonexistent"))
            continue
        verdict = assess_image(source)
        item = verdict.to_dict()
        item["assetId"] = asset_id
        verdicts.append(item)
        paths.append(Path(source))
        if verdict.status == STATUS_UNSAFE:
            unsafe.append(asset_id)
        elif verdict.status == STATUS_NEEDS_REVIEW:
            needs_review.append(asset_id)
        if verdict.is_text_heavy:
            text_heavy.append(asset_id)

    # 集合内近重复分组
    hashes = [_avg_hash(p) for p in paths]
    dup_groups: list[list[int]] = []
    used: set[int] = set()
    for i in range(len(hashes)):
        if i in used or hashes[i] is None:
            continue
        group = [i]
        for j in range(i + 1, len(hashes)):
            if j in used or hashes[j] is None:
                continue
            if (hashes[i] - hashes[j]) <= NEAR_DUP_HAMMING:
                group.append(j)
                used.add(j)
        if len(group) > 1:
            dup_groups.append(group)
            used.update(group)

    return {
        "verdicts": verdicts,
        "unsafe": unsafe,
        "needsReview": needs_review,
        "textHeavy": text_heavy,
        "duplicateGroups": dup_groups,
        "backends": backend_status(),
        "summary": {
            "total": len(verdicts),
            "unsafe": len(unsafe),
            "needsReview": len(needs_review),
            "textHeavy": len(text_heavy),
            "duplicateGroups": len(dup_groups),
        },
    }
