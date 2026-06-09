"""Download bundled fonts from google/fonts upstream paths."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from _common.paths import GITHUB_FONTS_RAW
from fonts.manifest import asset_abs, iter_font_entries, load_manifest, save_manifest, sha256_file


def _upstream_url(entry: dict[str, Any]) -> str:
    upstream = entry.get("upstream")
    if not isinstance(upstream, dict):
        raise ValueError(f"missing upstream for {entry.get('assetPath')}")
    direct = str(upstream.get("url", "")).strip()
    if direct:
        return direct
    path = str(upstream.get("path", "")).strip().lstrip("/")
    if path.startswith("gstatic/"):
        raise ValueError(
            f"missing upstream.url for gstatic path {path} ({entry.get('assetPath')})"
        )
    if not path:
        raise ValueError(f"missing upstream.path for {entry.get('assetPath')}")
    return f"{GITHUB_FONTS_RAW}/{path}"


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "qwq-app-fonts-fetch/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        dest.write_bytes(response.read())


def _github_latest_commit(path: str) -> str | None:
    import json
    import urllib.error
    import urllib.request

    api = f"https://api.github.com/repos/google/fonts/commits?path={path}&per_page=1"
    request = urllib.request.Request(
        api,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "qwq-app-fonts-fetch/1.0"},
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


def fetch_fonts(
    *,
    manifest_file: Path | None = None,
    family_filter: str | None = None,
    dry_run: bool = False,
    output: str = "text",
) -> dict[str, Any]:
    data = load_manifest(manifest_file)
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for entry in iter_font_entries(data):
        family = str(entry.get("family", ""))
        if family_filter and family != family_filter:
            continue
        asset_path = str(entry.get("assetPath", "")).strip()
        if not asset_path:
            errors.append("manifest entry missing assetPath")
            continue
        dest = asset_abs(asset_path)
        url = _upstream_url(entry)
        if dry_run:
            results.append(
                {
                    "family": family,
                    "weight": entry.get("weight"),
                    "assetPath": asset_path,
                    "url": url,
                    "status": "dry-run",
                }
            )
            continue
        try:
            _download(url, dest)
            digest = sha256_file(dest)
            entry["sha256"] = digest
            upstream = entry.setdefault("upstream", {})
            if isinstance(upstream, dict):
                path = str(upstream.get("path", "")).strip()
                if str(upstream.get("url", "")).strip():
                    upstream["pinnedCommit"] = upstream.get("pinnedCommit") or "v32"
                elif path:
                    latest = _github_latest_commit(path)
                    if latest:
                        upstream["pinnedCommit"] = latest
            results.append(
                {
                    "family": family,
                    "weight": entry.get("weight"),
                    "assetPath": asset_path,
                    "sha256": digest,
                    "status": "ok",
                }
            )
        except (urllib.error.URLError, OSError, ValueError) as exc:
            errors.append(f"{asset_path}: {exc}")

    if not dry_run and not errors:
        save_manifest(data, manifest_file)

    payload = {
        "status": "ok" if not errors else "fail",
        "manifestVersion": data.get("manifestVersion"),
        "files": results,
        "errors": errors,
    }
    if output == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        prefix = "[qwq-app fonts fetch]"
        for item in results:
            print(
                f"{prefix} OK family={item.get('family')} weight={item.get('weight')} "
                f"path={item.get('assetPath')} sha256={item.get('sha256', 'dry-run')}"
            )
        if errors:
            for err in errors:
                print(f"{prefix} FAIL {err}")
        else:
            print(
                f"{prefix} DONE families={len({r.get('family') for r in results})} "
                f"files={len(results)} manifestVersion={data.get('manifestVersion')}"
            )
    if errors:
        raise SystemExit(1)
    return payload


def write_sha256(*, manifest_file: Path | None = None) -> None:
    data = load_manifest(manifest_file)
    updated = 0
    for entry in iter_font_entries(data):
        asset_path = str(entry.get("assetPath", "")).strip()
        path = asset_abs(asset_path)
        if not path.is_file():
            raise SystemExit(f"[qwq-app fonts write-sha] missing file: {asset_path}")
        entry["sha256"] = sha256_file(path)
        updated += 1
    save_manifest(data, manifest_file)
    print(f"[qwq-app fonts write-sha] updated sha256 for {updated} entries")
