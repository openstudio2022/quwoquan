#!/usr/bin/env python3
"""纯只读核验随体对象，不隐式补库或下载。"""
from __future__ import annotations

import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from content.release.canonical.object_transaction_contract import _read_json, _safe_rel, _digest_file
from content.release.canonical.post_transaction_sources import read_object_sources
from core.paths import PUBLISH_ROOT
from core.publish_repository import canonical_files
from verify.verify_publish_purity import publish_structure_issues


def carried_media_closure_issues(publish_root: Path) -> list[dict[str, str]]:
    issues = []
    try:
        files = canonical_files(publish_root)
    except (OSError, ValueError) as exc:
        return [{"code": "DATA.PUBLISH.REPOSITORY_INVALID", "ref": str(exc)}]
    for path in files:
        relative = path.relative_to(publish_root)
        if path.name not in {"manifest.json", "profile.json"} or {"sources", "records"} & set(relative.parts):
            continue
        manifest = _read_json(path)
        try:
            sources = read_object_sources(path.parent, manifest)
            urls = ",".join(source["sourceUrl"] for source in sources)
            for asset in manifest.get("assets") or []:
                ref = _safe_rel(str(asset.get("path") or ""), label="asset.path")
                body = path.parent / ref
                if ref.parts[0] != "media" or body.is_symlink() or not body.is_file():
                    issues.append({"code": "DATA.PUBLISH.CARRIED_MEDIA_MISSING", "ref": f"{relative}:{ref} sourceUrl={urls}"})
                elif _digest_file(body) != asset.get("sha256") or body.stat().st_size != asset.get("bytes"):
                    issues.append({"code": "DATA.PUBLISH.CARRIED_MEDIA_DRIFT", "ref": f"{relative}:{ref} sourceUrl={urls}"})
        except (RuntimeError, OSError, ValueError) as exc:
            issues.append({"code": str(exc).split(":", 1)[0], "ref": f"{relative}: {exc}"})
    return issues


def main() -> int:
    structure = publish_structure_issues(PUBLISH_ROOT)
    issues = carried_media_closure_issues(PUBLISH_ROOT)
    print("[verify_publish_closure] " + ("FAIL" if structure or issues else "OK"))
    for issue in [*structure, *issues]:
        print(f"  - {issue}")
    return int(bool(structure or issues))


if __name__ == "__main__":
    raise SystemExit(main())
