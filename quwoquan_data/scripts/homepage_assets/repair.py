"""Scan and repair entity homepage asset closure.

This module intentionally keeps generation deterministic: cold-start entity pages
must be reproducible across alpha/beta/gamma/prod sample builds.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from _common.entity_page_quality import entity_page_quality_issues
from _common.image_safety import STATUS_UNSAFE, assess_image, is_low_texture_placeholder_graphic
from _common.io import read_json, write_json
from _common.paths import NOW_ISO, PUBLISH_ROOT, RUNTIME_ROOT

_ASSET_REF_RE = re.compile(r"asset://([A-Za-z0-9_./\u4e00-\u9fff-]+)")
_ZH_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass(frozen=True)
class HomepageIssue:
    root_kind: str
    entity_ref: str
    entity_dir: Path
    issues: tuple[str, ...]

    def as_json(self, repo_root: Path | None = None) -> dict[str, Any]:
        path = self.entity_dir
        if repo_root is not None:
            try:
                path = path.relative_to(repo_root)
            except ValueError:
                pass
        return {
            "rootKind": self.root_kind,
            "entityRef": self.entity_ref,
            "entityDir": path.as_posix(),
            "issues": list(self.issues),
        }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _entity_ref_from_dir(entity_dir: Path) -> str:
    parts = entity_dir.parts
    idx = parts.index("entities")
    return "/".join(parts[idx + 1 :])


def _runtime_task_id(entity_dir: Path) -> str:
    parts = entity_dir.parts
    try:
        task_idx = parts.index("tasks")
        entities_idx = parts.index("entities")
    except ValueError:
        return "homepage-assets-repair"
    return "/".join(parts[task_idx + 1 : entities_idx])


def _root_kind(entity_dir: Path) -> str:
    try:
        entity_dir.relative_to(PUBLISH_ROOT)
        return "publish"
    except ValueError:
        return "runtime"


def _iter_entity_dirs(roots: Iterable[Path]) -> list[Path]:
    dirs: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        entity_roots = [root / "entities"] if (root / "entities").is_dir() else []
        entity_roots.extend(path for path in root.rglob("entities") if path.is_dir())
        for entities in sorted(set(entity_roots)):
            for page in entities.rglob("page.md"):
                dirs.add(page.parent)
            for entity_json in entities.rglob("_entity.json"):
                dirs.add(entity_json.parent)
    return sorted(dirs)


def _page_refs(page: Path) -> set[str]:
    if not page.is_file():
        return set()
    refs: set[str] = set()
    for raw in _ASSET_REF_RE.findall(page.read_text(encoding="utf-8")):
        refs.add(raw.split("/")[-1])
    return refs


def _manifest_assets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    assets = manifest.get("assets") or []
    return assets if isinstance(assets, list) else []


def _asset_issues(entity_dir: Path) -> list[str]:
    page = entity_dir / "page.md"
    manifest_path = entity_dir / "manifest.json"
    issues: list[str] = []
    if not page.is_file():
        issues.append("missing page.md")
        return issues
    issues.extend(entity_page_quality_issues(page))
    refs = _page_refs(page)
    if not refs:
        issues.append("page has no asset:// reference")
    if not manifest_path.is_file():
        issues.append("missing manifest.json")
        return issues
    try:
        manifest = read_json(manifest_path)
    except Exception as exc:  # noqa: BLE001
        issues.append(f"invalid manifest.json: {exc}")
        return issues
    assets = _manifest_assets(manifest)
    if not assets:
        issues.append("manifest.assets empty")
    known_ids: set[str] = set()
    known_files: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("assetId") or asset.get("id") or "").strip()
        file_name = str(asset.get("fileName") or "").strip()
        if asset_id:
            known_ids.add(asset_id)
        if file_name:
            known_files.add(file_name)
        if not file_name:
            issues.append(f"asset {asset_id or '<missing-id>'} missing fileName")
            continue
        physical = entity_dir / "assets" / file_name
        if not physical.is_file():
            issues.append(f"asset file missing on disk: assets/{file_name}")
            continue
        if is_low_texture_placeholder_graphic(physical):
            issues.append(f"asset unsafe image: assets/{file_name} reasons=['low_texture_placeholder_graphic']")
    for ref in sorted(refs):
        if ref not in known_ids and ref not in known_files:
            issues.append(f"page.md asset ref not in manifest: {ref}")
    return issues


def scan_homepages(*, include_runtime: bool = True, include_publish: bool = True) -> list[HomepageIssue]:
    roots: list[Path] = []
    if include_runtime:
        roots.append(RUNTIME_ROOT / "tasks")
    if include_publish:
        roots.append(PUBLISH_ROOT)
    issues: list[HomepageIssue] = []
    for entity_dir in _iter_entity_dirs(roots):
        entity_ref = _entity_ref_from_dir(entity_dir)
        found = _asset_issues(entity_dir)
        if found:
            issues.append(
                HomepageIssue(
                    root_kind=_root_kind(entity_dir),
                    entity_ref=entity_ref,
                    entity_dir=entity_dir,
                    issues=tuple(found),
                )
            )
    return issues


def _load_entity(entity_dir: Path, entity_ref: str) -> dict[str, Any]:
    path = entity_dir / "_entity.json"
    if path.is_file():
        try:
            payload = read_json(path)
            if isinstance(payload, dict):
                return payload
        except Exception:  # noqa: BLE001
            pass
    domain, etype, name = entity_ref.split("/", 2)
    return {"label": name, "domain": domain, "type": etype, "tagRefs": []}


def _image_files(assets_dir: Path) -> list[Path]:
    if not assets_dir.is_dir():
        return []
    return sorted(
        p for p in assets_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    )


def _asset_id_for_file(label: str, path: Path, index: int) -> str:
    stem = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff-]+", "_", path.stem).strip("_")
    safe_label = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff-]+", "_", label).strip("_") or "entity"
    return stem or f"{safe_label}_homepage_{index}"


def _asset_manifest_from_existing(entity_ref: str, label: str, files: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    assets: list[dict[str, Any]] = []
    issues: list[str] = []
    for index, path in enumerate(files, start=1):
        verdict = assess_image(path)
        if verdict.status == STATUS_UNSAFE:
            issues.append(f"existing asset unsafe image: assets/{path.name} reasons={list(verdict.reasons)}")
            continue
        role = "hero" if index == 1 else "detail"
        assets.append(
            {
                "assetId": _asset_id_for_file(label, path, index),
                "fileName": path.name,
                "caption": f"{label}{'封面' if role == 'hero' else '实景'}",
                "imageLayout": "fullWidth" if role == "hero" else "wrapRight",
                "role": role,
            }
        )
    return assets, issues


def _ensure_page_asset_refs(page_path: Path, assets: list[dict[str, Any]]) -> None:
    if not page_path.is_file():
        return
    text = page_path.read_text(encoding="utf-8")
    existing_refs = _page_refs(page_path)
    missing = [asset for asset in assets[:2] if str(asset["assetId"]) not in existing_refs]
    if not missing:
        return
    lines = text.splitlines()
    insert_at = 1 if lines and lines[0].startswith("#") else 0
    refs = [
        f'{{asset://{asset["assetId"]}|{asset.get("imageLayout", "fullWidth")}|{asset.get("caption", "")}|width={"100%" if asset.get("role") == "hero" else "45%"}}}'
        for asset in missing
    ]
    updated = lines[:insert_at] + ["", *refs, ""] + lines[insert_at:]
    page_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def repair_homepage(issue: HomepageIssue) -> dict[str, Any]:
    entity_dir = issue.entity_dir
    entity_ref = issue.entity_ref
    entity = _load_entity(entity_dir, entity_ref)
    domain, etype, name = entity_ref.split("/", 2)
    entity.setdefault("label", name)
    entity["domain"] = str(entity.get("domain") or domain)
    entity["type"] = str(entity.get("type") or etype)
    entity["sourceTaskId"] = str(
        entity.get("sourceTaskId")
        or (_runtime_task_id(entity_dir) if issue.root_kind == "runtime" else "publish-homepage-assets-repair")
    )
    label = str(entity.get("label") or name)
    assets_dir = entity_dir / "assets"
    if not (entity_dir / "page.md").is_file():
        return {
            "entityRef": entity_ref,
            "rootKind": issue.root_kind,
            "entityDir": issue.entity_dir.as_posix(),
            "assetCount": 0,
            "remainingIssues": ["missing page.md; homepage-assets repair will not generate reader copy"],
        }
    quality_issues = entity_page_quality_issues(entity_dir / "page.md")
    if quality_issues:
        return {
            "entityRef": entity_ref,
            "rootKind": issue.root_kind,
            "entityDir": issue.entity_dir.as_posix(),
            "assetCount": 0,
            "remainingIssues": quality_issues,
        }
    assets, asset_issues = _asset_manifest_from_existing(entity_ref, label, _image_files(assets_dir))
    if asset_issues or not assets:
        return {
            "entityRef": entity_ref,
            "rootKind": issue.root_kind,
            "entityDir": issue.entity_dir.as_posix(),
            "assetCount": len(assets),
            "remainingIssues": asset_issues or ["no reusable real homepage assets; rerun download/build with verified images"],
        }
    manifest_path = entity_dir / "manifest.json"
    manifest = read_json(manifest_path) if manifest_path.is_file() else {}
    if not isinstance(manifest, dict):
        manifest = {}
    manifest["schemaVersion"] = manifest.get("schemaVersion") or "quwoquan.entity.homepage_manifest"
    manifest["entityRef"] = entity_ref
    manifest["tagRefs"] = entity.get("tagRefs") or manifest.get("tagRefs") or []
    manifest["assets"] = assets
    manifest["updatedAt"] = NOW_ISO
    entity_dir.mkdir(parents=True, exist_ok=True)
    _ensure_page_asset_refs(entity_dir / "page.md", assets)
    write_json(entity_dir / "_entity.json", entity)
    write_json(manifest_path, manifest)
    remaining = _asset_issues(entity_dir)
    return {
        "entityRef": entity_ref,
        "rootKind": issue.root_kind,
        "entityDir": issue.entity_dir.as_posix(),
        "assetCount": len(assets),
        "remainingIssues": remaining,
    }


def write_report(path: Path, issues: list[HomepageIssue], repairs: list[dict[str, Any]]) -> None:
    repo_root = _repo_root()
    payload = {
        "schemaVersion": "quwoquan.homepage_assets.report",
        "generatedAt": NOW_ISO,
        "issueCount": len(issues),
        "repairCount": len(repairs),
        "issues": [issue.as_json(repo_root) for issue in issues],
        "repairs": repairs,
    }
    write_json(path, payload)


def has_chinese_content(path: Path) -> bool:
    if not path.is_file():
        return False
    return bool(_ZH_RE.search(path.read_text(encoding="utf-8", errors="ignore")))
