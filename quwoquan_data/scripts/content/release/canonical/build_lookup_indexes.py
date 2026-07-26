#!/usr/bin/env python3
"""从自治对象包确定性重建 immutable release lookup index。"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from core.paths import (
    CONTROL_PLANE_TAXONOMY_ROOT,
    OUTPUT_ROOT,
    PUBLISH_ROOT,
    RELEASE_ROOT,
    REPO_ROOT,
)
from core.release_layout import payload_file

HOMEPAGE_SERVICE_YAML = (
    REPO_ROOT
    / "quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/operations.yaml"
)
ENVIRONMENTS_ROOT = REPO_ROOT / "quwoquan_ops/environments"
COVERAGE_ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _write_ndjson(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(_json_bytes(dict(row)) for row in rows))


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 顶层必须为 object: {path}")
    return value


def _scan_entities(canonical: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base = canonical / "entities"
    if not base.is_dir():
        return rows
    for path in sorted(base.rglob("_entity.json")):
        doc = _read_json(path)
        ref = path.parent.relative_to(base).as_posix()
        rows.append(
            {
                "entityRef": ref,
                "label": doc.get("label") or path.parent.name,
                "domain": doc.get("domain"),
                "etype": doc.get("type"),
                "tagRefs": sorted({str(ref) for ref in doc.get("tagRefs") or []}),
                "hasPage": (path.parent / "page.md").is_file(),
                "geoTagRef": str(doc.get("geoTagRef") or ""),
                "promotedAt": str(
                    (_read_json(path.parent / "manifest.json").get("quality") or {}).get(
                        "promotedAt"
                    )
                )
                if (path.parent / "manifest.json").is_file()
                else "",
            }
        )
    return rows


def _scan_posts(canonical: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base = canonical / "posts"
    if not base.is_dir():
        return rows
    for path in sorted(base.rglob("manifest.json")):
        doc = _read_json(path)
        rel = path.parent.relative_to(base).as_posix()
        rows.append(
            {
                "postRef": f"posts/{rel}",
                "contentType": doc.get("contentType"),
                "title": doc.get("publishTitle") or doc.get("title") or path.parent.parent.name,
                "tagRefs": sorted({str(ref) for ref in doc.get("tagRefs") or []}),
                "entityRefs": sorted({str(ref) for ref in doc.get("entityRefs") or []}),
            }
        )
    return rows


def _tag_links(
    taxonomy_root: Path,
    entities: list[dict[str, Any]],
    posts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, int]] = {}
    homepage_entities: dict[str, list[str]] = {}
    for row, kind in [*((row, "entity") for row in entities), *((row, "post") for row in posts)]:
        for ref in row.get("tagRefs") or []:
            entry = counts.setdefault(str(ref), {"entities": 0, "posts": 0})
            entry["entities" if kind == "entity" else "posts"] += 1
            if kind == "entity" and row.get("hasPage"):
                homepage_entities.setdefault(str(ref), []).append(str(row["entityRef"]))
    rows: list[dict[str, Any]] = []
    if taxonomy_root.is_dir():
        for definition in sorted(taxonomy_root.rglob("_definition.json")):
            ref = definition.parent.relative_to(taxonomy_root).as_posix()
            ref_counts = counts.get(ref, {"entities": 0, "posts": 0})
            candidates = sorted(set(homepage_entities.get(ref) or []))
            row: dict[str, Any] = {"tagRef": ref, "counts": ref_counts}
            if (definition.parent / "page.md").is_file():
                row["targetKind"] = "landing"
            elif len(candidates) == 1:
                row.update(
                    {
                        "targetKind": "homepage",
                        "routePath": "/homepages/{id}",
                        "homepageEntityRef": candidates[0],
                    }
                )
            elif ref_counts["entities"] or ref_counts["posts"]:
                row["targetKind"] = "search"
            else:
                row["targetKind"] = "none"
            rows.append(row)
    return rows


def _introduction_path_template() -> str:
    doc = yaml.safe_load(HOMEPAGE_SERVICE_YAML.read_text(encoding="utf-8"))
    for route in doc.get("api_routes") or []:
        if route.get("operation") == "GetHomepageIntroduction":
            return str(route.get("path") or "")
    raise ValueError(f"{HOMEPAGE_SERVICE_YAML} 缺 GetHomepageIntroduction 路由")


def _environment_api_bases() -> dict[str, str]:
    bases: dict[str, str] = {}
    for env in COVERAGE_ENVIRONMENTS:
        runtime_path = ENVIRONMENTS_ROOT / env / "runtime.yaml"
        doc = yaml.safe_load(runtime_path.read_text(encoding="utf-8")) or {}
        if doc.get("schema") != "environment-runtime" or doc.get("environment") != env:
            raise ValueError(f"环境 runtime 身份不一致: {runtime_path}")
        node = doc.get("publicBases") or {}
        base = str(node.get("api") or "").strip().rstrip("/")
        if base:
            bases[env] = base
    return bases


def _latest_env_homepage_imports(release_base: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for env in COVERAGE_ENVIRONMENTS:
        runs_root = OUTPUT_ROOT / "env" / env / "runs" / "data-release"
        if not runs_root.is_dir():
            continue
        for report_path in sorted(runs_root.glob("*/*/import-homepage.json")):
            report = _read_json(report_path)
            if report.get("dryRun"):
                continue
            finished = str(report.get("finishedAt") or "")
            if env in latest and finished <= str(latest[env]["finishedAt"]):
                continue
            release_id = report_path.parents[1].name
            desired_path = payload_file(release_base / release_id, "desired_state.json")
            desired = _read_json(desired_path) if desired_path.is_file() else {}
            entities = {
                str(ref).removeprefix("/entity/")
                for ref in ((desired.get("desiredRefs") or {}).get("entities") or [])
            }
            latest[env] = {
                "releaseId": release_id,
                "finishedAt": finished,
                "entities": entities,
                "entityRefToHomepageId": {
                    str(key): str(value)
                    for key, value in (report.get("entityRefToHomepageId") or {}).items()
                },
            }
    return latest


def _coverage_province(geo_ref: str) -> str:
    prefix = "Topic/地理/行政区/"
    if not geo_ref.startswith(prefix):
        return "unknown"
    parts = [part for part in geo_ref[len(prefix) :].strip("/").split("/") if part]
    return parts[1] if len(parts) >= 2 else (parts[0] if parts else "unknown")


def _coverage_rows(
    canonical: Path,
    entities: list[dict[str, Any]],
    release_base: Path,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    from governance.coverage.master_list import (
        iter_master_leaves,
        load_master_list_file,
        master_list_files,
    )

    entities_by_ref = {str(row["entityRef"]): row for row in entities}
    env_imports = _latest_env_homepage_imports(release_base)
    bases = _environment_api_bases()
    intro_path = _introduction_path_template()
    rows_by_province: dict[str, list[dict[str, Any]]] = defaultdict(list)
    primary_refs: set[str] = set()
    homepage_count = 0

    def env_cells(entity_ref: str) -> dict[str, dict[str, Any]]:
        cells: dict[str, dict[str, Any]] = {}
        for env in COVERAGE_ENVIRONMENTS:
            info = env_imports.get(env)
            imported = bool(info and entity_ref in info["entities"])
            cell: dict[str, Any] = {"imported": imported}
            if imported and info is not None:
                cell["releaseId"] = info["releaseId"]
                cell["importedAt"] = info["finishedAt"]
                base = bases.get(env, "")
                if base:
                    homepage_id = info["entityRefToHomepageId"].get(entity_ref, "")
                    path = intro_path.replace("{homepageId}", homepage_id) if homepage_id else intro_path
                    cell["introductionUrl"] = f"{base}{path}"
            cells[env] = cell
        return cells

    for path in master_list_files():
        data = load_master_list_file(path)
        for _district, leaf in iter_master_leaves(data):
            canonical_name = str(leaf.get("canonicalName") or leaf.get("name") or "").strip()
            entity_type = str(leaf.get("entityType") or "").strip()
            if not canonical_name or not entity_type:
                continue
            entity_ref = f"{entity_type}/{canonical_name}"
            entity = entities_by_ref.get(entity_ref) or {}
            geo_ref = str(leaf.get("geoTagRef") or "")
            base_row = {
                "entityRef": entity_ref,
                "canonicalName": canonical_name,
                "entityType": entity_type,
                "geoTagRef": geo_ref,
                "masterListed": True,
                "hasHomepage": bool(entity.get("hasPage")),
                "promotedAt": str(entity.get("promotedAt") or ""),
                "envImports": env_cells(entity_ref),
            }
            if entity_ref not in primary_refs:
                primary_refs.add(entity_ref)
                homepage_count += int(base_row["hasHomepage"])
            primary = _coverage_province(geo_ref)
            provinces = {primary}
            provinces.update(
                _coverage_province(str(ref)) for ref in leaf.get("geoTagRefs") or []
            )
            for province in sorted(provinces):
                rows_by_province[province].append(
                    {**base_row, "province": province, "isPrimary": province == primary}
                )

    for entity_ref, entity in entities_by_ref.items():
        if entity_ref in primary_refs:
            continue
        geo_ref = str(entity.get("geoTagRef") or "")
        province = _coverage_province(geo_ref)
        primary_refs.add(entity_ref)
        homepage_count += int(bool(entity.get("hasPage")))
        parts = entity_ref.split("/")
        rows_by_province[province].append(
            {
                "entityRef": entity_ref,
                "canonicalName": parts[-1],
                "entityType": "/".join(parts[:2]),
                "geoTagRef": geo_ref,
                "masterListed": False,
                "hasHomepage": bool(entity.get("hasPage")),
                "promotedAt": str(entity.get("promotedAt") or ""),
                "envImports": env_cells(entity_ref),
                "province": province,
                "isPrimary": True,
            }
        )
    summary = {
        "entities": len(primary_refs),
        "entitiesWithHomepage": homepage_count,
        "rows": sum(len(rows) for rows in rows_by_province.values()),
        "provinces": len(rows_by_province),
    }
    return dict(rows_by_province), summary


def _index_hash(files: Iterable[Path], root: Path) -> str:
    digest = hashlib.sha256(b"quwoquan-release-index\0")
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def build_publish_lookup_indexes(
    *,
    release_id: str,
    canonical_root: Path | None = None,
    release_root: Path | None = None,
    taxonomy_root: Path | None = None,
) -> dict[str, Any]:
    """只写 release/{releaseId}/index；存在即逐字节验证，不覆盖。"""
    if not release_id:
        raise ValueError("release_id required；禁止写 publish/index")
    canonical = canonical_root or PUBLISH_ROOT
    release = (release_root or RELEASE_ROOT) / release_id
    desired = payload_file(release, "desired_state.json")
    if not desired.is_file():
        raise FileNotFoundError(f"release desired_state 不存在：{desired}")
    target = payload_file(release, "index/lookups")
    entities = _scan_entities(canonical)
    posts = _scan_posts(canonical)
    tag_links = _tag_links(taxonomy_root or CONTROL_PLANE_TAXONOMY_ROOT, entities, posts)
    coverage_rows, coverage_summary = _coverage_rows(
        canonical,
        entities,
        release_root or RELEASE_ROOT,
    )
    payloads = {
        "entities.ndjson": b"".join(_json_bytes(row) for row in entities),
        "posts.ndjson": b"".join(_json_bytes(row) for row in posts),
        "tag_link_targets.ndjson": b"".join(_json_bytes(row) for row in tag_links),
        **{
            f"coverage/{province}.ndjson": b"".join(
                _json_bytes(row) for row in sorted(rows, key=lambda item: item["entityRef"])
            )
            for province, rows in sorted(coverage_rows.items())
        },
    }
    if target.exists():
        for name, expected in payloads.items():
            path = target / name
            if not path.is_file() or path.read_bytes() != expected:
                raise FileExistsError(f"immutable release index conflict: {path}")
    else:
        for name, payload in payloads.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    files = [target / name for name in payloads]
    result = {
        "releaseId": release_id,
        "entities": len(entities),
        "posts": len(posts),
        "tagLinkTargets": len(tag_links),
        "coverageRows": coverage_summary["rows"],
        "coverageEntities": coverage_summary["entities"],
        "indexHash": _index_hash(files, release),
    }
    manifest = target / "manifest.json"
    expected_manifest = _json_bytes(
        {
            "schema": "quwoquan_data.release_lookup_index",
            **result,
            "coverage": coverage_summary,
        }
    )
    if manifest.exists() and manifest.read_bytes() != expected_manifest:
        raise FileExistsError(f"immutable release index manifest conflict: {manifest}")
    if not manifest.exists():
        manifest.write_bytes(expected_manifest)
    return result
