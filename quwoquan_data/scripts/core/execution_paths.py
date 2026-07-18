"""Execution, release and object workspace path derivation."""
from __future__ import annotations
import os
import re
from pathlib import Path
from core import paths as _paths
from core.paths import (
    DEFAULT_EXECUTION_CONTENT_TYPE,
    DEFAULT_EXECUTION_PHASE, DEFAULT_EXECUTION_SUPPLY_MODE, DataRoot,
    EXECUTION_CONTENT_TYPES, EXECUTION_PHASES, EXECUTION_SUPPLY_MODES,
    OBJECT_STAGES, STAGE_COMPOSE,
    STAGE_DOWNLOAD, WORKSPACE_ROOT_BY_COMMAND, _INTENT_LABEL_MAX,
    _LABEL_STRIP_RE, is_execution_id, normalize_execution_id,
    normalize_execution_workspace_command, execution_root,
)

def runtime_shared_dir() -> Path:
    return _paths.DATA_LOCAL_ROOT / "workspace"

def execution_sequence_path() -> Path:
    return runtime_shared_dir() / "execution_sequence.json"

def execution_sequence_lock_path() -> Path:
    return runtime_shared_dir() / ".execution_sequence.lock"

def execution_data(execution_id: str) -> DataRoot:
    return DataRoot(execution_root(execution_id))

def execution_root_entry(execution_id: str, name: str) -> Path:
    return execution_root(execution_id) / name

def _execution_shared_path(execution_id: str, filename: str) -> Path:
    return execution_shared_dir(execution_id) / filename

def resolve_existing_execution_shared_path(execution_id: str, filename: str) -> Path:
    """读取唯一 canonical execution `_shared/` 路径。"""
    return _execution_shared_path(execution_id, filename)

def execution_manifest_path(execution_id: str) -> Path:
    """The single immutable execution manifest."""
    return execution_root(execution_id) / "execution_manifest.json"

def execution_spec_path(execution_id: str) -> Path:
    """Versioned execution input copied into the work package at creation time."""
    return execution_root(execution_id) / "0.plan" / "execution_spec.yaml"

def dedup_ledger(execution_id: str) -> Path:
    """跨批次去重账本（completedEntities/...）；与任务定义快照 execution_manifest_path.json 分离。"""
    return _execution_shared_path(execution_id, "dedup_ledger.json")

def execution_catalog(execution_id: str) -> Path:
    return _execution_shared_path(execution_id, "catalog.ndjson")

def execution_explore_packet_path(execution_id: str) -> Path:
    return execution_shared_dir(execution_id) / "explore_packet.json"

def execution_baseline_freeze_packet_path(execution_id: str) -> Path:
    return execution_shared_dir(execution_id) / "baseline_freeze_packet.json"

def publish_data() -> DataRoot:
    return DataRoot(_paths.PUBLISH_ROOT)

def release_ref(release_id: str) -> str:
    """逻辑 release 引用（相对 OUTPUT_ROOT）。"""
    return f"data/releases/{release_id}"

def env_data_release_run_root(
    env: str,
    release_id: str,
    run_id: str,
    *,
    output_root: Path | None = None,
) -> Path:
    """环境 release 执行证据：env/<env>/runs/data-release/<releaseId>/<runId>/"""
    base = output_root or _paths.OUTPUT_ROOT
    return (
        base
        / "env"
        / env
        / "runs"
        / "data-release"
        / release_id
        / run_id
    )

def env_data_release_evidence_ref(env: str, release_id: str, run_id: str) -> str:
    return (
        f"env/{env}/runs/data-release/{release_id}/{run_id}"
    )

def release_root(release_id: str) -> Path:
    return _paths.RELEASE_ROOT / release_id

def release_manifest(release_id: str) -> Path:
    return release_root(release_id) / "release_manifest.json"

def execution_entities(execution_id: str) -> Path:
    return _execution_shared_path(execution_id, "entities.ndjson")

def execution_tags(execution_id: str) -> Path:
    return _execution_shared_path(execution_id, "tags.ndjson")

def _execution_axis(env_key: str, allowed: tuple[str, ...], default: str) -> str:
    value = str(os.environ.get(env_key, "") or "").strip()
    if not value:
        return default
    if value not in allowed:
        raise ValueError(
            f"{env_key}={value!r} 不在允许值 {allowed} 内；一次执行必须唯一声明该维度"
        )
    return value

def execution_phase() -> str:
    """当前执行阶段声明（env `QWQ_EXECUTION_PHASE`，默认 e2e）。"""
    return _execution_axis("QWQ_EXECUTION_PHASE", EXECUTION_PHASES, DEFAULT_EXECUTION_PHASE)

def execution_content_type() -> str:
    """当前执行内容类型声明（env `QWQ_EXECUTION_CONTENT_TYPE`，默认 article）。"""
    return _execution_axis("QWQ_EXECUTION_CONTENT_TYPE", EXECUTION_CONTENT_TYPES, DEFAULT_EXECUTION_CONTENT_TYPE)

def execution_supply_mode() -> str:
    """当前执行供给模式声明（env `QWQ_EXECUTION_SUPPLY_MODE`，默认 site_primary）。"""
    return _execution_axis("QWQ_EXECUTION_SUPPLY_MODE", EXECUTION_SUPPLY_MODES, DEFAULT_EXECUTION_SUPPLY_MODE)

def sanitize_intent_label(text: str) -> str:
    """清洗执行意图标签：去路径分隔/空白，保留足够的可读语义。"""
    cleaned = _LABEL_STRIP_RE.sub("", str(text or "").strip())
    return cleaned[:_INTENT_LABEL_MAX]

def executions_root() -> Path:
    """All execution work packages."""
    return _paths.DATA_EXECUTIONS_ROOT

def iter_execution_ids(execution_id: str) -> list[str]:
    return [normalize_execution_id(execution_id)] if execution_root(execution_id).is_dir() else []

def iter_all_execution_dirs() -> list[Path]:
    root = executions_root()
    if not root.is_dir():
        return []
    return sorted(
        path for path in root.iterdir()
        if path.is_dir() and is_execution_id(path.name)
    )

def _workspace_name(command: str) -> str:
    return WORKSPACE_ROOT_BY_COMMAND[normalize_execution_workspace_command(command)]

def execution_id_from_dir(execution_dir: Path) -> str:
    return execution_dir.name if is_execution_id(execution_dir.name) else ""

def execution_command_root(execution_id: str, command: str) -> Path:
    return (
        execution_root(execution_id)
        / "_shared"
        / "workspace"
        / _workspace_name(command)
    )

def execution_inputs_dir(execution_id: str, command: str, step: str) -> Path:
    return execution_command_root(execution_id, command) / "inputs" / step

def execution_results_dir(execution_id: str, command: str, step: str) -> Path:
    return execution_command_root(execution_id, command) / "results" / step

def execution_assistant_task(execution_id: str, command: str, step: str) -> Path:
    return execution_command_root(execution_id, command) / "assistant_tasks" / f"{step}.json"

def execution_sources_dir(execution_id: str, entity_name: str) -> Path:
    return execution_command_root(execution_id, "source") / "sources" / entity_name

def ensure_object_stages(object_dir: Path, *, through_stage: str | None = None) -> None:
    """确保对象过程阶段目录存在（1.download → 5.review）。

    对象同构契约要求每步产物落在编号阶段子目录；resume/部分失败时常只创建了
    1.download 而缺 2.quality/3.compose 等，导致目录树不完整。在 download/compose/
    materialize 入口调用本函数，保证阶段树从第一步起完整可审计。
    """
    stages = OBJECT_STAGES
    if through_stage and through_stage in OBJECT_STAGES:
        end = OBJECT_STAGES.index(through_stage) + 1
        stages = OBJECT_STAGES[:end]
    for stage in stages:
        (object_dir / stage).mkdir(parents=True, exist_ok=True)

def execution_shared_dir(execution_id: str) -> Path:
    """执行级公共产物（跨对象共享，不属于任一对象）。"""
    return execution_root(execution_id) / "_shared"

def execution_audit_summary_path(execution_id: str) -> Path:
    """执行级审计摘要（脚本验收结果 + 抽检锚点）。"""
    return execution_shared_dir(execution_id) / "audit_summary.json"

def execution_audit_markdown_path(execution_id: str) -> Path:
    """执行级人工抽检清单。"""
    return execution_shared_dir(execution_id) / "audit_summary.md"

def execution_content_plan_packet_path(execution_id: str) -> Path:
    """证据驱动篇目规划包（content_plan checkpoint 产出）。"""
    return execution_shared_dir(execution_id) / "content_plan_packet.json"

def execution_run_journal_path(execution_id: str) -> Path:
    """执行问题→修复→规范缺口日记。"""
    return execution_shared_dir(execution_id) / "run_journal.md"

def execution_posts_root(execution_id: str) -> Path:
    """成品内容对象根：`tasks/<executionId>/posts/{type}/{angle}/{title}/{seq}/`。"""
    return execution_root(execution_id) / "posts"

def execution_post_roots(execution_id: str) -> list[Path]:
    """存在的成品 posts 根。"""
    roots = [execution_posts_root(execution_id)]
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r)
        if key in seen or not r.is_dir():
            continue
        seen.add(key)
        out.append(r)
    return out

def execution_runtime_state_path(execution_id: str) -> Path:
    """Mutable execution runtime state; identity remains execution_manifest.json."""
    return execution_root(execution_id) / "_shared" / "runtime_state.json"

def execution_entity_object_dir(
    execution_id: str, domain: str, etype: str, name: str
) -> Path:
    return execution_root(execution_id) / "entities" / domain / etype / name

def execution_sources_root(execution_id: str) -> Path:
    """Canonical physical source-unit pool: `tasks/<executionId>/sources/{sourceUnitId}/`."""
    return execution_root(execution_id) / "sources"

def execution_source_unit_dir(execution_id: str, source_unit_id: str) -> Path:
    # 可读命名契约：目录名保留中文实体名（\w 含 unicode），仅替换路径危险字符。
    unit_id = re.sub(r"[^\w.\-]+", "_", str(source_unit_id or "").strip()).strip("_")
    if not unit_id:
        unit_id = "source_unit"
    return execution_sources_root(execution_id) / unit_id

def execution_entity_stage_dir(
    execution_id: str, domain: str, etype: str, name: str, stage: str
) -> Path:
    return execution_entity_object_dir(execution_id, domain, etype, name) / stage

def execution_post_object_dir(
    execution_id: str,
    content_type: str,
    angle: str,
    title: str,
    seq: int = 1,
) -> Path:
    return (
        execution_root(execution_id)
        / "posts"
        / content_type
        / angle
        / title
        / str(seq)
    )

def execution_post_stage_dir(
    execution_id: str,
    content_type: str,
    angle: str,
    title: str,
    seq: int,
    stage: str,
) -> Path:
    return (
        execution_post_object_dir(execution_id, content_type, angle, title, seq) / stage
    )

def object_source_unit_dir(object_dir: Path, ordinal: int, source_id: str) -> Path:
    """Object-local source evidence path for an explicit fixture or isolated object."""
    return object_dir / STAGE_DOWNLOAD / "sources" / f"{ordinal:02d}.{source_id}"

def relative_execution_ref(target: Path, execution_id: str) -> str:
    """把执行内绝对路径转成相对执行根的 POSIX 相对路径。

    用于 manifest/provenance 的 citedSourceRefs / sourceAssetRef / sourcePaths，
    禁止绝对路径进入发布契约。
    """
    base = execution_root(execution_id).resolve()
    return os.path.relpath(Path(target).resolve(), base).replace(os.sep, "/")

def object_index_path(object_dir: Path) -> Path:
    """对象索引 _object.json（实体过程对象根 / 内容对象根各一份）。"""
    return object_dir / "_object.json"

def execution_source_catalog_path(execution_id: str) -> Path:
    """受控来源类目（执行级共享，唯一真相源）。"""
    return execution_shared_dir(execution_id) / "source_catalog.json"

def execution_state_path(execution_id: str) -> Path:
    """workflow 状态属执行工作区，落 _shared（不进对象目录、不进 publish）。"""
    return execution_shared_dir(execution_id) / "execution_state.json"

def execution_assistant_tasks_dir(execution_id: str) -> Path:
    """会话任务投递（执行工作区，可清理可重投）。"""
    return execution_shared_dir(execution_id) / "assistant_tasks"

def execution_command_packets_dir(execution_id: str) -> Path:
    """workflow 过程 packet 落点（执行工作区，按 stage 分文件）。"""
    return execution_shared_dir(execution_id) / "command_packets"

def execution_command_packet_path(execution_id: str, stage: str) -> Path:
    return execution_command_packets_dir(execution_id) / f"{stage}.json"

def execution_entity_page_input_path(
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
) -> Path:
    """实体主页输入契约：执行内对象过程 `3.compose/entity_page_input.json`。"""
    return execution_entity_stage_dir(execution_id, domain, etype, name, STAGE_COMPOSE) / "entity_page_input.json"

def ensure_execution_layout(execution_id: str) -> Path:
    root = execution_root(execution_id)
    root.mkdir(parents=True, exist_ok=True)
    execution_shared_dir(execution_id).mkdir(parents=True, exist_ok=True)
    d = execution_data(execution_id)
    d.entities_dir().mkdir(exist_ok=True)
    return root

def ensure_execution_command_layout(execution_id: str, command: str) -> Path:
    cmd_root = execution_command_root(execution_id, command)
    (cmd_root / "inputs").mkdir(parents=True, exist_ok=True)
    (cmd_root / "results").mkdir(parents=True, exist_ok=True)
    (cmd_root / "assistant_tasks").mkdir(parents=True, exist_ok=True)
    return cmd_root
