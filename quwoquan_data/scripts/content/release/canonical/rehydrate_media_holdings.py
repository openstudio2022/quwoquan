#!/usr/bin/env python3
"""Rehydrate the content library from the sources recorded beside the tree.

Canonical publish carries references and never bodies, so a clean checkout owns
no media at all and every closure check fails for want of bytes rather than for
any defect in the tree. The rights record kept next to each object already names
the upstream asset it was captured from, and refetching that URL reproduces the
recorded digest byte for byte, so most holdings need no storage of their own.

The exception is a holding that was derived rather than captured — an avatar
square-cropped and re-encoded — whose bytes depend on the encoder that produced
them and therefore cannot be refetched. Those are carried as reference bytes in
version control instead, which is also why they must not live in the publish
tree: that tree's contract is references only.

Both routes end at the same admission, which verifies bytes against the declared
digest, so neither a drifted upstream nor a corrupted seed can enter the library
under a digest it does not hash to.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.content_library import (  # noqa: E402
    MediaHoldingError,
    admit_library_bytes,
    admit_library_entry,
    resolve_media_holding,
)
from core.paths import PUBLISH_ROOT  # noqa: E402

REFERENCE_MEDIA_ROOT = SCRIPTS_ROOT.parent / "reference/golden_media"
MEDIA_KIND = "media"
_CAS_OBJECT_KEY = re.compile(
    r"media/objects/sha256/[0-9a-f]{2}/[0-9a-f]{2}/(?P<digest>[0-9a-f]{64})\.[a-z0-9]+"
)
# Wikimedia refuses the stdlib default agent, and a refusal here would read as a
# missing holding rather than as a fetch that was turned away.
_FETCH_HEADERS = {
    "User-Agent": "quwoquan-media-rehydration/1.0 (content library rehydration)"
}
_FETCH_TIMEOUT_SECONDS = 60
# A whole tree's worth of holdings arrives as one burst, which upstream answers
# with throttling rather than refusal; without a wait-and-retry the run reports
# the throttle as a missing source and buries a healthy upstream.
_FETCH_ATTEMPTS = 4
_FETCH_BACKOFF_SECONDS = 2.0


class FetchRefused(RuntimeError):
    """Upstream did not yield the bytes, with the reason kept for the report."""


@dataclass(frozen=True, slots=True)
class MediaSource:
    """Where one required holding can be obtained, and what it must hash to."""

    digest: str
    url: str = ""
    declared_bytes: int = 0


def _walk_asset_records(node: object, sources: dict[str, MediaSource]) -> None:
    if isinstance(node, dict):
        asset = node.get("asset")
        url = node.get("originalAssetUrl")
        if isinstance(asset, dict) and isinstance(url, str) and url:
            digest = str(asset.get("sha256") or "").removeprefix("sha256:")
            if digest and digest not in sources:
                declared = asset.get("bytes")
                sources[digest] = MediaSource(
                    digest=digest,
                    url=url,
                    declared_bytes=declared if isinstance(declared, int) else 0,
                )
        for value in node.values():
            _walk_asset_records(value, sources)
    elif isinstance(node, list):
        for value in node:
            _walk_asset_records(value, sources)


def required_digests(publish_root: Path) -> set[str]:
    """Every media digest the canonical tree references, counted once."""

    digests: set[str] = set()
    for path in sorted(publish_root.rglob("*.json")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in _CAS_OBJECT_KEY.finditer(text):
            digests.add(match.group("digest"))
    return digests


def recorded_sources(publish_root: Path) -> dict[str, MediaSource]:
    """The upstream asset each holding was captured from, keyed by digest."""

    sources: dict[str, MediaSource] = {}
    for path in sorted(publish_root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        _walk_asset_records(payload, sources)
    return sources


def _reference_entry(digest: str) -> Path | None:
    if not REFERENCE_MEDIA_ROOT.is_dir():
        return None
    for candidate in sorted(REFERENCE_MEDIA_ROOT.glob(f"{digest}.*")):
        if candidate.is_file():
            return candidate
    return None


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers=_FETCH_HEADERS)
    last_error: Exception | None = None
    for attempt in range(_FETCH_ATTEMPTS):
        if attempt:
            time.sleep(_FETCH_BACKOFF_SECONDS * (2 ** (attempt - 1)))
        try:
            with urllib.request.urlopen(
                request, timeout=_FETCH_TIMEOUT_SECONDS
            ) as response:
                return response.read()
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            last_error = error
    raise FetchRefused(f"{url}: {last_error}")


def rehydrate_one(digest: str, source: MediaSource | None) -> tuple[str, str]:
    """Admit one holding, reporting which route honoured it and why if none did."""

    try:
        resolve_media_holding(digest)
        return "already_held", ""
    except (MediaHoldingError, ValueError):
        pass

    entry = _reference_entry(digest)
    if entry is not None:
        admit_library_entry(entry, kind=MEDIA_KIND, sha256=digest)
        return "from_reference_bytes", ""

    if source is None or not source.url:
        return "unresolved_no_source", "no recorded upstream asset"

    try:
        body = _fetch(source.url)
    except FetchRefused as refusal:
        return "unresolved_fetch_failed", str(refusal)

    admitted = admit_library_bytes(body, kind=MEDIA_KIND)
    if admitted.name != digest:
        return (
            "unresolved_digest_drift",
            f"upstream now hashes to {admitted.name}; holding was derived, "
            "so it must be carried as reference bytes",
        )
    return "from_recorded_source", ""


def main() -> int:
    digests = required_digests(PUBLISH_ROOT)
    sources = recorded_sources(PUBLISH_ROOT)
    outcomes: dict[str, list[tuple[str, str]]] = {}
    for digest in sorted(digests):
        outcome, reason = rehydrate_one(digest, sources.get(digest))
        outcomes.setdefault(outcome, []).append((digest, reason))

    for outcome in sorted(outcomes):
        print(f"[rehydrate_media_holdings] {outcome}: {len(outcomes[outcome])}")
    unresolved = [
        (digest, reason)
        for outcome, items in outcomes.items()
        if outcome.startswith("unresolved")
        for digest, reason in items
    ]
    if unresolved:
        print("[rehydrate_media_holdings] FAIL")
        for digest, reason in sorted(unresolved):
            print(f"  - unresolved holding: {digest}: {reason}")
        return 1
    print(f"[rehydrate_media_holdings] OK: {len(digests)} holdings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
