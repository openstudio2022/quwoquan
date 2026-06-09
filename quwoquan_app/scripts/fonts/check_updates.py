"""Check upstream drift for bundled fonts."""

from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from _common.paths import APP_ROOT
from fonts.manifest import iter_font_entries, load_manifest


def _github_latest_commit(path: str) -> str | None:
    api = f"https://api.github.com/repos/google/fonts/commits?path={path}&per_page=1"
    request = urllib.request.Request(
        api,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "qwq-app-fonts-check/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list) or not payload:
        return None
    sha = payload[0].get("sha")
    return str(sha) if sha else None


def _flutter_engine_hash() -> str | None:
    try:
        proc = subprocess.run(
            ["flutter", "--version"],
            cwd=str(APP_ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    match = re.search(r"Engine • hash ([0-9a-f]+)", proc.stdout)
    return match.group(1) if match else None


def _load_roboto_map() -> dict[str, Any]:
    map_path = Path(__file__).resolve().parent / "flutter_engine_roboto_map.yaml"
    if not map_path.is_file():
        return {}
    data = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def check_updates(
    *,
    manifest_file: Path | None = None,
    output: str = "text",
    report: Path | None = None,
    fail_on_drift: bool = False,
) -> dict[str, Any]:
    data = load_manifest(manifest_file)
    drifts: list[dict[str, Any]] = []
    ok_count = 0

    for entry in iter_font_entries(data):
        upstream = entry.get("upstream")
        if not isinstance(upstream, dict):
            continue
        path = str(upstream.get("path", "")).strip()
        pinned = str(upstream.get("pinnedCommit", "")).strip()
        direct_url = str(upstream.get("url", "")).strip()
        if direct_url:
            ok_count += 1
            continue
        latest = _github_latest_commit(path) if path else None
        if latest and pinned and latest != pinned:
            drifts.append(
                {
                    "family": entry.get("family"),
                    "weight": entry.get("weight"),
                    "assetPath": entry.get("assetPath"),
                    "pinnedCommit": pinned,
                    "latestCommit": latest,
                }
            )
        else:
            ok_count += 1

    engine_hash = _flutter_engine_hash()
    engine_notes: list[str] = []
    roboto_map = _load_roboto_map()
    entries = roboto_map.get("entries")
    if engine_hash and isinstance(entries, list):
        matched = any(
            isinstance(item, dict) and item.get("engineHash") == engine_hash for item in entries
        )
        if not matched:
            engine_notes.append(
                f"Flutter engine {engine_hash} not listed in flutter_engine_roboto_map.yaml; "
                "update map after SDK upgrade"
            )

    payload = {
        "status": "warn" if drifts or engine_notes else "ok",
        "manifestVersion": data.get("manifestVersion"),
        "drift": drifts,
        "engineNotes": engine_notes,
        "summary": {"drift": len(drifts), "ok": ok_count},
    }

    if output == "json":
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        print(rendered)
    elif output == "markdown":
        lines = [
            "# Bundled fonts update report",
            "",
            f"- manifestVersion: {data.get('manifestVersion')}",
            f"- drift: {len(drifts)}",
            "",
        ]
        for item in drifts:
            lines.append(
                f"- WARN {item.get('family')}/{item.get('weight')} "
                f"pinned={item.get('pinnedCommit')} latest={item.get('latestCommit')}"
            )
        for note in engine_notes:
            lines.append(f"- WARN {note}")
        rendered = "\n".join(lines)
        print(rendered)
    else:
        prefix = "[qwq-app fonts check-updates]"
        for item in drifts:
            print(
                f"{prefix} WARN {item.get('family')}/{item.get('weight')} "
                f"upstream drift pinned={item.get('pinnedCommit')} latest={item.get('latestCommit')}"
            )
        for note in engine_notes:
            print(f"{prefix} WARN {note}")
        print(f"{prefix} SUMMARY drift={len(drifts)} ok={ok_count}")

    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if fail_on_drift and (drifts or engine_notes):
        raise SystemExit(1)
    return payload
