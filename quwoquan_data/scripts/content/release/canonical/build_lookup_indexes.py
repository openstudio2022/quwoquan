#!/usr/bin/env python3
"""Deterministically build immutable release lookup indexes."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.paths import CONTROL_PLANE_TAXONOMY_ROOT, PUBLISH_ROOT, RELEASE_ROOT
from core.release_layout import attestation_root, payload_file
from core.schema import assert_valid
from governance.coverage import master_list as coverage_master_list


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON top level must be an object: {path}")
    return value


def _safe_release_id(value: str) -> str:
    text = str(value or "").strip()
    if not text or text in {".", ".."} or "/" in text or "\\" in text:
        raise ValueError(f"release_id is unsafe: {value!r}")
    return text


def _safe_ref(value: object, *, label: str, kind: str = "") -> str:
    text = str(value or "").strip()
    prefix = f"{kind}/" if kind else ""
    if prefix and text.startswith(prefix):
        text = text.removeprefix(prefix)
    relative = Path(text)
    if (
        not text
        or "\\" in text
        or relative.is_absolute()
        or ".." in relative.parts
        or any(part in {"", "."} for part in relative.parts)
    ):
        raise ValueError(f"{label} contains an unsafe path: {value!r}")
    return relative.as_posix()


def _desired_refs(
    desired: Mapping[str, Any],
    *,
    release_id: str,
) -> dict[str, tuple[str, ...]]:
    assert_valid(
        dict(desired),
        "release",
        "release_desired_state",
        label=f"release lookup desired state:{release_id}",
    )
    if str(desired.get("releaseId") or "") != release_id:
        raise ValueError("desired_state releaseId does not match release_id")
    raw_refs = desired.get("desiredRefs")
    if not isinstance(raw_refs, Mapping):
        raise ValueError("desiredRefs must be an object")
    result: dict[str, tuple[str, ...]] = {}
    for kind in ("entities", "posts", "creators", "tags"):
        values = raw_refs.get(kind)
        if not isinstance(values, list):
            raise ValueError(f"desiredRefs.{kind} must be an array")
        normalized = tuple(
            sorted(
                {
                    _safe_ref(
                        value,
                        label=f"desiredRefs.{kind}",
                        kind=kind if kind in {"entities", "posts", "creators", "tags"} else "",
                    )
                    for value in values
                }
            )
        )
        if len(normalized) != len(values):
            raise ValueError(f"desiredRefs.{kind} contains duplicate normalized refs")
        result[kind] = normalized
    return result


def _object_directory(base: Path, ref: str, *, label: str) -> Path:
    directory = base / ref
    try:
        directory.resolve().relative_to(base.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes its snapshot root: {ref}") from exc
    if directory.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {ref}")
    return directory


def _object_file(directory: Path, relative_path: object, *, label: str) -> Path:
    relative = _safe_ref(relative_path, label=label)
    path = directory / relative
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes its object snapshot") from exc
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    return path


def _assert_within_root(path: Path, root: Path, *, label: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes its root: {path}") from exc


def _string_refs(path: Path, key: str) -> list[str]:
    if not path.is_file():
        return []
    return sorted(
        {
            str(value)
            for value in (_read_json(path).get(key) or [])
            if str(value).strip()
        }
    )


def _scan_entities(
    canonical: Path,
    refs: Sequence[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base = canonical / "entities"
    for ref in refs:
        directory = _object_directory(
            base,
            ref,
            label="desiredRefs.entities",
        )
        path = _object_file(
            directory,
            "_entity.json",
            label=f"entity snapshot {ref}",
        )
        if not path.is_file():
            raise FileNotFoundError(f"release entity snapshot missing: {path}")
        document = _read_json(path)
        manifest_path = _object_file(
            directory,
            "manifest.json",
            label=f"entity snapshot {ref}.manifest",
        )
        manifest = (
            _read_json(manifest_path)
            if manifest_path.is_file()
            else {}
        )
        tag_refs = document.get("tagRefs") or _string_refs(
            directory / "tag.refs.json",
            "tagRefs",
        )
        geo_refs = document.get("geoTagRefs") or []
        primary_geo_ref = str(document.get("geoTagRef") or "")
        if primary_geo_ref and primary_geo_ref not in geo_refs:
            geo_refs = [primary_geo_ref, *geo_refs]
        rows.append(
            {
                "entityRef": ref,
                "label": document.get("label") or directory.name,
                "domain": document.get("domain"),
                "etype": document.get("type"),
                "tagRefs": sorted({str(ref) for ref in tag_refs}),
                "geoTagRef": primary_geo_ref,
                "geoTagRefs": sorted({str(ref) for ref in geo_refs if str(ref)}),
                "hasPage": (directory / "page.md").is_file(),
                "promotedAt": str(
                    (manifest.get("quality") or {}).get("promotedAt") or ""
                ),
            }
        )
    return rows


def _scan_posts(
    canonical: Path,
    refs: Sequence[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base = canonical / "posts"
    for ref in refs:
        directory = _object_directory(
            base,
            ref,
            label="desiredRefs.posts",
        )
        path = _object_file(
            directory,
            "manifest.json",
            label=f"post snapshot {ref}",
        )
        if not path.is_file():
            raise FileNotFoundError(f"release post snapshot missing: {path}")
        document = _read_json(path)
        tag_refs = document.get("tagRefs") or _string_refs(
            _object_file(
                directory,
                document.get("tagRefsRef") or "tag.refs.json",
                label=f"post snapshot {ref}.tagRefsRef",
            ),
            "tagRefs",
        )
        entity_refs = document.get("entityRefs") or _string_refs(
            _object_file(
                directory,
                document.get("entityRefsRef") or "entity.refs.json",
                label=f"post snapshot {ref}.entityRefsRef",
            ),
            "entityRefs",
        )
        rows.append(
            {
                "postRef": f"posts/{ref}",
                "contentType": document.get("contentType"),
                "title": document.get("publishTitle") or document.get("title"),
                "tagRefs": sorted({str(ref) for ref in tag_refs}),
                "entityRefs": sorted({str(ref) for ref in entity_refs}),
            }
        )
    return rows


def _tag_links(
    taxonomy_root: Path,
    refs: Sequence[str],
    entities: list[dict[str, Any]],
    posts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, int]] = {}
    homepage_entities: dict[str, list[str]] = defaultdict(list)
    for row, kind in [
        *((row, "entity") for row in entities),
        *((row, "post") for row in posts),
    ]:
        for ref in row.get("tagRefs") or []:
            entry = counts.setdefault(str(ref), {"entities": 0, "posts": 0})
            entry["entities" if kind == "entity" else "posts"] += 1
            if kind == "entity" and row.get("hasPage"):
                homepage_entities[str(ref)].append(str(row["entityRef"]))

    rows: list[dict[str, Any]] = []
    for ref in refs:
        directory = _object_directory(
            taxonomy_root,
            ref,
            label="desiredRefs.tags",
        )
        definition = _object_file(
            directory,
            "_definition.json",
            label=f"taxonomy snapshot {ref}",
        )
        if not definition.is_file():
            raise FileNotFoundError(f"release taxonomy snapshot missing: {definition}")
        candidates = sorted(set(homepage_entities.get(ref) or []))
        row: dict[str, Any] = {
            "tagRef": ref,
            "counts": counts.get(ref, {"entities": 0, "posts": 0}),
        }
        if (directory / "page.md").is_file():
            row["targetKind"] = "landing"
        elif len(candidates) == 1:
            row.update(
                {
                    "targetKind": "homepage",
                    "routePath": "/homepages/{id}",
                    "homepageEntityRef": candidates[0],
                }
            )
        elif sum(row["counts"].values()) > 0:
            row["targetKind"] = "search"
        else:
            row["targetKind"] = "none"
        rows.append(row)
    return rows


def _province(geo_ref: str) -> str:
    parts = str(geo_ref).split("/")
    return parts[4] if len(parts) > 4 else ""


def _coverage_rows(
    entities: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    entities_by_ref = {str(row["entityRef"]): row for row in entities}
    rows: list[dict[str, Any]] = []
    master_refs: set[str] = set()
    for path in coverage_master_list.master_list_files():
        document = coverage_master_list.load_master_list_file(path)
        province = str(document.get("province") or path.parent.name)
        for _district, leaf in coverage_master_list.iter_master_leaves(document):
            entity_ref = (
                f"{str(leaf.get('entityType') or '').strip('/')}/"
                f"{str(leaf.get('canonicalName') or leaf.get('name') or '')}"
            )
            master_refs.add(entity_ref)
            primary_geo_ref = str(leaf.get("geoTagRef") or "")
            geo_refs = [
                str(ref)
                for ref in (leaf.get("geoTagRefs") or [primary_geo_ref])
                if str(ref)
            ]
            if primary_geo_ref and primary_geo_ref not in geo_refs:
                geo_refs.insert(0, primary_geo_ref)
            for geo_ref in geo_refs:
                row = entities_by_ref.get(entity_ref) or {}
                rows.append(
                    {
                        "entityRef": entity_ref,
                        "canonicalName": str(
                            leaf.get("canonicalName") or leaf.get("name") or ""
                        ),
                        "entityType": str(leaf.get("entityType") or ""),
                        "geoTagRef": geo_ref,
                        "province": _province(geo_ref) or province,
                        "hasHomepage": bool(row.get("hasPage")),
                        "promotedAt": str(row.get("promotedAt") or ""),
                        "masterListed": True,
                        "isPrimary": geo_ref == primary_geo_ref,
                    }
                )
    for entity_ref, entity in sorted(entities_by_ref.items()):
        if entity_ref in master_refs:
            continue
        geo_ref = str(entity.get("geoTagRef") or "")
        rows.append(
            {
                "entityRef": entity_ref,
                "canonicalName": str(entity.get("label") or ""),
                "entityType": "/".join(
                    filter(None, (entity.get("domain"), entity.get("etype")))
                ),
                "geoTagRef": geo_ref,
                "province": _province(geo_ref),
                "hasHomepage": bool(entity.get("hasPage")),
                "promotedAt": str(entity.get("promotedAt") or ""),
                "masterListed": False,
                "isPrimary": True,
            }
        )
    shards: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["province"]:
            shards[str(row["province"])].append(row)
    primary = [row for row in rows if row["isPrimary"]]
    return (
        {key: value for key, value in sorted(shards.items())},
        {
            "rows": len(rows),
            "entities": len({str(row["entityRef"]) for row in primary}),
            "entitiesWithHomepage": len(
                {
                    str(row["entityRef"])
                    for row in primary
                    if row["hasHomepage"]
                }
            ),
        },
    )


def _index_hash(files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, payload in sorted(files.items()):
        relative = f"payload/index/lookups/{name}".encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return f"sha256:{digest.hexdigest()}"


def _verify_create_once_tree(
    target: Path,
    expected: Mapping[str, bytes],
) -> None:
    if not target.is_dir() or target.is_symlink():
        raise FileExistsError(f"immutable release index conflict: {target}")
    actual: dict[str, bytes] = {}
    allowed_directories = {
        parent.as_posix()
        for name in expected
        for parent in Path(name).parents
        if parent != Path(".")
    }
    for path in sorted(target.rglob("*")):
        relative = path.relative_to(target).as_posix()
        if path.is_symlink():
            raise FileExistsError(f"immutable release index conflict: {path}")
        if path.is_dir():
            if relative not in allowed_directories:
                raise FileExistsError(f"immutable release index conflict: {path}")
            continue
        if not path.is_file():
            raise FileExistsError(f"immutable release index conflict: {path}")
        actual[relative] = path.read_bytes()
    if set(actual) != set(expected):
        raise FileExistsError(f"immutable release index conflict: {target}")
    for name, payload in expected.items():
        if actual[name] != payload:
            raise FileExistsError(f"immutable release index conflict: {target / name}")


def _write_create_once_tree(
    target: Path,
    expected: Mapping[str, bytes],
) -> None:
    if target.exists():
        _verify_create_once_tree(target, expected)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{target.name}.",
            dir=target.parent,
        )
    )
    try:
        for name, payload in sorted(expected.items()):
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        try:
            os.rename(temporary, target)
        except OSError:
            if not target.exists():
                raise
            _verify_create_once_tree(target, expected)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def build_publish_lookup_indexes(
    *,
    release_id: str,
    canonical_root: Path | None = None,
    release_root: Path | None = None,
    taxonomy_root: Path | None = None,
) -> dict[str, Any]:
    """Write release lookup indexes once, then verify byte identity."""
    release_id = _safe_release_id(release_id)
    canonical = canonical_root or PUBLISH_ROOT
    release_base = release_root or RELEASE_ROOT
    release = release_base / release_id
    _assert_within_root(
        release,
        release_base,
        label="release_id",
    )
    if release.is_symlink():
        raise ValueError("release root must not be a symlink")
    desired = payload_file(release, "desired_state.json")
    _assert_within_root(
        desired,
        release,
        label="release desired_state",
    )
    if desired.is_symlink():
        raise ValueError("release desired_state must not be a symlink")
    if not desired.is_file():
        raise FileNotFoundError(f"release desired_state missing: {desired}")

    desired_refs = _desired_refs(
        _read_json(desired),
        release_id=release_id,
    )
    target = payload_file(release, "index/lookups")
    _assert_within_root(
        target,
        release,
        label="release lookup target",
    )
    release_attestation = attestation_root(release) / "release.json"
    _assert_within_root(
        release_attestation,
        release,
        label="release attestation",
    )
    if release_attestation.exists() and not target.exists():
        raise ValueError(
            "attested release is immutable; build lookup indexes before attestation"
        )
    entities = _scan_entities(canonical, desired_refs["entities"])
    posts = _scan_posts(canonical, desired_refs["posts"])
    used_tag_refs = {
        str(ref)
        for row in [*entities, *posts]
        for ref in row.get("tagRefs") or []
    }
    missing_tag_refs = sorted(used_tag_refs - set(desired_refs["tags"]))
    if missing_tag_refs:
        raise ValueError(
            "desiredRefs.tags does not close entity/post tagRefs: "
            + ", ".join(missing_tag_refs)
        )
    tag_links = _tag_links(
        taxonomy_root or CONTROL_PLANE_TAXONOMY_ROOT,
        desired_refs["tags"],
        entities,
        posts,
    )
    coverage, coverage_summary = _coverage_rows(
        entities,
    )
    payloads = {
        "entities.ndjson": b"".join(_json_bytes(row) for row in entities),
        "posts.ndjson": b"".join(_json_bytes(row) for row in posts),
        "tag_link_targets.ndjson": b"".join(
            _json_bytes(row) for row in tag_links
        ),
        **{
            f"coverage/{province}.ndjson": b"".join(
                _json_bytes(row)
                for row in sorted(rows, key=lambda item: item["entityRef"])
            )
            for province, rows in coverage.items()
        },
    }
    result = {
        "releaseId": release_id,
        "entities": len(entities),
        "posts": len(posts),
        "tagLinkTargets": len(tag_links),
        "coverageRows": coverage_summary["rows"],
        "coverageEntities": coverage_summary["entities"],
        "indexHash": _index_hash(payloads),
    }
    expected_manifest = _json_bytes(
        {
            "schema": "quwoquan_data.release_lookup_index",
            **result,
            "coverage": coverage_summary,
        }
    )
    manifest_document = json.loads(expected_manifest)
    assert_valid(
        manifest_document,
        "release",
        "release_lookup_index",
        label=f"release lookup index:{release_id}",
    )
    _write_create_once_tree(
        target,
        {**payloads, "manifest.json": expected_manifest},
    )
    return result
