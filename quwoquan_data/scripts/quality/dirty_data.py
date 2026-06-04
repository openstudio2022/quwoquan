"""历史脏数据扫描与删除。"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from _common.io import write_json
from _common.paths import DATA_ROOT, PUBLISH_ROOT, RUNTIME_ROOT
from homepage_assets.repair import scan_homepages
from verify_content_quality import FORBIDDEN, asset_closure_issues


_DIRTY_ENTITY_TOKENS = (
    "engineering/template phrase",
    "generated system explainer",
    "low_texture_placeholder_graphic",
    "asset ref not in manifest",
    "asset unsafe image",
)


def _repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(DATA_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def entity_homepage_dirty_issues(issues: list[str]) -> list[str]:
    return [item for item in issues if any(token in item for token in _DIRTY_ENTITY_TOKENS)]


def _post_roots() -> list[Path]:
    roots: list[Path] = []
    roots.extend(path for path in (RUNTIME_ROOT / "tasks").rglob("produce/posts") if path.is_dir())
    if (PUBLISH_ROOT / "posts").is_dir():
        roots.append(PUBLISH_ROOT / "posts")
    seen: set[str] = set()
    out: list[Path] = []
    for root in roots:
        key = str(root.resolve())
        if key not in seen:
            seen.add(key)
            out.append(root)
    return out


def scan_dirty_data() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for issue in scan_homepages(include_runtime=True, include_publish=True):
        dirty_issues = entity_homepage_dirty_issues(issue.issues)
        if not dirty_issues:
            continue
        rows.append(
            {
                "kind": "entity_homepage",
                "path": _repo_rel(issue.entity_dir),
                "issues": dirty_issues,
            }
        )
    for root in _post_roots():
        for manifest_path in sorted(root.rglob("manifest.json")):
            post_dir = manifest_path.parent
            try:
                import json

                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                rows.append({"kind": "post_package", "path": _repo_rel(post_dir), "issues": [f"manifest unreadable: {exc}"]})
                continue
            found = list(asset_closure_issues(post_dir, manifest))
            article_path = post_dir / "article.md"
            if article_path.is_file():
                article = article_path.read_text(encoding="utf-8", errors="ignore")
                for word in FORBIDDEN:
                    if word in article:
                        found.append(f"{article_path}: forbidden phrase found: {word}")
            if found:
                rows.append(
                    {
                        "kind": "post_package",
                        "path": _repo_rel(post_dir),
                        "issues": found,
                    }
                )
    return rows


def delete_dirty_data(rows: list[dict[str, Any]]) -> list[str]:
    deleted: list[str] = []
    for row in rows:
        path = DATA_ROOT / str(row.get("path") or "")
        if row.get("kind") == "entity_homepage":
            for name in ("page.md", "manifest.json"):
                target = path / name
                if target.exists():
                    target.unlink()
                    deleted.append(_repo_rel(target))
            assets = path / "assets"
            if assets.exists():
                shutil.rmtree(assets)
                deleted.append(_repo_rel(assets))
        elif row.get("kind") == "post_package" and path.exists():
            shutil.rmtree(path)
            deleted.append(_repo_rel(path))
    return deleted


def write_dirty_report(path: Path, rows: list[dict[str, Any]], deleted: list[str]) -> Path:
    write_json(
        path,
        {
            "schemaVersion": "quwoquan.dirty_data_report.v1",
            "issueCount": len(rows),
            "deleteCount": len(deleted),
            "issues": rows,
            "deleted": deleted,
        },
    )
    return path
