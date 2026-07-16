"""路径真相源 — 统一目录结构

核心原则：
- publish/ 只保留最终 creators/entities/posts/media canonical 对象；taxonomy 属于 control plane
- `data/tasks/<executionId>` 是唯一过程工作包
- 所有 ID 从目录路径推导，JSON 中不重复存储
- entities 三层目录：entities/{领域}/{类型}/{名称}/（如 entities/地点/景区/峨眉山/）
- tags 全目录化，每个标签 = 目录 + _definition.json
- posts 按内容角度标签分类，实际路径为 posts/{载体}/{angle}/{title}/{seq}/（angle 取内容角度最后一段）
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path

# 代码仓库 data 根：schema 是受版本控制、不可手改的契约真相源，必须跟代码走，
# 不随运行时 QWQ_DATA_ROOT 漂移；隔离/多环境只覆盖运行时数据根，不应丢失契约。
_REPO_DATA_ROOT = Path(__file__).resolve().parents[2]
# 仓库根（quwoquan_data 的上级）：服务侧 contracts/metadata 等跨工程契约真相源都挂在这里，
# 同样受版本控制、跟代码走，禁止用 DATA_ROOT.parent 推导（隔离根下会漂移到 /tmp/quwoquan_service）。
REPO_ROOT = _REPO_DATA_ROOT.parent
# 服务侧 metadata 契约根（字段/错误码/path/ui_config 等唯一真相源），跨工程消费统一走此常量。
SERVICE_CONTRACTS_METADATA_ROOT = Path(
    os.environ.get(
        "QWQ_SERVICE_CONTRACTS_METADATA_ROOT",
        REPO_ROOT / "quwoquan_service" / "contracts" / "metadata",
    )
)
DATA_ROOT = Path(os.environ.get("QWQ_DATA_ROOT", _REPO_DATA_ROOT))

# ─── 统一输出根（版本控制之外、工程目录之内）────────────────────────
# 仓内只保留可复用的输入契约与 canonical publish/**。所有可重跑执行物只有
# `.qwq_output/data/` 一个根：tasks/<executionId>、releases/<releaseId>、local/。
# 不再支持 QWQ_RUNTIME_ROOT、runtime/batches 或第二个 state 根。
_DEFAULT_OUTPUT_ROOT = REPO_ROOT / ".qwq_output"
if os.environ.get("QWQ_OUTPUT_ROOT"):
    OUTPUT_ROOT = Path(os.environ["QWQ_OUTPUT_ROOT"])
elif os.environ.get("QWQ_DATA_ROOT"):
    OUTPUT_ROOT = DATA_ROOT
else:
    OUTPUT_ROOT = _DEFAULT_OUTPUT_ROOT

DATA_OUTPUT_ROOT = OUTPUT_ROOT / "data"
DATA_EXECUTIONS_ROOT = DATA_OUTPUT_ROOT / "tasks"
DATA_LOCAL_ROOT = DATA_OUTPUT_ROOT / "local"
RELEASE_ROOT = DATA_OUTPUT_ROOT / "releases"

# Internal implementation alias.  It deliberately resolves to the single
# execution work-package root; callers must not create a separate runtime tree.
RUNTIME_ROOT = DATA_EXECUTIONS_ROOT


def current_runtime_root() -> Path:
    return DATA_EXECUTIONS_ROOT


# publish 是唯一发布主线生成输出：物理不出仓（默认 quwoquan_data/publish，不随
# OUTPUT_ROOT 漂移），且只保存已审核的消费者对象。taxonomy/profile/template 等
# 可复用静态输入必须留在控制面；隔离根（QWQ_DATA_ROOT/QWQ_PUBLISH_ROOT）覆盖时才漂移。
PUBLISH_ROOT = Path(os.environ.get("QWQ_PUBLISH_ROOT", DATA_ROOT / "publish"))
SCHEMA_ROOT = Path(os.environ.get("QWQ_SCHEMA_ROOT", _REPO_DATA_ROOT / "schema"))
# Repo-wide scans that do not belong to one execution are disposable workspace
# evidence, never synthetic children under `tasks/`.
OUTPUT_ARTIFACTS_ROOT = DATA_LOCAL_ROOT / "workspace" / "reports"

DEFAULT_SANDBOX_ROOT = _DEFAULT_OUTPUT_ROOT


def default_output_root() -> Path:
    """Canonical in-project gitignored output root for all runtime-phase output.

    Runner scripts and scaled/e2e/operations runs default their output here. Keeping
    the root inside the repo (gitignored) keeps everything manageable in one place
    while schema/contracts and ``publish/`` stay version-controlled and physically
    isolated from run output.
    """
    return _DEFAULT_OUTPUT_ROOT

# ─── 可复用内容控制面（版本控制内）──────────────────────────────────
# families/_shared 只保存 recipe、preset、instructions 与 runtime profile。
# 任务实例不进入 control_plane；唯一实例根是 DATA_EXECUTIONS_ROOT/<executionId>。
FAMILIES_ROOT = Path(
    os.environ.get("QWQ_FAMILIES_ROOT", _REPO_DATA_ROOT / "control_plane" / "families")
)
CONTROL_PLANE_SHARED_ROOT = _REPO_DATA_ROOT / "control_plane" / "_shared"
CONTROL_PLANE_CATALOGS_ROOT = CONTROL_PLANE_SHARED_ROOT / "catalogs"
CONTROL_PLANE_ROUTING_ROOT = CONTROL_PLANE_SHARED_ROOT / "routing"
CONTROL_PLANE_GOVERNANCE_ROOT = _REPO_DATA_ROOT / "control_plane" / "governance"
CONTROL_PLANE_TAXONOMY_ROOT = CONTROL_PLANE_GOVERNANCE_ROOT / "taxonomy"
CONTROL_PLANE_CREATOR_POOL_ROOT = CONTROL_PLANE_GOVERNANCE_ROOT / "creator_pool"
def normalize_family_ref(ref: str) -> str:
    """preset/recipe 引用即家族包内相对路径（不含类型后缀），如 content/travel/homepage/base。"""
    return str(ref or "").strip().strip("/")


def preset_path(preset_ref: str) -> Path:
    """presetRef → control_plane/families/<ref>.preset.yaml（任务默认值唯一真相源）。"""
    return FAMILIES_ROOT / f"{normalize_family_ref(preset_ref)}.preset.yaml"


def recipe_path(recipe_ref: str) -> Path:
    """recipeRef → control_plane/families/<ref>.recipe.yaml（命名运行配方真相源）。"""
    return FAMILIES_ROOT / f"{normalize_family_ref(recipe_ref)}.recipe.yaml"


def iter_family_files(suffix: str) -> list[Path]:
    """扫描家族包内某类型后缀的全部文件（lint/registry 消费，不建第二索引）。"""
    if not FAMILIES_ROOT.is_dir():
        return []
    return sorted(p for p in FAMILIES_ROOT.rglob(f"*{suffix}") if p.is_file())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


NOW_ISO = now_iso()
EXECUTION_SHARED_LEDGER_FILENAMES = (
    "catalog.ndjson",
    "dedup_ledger.json",
    "entities.ndjson",
    "tags.ndjson",
)
EXECUTION_ROOT_ALLOWED_ENTRIES = frozenset({
    "0.plan",
    "sources",
    "entities",
    "posts",
    "_shared",
    "evidence",
    "execution_manifest.json",
    "publish_ref.json",
})

# ─── execution 证据面：_shared 只保留跨阶段账本和不可重算决定。 ──────
# execution/_shared 最小证据面：跨对象账本 + explore/baseline 阶段的不可重算决策包。
EXECUTION_SHARED_ALLOWED_ENTRIES = frozenset({
    *EXECUTION_SHARED_LEDGER_FILENAMES,
    "baseline_freeze_packet.json",
    "baseline_report.json",
    "explore_packet.json",
    "discovery_adopt",
})

# execution/_shared 权威证据（不可重算真相源）：readiness / monitoring / ship /
# release 消费方只认这些 canonical 条目；新增证据必须先登记再写入。
EXECUTION_SHARED_AUTHORITATIVE_ENTRIES = frozenset({
    *EXECUTION_SHARED_LEDGER_FILENAMES,
    "execution_progress.json",
    "target_selection.json",
    "runtime_state.json",
    # 执行权威证据清单（目录规范冻结的十项）
    "content_plan_packet.json",
    "content_object_index.json",
    "env_ready_report.json",
    "workflow_state.json",
    "token_ledger.json",
    "managed_execution_audit.json",
    "scale_readiness.json",
    "ship_report.json",
    "failure_ledger.jsonl",
    # 执行级真相源（人工决策记录 / 放弃归因 / 账本，均不可重算）
    "source_catalog.json",
    "asset_id_registry.json",
    "audit_summary.json",
    "audit_summary.md",
    "run_journal.md",
    "base_draft_ledger.json",
    "execution_reducer_gate.json",
    "content_plan_source_diagnostics.json",
    "source_unavailable_targets.json",
    "reasoned_rejects.json",
    "inactive_entity_artifacts.json",
    "abandoned_homepage_artifacts.json",
    "quality_target_report.json",
    "download_repair.json",
    "import_report.json",
    "staging_import_report.json",
    "gamma_import_report.json",
    "trial_review.json",
    "review",
})

# execution/_shared 可清理调试/过程层：跑完即可删、重跑可重建；不得被
# readiness/审计当作真相源引用（摘要须先沉淀进上面的权威条目）。
EXECUTION_SHARED_RECLAIMABLE_ENTRIES = frozenset({
    "workspace",
    "assistant_tasks",
    "workflow_packets",
    "object_queue",
    "image_safety_cache",
    "download_source_screen",
    "download_events.jsonl",
    "download_progress.json",
    "auto_research_plan.json",
    "auto_research_progress.json",
    "source_research_guidance.json",
    "agent_result_envelopes",
    "envelopes",
    "controller_lease.json",
    "controller_lease.lock",
})


def execution_shared_entry_role(name: str) -> str:
    """execution/_shared 条目角色：authoritative / reclaimable / unknown。

    `tmp_` 前缀一律视作可清理过程层；unknown 条目由目录证据链门 BLOCK。
    """
    if name in EXECUTION_SHARED_AUTHORITATIVE_ENTRIES:
        return "authoritative"
    # ship 按环境回写导入审计副本：{env}_import_report.json 与
    # homepage-{env}_import_report.json（WP4 homepage importer 通道），
    # 环境名开放集合，用后缀规则而非逐环境枚举。
    if name.endswith("_import_report.json"):
        return "authoritative"
    if name in EXECUTION_SHARED_RECLAIMABLE_ENTRIES or name.startswith("tmp_"):
        return "reclaimable"
    return "unknown"

WORKSPACE_ROOT_BY_COMMAND = {
    "source": "source",
    "homepage": "homepage",
    "post": "post",
    "release": "release",
    "execution": "execution",
}


def normalize_execution_workspace_command(command: str) -> str:
    """Return the only accepted execution workspace identity.

    Execution reports are partitioned by a small, stable ownership set.  Stage
    names and controller implementation names must never become a workspace
    axis, otherwise writers and readers silently diverge.
    """
    normalized = str(command or "").strip()
    if normalized not in WORKSPACE_ROOT_BY_COMMAND:
        raise ValueError(f"unsupported execution workspace: {command}")
    return normalized


# ─── executionId ↔ work package ───────────────────────────────────
# Content execution has one identity and one runtime work package.
_EXECUTION_ID_PATH_RE = re.compile(
    r"^20\d{6}--[a-z][a-z0-9-]*-(homepage|article|image|video)-"
    r"[a-z][a-z0-9-]*--[a-z0-9][a-z0-9-]*--(canary|m1|m2|m3)-\d{3,}$"
)


def is_execution_id(value: str) -> bool:
    return _EXECUTION_ID_PATH_RE.fullmatch(str(value or "").strip()) is not None


def normalize_execution_id(execution_id: str) -> str:
    return execution_id.strip().strip("/")


def validate_execution_path_id(execution_id: str) -> str:
    normalized = normalize_execution_id(execution_id)
    if not is_execution_id(normalized):
        raise ValueError("content runtime requires a valid executionId")
    return normalized


def execution_root(execution_id: str) -> Path:
    return DATA_EXECUTIONS_ROOT / validate_execution_path_id(execution_id)


# ─── 并发锁（runtime 侧）─────────────────────────────────────────────
def execution_lock_path(execution_id: str) -> Path:
    return execution_root(execution_id) / ".lock"


def publish_lock_path() -> Path:
    return PUBLISH_ROOT / ".promote.lock"


# ─── publish 单一主线（已去版本化）───────────────────────────────
def publish_meta_path() -> Path:
    return PUBLISH_ROOT / "publish_meta.json"


# ─── 同构路径（runtime task 与 publish 共用）─────────────────────
class DataRoot:
    """runtime task 或 publish version 下的统一数据根。"""

    def __init__(self, root: Path):
        self.root = root

    # entities: entities/{domain}/{type}/{name}/
    def entities_dir(self) -> Path:
        return self.root / "entities"

    def entity_dir(self, domain: str, etype: str, name: str) -> Path:
        return self.entities_dir() / domain / etype / name

    def entity_json(self, domain: str, etype: str, name: str) -> Path:
        return self.entity_dir(domain, etype, name) / "_entity.json"

    def entity_page(self, domain: str, etype: str, name: str) -> Path:
        return self.entity_dir(domain, etype, name) / "page.md"

    def entity_manifest(self, domain: str, etype: str, name: str) -> Path:
        return self.entity_dir(domain, etype, name) / "manifest.json"

    # tags: tags/{dim}/{...path}/_definition.json
    def tags_dir(self) -> Path:
        return self.root / "tags"

    def taxonomy(self) -> Path:
        return self.tags_dir() / "_taxonomy.json"

    def tag_dir(self, tag_path: str) -> Path:
        return self.tags_dir() / tag_path

    def tag_file(self, tag_path: str) -> Path:
        return self.tag_dir(tag_path) / "_definition.json"

    def tag_dimension_dir(self, dim: str) -> Path:
        return self.tags_dir() / dim

    # posts: posts/{content_type}/{angle_tag}/{title}/{seq}/
    def posts_dir(self) -> Path:
        return self.root / "posts"

    def post_type_dir(self, content_type: str) -> Path:
        return self.posts_dir() / content_type

    def post_dir(self, content_type: str, angle_tag: str, title: str, seq: int = 1) -> Path:
        return self.post_type_dir(content_type) / angle_tag / title / str(seq)

    def post_article(self, content_type: str, angle_tag: str, title: str, seq: int = 1) -> Path:
        return self.post_dir(content_type, angle_tag, title, seq) / "article.md"

    def post_manifest(self, content_type: str, angle_tag: str, title: str, seq: int = 1) -> Path:
        return self.post_dir(content_type, angle_tag, title, seq) / "manifest.json"


def runtime_shared_dir() -> Path:
    return DATA_LOCAL_ROOT / "workspace"


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


# ─── publish 同构（单一主线）─────────────────────────────────────
def publish_data() -> DataRoot:
    return DataRoot(PUBLISH_ROOT)


# ─── release 输出（供服务端 bulk import 消费）─────────────────────
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
    base = output_root or OUTPUT_ROOT
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
    return RELEASE_ROOT / release_id


def release_manifest(release_id: str) -> Path:
    return release_root(release_id) / "release_manifest.json"


# ─── execution 产物快捷路径（assemble 消费）───────────────────────
def execution_entities(execution_id: str) -> Path:
    return _execution_shared_path(execution_id, "entities.ndjson")


def execution_tags(execution_id: str) -> Path:
    return _execution_shared_path(execution_id, "tags.ndjson")


# ─── execution 内部阶段路径 ───────────────────────────────────────
# contentType 与 supplyMode 是运行状态字段，不形成第二套目录身份。
EXECUTION_PHASES = ("e2e", "operations")
EXECUTION_CONTENT_TYPES = ("homepage", "article", "image", "video")
EXECUTION_SUPPLY_MODES = ("site_primary", "search_supplement")
DEFAULT_EXECUTION_PHASE = "e2e"
DEFAULT_EXECUTION_CONTENT_TYPE = "article"
DEFAULT_EXECUTION_SUPPLY_MODE = "site_primary"


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
_LABEL_STRIP_RE = re.compile(r"[\s/\\:]+")
_INTENT_LABEL_MAX = 64
def sanitize_intent_label(text: str) -> str:
    """清洗执行意图标签：去路径分隔/空白，保留足够的可读语义。"""
    cleaned = _LABEL_STRIP_RE.sub("", str(text or "").strip())
    return cleaned[:_INTENT_LABEL_MAX]


def executions_root() -> Path:
    """All execution work packages."""
    return DATA_EXECUTIONS_ROOT


def iter_execution_ids(execution_id: str) -> list[str]:
    return [normalize_execution_id(execution_id)] if execution_root(execution_id).is_dir() else []


def iter_all_execution_dirs() -> list[Path]:
    if not DATA_EXECUTIONS_ROOT.is_dir():
        return []
    return sorted(
        path for path in DATA_EXECUTIONS_ROOT.iterdir()
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


# ─── 对象同构目录（与 publish DataRoot 同构 + 过程阶段编号）─────────
# 实体对象 = tasks/{executionId}/entities/{domain}/{type}/{name}/
# 内容对象 = tasks/{executionId}/posts/{contentType}/{angle}/{title}/{seq}/
# 对象目录下过程阶段统一编号；成品落对象根（promote 时与 publish 同名直拷）。
STAGE_DOWNLOAD = "1.download"
STAGE_QUALITY = "2.quality"
STAGE_COMPOSE = "3.compose"
STAGE_DRAFT = "4.draft"
STAGE_REVIEW = "5.review"
# 对象过程阶段统一线性枚举；实体/内容共享同一阶段骨架，差异只体现在阶段产物内容。
OBJECT_STAGES = (
    STAGE_DOWNLOAD,
    STAGE_QUALITY,
    STAGE_COMPOSE,
    STAGE_DRAFT,
    STAGE_REVIEW,
)


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


# ─── 对象索引与批次工作区（规格 §14/§15；纯新增，零回归）─────────────
def object_index_path(object_dir: Path) -> Path:
    """对象索引 _object.json（实体过程对象根 / 内容对象根各一份）。"""
    return object_dir / "_object.json"


def execution_source_catalog_path(execution_id: str) -> Path:
    """受控来源类目（执行级共享，唯一真相源）。"""
    return execution_shared_dir(execution_id) / "source_catalog.json"


def execution_workflow_state_path(execution_id: str) -> Path:
    """workflow 状态属执行工作区，落 _shared（不进对象目录、不进 publish）。"""
    return execution_shared_dir(execution_id) / "workflow_state.json"


def execution_assistant_tasks_dir(execution_id: str) -> Path:
    """会话任务投递（执行工作区，可清理可重投）。"""
    return execution_shared_dir(execution_id) / "assistant_tasks"


def execution_workflow_packets_dir(execution_id: str) -> Path:
    """workflow 过程 packet 落点（执行工作区，按 stage 分文件）。"""
    return execution_shared_dir(execution_id) / "workflow_packets"


def execution_workflow_packet_path(execution_id: str, stage: str) -> Path:
    return execution_workflow_packets_dir(execution_id) / f"{stage}.json"


def execution_entity_page_input_path(
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
) -> Path:
    """实体主页输入契约：执行内对象过程 `3.compose/entity_page_input.json`。"""
    return execution_entity_stage_dir(execution_id, domain, etype, name, STAGE_COMPOSE) / "entity_page_input.json"


# ─── layout helpers ───────────────────────────────────────────────
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
