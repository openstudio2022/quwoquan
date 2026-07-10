"""Build lookup indexes from the single publish mainline (entities and posts).

The index layer keeps `_entity.json` as the fact source while exposing
compact NDJSON shards for search and reverse lookup.
"""
from __future__ import annotations


import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import NOW_ISO, PUBLISH_ROOT, REPO_ROOT  # noqa: E402

PUBLISH_MAINLINE = PUBLISH_ROOT
INDEX_ROOT = PUBLISH_MAINLINE / "index"
ENTITY_INDEX_ROOT = INDEX_ROOT / "entities"
POST_INDEX_ROOT = INDEX_ROOT / "posts"
LINK_TARGET_ROOT = INDEX_ROOT / "link_targets"
COVERAGE_INDEX_ROOT = INDEX_ROOT / "coverage"

# metadata-first：introduction API path 与实体主页 route 均从契约读取，禁止硬编码。
HOMEPAGE_SERVICE_YAML = (
    REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "entity" / "homepage" / "service.yaml"
)
UI_SURFACES_YAML = (
    REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "ui_surfaces.yaml"
)
ENV_TOPOLOGY_MANIFEST = REPO_ROOT / "quwoquan_ops" / "environments" / "environment_topology_manifest.yaml"
COVERAGE_ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")


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
    LINK_TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    COVERAGE_INDEX_ROOT.mkdir(parents=True, exist_ok=True)


# ─── metadata / topology 契约读取（path 与 URL base 唯一真相源） ───────────
def introduction_path_template() -> str:
    """GetHomepageIntroduction API path 模板（唯一真相源 service.yaml）。"""
    doc = yaml.safe_load(HOMEPAGE_SERVICE_YAML.read_text(encoding="utf-8"))
    for route in doc.get("api_routes") or []:
        if route.get("operation") == "GetHomepageIntroduction":
            return str(route.get("path") or "")
    raise ValueError(f"{HOMEPAGE_SERVICE_YAML} 缺 GetHomepageIntroduction 路由")


def homepage_detail_route_template() -> str:
    """实体主页 App route path 模板（唯一真相源 ui_surfaces.yaml homepageDetail）。"""
    doc = yaml.safe_load(UI_SURFACES_YAML.read_text(encoding="utf-8"))
    for surface in doc.get("surfaces") or []:
        if surface.get("route_id") == "homepageDetail":
            return str(surface.get("path_template") or "")
    raise ValueError(f"{UI_SURFACES_YAML} 缺 homepageDetail surface")


def environment_api_bases() -> dict[str, str]:
    """四环境 API base（唯一真相源 environment_topology_manifest.yaml publicBases.api）。"""
    doc = yaml.safe_load(ENV_TOPOLOGY_MANIFEST.read_text(encoding="utf-8"))
    bases: dict[str, str] = {}
    for env in COVERAGE_ENVIRONMENTS:
        node = ((doc.get("environments") or {}).get(env) or {}).get("publicBases") or {}
        base = str(node.get("api") or "").strip().rstrip("/")
        if base:
            bases[env] = base
    return bases


def build_entity_index() -> tuple[int, list[Path]]:
    records_by_file: dict[str, list[dict]] = defaultdict(list)
    entity_lookup: dict[str, dict] = {}
    entity_count = 0

    for entity_file in sorted(PUBLISH_MAINLINE.rglob("_entity.json")):
        if "entities" not in entity_file.parts:
            continue
        rel = entity_file.parent.relative_to(PUBLISH_MAINLINE)
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
            "sourceTaskId": data.get("sourceTaskId"),
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

    for manifest in sorted(PUBLISH_MAINLINE.rglob("manifest.json")):
        if "entities" in manifest.parts or "index" in manifest.parts:
            continue
        if "posts" not in manifest.parts:
            continue
        data = read_json(manifest)
        rel = manifest.parent.relative_to(PUBLISH_MAINLINE)
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
            "sourceTaskId": data.get("sourceTaskId"),
            "sourceBatchId": data.get("sourceBatchId"),
            "createdAt": data.get("createdAt", ""),
            "updatedAt": data.get("updatedAt", ""),
            "publishedAt": data.get("publishedAt", ""),
        }
        records_by_file[f"{safe_slug(content_type)}__{safe_slug(angle)}__{fanout}.ndjson"].append(record)
        post_count += 1

    written_files: list[Path] = []
    for file_name, records in sorted(records_by_file.items()):
        out_path = POST_INDEX_ROOT / file_name
        write_ndjson(out_path, sorted(records, key=lambda r: (r["contentType"], r["angle"], r["title"], r["seq"])))
        written_files.append(out_path)

    return post_count, written_files


def _tag_counts_from_publish() -> tuple[dict[str, int], dict[str, int]]:
    """Return tagRef -> post/entity counts without making tag definitions a UI truth source."""
    post_counts: dict[str, int] = defaultdict(int)
    entity_counts: dict[str, int] = defaultdict(int)
    for manifest in sorted(PUBLISH_MAINLINE.rglob("manifest.json")):
        if "entities" in manifest.parts or "index" in manifest.parts or "posts" not in manifest.parts:
            continue
        try:
            data = read_json(manifest)
        except Exception:  # noqa: BLE001
            continue
        for tag_ref in data.get("tagRefs") or []:
            if isinstance(tag_ref, str) and tag_ref.strip():
                post_counts[tag_ref.strip()] += 1
    for entity_file in sorted(PUBLISH_MAINLINE.rglob("_entity.json")):
        if "entities" not in entity_file.parts or "index" in entity_file.parts:
            continue
        try:
            data = read_json(entity_file)
        except Exception:  # noqa: BLE001
            continue
        for tag_ref in data.get("tagRefs") or []:
            if isinstance(tag_ref, str) and tag_ref.strip():
                entity_counts[tag_ref.strip()] += 1
    return dict(post_counts), dict(entity_counts)


def _tag_entity_refs_from_publish() -> dict[str, list[str]]:
    """tagRef -> 打了该标签的 publish 实体 ref 列表（保序去重）。"""
    refs_by_tag: dict[str, list[str]] = defaultdict(list)
    for entity_file in sorted(PUBLISH_MAINLINE.rglob("_entity.json")):
        if "entities" not in entity_file.parts or "index" in entity_file.parts:
            continue
        rel = entity_file.parent.relative_to(PUBLISH_MAINLINE)
        if len(rel.parts) < 4 or rel.parts[0] != "entities":
            continue
        entity_ref = "/".join(rel.parts[1:4])
        data = read_json(entity_file)
        for tag_ref in data.get("tagRefs") or []:
            key = str(tag_ref).strip()
            if key and entity_ref not in refs_by_tag[key]:
                refs_by_tag[key].append(entity_ref)
    return dict(refs_by_tag)


def build_tag_link_target_index() -> tuple[int, list[Path]]:
    """Build derived tag link targets.

    Tag taxonomy (`publish/tags/**/_definition.json`) remains semantic-only. Whether
    a tag is clickable is derived from browsable targets: a tag landing page wins;
    a place tag uniquely identifying one published homepage binds the homepage
    route (WP4-2); otherwise a search landing is exposed only when there is
    content to browse.
    """
    tags_root = PUBLISH_MAINLINE / "tags"
    if not tags_root.is_dir():
        return 0, []
    post_counts, entity_counts = _tag_counts_from_publish()
    entity_refs_by_tag = _tag_entity_refs_from_publish()
    homepage_route = homepage_detail_route_template()
    records: list[dict] = []
    for definition in sorted(tags_root.rglob("_definition.json")):
        tag_ref = definition.parent.relative_to(tags_root).as_posix()
        try:
            data = read_json(definition)
        except Exception:  # noqa: BLE001
            data = {}
        landing_page = definition.parent / "page.md"
        post_count = post_counts.get(tag_ref, 0)
        entity_count = entity_counts.get(tag_ref, 0)
        # WP4-2：地点相关标签唯一命中一个有主页实体 → routePath 绑定实体主页路由
        # （entityRef 形态：{id} 占位由消费方经 entityRef→homepageId 映射换算）。
        tagged_refs = entity_refs_by_tag.get(tag_ref) or []
        homepage_refs = [
            ref for ref in tagged_refs
            if (PUBLISH_MAINLINE / "entities" / ref / "page.md").is_file()
        ]
        if landing_page.is_file():
            target_kind = "landing"
            route_path = f"/tag/{quote(tag_ref, safe='/')}"
        elif not post_count and len(homepage_refs) == 1:
            target_kind = "homepage"
            route_path = homepage_route
        elif post_count or entity_count:
            target_kind = "search"
            route_path = f"/search?tagRef={quote(tag_ref, safe='')}"
        else:
            target_kind = "none"
            route_path = ""
        record = {
            "tagRef": tag_ref,
            "label": data.get("label") or definition.parent.name,
            "targetKind": target_kind,
            "routePath": route_path,
            "hasHomepage": landing_page.is_file(),
            "postCount": post_count,
            "objectCount": entity_count,
        }
        if target_kind == "homepage":
            record["homepageEntityRef"] = homepage_refs[0]
        records.append(record)
    out_path = LINK_TARGET_ROOT / "tags.ndjson"
    write_ndjson(out_path, sorted(records, key=lambda r: r["tagRef"]))
    return len(records), [out_path]


# ─── WP4-1 覆盖账本（coverage 核对面；lookup 是检索面，职责分开） ─────────
def _latest_env_homepage_imports() -> dict[str, dict]:
    """各环境最新一次非 dry-run homepage 导入证据。

    返回 env -> {releaseId, finishedAt, entities, entityRefToHomepageId}；
    entities 来自同 release 目录 `{env}.json` 的 desiredRefs.entities（导入面），
    entityRefToHomepageId 来自 import-homepage 报告 v2 映射产物（v1 无映射为空）。
    """
    releases_root = PUBLISH_MAINLINE / "env_releases"
    latest: dict[str, dict] = {}
    if not releases_root.is_dir():
        return latest
    for release_dir in sorted(releases_root.iterdir()):
        if not release_dir.is_dir():
            continue
        for env in COVERAGE_ENVIRONMENTS:
            report_path = release_dir / f"import-homepage-{env}.json"
            if not report_path.is_file():
                continue
            report = read_json(report_path)
            if report.get("dryRun"):
                continue
            finished = str(report.get("finishedAt") or "")
            if env in latest and finished <= latest[env]["finishedAt"]:
                continue
            entities: set[str] = set()
            env_manifest = release_dir / f"{env}.json"
            if env_manifest.is_file():
                refs = (read_json(env_manifest).get("desiredRefs") or {}).get("entities") or []
                entities = {normalize_entity_ref(str(r)) for r in refs if str(r).strip()}
            latest[env] = {
                "releaseId": release_dir.name,
                "finishedAt": finished,
                "entities": entities,
                "entityRefToHomepageId": {
                    str(k): str(v)
                    for k, v in (report.get("entityRefToHomepageId") or {}).items()
                },
            }
    return latest


def _coverage_province(geo_ref: str) -> str:
    """geoTagRef -> 省级归属名（原名，非 slug；未命中行政区树前缀返回 unknown）。"""
    prefix = "Topic/地理/行政区/"
    if not geo_ref.startswith(prefix):
        return "unknown"
    parts = [p for p in geo_ref[len(prefix):].strip("/").split("/") if p]
    return parts[1] if len(parts) >= 2 else (parts[0] if parts else "unknown")


def _coverage_env_imports(
    entity_ref: str,
    env_imports: dict[str, dict],
    api_bases: dict[str, str],
    intro_path: str,
) -> dict[str, dict]:
    """每环境导入状态 + introductionUrl（entityRef 行形态：{homepageId} 有映射时展开）。"""
    out: dict[str, dict] = {}
    for env in COVERAGE_ENVIRONMENTS:
        info = env_imports.get(env)
        imported = bool(info and entity_ref in info["entities"])
        cell: dict = {"imported": imported}
        if imported:
            cell["releaseId"] = info["releaseId"]
            cell["importedAt"] = info["finishedAt"]
            base = api_bases.get(env, "")
            if base:
                homepage_id = info["entityRefToHomepageId"].get(entity_ref, "")
                path = intro_path.replace("{homepageId}", homepage_id) if homepage_id else intro_path
                cell["introductionUrl"] = f"{base}{path}"
        out[env] = cell
    return out


def build_coverage_index() -> tuple[int, list[Path], dict]:
    """覆盖账本 publish/index/coverage/{省}.ndjson（可重建核对面）。

    主清单目录（walk verticals/travel/coverage/中国/）是骨架；publish 主线给
    hasHomepage/promotedAt；env_releases 导入报告给各环境导入状态。跨省地点在
    主/次归属省分片均出现（isPrimary 标注），全国汇总按 primary 去重；publish
    有而主清单缺的实体补 masterListed=false 行（不留盲区）。
    """
    from _common.coverage_master_list import (
        iter_master_leaves,
        load_master_list_file,
        master_list_files,
    )

    env_imports = _latest_env_homepage_imports()
    api_bases = environment_api_bases()
    intro_path = introduction_path_template()

    records_by_province: dict[str, list[dict]] = defaultdict(list)
    primary_refs: set[str] = set()
    primary_with_homepage = 0

    for path in master_list_files():
        data = load_master_list_file(path)
        for _district, leaf in iter_master_leaves(data):
            canonical = str(leaf.get("canonicalName") or leaf.get("name") or "").strip()
            entity_type = str(leaf.get("entityType") or "").strip()
            geo_ref = str(leaf.get("geoTagRef") or "").strip()
            if not canonical or not entity_type:
                continue
            entity_ref = f"{entity_type}/{canonical}"
            entity_dir = PUBLISH_MAINLINE / "entities" / entity_ref
            has_homepage = (entity_dir / "page.md").is_file()
            promoted_at = ""
            manifest_path = entity_dir / "manifest.json"
            if manifest_path.is_file():
                quality = read_json(manifest_path).get("quality") or {}
                promoted_at = str(quality.get("promotedAt") or "")
            base_record = {
                "entityRef": entity_ref,
                "canonicalName": canonical,
                "entityType": entity_type,
                "geoTagRef": geo_ref,
                "sourceReadiness": str(leaf.get("sourceReadiness") or ""),
                "masterListed": True,
                "hasHomepage": has_homepage,
                "promotedAt": promoted_at,
                "envImports": _coverage_env_imports(entity_ref, env_imports, api_bases, intro_path),
            }
            if entity_ref not in primary_refs:
                primary_refs.add(entity_ref)
                if has_homepage:
                    primary_with_homepage += 1
            primary_province = _coverage_province(geo_ref)
            provinces = {primary_province}
            for extra_ref in leaf.get("geoTagRefs") or []:
                provinces.add(_coverage_province(str(extra_ref)))
            for province in sorted(provinces):
                records_by_province[province].append(
                    {**base_record, "province": province, "isPrimary": province == primary_province}
                )

    # publish 有而主清单缺的实体（历史/命名漂移）也进核对面，不留盲区。
    entities_root = PUBLISH_MAINLINE / "entities"
    if entities_root.is_dir():
        for entity_file in sorted(entities_root.rglob("_entity.json")):
            rel = entity_file.parent.relative_to(entities_root)
            if len(rel.parts) != 3:
                continue
            entity_ref = rel.as_posix()
            if entity_ref in primary_refs:
                continue
            data = read_json(entity_file)
            geo_ref = str(data.get("geoTagRef") or "")
            province = _coverage_province(geo_ref)
            has_homepage = (entity_file.parent / "page.md").is_file()
            promoted_at = ""
            manifest_path = entity_file.parent / "manifest.json"
            if manifest_path.is_file():
                quality = read_json(manifest_path).get("quality") or {}
                promoted_at = str(quality.get("promotedAt") or "")
            primary_refs.add(entity_ref)
            if has_homepage:
                primary_with_homepage += 1
            records_by_province[province].append(
                {
                    "entityRef": entity_ref,
                    "canonicalName": rel.parts[2],
                    "entityType": "/".join(rel.parts[:2]),
                    "geoTagRef": geo_ref,
                    "sourceReadiness": "",
                    "masterListed": False,
                    "hasHomepage": has_homepage,
                    "promotedAt": promoted_at,
                    "envImports": _coverage_env_imports(entity_ref, env_imports, api_bases, intro_path),
                    "province": province,
                    "isPrimary": True,
                }
            )

    written_files: list[Path] = []
    row_count = 0
    for province, records in sorted(records_by_province.items()):
        out_path = COVERAGE_INDEX_ROOT / f"{safe_slug(province)}.ndjson"
        write_ndjson(out_path, sorted(records, key=lambda r: r["entityRef"]))
        written_files.append(out_path)
        row_count += len(records)

    summary = {
        "entities": len(primary_refs),
        "entitiesWithHomepage": primary_with_homepage,
        "rows": row_count,
        "provinces": len(records_by_province),
    }
    return row_count, written_files, summary


def build_publish_lookup_indexes() -> dict[str, int]:
    clear_index_root()
    entity_count, entity_files = build_entity_index()
    entity_lookup: dict[str, dict] = globals().get("_ENTITY_LOOKUP", {})
    post_count, post_files = build_post_index(entity_lookup)
    tag_link_count, tag_link_files = build_tag_link_target_index()
    coverage_rows, coverage_files, coverage_summary = build_coverage_index()
    write_json(
        INDEX_ROOT / "_manifest.json",
        {
            "schemaVersion": "quwoquan.publish.lookup_index_manifest",
            "entities": {
                "count": entity_count,
                "files": [str(p.relative_to(PUBLISH_MAINLINE)) for p in entity_files],
            },
            "posts": {
                "count": post_count,
                "files": [str(p.relative_to(PUBLISH_MAINLINE)) for p in post_files],
            },
            "linkTargets": {
                "tags": {
                    "count": tag_link_count,
                    "files": [str(p.relative_to(PUBLISH_MAINLINE)) for p in tag_link_files],
                },
            },
            "coverage": {
                **coverage_summary,
                "files": [str(p.relative_to(PUBLISH_MAINLINE)) for p in coverage_files],
            },
            "updatedAt": NOW_ISO,
        },
    )
    return {
        "entities": entity_count,
        "posts": post_count,
        "tagLinkTargets": tag_link_count,
        "coverageRows": coverage_rows,
        "coverageEntities": coverage_summary["entities"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 publish 主线实体与 post lookup 索引")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        entity_count = 0
        post_count = 0
        for entity_file in sorted(PUBLISH_MAINLINE.rglob("_entity.json")):
            if "entities" in entity_file.parts:
                entity_count += 1
        for manifest in sorted(PUBLISH_MAINLINE.rglob("manifest.json")):
            if "entities" not in manifest.parts and "index" not in manifest.parts and "posts" in manifest.parts:
                post_count += 1
        print(f"[dry-run] entities={entity_count}, posts={post_count}")
        return
    counts = build_publish_lookup_indexes()
    print(f"索引已生成：entities={counts['entities']}, posts={counts['posts']}")


if __name__ == "__main__":
    main()
