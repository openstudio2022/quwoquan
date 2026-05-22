"""Build lookup indexes from publish/v1 entities and posts.

The index layer keeps `_entity.json` as the fact source while exposing
compact NDJSON shards for search and reverse lookup.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import NOW_ISO, PUBLISH_ROOT  # noqa: E402

V1_ROOT = PUBLISH_ROOT / "v1"
INDEX_ROOT = V1_ROOT / "index"
ENTITY_INDEX_ROOT = INDEX_ROOT / "entities"
POST_INDEX_ROOT = INDEX_ROOT / "posts"


def safe_slug(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "unknown"
    return value.replace("/", "_").replace("\\", "_").replace(" ", "_")


def normalize_entity_ref(raw_ref: str) -> str:
    """Normalize `/entity/a/b/c` and `a/b/c` to `a/b/c`."""
    raw_ref = (raw_ref or "").strip()
    if not raw_ref:
        return ""
    parts = raw_ref.strip("/").split("/")
    if not parts or parts == [""]:
        return ""
    if parts[0] == "entity" and len(parts) >= 4:
        return "/".join(parts[1:])
    if len(parts) >= 3:
        return "/".join(parts[:3])
    return "/".join(parts)


def parse_entity_ref(raw_ref: str) -> tuple[str, str, str]:
    ref = normalize_entity_ref(raw_ref)
    parts = ref.split("/")
    if len(parts) < 3:
        return "", "", ref
    domain, etype = parts[0], parts[1]
    name = "/".join(parts[2:])
    return domain, etype, name


def parse_post_path(rel_parts: tuple[str, ...]) -> tuple[str, str, str, str]:
    """Parse `posts/{contentType}/{angle}/...` and `posts/{contentType}/内容角度/{angle}/...`."""
    if not rel_parts:
        return "", "", "", ""
    content_type = rel_parts[0]
    if len(rel_parts) >= 5 and rel_parts[1] == "内容角度":
        angle = rel_parts[2]
        title = rel_parts[3]
        seq = rel_parts[4]
    elif len(rel_parts) >= 4:
        angle = rel_parts[1]
        title = rel_parts[2]
        seq = rel_parts[3]
    else:
        angle = rel_parts[1] if len(rel_parts) > 1 else ""
        title = rel_parts[2] if len(rel_parts) > 2 else ""
        seq = rel_parts[3] if len(rel_parts) > 3 else ""
    return content_type, angle, title, seq


def geo_fanout(geo_ref: str) -> str:
    prefix = "Topic/地理/行政区/"
    if not geo_ref.startswith(prefix):
        return "unknown"
    path = geo_ref[len(prefix):].strip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        return safe_slug(parts[1])
    if parts:
        return safe_slug(parts[0])
    return "unknown"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_ndjson(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clear_index_root() -> None:
    if INDEX_ROOT.exists():
        shutil.rmtree(INDEX_ROOT)
    ENTITY_INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    POST_INDEX_ROOT.mkdir(parents=True, exist_ok=True)


def build_entity_index() -> tuple[int, list[Path]]:
    records_by_file: dict[str, list[dict]] = defaultdict(list)
    entity_lookup: dict[str, dict] = {}
    entity_count = 0

    for entity_file in sorted(V1_ROOT.rglob("_entity.json")):
        if "entities" not in entity_file.parts:
            continue
        rel = entity_file.parent.relative_to(V1_ROOT)
        parts = rel.parts
        if len(parts) < 4 or parts[0] != "entities":
            continue
        domain, etype, name = parts[1], parts[2], parts[3]
        data = read_json(entity_file)
        entity_ref = f"{domain}/{etype}/{name}"
        geo_ref = data.get("geoTagRef", "")
        aliases = data.get("aliases", [])
        fanout = geo_fanout(geo_ref)
        record = {
            "entityRef": entity_ref,
            "entityPath": f"entities/{entity_ref}",
            "domain": domain,
            "etype": etype,
            "name": name,
            "label": data.get("label", name),
            "aliases": aliases,
            "geoTagRef": geo_ref,
            "geoFanout": fanout,
            "tagRefs": data.get("tagRefs", []),
            "tagCount": len(data.get("tagRefs", [])),
            "sourceRef": data.get("sourceRef", ""),
            "updatedAt": data.get("updatedAt", NOW_ISO),
        }
        records_by_file[f"{safe_slug(domain)}__{safe_slug(etype)}__{fanout}.ndjson"].append(record)
        entity_lookup[entity_ref] = record
        entity_lookup[f"/entity/{entity_ref}"] = record
        entity_lookup[record["entityPath"]] = record
        entity_count += 1

    written_files: list[Path] = []
    for file_name, records in sorted(records_by_file.items()):
        out_path = ENTITY_INDEX_ROOT / file_name
        write_ndjson(out_path, sorted(records, key=lambda r: (r["name"], r["entityRef"])))
        written_files.append(out_path)

    # return entity count and preserve lookup in module global for posts
    globals()["_ENTITY_LOOKUP"] = entity_lookup
    return entity_count, written_files


def build_post_index(entity_lookup: dict[str, dict]) -> tuple[int, list[Path]]:
    records_by_file: dict[str, list[dict]] = defaultdict(list)
    post_count = 0

    for manifest in sorted(V1_ROOT.rglob("manifest.json")):
        if "entities" in manifest.parts or "index" in manifest.parts:
            continue
        if "posts" not in manifest.parts:
            continue
        data = read_json(manifest)
        rel = manifest.parent.relative_to(V1_ROOT)
        parts = rel.parts
        if not parts or parts[0] != "posts":
            continue
        content_type, angle, title, seq = parse_post_path(parts[1:])
        post_ref = str(rel)
        raw_entity_ref = data.get("entityRefs", [""])[0] if data.get("entityRefs") else ""
        entity_ref = normalize_entity_ref(raw_entity_ref)
        entity_meta = entity_lookup.get(entity_ref, {})
        geo_ref = entity_meta.get("geoTagRef", "")
        fanout = geo_fanout(geo_ref)
        entity_domain, entity_type, entity_name = parse_entity_ref(entity_ref)
        record = {
            "postRef": post_ref,
            "postPath": post_ref,
            "contentType": content_type,
            "angle": angle,
            "title": title,
            "seq": seq,
            "entityRef": entity_ref,
            "entityDomain": entity_domain,
            "entityType": entity_type,
            "entityName": entity_name,
            "entityGeoTagRef": geo_ref,
            "tagRefs": data.get("tagRefs", []),
            "tagCount": len(data.get("tagRefs", [])),
            "updatedAt": data.get("updatedAt", NOW_ISO),
        }
        records_by_file[f"{safe_slug(content_type)}__{safe_slug(angle)}__{fanout}.ndjson"].append(record)
        post_count += 1

    written_files: list[Path] = []
    for file_name, records in sorted(records_by_file.items()):
        out_path = POST_INDEX_ROOT / file_name
        write_ndjson(out_path, sorted(records, key=lambda r: (r["contentType"], r["angle"], r["title"], r["seq"])))
        written_files.append(out_path)

    return post_count, written_files


def build_publish_lookup_indexes() -> dict[str, int]:
    clear_index_root()
    entity_count, entity_files = build_entity_index()
    entity_lookup: dict[str, dict] = globals().get("_ENTITY_LOOKUP", {})
    post_count, post_files = build_post_index(entity_lookup)
    write_json(
        INDEX_ROOT / "_manifest.json",
        {
            "schemaVersion": "quwoquan.publish.lookup_index_manifest",
            "entities": {
                "count": entity_count,
                "files": [str(p.relative_to(V1_ROOT)) for p in entity_files],
            },
            "posts": {
                "count": post_count,
                "files": [str(p.relative_to(V1_ROOT)) for p in post_files],
            },
            "updatedAt": NOW_ISO,
        },
    )
    return {"entities": entity_count, "posts": post_count}


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 publish/v1 实体与 post lookup 索引")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        entity_count = 0
        post_count = 0
        for entity_file in sorted(V1_ROOT.rglob("_entity.json")):
            if "entities" in entity_file.parts:
                entity_count += 1
        for manifest in sorted(V1_ROOT.rglob("manifest.json")):
            if "entities" not in manifest.parts and "index" not in manifest.parts and "posts" in manifest.parts:
                post_count += 1
        print(f"[dry-run] entities={entity_count}, posts={post_count}")
        return
    counts = build_publish_lookup_indexes()
    print(f"索引已生成：entities={counts['entities']}, posts={counts['posts']}")


if __name__ == "__main__":
    main()
