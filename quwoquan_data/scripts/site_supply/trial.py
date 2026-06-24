"""Controlled-trial fixtures for site-supply."""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import functools
import hashlib
import json
import math
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

import yaml

from _common.io import read_json, write_json
from _common.paths import DATA_ROOT, RUNTIME_ROOT, now_iso
from download.fetch import fetch_image_payload, fetch_source_payload

from site_supply.core import *  # noqa: F403
from site_supply.packets import *  # noqa: F403

def _trial_text(index: int) -> str:
    return (
        f"这是第 {index} 个网站维度结构试跑候选，包含路线、地点、时间、交通、体验判断、"
        "证据映射、实体 mention 和后续 content_plan handoff 所需的事实边界。"
        "该文本用于验证 stage gate、repair、score、map 和 rollup 的结构稳定性，不代表真实发布正文。"
    )

def _trial_lane_counts(args: argparse.Namespace) -> dict[str, int]:
    explicit = {
        "article": args.article_count,
        "image": args.image_count,
        "video": args.video_count,
    }
    if any(value is not None for value in explicit.values()):
        counts = {lane: int(value or 0) for lane, value in explicit.items()}
        total = sum(counts.values())
        if args.target_count is not None and int(args.target_count) != total:
            raise SystemExit("--target-count must equal article/image/video count sum when lane counts are explicit")
        if total <= 0:
            raise SystemExit("at least one lane count must be >0")
        return {lane: count for lane, count in counts.items() if count > 0}
    if args.target_count is None:
        raise SystemExit("--target-count is required unless explicit lane counts are provided")
    return {"article": int(args.target_count)}

def _trial_url(profile: Mapping[str, Any], *, batch_id: str, lane: str, index: int) -> str:
    allowed_paths = [str(x) for x in (profile.get("allowedPaths") or []) if str(x)]
    pattern = allowed_paths[0] if allowed_paths else "https://example.com/*"
    token = f"site-trial/{lane}/{batch_id}-{index:06d}.html"
    if "*" in pattern:
        return pattern.replace("*", token, 1)
    return f"{pattern.rstrip('/')}/{token}"

def _trial_assets(profile: Mapping[str, Any], *, url: str, lane: str, index: int) -> list[dict[str, Any]]:
    if lane not in {"image", "video"}:
        return []
    platform = str(profile.get("platform") or profile.get("siteId") or "site")
    ext = "jpg" if lane == "image" else "mp4"
    terms_url = str(profile.get("termsUrl") or url)
    return [{
        "assetId": _stable_ref("asset", url, lane, index),
        "url": f"{url}#controlled-{lane}-{index:06d}.{ext}",
        "sourceUrl": url,
        "license": "validation_only_not_for_publish",
        "credit": f"{platform} controlled trial",
        "termsUrl": terms_url,
        "usageScope": "site_supply_controlled_trial_only",
        "modelReleaseStatus": "not_required",
        "publishable": False,
    }]

__all__ = [name for name in globals() if not name.startswith("__")]
