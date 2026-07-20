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
REPO_DATA_ROOT = _REPO_DATA_ROOT
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
    "execution_state.json",
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
    "command_packets",
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
    r"[a-z][a-z0-9-]*--[a-z0-9][a-z0-9-]*--(canary|m1|m2|m3|h10k)-\d{3,}$"
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




























# ─── publish 同构（单一主线）─────────────────────────────────────


# ─── release 输出（供服务端 bulk import 消费）─────────────────────










# ─── execution 产物快捷路径（assemble 消费）───────────────────────




# ─── execution 内部阶段路径 ───────────────────────────────────────
# contentType 与 supplyMode 是运行状态字段，不形成第二套目录身份。
EXECUTION_PHASES = ("e2e", "operations")
EXECUTION_CONTENT_TYPES = ("homepage", "article", "image", "video")
EXECUTION_SUPPLY_MODES = ("site_primary", "search_supplement")
DEFAULT_EXECUTION_PHASE = "e2e"
DEFAULT_EXECUTION_CONTENT_TYPE = "article"
DEFAULT_EXECUTION_SUPPLY_MODE = "site_primary"








_LABEL_STRIP_RE = re.compile(r"[\s/\\:]+")
_INTENT_LABEL_MAX = 64






















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




































# ─── 对象索引与批次工作区（规格 §14/§15；纯新增，零回归）─────────────














# ─── layout helpers ───────────────────────────────────────────────
from core.execution_paths import (
    dedup_ledger,
    ensure_execution_command_layout,
    ensure_execution_layout,
    ensure_object_stages,
    env_data_release_evidence_ref,
    env_data_release_run_root,
    execution_assistant_task,
    execution_assistant_tasks_dir,
    execution_audit_markdown_path,
    execution_audit_summary_path,
    execution_baseline_freeze_packet_path,
    execution_catalog,
    execution_command_packet_path,
    execution_command_packets_dir,
    execution_command_root,
    execution_content_plan_packet_path,
    execution_content_type,
    execution_data,
    execution_entities,
    execution_entity_object_dir,
    execution_entity_page_input_path,
    execution_entity_stage_dir,
    execution_explore_packet_path,
    execution_id_from_dir,
    execution_inputs_dir,
    execution_manifest_path,
    execution_phase,
    execution_post_object_dir,
    execution_post_roots,
    execution_post_stage_dir,
    execution_posts_root,
    execution_results_dir,
    execution_root_entry,
    execution_run_journal_path,
    execution_runtime_state_path,
    execution_sequence_lock_path,
    execution_sequence_path,
    execution_shared_dir,
    execution_source_catalog_path,
    execution_source_unit_dir,
    execution_sources_dir,
    execution_sources_root,
    execution_spec_path,
    execution_state_path,
    execution_supply_mode,
    execution_tags,
    executions_root,
    iter_all_execution_dirs,
    iter_execution_ids,
    object_index_path,
    object_source_unit_dir,
    publish_data,
    relative_execution_ref,
    release_manifest,
    release_ref,
    release_root,
    resolve_existing_execution_shared_path,
    runtime_shared_dir,
    sanitize_intent_label,
)
