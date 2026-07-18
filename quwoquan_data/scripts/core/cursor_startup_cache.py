"""Disposable cache for successful Cursor startup admission probes."""
from __future__ import annotations

import json
import time
from pathlib import Path

from core.cursor_startup_probe import cursor_startup_probe
from core.paths import DATA_LOCAL_ROOT
from core.runtime_policy import active_runtime_policy


_CURSOR_STARTUP_PROBE_CACHE_FILENAME = "cursor_startup_probe_cache.json"


def cursor_startup_probe_cache_path() -> Path:
    return DATA_LOCAL_ROOT / "cache" / "cursor" / _CURSOR_STARTUP_PROBE_CACHE_FILENAME


def cached_cursor_startup_probe(
    *,
    model: str,
    runtime: str,
    timeout_seconds: float,
) -> dict:
    """Reuse only a recent successful probe from the disposable repo cache."""
    ttl = active_runtime_policy().cursor_startup_probe_cache_ttl_seconds
    cache_key = f"{model}::{runtime}"
    cache_path = cursor_startup_probe_cache_path()
    if ttl > 0 and cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            entry = cached.get(cache_key) if isinstance(cached, dict) else None
            if (
                isinstance(entry, dict)
                and bool((entry.get("report") or {}).get("ready"))
                and (time.time() - float(entry.get("cachedAtEpoch") or 0)) < ttl
            ):
                report = dict(entry["report"])
                report["cacheHit"] = True
                report["cachedAt"] = entry.get("cachedAt")
                return report
        except (OSError, ValueError, TypeError):
            pass
    report = cursor_startup_probe(
        model=model,
        runtime=runtime,
        timeout_seconds=timeout_seconds,
    )
    if ttl > 0 and bool(report.get("ready")):
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            existing: dict = {}
            if cache_path.is_file():
                try:
                    existing = json.loads(cache_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    existing = {}
            if not isinstance(existing, dict):
                existing = {}
            existing[cache_key] = {
                "cachedAtEpoch": time.time(),
                "cachedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "report": report,
            }
            cache_path.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
    return report


__all__ = ["cached_cursor_startup_probe", "cursor_startup_probe_cache_path"]
