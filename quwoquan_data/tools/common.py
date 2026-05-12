from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

DATA_ROOT = Path(
    os.getenv("QWQ_DATA_ROOT", Path(__file__).resolve().parents[1])
).resolve()
REPO_ROOT = Path(
    os.getenv("QWQ_REPO_ROOT", DATA_ROOT.parent)
).resolve()
RUNTIME_ROOT = Path(
    os.getenv("QWQ_RUNTIME_ROOT", DATA_ROOT / "runtime")
).resolve()
FIXTURE_ROOT = Path(
    os.getenv("QWQ_FIXTURE_ROOT", DATA_ROOT / "tests" / "fixtures")
).resolve()
RUNTIME_FIXTURE_SEED_ROOT = FIXTURE_ROOT / "runtime_seed"

SCHEMA_ROOT = DATA_ROOT / "schema"
CRAWL_SPEC_ROOT = RUNTIME_ROOT / "specs"
TREES_ROOT = RUNTIME_ROOT / "trees"
RUNS_ROOT = RUNTIME_ROOT / "runs"
PUBLISH_ROOT = RUNTIME_ROOT / "publish"
OUT_ROOT = RUNTIME_ROOT / "out"
DOWNLOADS_ROOT = RUNTIME_ROOT / "downloads"
SEED_ROOT = RUNTIME_ROOT / "seed"
ENTITY_CATALOG_ROOT = SEED_ROOT / "entity_catalog"
TAG_CATALOG_ROOT = SEED_ROOT / "tag_catalog"
GRAPH_ROOT = SEED_ROOT / "graph"
SOURCE_REGISTRY_PATH = SEED_ROOT / "source_registry.yaml"
SOURCE_DOWNLOADS_ROOT = DOWNLOADS_ROOT / "sources"
IMAGE_DOWNLOADS_ROOT = DOWNLOADS_ROOT / "images"

COMPAT_CRAWL_SPEC_ROOT = DATA_ROOT / "crawl_specs"
COMPAT_TREES_ROOT = DATA_ROOT / "trees"
COMPAT_RUNS_ROOT = DATA_ROOT / "runs"
COMPAT_PUBLISH_ROOT = DATA_ROOT / "publish"
COMPAT_OUT_ROOT = DATA_ROOT / "out"
COMPAT_BATCH_PLAN_ROOT = DATA_ROOT / "batch_plans"
COMPAT_RAW_ROOT = DATA_ROOT / "raw"
USER_POOL_PATH = (
    REPO_ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "_shared"
    / "test_fixtures"
    / "user_pool.json"
)

SUPPORTED_TARGETS = {"alpha", "beta", "gamma", "prod"}
SUPPORTED_CONTENT_TYPES = {"image", "article"}
SUPPORTED_SEARCH_PROVIDERS = {"cursor_commands", "native_fetch"}
DISCOVERY_SCHEMA_VERSION = "quwoquan_data.crawl_discovery"
COMPAT_DISCOVERY_SCHEMA_VERSIONS = {"quwoquan_data.crawl_discovery.v2"}
TOPIC_TASK_SCHEMA_VERSION = "quwoquan_data.topic_task"
COMPAT_TOPIC_TASK_SCHEMA_VERSIONS = {"quwoquan_data.topic_task.v2"}
TOPIC_ASSET_MANIFEST_SCHEMA_VERSION = "quwoquan_data.topic_asset_manifest"
COMPAT_TOPIC_ASSET_MANIFEST_SCHEMA_VERSIONS = {"quwoquan_data.topic_asset_manifest.v1"}
TOPIC_ENRICHMENT_SCHEMA_VERSION = "quwoquan_data.topic_enrichment"
COMPAT_TOPIC_ENRICHMENT_SCHEMA_VERSIONS = {"quwoquan_data.topic_enrichment.v1"}
PACKAGE_MANIFEST_SCHEMA_VERSION = "quwoquan_data.package_manifest"
COMPAT_PACKAGE_MANIFEST_SCHEMA_VERSIONS = {"2", 2}

# 其它 crawl 主线产物（写入侧统一从此处导出，避免字面量散落在各模块）
TOPIC_COMPOSE_SUMMARY_SCHEMA_VERSION = "quwoquan_data.compose_summary"
TOPIC_AUDIT_SUMMARY_SCHEMA_VERSION = "quwoquan_data.topic_audit_summary"
POST_REVIEW_SCHEMA_VERSION = "quwoquan_data.post_review"
CRAWL_PROJECTION_SCHEMA_VERSION = "quwoquan_data.crawl_projection"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_runtime_layout() -> None:
    for path in (
        RUNTIME_ROOT,
        CRAWL_SPEC_ROOT,
        TREES_ROOT,
        RUNS_ROOT,
        PUBLISH_ROOT,
        OUT_ROOT,
        SEED_ROOT,
        ENTITY_CATALOG_ROOT,
        TAG_CATALOG_ROOT,
        GRAPH_ROOT,
        DOWNLOADS_ROOT,
        SOURCE_DOWNLOADS_ROOT,
        IMAGE_DOWNLOADS_ROOT,
    ):
        ensure_directory(path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    ensure_directory(path.parent)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(read_text(path))


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_yaml(path: Path) -> Any:
    return yaml.safe_load(read_text(path))


def write_yaml(path: Path, payload: Any) -> None:
    write_text(path, yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in read_text(path).splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    body = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    if body:
        body += "\n"
    write_text(path, body)


def runtime_path(*parts: str) -> Path:
    return RUNTIME_ROOT.joinpath(*parts)


def runtime_rel_ref(path: Path) -> str:
    return path.resolve().relative_to(RUNTIME_ROOT).as_posix()


def ref_path(ref: str) -> Path:
    return runtime_path(*Path(ref).parts)


def ref_exists(ref: str) -> bool:
    return ref_path(ref).exists()


def rel_ref(path: Path) -> str:
    return runtime_rel_ref(path)


def list_yaml_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.yaml") if path.is_file())


def tree_files(tree_name: str) -> list[Path]:
    return list_yaml_files(TREES_ROOT / tree_name)


def _runtime_spec_candidate(spec_arg: str) -> Path:
    normalized = spec_arg.strip().replace("\\", "/")
    if normalized.endswith(".yaml") and "/" not in normalized:
        return CRAWL_SPEC_ROOT / normalized
    if normalized.endswith(".yaml"):
        for prefix in (
            "quwoquan_data/runtime/specs/",
            "runtime/specs/",
            "quwoquan_data/crawl_specs/",
            "crawl_specs/",
            "specs/",
        ):
            if normalized.startswith(prefix):
                return CRAWL_SPEC_ROOT / normalized[len(prefix) :]
        return CRAWL_SPEC_ROOT / Path(normalized).name
    return CRAWL_SPEC_ROOT / f"{normalized}.yaml"


def crawl_spec_path_from_arg(spec_arg: str) -> Path:
    path = Path(spec_arg)
    if path.is_absolute():
        return path
    repo_candidate = (REPO_ROOT / spec_arg).resolve()
    if repo_candidate.exists():
        return repo_candidate
    runtime_candidate = _runtime_spec_candidate(spec_arg)
    if runtime_candidate.exists():
        return runtime_candidate
    compat_candidate = COMPAT_CRAWL_SPEC_ROOT / Path(spec_arg).name
    if compat_candidate.exists():
        return compat_candidate
    return runtime_candidate


def spec_path_for_id(spec_id: str) -> Path:
    return CRAWL_SPEC_ROOT / f"{spec_id}.yaml"


def runs_spec_dir(spec_id: str) -> Path:
    return RUNS_ROOT / spec_id


def discovery_path(spec_id: str) -> Path:
    return runs_spec_dir(spec_id) / "discovery.json"


def topic_tasks_path(spec_id: str) -> Path:
    return runs_spec_dir(spec_id) / "topic_tasks.ndjson"


def run_topic_dir(spec_id: str, topic_id: str) -> Path:
    return runs_spec_dir(spec_id) / "topics" / topic_id


def run_topic_file(spec_id: str, topic_id: str, name: str) -> Path:
    return run_topic_dir(spec_id, topic_id) / name


def topic_pages_root(spec_id: str, topic_id: str) -> Path:
    return run_topic_dir(spec_id, topic_id) / "pages"


def topic_page_dir(spec_id: str, topic_id: str, source_id: str) -> Path:
    return topic_pages_root(spec_id, topic_id) / source_id


def download_topic_source_dir(spec_id: str, topic_id: str, source_id: str) -> Path:
    return SOURCE_DOWNLOADS_ROOT / spec_id / topic_id / source_id


def download_topic_image_dir(spec_id: str, topic_id: str, source_id: str) -> Path:
    return IMAGE_DOWNLOADS_ROOT / spec_id / topic_id / source_id


def publish_topic_dir(topic_id: str) -> Path:
    return PUBLISH_ROOT / topic_id


def out_topic_dir(topic_id: str) -> Path:
    return OUT_ROOT / topic_id


def load_user_pool() -> dict[str, dict[str, str]]:
    payload = read_json(USER_POOL_PATH)
    result: dict[str, dict[str, str]] = {}
    for item in payload.get("users", []):
        user_id = item.get("userId")
        if not user_id:
            continue
        result[user_id] = {
            "userId": user_id,
            "displayName": item.get("displayName") or item.get("nickname") or user_id,
            "avatarObjectKey": item.get("avatarObjectKey", ""),
            "backgroundObjectKey": item.get("backgroundObjectKey", ""),
        }
    return result


def tag_id_for_ref(ref: str) -> str:
    payload = read_yaml(ref_path(ref))
    return str(payload["tag_id"])


def entity_payload_for_ref(ref: str) -> dict[str, Any]:
    payload = dict(read_yaml(ref_path(ref)))
    payload.setdefault("entity_ref", ref)
    return payload


def content_template_for_ref(ref: str) -> dict[str, Any]:
    payload = dict(read_yaml(ref_path(ref)))
    payload.setdefault("content_ref", ref)
    return payload


def entity_name_for_ref(ref: str) -> str:
    return str(read_yaml(ref_path(ref)).get("name", Path(ref).stem))


def tag_label_for_ref(ref: str) -> str:
    return str(read_yaml(ref_path(ref)).get("label", Path(ref).stem))
