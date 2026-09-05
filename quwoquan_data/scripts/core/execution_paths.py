"""Pure execution/object/release path derivation."""
from __future__ import annotations

import os
import re
from pathlib import Path

from core import paths as _paths
from core.data_root import DataRoot
from core.paths import (
    OBJECT_STAGES, STAGE_COMPOSE, STAGE_DOWNLOAD,
    _INTENT_LABEL_MAX, _LABEL_STRIP_RE, execution_root, is_execution_id,
    normalize_execution_id,
)


def execution_data(execution_id: str) -> DataRoot:
    return DataRoot(execution_root(execution_id))

def execution_root_entry(execution_id: str, name: str) -> Path:
    return execution_root(execution_id) / name

def execution_manifest_path(execution_id: str) -> Path:
    return execution_root(execution_id) / "execution_manifest.json"

def publish_data() -> DataRoot:
    return DataRoot(_paths.PUBLISH_ROOT)

def release_ref(release_id: str) -> str:
    return f"data/releases/{release_id}"

def env_data_release_run_root(env: str, release_id: str, run_id: str, *, output_root: Path | None = None) -> Path:
    return (output_root or _paths.OUTPUT_ROOT) / "env" / env / "runs" / "data-release" / release_id / run_id

def env_data_release_evidence_ref(env: str, release_id: str, run_id: str) -> str:
    return f"env/{env}/runs/data-release/{release_id}/{run_id}"

def release_root(release_id: str) -> Path:
    return _paths.RELEASE_ROOT / release_id

def release_manifest(release_id: str) -> Path:
    return release_root(release_id) / "release_manifest.json"

def sanitize_intent_label(text: str) -> str:
    return _LABEL_STRIP_RE.sub("", str(text or "").strip())[:_INTENT_LABEL_MAX]

def executions_root() -> Path:
    return _paths.DATA_EXECUTIONS_ROOT

def iter_execution_ids(execution_id: str) -> list[str]:
    return [normalize_execution_id(execution_id)] if execution_root(execution_id).is_dir() else []

def iter_all_execution_dirs() -> list[Path]:
    root = executions_root()
    return sorted(path for path in root.iterdir() if path.is_dir() and is_execution_id(path.name)) if root.is_dir() else []

def execution_id_from_dir(execution_dir: Path) -> str:
    return execution_dir.name if is_execution_id(execution_dir.name) else ""

def ensure_object_stages(object_dir: Path) -> None:
    for stage in OBJECT_STAGES:
        (object_dir / stage).mkdir(parents=True, exist_ok=True)

def execution_shared_dir(execution_id: str) -> Path:
    return execution_root(execution_id) / "_shared"

def execution_posts_root(execution_id: str) -> Path:
    return execution_root(execution_id) / "posts"

def execution_post_roots(execution_id: str) -> list[Path]:
    root = execution_posts_root(execution_id)
    return [root] if root.is_dir() else []

def execution_entity_object_dir(execution_id: str, domain: str, etype: str, name: str) -> Path:
    return execution_root(execution_id) / "entities" / domain / etype / name

def execution_sources_root(execution_id: str) -> Path:
    return execution_root(execution_id) / "sources"

def execution_source_unit_dir(execution_id: str, source_unit_id: str) -> Path:
    unit = re.sub(r"[^\w.\-]+", "_", str(source_unit_id or "").strip()).strip("_") or "source_unit"
    return execution_sources_root(execution_id) / unit

def execution_entity_stage_dir(execution_id: str, domain: str, etype: str, name: str, stage: str) -> Path:
    return execution_entity_object_dir(execution_id, domain, etype, name) / stage

def execution_post_object_dir(execution_id: str, content_type: str, angle: str, title: str, seq: int = 1) -> Path:
    return execution_root(execution_id) / "posts" / content_type / angle / title / str(seq)

def execution_post_stage_dir(execution_id: str, content_type: str, angle: str, title: str, seq: int, stage: str) -> Path:
    return execution_post_object_dir(execution_id, content_type, angle, title, seq) / stage

def object_source_unit_dir(object_dir: Path, ordinal: int, source_id: str) -> Path:
    return object_dir / STAGE_DOWNLOAD / "sources" / f"{ordinal:02d}.{source_id}"

def relative_execution_ref(target: Path, execution_id: str) -> str:
    root = execution_root(execution_id).resolve()
    candidate = Path(target).resolve()
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"path is outside execution root: {candidate}") from exc

def object_index_path(object_dir: Path) -> Path:
    return object_dir / "_object.json"

def execution_entity_page_input_path(execution_id: str, domain: str, etype: str, name: str) -> Path:
    return execution_entity_stage_dir(execution_id, domain, etype, name, STAGE_COMPOSE) / "entity_page_input.json"

def ensure_execution_layout(execution_id: str) -> Path:
    root = execution_root(execution_id)
    root.mkdir(parents=True, exist_ok=True)
    execution_shared_dir(execution_id).mkdir(parents=True, exist_ok=True)
    execution_data(execution_id).entities_dir().mkdir(exist_ok=True)
    return root
