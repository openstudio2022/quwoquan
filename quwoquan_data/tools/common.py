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
SCHEMA_ROOT = DATA_ROOT / "schema"
TREES_ROOT = DATA_ROOT / "trees"
BATCH_PLAN_ROOT = DATA_ROOT / "batch_plans"
RAW_ROOT = DATA_ROOT / "raw"
PUBLISH_ROOT = DATA_ROOT / "publish"
OUT_ROOT = DATA_ROOT / "out"
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
SUPPORTED_SEARCH_PROVIDERS = {"cursor_commands"}
RETRIEVAL_PLAN_SCHEMA_VERSION = "quwoquan_data.retrieval_plan.v1"
BATCH_LOOP_STATE_SCHEMA_VERSION = "quwoquan_data.batch_loop_state.v1"
RAW_EVIDENCE_SCHEMA_VERSION = "quwoquan_data.raw_evidence.v1"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def ref_path(ref: str) -> Path:
    return DATA_ROOT / ref


def ref_exists(ref: str) -> bool:
    return ref_path(ref).exists()


def rel_ref(path: Path) -> str:
    return path.resolve().relative_to(DATA_ROOT).as_posix()


def list_yaml_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.yaml") if path.is_file())


def tree_files(tree_name: str) -> list[Path]:
    return list_yaml_files(TREES_ROOT / tree_name)


def batch_plan_path_from_arg(plan_arg: str) -> Path:
    path = Path(plan_arg)
    if path.is_absolute():
        return path
    return (REPO_ROOT / plan_arg).resolve()


def raw_batch_dir(batch_id: str) -> Path:
    return RAW_ROOT / batch_id


def raw_batch_file(batch_id: str, name: str) -> Path:
    return raw_batch_dir(batch_id) / name


def publish_batch_dir(batch_id: str) -> Path:
    return PUBLISH_ROOT / batch_id


def out_batch_dir(batch_id: str) -> Path:
    return OUT_ROOT / batch_id


def retrieval_plan_path(batch_id: str) -> Path:
    return raw_batch_file(batch_id, "retrieval_plan.json")


def loop_state_path(batch_id: str) -> Path:
    return raw_batch_file(batch_id, "loop_state.json")


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
