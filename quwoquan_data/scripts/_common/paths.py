"""路径真相源 — 统一目录结构

核心原则：
- publish/ 仍保持 entities/tags/posts 同构；runtime task 只保留实体真相源与批次对象树，
  内容真相源落 `batches/<batch>/posts/`，task 根 `posts/` 已退役
- 所有 ID 从目录路径推导，JSON 中不重复存储
- entities 三层目录：entities/{领域}/{类型}/{名称}/（如 entities/地点/景区/峨眉山/）
- tags 全目录化，每个标签 = 目录 + _definition.json
- posts 按内容角度标签分类，实际路径为 posts/{载体}/{angle}/{title}/{seq}/（angle 取内容角度最后一段）
- sop 目录与实体类型对齐：sop/主页/{领域}/{类型}/
"""
from __future__ import annotations

from datetime import datetime, timezone
import functools
import hashlib
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
# 目录规范裁定（数据输出规范计划）：
# - 仓内（版本控制）只保留两类长期真相源：输入契约（tasks/schema/templates/scripts）
#   与发布主线 publish/**；
# - 其余一切运行期输出（local/data-runtime 批次树 / release 过程 / runs 摘要索引 / app 验证证据）
#   统一落到 QWQ_OUTPUT_ROOT，默认 `<repo>/.qwq_output/`（gitignore 隔离，工程内可统一管理）；
# - 禁止默认写到 /tmp、~/qwq_* 等工程外路径（只允许显式 env 覆盖用于隔离实验）。
# - release 按工程域分组；data 发布包默认只写 `.qwq_output/release/data/<releaseId>`。
# 当 QWQ_DATA_ROOT 被显式覆盖（测试隔离根）时，输出根跟随 DATA_ROOT
# （local/data-runtime/publish/release 同根隔离）。
_DEFAULT_OUTPUT_ROOT = REPO_ROOT / ".qwq_output"
if os.environ.get("QWQ_OUTPUT_ROOT"):
    OUTPUT_ROOT = Path(os.environ["QWQ_OUTPUT_ROOT"])
elif os.environ.get("QWQ_DATA_ROOT"):
    OUTPUT_ROOT = DATA_ROOT
else:
    OUTPUT_ROOT = _DEFAULT_OUTPUT_ROOT

RUNTIME_ROOT = Path(os.environ.get("QWQ_RUNTIME_ROOT", OUTPUT_ROOT / "local" / "data-runtime"))


def current_runtime_root() -> Path:
    runtime_root = os.environ.get("QWQ_RUNTIME_ROOT")
    if runtime_root:
        return Path(runtime_root)
    output_root = os.environ.get("QWQ_OUTPUT_ROOT")
    if output_root:
        return Path(output_root) / "local" / "data-runtime"
    data_root = os.environ.get("QWQ_DATA_ROOT")
    if data_root:
        return Path(data_root) / "local" / "data-runtime"
    return RUNTIME_ROOT


# publish 是唯一发布主线生成输出：物理不出仓（默认 quwoquan_data/publish，不随
# OUTPUT_ROOT 漂移），但仅契约子树受版本控制（tags/creators/user_media；其余
# entities/posts/index 等由根 .gitignore `quwoquan_data/publish/**` 排除）；
# 隔离根（QWQ_DATA_ROOT/QWQ_PUBLISH_ROOT）覆盖时才漂移。
PUBLISH_ROOT = Path(os.environ.get("QWQ_PUBLISH_ROOT", DATA_ROOT / "publish"))
RELEASE_ROOT = Path(os.environ.get("QWQ_RELEASE_ROOT", OUTPUT_ROOT / "release" / "data"))
SCHEMA_ROOT = Path(os.environ.get("QWQ_SCHEMA_ROOT", _REPO_DATA_ROOT / "schema"))
SOP_ROOT = DATA_ROOT / "sop"
# 输出侧摘要索引根（只回指、不承载权威证据）：.qwq_output/runs/data/**。
OUTPUT_ARTIFACTS_ROOT = Path(
    os.environ.get("QWQ_OUTPUT_ARTIFACTS_ROOT", OUTPUT_ROOT / "runs" / "data")
)

DEFAULT_SANDBOX_ROOT = _DEFAULT_OUTPUT_ROOT


def default_output_root() -> Path:
    """Canonical in-project gitignored output root for all runtime-phase output.

    Runner scripts and scaled/e2e/operations runs default their output here. Keeping
    the root inside the repo (gitignored) keeps everything manageable in one place
    while schema/contracts and ``publish/`` stay version-controlled and physically
    isolated from run output.
    """
    return _DEFAULT_OUTPUT_ROOT

TASKS_ROOT = RUNTIME_ROOT / "tasks"

# ─── 统一数据任务控制面（control_plane/：任务输入契约唯一真相源）────────
# 结构（docs/pipeline_directory_layout_spec.md 仓内层规范）：
#   control_plane/tasks/<taskId>/task.yaml      任务实例注册表（task.yaml 入库，进度本地）
#   control_plane/families/<家族路径>/*.preset.yaml|*.recipe.yaml|*.repair.yaml|*.instructions.md
#                                                家族包：同族模板/配方/指令/修补策略同目录扁平共存
#   control_plane/_shared/*.runtime.yaml         跨家族共享运行环境 profile
# 默认机制唯一真相源 = task.yaml.presetRef → families/<ref>.preset.yaml；
# 旧 `_defaults.yaml` 路径继承链已退役，禁止回归。
# tasks 注册表随 DATA_ROOT（测试隔离根可整体覆盖）；families/_shared 是版本控制
# 契约，跟代码走、不随运行时数据根漂移（QWQ_FAMILIES_ROOT 仅供测试注入）。
CONTROL_PLANE_ROOT = DATA_ROOT / "control_plane"
COMMITTED_TASKS_ROOT = Path(
    os.environ.get("QWQ_COMMITTED_TASKS_ROOT", CONTROL_PLANE_ROOT / "tasks")
)
FAMILIES_ROOT = Path(
    os.environ.get("QWQ_FAMILIES_ROOT", _REPO_DATA_ROOT / "control_plane" / "families")
)
CONTROL_PLANE_SHARED_ROOT = _REPO_DATA_ROOT / "control_plane" / "_shared"
COMMANDS = ("explore", "build", "download", "produce", "publish")


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
TASK_SHARED_LEDGER_FILENAMES = (
    "catalog.ndjson",
    "dedup_ledger.json",
    "entities.ndjson",
    "tags.ndjson",
)
TASK_ROOT_ALLOWED_ENTRIES = frozenset({
    "entities",
    "_shared",
    "task_manifest.json",
})
TASK_ROOT_LEGACY_COMPAT_ENTRIES = frozenset({
    *TASK_SHARED_LEDGER_FILENAMES,
    "posts",
    "entity_pages",
    "graph",
    "changeset",
})

# ─── 证据面瘦身（数据输出规范）：local/data-runtime/tasks 与 batch/_shared 只保留
#     不可重算真相源；调试/过程态降级为可清理层。 ────────────────────
# task/_shared 最小证据面：跨批次账本 + explore/baseline 阶段的不可重算决策包。
TASK_SHARED_ALLOWED_ENTRIES = frozenset({
    *TASK_SHARED_LEDGER_FILENAMES,
    "baseline_freeze_packet.json",
    "baseline_report.json",
    "explore_packet.json",
    "discovery_adopt",
})

# batch/_shared 权威证据（不可重算真相源）：readiness / monitoring / ship /
# release 消费方只认这些 canonical 条目；新增证据必须先登记再写入。
BATCH_SHARED_AUTHORITATIVE_ENTRIES = frozenset({
    # 批次权威证据清单（目录规范冻结的十项）
    "content_plan_packet.json",
    "content_object_index.json",
    "env_ready_report.json",
    "task_workflow_state.json",
    "token_ledger.json",
    "managed_batch_audit.json",
    "sdk_monitoring_report.json",
    "scale_readiness.json",
    "ship_report.json",
    "failure_ledger.jsonl",
    # 既有批次级真相源（人工决策记录 / 放弃归因 / 账本，均不可重算）
    "source_catalog.json",
    "asset_id_registry.json",
    "audit_summary.json",
    "audit_summary.md",
    "run_journal.md",
    "base_draft_ledger.json",
    "batch_reducer_gate.json",
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

# batch/_shared 可清理调试/过程层：跑完即可删、重跑可重建；不得被
# readiness/审计当作真相源引用（摘要须先沉淀进上面的权威条目）。
BATCH_SHARED_RECLAIMABLE_ENTRIES = frozenset({
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


def batch_shared_entry_role(name: str) -> str:
    """batch/_shared 条目角色：authoritative / reclaimable / unknown。

    `tmp_` 前缀一律视作可清理过程层；unknown 条目由目录证据链门 BLOCK。
    """
    if name in BATCH_SHARED_AUTHORITATIVE_ENTRIES:
        return "authoritative"
    # ship 按环境回写导入审计副本：{env}_import_report.json 与
    # homepage-{env}_import_report.json（WP4 homepage importer 通道），
    # 环境名开放集合，用后缀规则而非逐环境枚举。
    if name.endswith("_import_report.json"):
        return "authoritative"
    if name in BATCH_SHARED_RECLAIMABLE_ENTRIES or name.startswith("tmp_"):
        return "reclaimable"
    return "unknown"

WORKSPACE_ROOT_BY_COMMAND = {
    "build": "task_build",
    "download": "task_download",
    "produce": "task_produce",
    "publish": "task_publish",
    "pipeline": "task_workflow",
    "task_run": "task_workflow",
    "workflow": "task_workflow",
    "workflow_run": "task_workflow",
}


# ─── taskId ↔ 目录 互转 ────────────────────────────────────────────
# taskId 即斜杠路径：<vertical>/<organizeBy>/<key>[/<category>]/<name>
# committed: tasks/<taskId>/   runtime: local/data-runtime/tasks/<taskId>/（task_root 已支持嵌套）
def normalize_task_id(task_id: str) -> str:
    return task_id.strip().strip("/")


def task_id_from_committed_path(path: Path) -> str:
    """从 committed 目录反推 taskId。"""
    return str(Path(path).resolve().relative_to(COMMITTED_TASKS_ROOT.resolve())).replace(os.sep, "/")


def committed_task_root(task_id: str) -> Path:
    return COMMITTED_TASKS_ROOT / normalize_task_id(task_id)


def committed_task_spec(task_id: str) -> Path:
    return committed_task_root(task_id) / "task.yaml"


def committed_task_progress(task_id: str) -> Path:
    return committed_task_root(task_id) / "progress.json"


def committed_task_runs_dir(task_id: str) -> Path:
    return committed_task_root(task_id) / "runs"


def committed_task_notes(task_id: str) -> Path:
    return committed_task_root(task_id) / "notes.md"


def iter_committed_task_specs() -> list[Path]:
    """扫描全部 committed task.yaml（registry 实时生成依据，不维护第二真相源）。"""
    if not COMMITTED_TASKS_ROOT.is_dir():
        return []
    return sorted(COMMITTED_TASKS_ROOT.rglob("task.yaml"))


# ─── 并发锁（runtime 侧）─────────────────────────────────────────────
def task_lock_path(task_id: str) -> Path:
    return task_root(task_id) / ".lock"


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

    # sop: sop/主页/{domain}/{type}/ -> guide.md, template.md, example.md
    def sop_dir(self, domain: str, etype: str) -> Path:
        return SOP_ROOT / "主页" / domain / etype

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


# ─── task 级路径 ──────────────────────────────────────────────────
def task_root(task_id: str) -> Path:
    return TASKS_ROOT / task_id


def runtime_shared_dir() -> Path:
    return RUNTIME_ROOT / "_shared"


def global_batch_seq_path() -> Path:
    return runtime_shared_dir() / "global_batch_seq.json"


def global_batch_seq_lock_path() -> Path:
    return runtime_shared_dir() / ".global_batch_seq.lock"


def task_data(task_id: str) -> DataRoot:
    return DataRoot(task_root(task_id))


def task_shared_dir(task_id: str) -> Path:
    return task_root(task_id) / "_shared"


def task_root_entry(task_id: str, name: str) -> Path:
    return task_root(task_id) / name


def _task_shared_path(task_id: str, filename: str) -> Path:
    return task_shared_dir(task_id) / filename


def resolve_existing_task_shared_path(task_id: str, filename: str) -> Path:
    """读取 canonical task `_shared/` 路径；旧 task 根镜像位不再参与 fallback。"""
    return _task_shared_path(task_id, filename)


def iter_existing_task_legacy_entries(task_id: str) -> list[Path]:
    root = task_root(task_id)
    out: list[Path] = []
    for name in TASK_ROOT_LEGACY_COMPAT_ENTRIES:
        path = root / name
        if path.exists():
            out.append(path)
    return sorted(out, key=lambda path: path.name)


def task_manifest(task_id: str) -> Path:
    """任务定义快照（§14.1：vertical/organizeBy/scope/content.angles），由 task run 写。"""
    return task_root(task_id) / "task_manifest.json"


def dedup_ledger(task_id: str) -> Path:
    """跨批次去重账本（completedEntities/...）；与任务定义快照 task_manifest.json 分离。"""
    return _task_shared_path(task_id, "dedup_ledger.json")


def task_catalog(task_id: str) -> Path:
    return _task_shared_path(task_id, "catalog.ndjson")


def task_explore_packet_path(task_id: str) -> Path:
    return task_shared_dir(task_id) / "explore_packet.json"


def task_baseline_freeze_packet_path(task_id: str) -> Path:
    return task_shared_dir(task_id) / "baseline_freeze_packet.json"


# ─── fan-out 编排（runtime 级共享，不进 publish）──────────────────────
def orchestrate_root() -> Path:
    """fan-out 编排计划根（runtime 级，跨 task 共享）。"""
    return RUNTIME_ROOT / "_shared" / "orchestrate"


def fanout_plan_dir(plan_id: str) -> Path:
    return orchestrate_root() / plan_id


def fanout_plan_path(plan_id: str) -> Path:
    """冻结计划真相源：runtime/_shared/orchestrate/{planId}/fanout_plan.json。"""
    return fanout_plan_dir(plan_id) / "fanout_plan.json"


def fanout_dispatch_state_path(plan_id: str) -> Path:
    """dispatch 幂等账本：记录已建 task/batch、已 enqueue 分区（可重放）。"""
    return fanout_plan_dir(plan_id) / "dispatch_state.json"


def fanout_rollup_path(plan_id: str) -> Path:
    return fanout_plan_dir(plan_id) / "rollup.json"


def fanout_summary_path(plan_id: str) -> Path:
    """fanout 计划级汇总：把 rollup/run_matrix/workflow_state 对齐成单独摘要。"""
    return fanout_plan_dir(plan_id) / "summary.json"


def fanout_run_matrix_path(plan_id: str) -> Path:
    """fanout 运行矩阵：每个 ref/worker/orchestrator 的运行证据账本。"""
    return fanout_plan_dir(plan_id) / "run_matrix.json"


# ─── publish 同构（单一主线）─────────────────────────────────────
def publish_data() -> DataRoot:
    return DataRoot(PUBLISH_ROOT)


# ─── release 输出（供服务端 bulk import 消费）─────────────────────
def release_root(release_id: str) -> Path:
    return RELEASE_ROOT / release_id


def release_manifest(release_id: str) -> Path:
    return release_root(release_id) / "release_manifest.json"


# ─── task 产物快捷路径（assemble 消费）────────────────────────────
def task_entities(task_id: str) -> Path:
    return _task_shared_path(task_id, "entities.ndjson")


def task_tags(task_id: str) -> Path:
    return _task_shared_path(task_id, "tags.ndjson")


# ─── batch 级路径 ─────────────────────────────────────────────────
# 目录规范（数据输出规范计划）：批次树按「阶段 × 内容类型 × 供给模式」三级主键分层：
#   local/data-runtime/{phase}/{contentType}/{supplyMode}/{intentLabel}-{taskHash}__{batch}/
# - phase ∈ {e2e, operations}：端到端试跑验证 vs 自动化运营正式跑批（单元测试走 tempfile 根，无批次概念）。
# - contentType ∈ {homepage, article, image, video}：一批次只跑一种内容类型，禁止混批。
# - supplyMode ∈ {site_primary, search_supplement}：站点主线 vs 搜索小流量补全，必须分批分路径。
# - sourceKey/siteId 记入 batch_manifest.json 字段，不作目录层级（控制目录深度）。
# 叶目录命名沿用 `{intentLabel}-{taskHash}__{batch}`：
# - intentLabel = ≤16 字人类可读任务意图标签（committed task.yaml.intentLabel，缺省回退 taskId 末段）。
# - taskHash = 归一 taskId 的稳定短哈希（8 hex），消歧「同名不同分区任务共用 batchId」碰撞
#   （fanout 各分区叶任务名相同且共享 fanout_<plan> 批次，旧的 tasks/<taskId>/batches 由 taskId 路径天然区分，
#    上提到顶层后必须由 taskHash 重新提供任务唯一性）。
# - batch→task 反查唯一依据仍是 batch_manifest.json.taskId；taskHash 只保证目录唯一与候选过滤精确。
BATCH_PHASES = ("e2e", "operations")
BATCH_CONTENT_TYPES = ("homepage", "article", "image", "video")
BATCH_SUPPLY_MODES = ("site_primary", "search_supplement")
DEFAULT_BATCH_PHASE = "e2e"
DEFAULT_BATCH_CONTENT_TYPE = "article"
DEFAULT_BATCH_SUPPLY_MODE = "site_primary"


def _batch_axis(env_key: str, allowed: tuple[str, ...], default: str) -> str:
    value = str(os.environ.get(env_key, "") or "").strip()
    if not value:
        return default
    if value not in allowed:
        raise ValueError(
            f"{env_key}={value!r} 不在允许值 {allowed} 内；一批次必须唯一声明该维度"
        )
    return value


def batch_phase() -> str:
    """当前批次阶段声明（env `QWQ_BATCH_PHASE`，默认 e2e）。"""
    return _batch_axis("QWQ_BATCH_PHASE", BATCH_PHASES, DEFAULT_BATCH_PHASE)


def batch_content_type() -> str:
    """当前批次内容类型声明（env `QWQ_BATCH_CONTENT_TYPE`，默认 article）。"""
    return _batch_axis("QWQ_BATCH_CONTENT_TYPE", BATCH_CONTENT_TYPES, DEFAULT_BATCH_CONTENT_TYPE)


def batch_supply_mode() -> str:
    """当前批次供给模式声明（env `QWQ_BATCH_SUPPLY_MODE`，默认 site_primary）。"""
    return _batch_axis("QWQ_BATCH_SUPPLY_MODE", BATCH_SUPPLY_MODES, DEFAULT_BATCH_SUPPLY_MODE)
_LABEL_STRIP_RE = re.compile(r"[\s/\\:]+")
_INTENT_LABEL_MAX = 16
_TASK_HASH_LEN = 8


def task_discriminator(task_id: str) -> str:
    """归一 taskId 的稳定短哈希（8 hex），用于顶层批次目录消歧。

    纯函数、与 committed 规格无关 → 任务全生命周期稳定，无读写时序/缓存分叉风险。
    """
    norm = normalize_task_id(task_id)
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:_TASK_HASH_LEN]


def sanitize_intent_label(text: str) -> str:
    """清洗任务意图标签：去路径分隔/空白，截断到 ≤16 字（按字符数）。"""
    cleaned = _LABEL_STRIP_RE.sub("", str(text or "").strip())
    return cleaned[:_INTENT_LABEL_MAX]


@functools.lru_cache(maxsize=8192)
def _committed_intent_label(task_id_norm: str) -> str:
    """读取 committed task.yaml.intentLabel（lru 缓存；写规格后须 cache_clear）。"""
    spec_path = committed_task_spec(task_id_norm)
    if not spec_path.is_file():
        return ""
    try:
        import yaml  # 惰性导入：低层路径模块不强依赖 yaml

        data = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return ""
    if isinstance(data, dict):
        return str(data.get("intentLabel") or "").strip()
    return ""


def task_intent_label(task_id: str) -> str:
    """顶层批次目录前缀：≤16 字人类可读任务意图标签。

    真相源 committed `task.yaml.intentLabel`（运行期不可变 → 纯解析、稳定）；
    缺省回退 taskId 末段清洗截断。不分配序号、不写第二索引文件。
    """
    norm = normalize_task_id(task_id)
    label = _committed_intent_label(norm)
    if not label:
        label = norm.split("/")[-1] if norm else ""
    return sanitize_intent_label(label) or "task"


def clear_intent_label_cache() -> None:
    """committed task.yaml 写入后调用，避免 intentLabel 解析读到旧缓存。"""
    _committed_intent_label.cache_clear()


def batches_root() -> Path:
    """当前批次落位根：local/data-runtime/{phase}/{contentType}/{supplyMode}/。

    三级主键由 env 声明（`QWQ_BATCH_PHASE` / `QWQ_BATCH_CONTENT_TYPE` /
    `QWQ_BATCH_SUPPLY_MODE`），一批次运行期内唯一且不可变。
    """
    return phase_batches_root(batch_phase(), batch_content_type(), batch_supply_mode())


def phase_batches_root(phase: str, content_type: str, supply_mode: str) -> Path:
    if phase not in BATCH_PHASES:
        raise ValueError(f"phase={phase!r} 不在 {BATCH_PHASES} 内")
    if content_type not in BATCH_CONTENT_TYPES:
        raise ValueError(f"contentType={content_type!r} 不在 {BATCH_CONTENT_TYPES} 内")
    if supply_mode not in BATCH_SUPPLY_MODES:
        raise ValueError(f"supplyMode={supply_mode!r} 不在 {BATCH_SUPPLY_MODES} 内")
    return RUNTIME_ROOT / phase / content_type / supply_mode


def iter_batches_roots() -> list[Path]:
    """全部 canonical 批次根，只返回已存在目录。"""
    roots: list[Path] = []
    for phase in BATCH_PHASES:
        for content_type in BATCH_CONTENT_TYPES:
            for supply_mode in BATCH_SUPPLY_MODES:
                root = RUNTIME_ROOT / phase / content_type / supply_mode
                if root.is_dir():
                    roots.append(root)
    return roots


def task_dir_prefix(task_id: str) -> str:
    """顶层批次目录的任务唯一前缀：`{intentLabel}-{taskHash}__`。

    含 taskHash → 该前缀任务唯一，可直接用于候选目录精确过滤与 batchId 还原。
    """
    return f"{task_intent_label(task_id)}-{task_discriminator(task_id)}__"


def batch_dir_name(task_id: str, batch_id: str) -> str:
    return f"{task_dir_prefix(task_id)}{batch_id}"


def batch_root(task_id: str, batch_id: str) -> Path:
    """批次根解析：只扫描 canonical 分层树；不存在则按当前声明落位。"""
    name = batch_dir_name(task_id, batch_id)
    for root in iter_batches_roots():
        candidate = root / name
        if candidate.is_dir():
            return candidate
    return batches_root() / name


def iter_task_batch_dirs(task_id: str) -> list[Path]:
    """列出某任务的所有批次目录（反查唯一依据 batch_manifest.taskId）。

    前缀 `{intentLabel}-{taskHash}__` 任务唯一 → 候选过滤已可精确定位；
    仍读 `batch_manifest.json.taskId` 做归属确认（manifest 为反查唯一真相源，
    建目录中途 manifest 尚未写时按前缀归属为候选）。
    """
    norm = normalize_task_id(task_id)
    prefix = task_dir_prefix(task_id)
    out: list[Path] = []
    for root in iter_batches_roots():
        for d in sorted(root.iterdir()):
            if not d.is_dir() or not d.name.startswith(prefix):
                continue
            manifest = d / "batch_manifest.json"
            if manifest.is_file():
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
                mtid = normalize_task_id(str((data or {}).get("taskId") or "")) if isinstance(data, dict) else ""
                if mtid and mtid != norm:
                    continue
            out.append(d)
    return out


def iter_task_batch_ids(task_id: str) -> list[str]:
    """列出某任务的所有批次 batchId（去掉 `{intentLabel}-{taskHash}__` 前缀）。"""
    prefix = task_dir_prefix(task_id)
    return [d.name[len(prefix):] for d in iter_task_batch_dirs(task_id)]


def iter_all_batch_dirs() -> list[Path]:
    """跨任务列出全部 canonical 批次目录（verify/scan/dirty/审计消费）。"""
    out: list[Path] = []
    for root in iter_batches_roots():
        out.extend(d for d in root.iterdir() if d.is_dir())
    return sorted(out)


def batch_task_id(batch_dir: Path) -> str:
    """从批次目录读取归属 taskId（反查唯一依据）。"""
    manifest = batch_dir / "batch_manifest.json"
    if not manifest.is_file():
        return ""
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if isinstance(data, dict):
        return normalize_task_id(str(data.get("taskId") or ""))
    return ""


def batch_command_root(task_id: str, batch_id: str, command: str) -> Path:
    return batch_root(task_id, batch_id) / WORKSPACE_ROOT_BY_COMMAND.get(command, command)


def batch_inputs_dir(task_id: str, batch_id: str, command: str, step: str) -> Path:
    return batch_command_root(task_id, batch_id, command) / "inputs" / step


def batch_results_dir(task_id: str, batch_id: str, command: str, step: str) -> Path:
    return batch_command_root(task_id, batch_id, command) / "results" / step


def batch_assistant_task(task_id: str, batch_id: str, command: str, step: str) -> Path:
    return batch_command_root(task_id, batch_id, command) / "assistant_tasks" / f"{step}.json"


def batch_sources_dir(task_id: str, batch_id: str, entity_name: str) -> Path:
    return batch_command_root(task_id, batch_id, "download") / "sources" / entity_name


# ─── 对象同构目录（与 publish DataRoot 同构 + 过程阶段编号）─────────
# 真相源：docs/pipeline_directory_layout_spec.md。
# 实体对象 = batches/{batch}/entities/{domain}/{type}/{name}/
# 内容对象 = batches/{batch}/posts/{contentType}/{angle}/{title}/{seq}/
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


def batch_shared_dir(task_id: str, batch_id: str) -> Path:
    """批次级公共产物（跨对象共享，不属于任一对象）。"""
    return batch_root(task_id, batch_id) / "_shared"


def batch_audit_summary_path(task_id: str, batch_id: str) -> Path:
    """批次级审计摘要（脚本验收结果 + 抽检锚点）。"""
    return batch_shared_dir(task_id, batch_id) / "audit_summary.json"


def batch_audit_markdown_path(task_id: str, batch_id: str) -> Path:
    """批次级人工抽检清单。"""
    return batch_shared_dir(task_id, batch_id) / "audit_summary.md"


def batch_content_plan_packet_path(task_id: str, batch_id: str) -> Path:
    """证据驱动篇目规划包（content_plan checkpoint 产出）。"""
    return batch_shared_dir(task_id, batch_id) / "content_plan_packet.json"


def batch_run_journal_path(task_id: str, batch_id: str) -> Path:
    """批次运行问题→修复→规范缺口日记。"""
    return batch_shared_dir(task_id, batch_id) / "run_journal.md"


def batch_posts_root(task_id: str, batch_id: str) -> Path:
    """成品内容对象根（对象优先）：`batch/posts/{type}/{angle}/{title}/{seq}/`。"""
    return batch_root(task_id, batch_id) / "posts"


def batch_post_roots(task_id: str, batch_id: str) -> list[Path]:
    """成品 posts 根候选（存在的）：对象优先 `batch/posts`。"""
    roots = [batch_posts_root(task_id, batch_id)]
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r)
        if key in seen or not r.is_dir():
            continue
        seen.add(key)
        out.append(r)
    return out


def batch_manifest_path(task_id: str, batch_id: str) -> Path:
    """批次级公共信息：参数/env/salt/命令链/时间（不在对象目录重复）。"""
    return batch_root(task_id, batch_id) / "batch_manifest.json"


def batch_entity_object_dir(
    task_id: str, batch_id: str, domain: str, etype: str, name: str
) -> Path:
    return batch_root(task_id, batch_id) / "entities" / domain / etype / name


def batch_sources_root(task_id: str, batch_id: str) -> Path:
    """Canonical physical source-unit pool: `batch/sources/{sourceUnitId}/`."""
    return batch_root(task_id, batch_id) / "sources"


def batch_source_unit_dir(task_id: str, batch_id: str, source_unit_id: str) -> Path:
    # 可读命名契约：目录名保留中文实体名（\w 含 unicode），仅替换路径危险字符。
    unit_id = re.sub(r"[^\w.\-]+", "_", str(source_unit_id or "").strip()).strip("_")
    if not unit_id:
        unit_id = "source_unit"
    return batch_sources_root(task_id, batch_id) / unit_id


def batch_entity_stage_dir(
    task_id: str, batch_id: str, domain: str, etype: str, name: str, stage: str
) -> Path:
    return batch_entity_object_dir(task_id, batch_id, domain, etype, name) / stage


def batch_post_object_dir(
    task_id: str,
    batch_id: str,
    content_type: str,
    angle: str,
    title: str,
    seq: int = 1,
) -> Path:
    return (
        batch_root(task_id, batch_id)
        / "posts"
        / content_type
        / angle
        / title
        / str(seq)
    )


def batch_post_stage_dir(
    task_id: str,
    batch_id: str,
    content_type: str,
    angle: str,
    title: str,
    seq: int,
    stage: str,
) -> Path:
    return (
        batch_post_object_dir(task_id, batch_id, content_type, angle, title, seq) / stage
    )


def source_unit_dir(object_dir: Path, ordinal: int, source_id: str) -> Path:
    """Legacy object-local source-unit path for older fixtures only.

    Current production source units live under `batch/sources/{sourceUnitId}/`
    and objects only keep `1.download/source_refs.json` soft refs.
    """
    return object_dir / STAGE_DOWNLOAD / "sources" / f"{ordinal:02d}.{source_id}"


def relative_batch_ref(target: Path, task_id: str, batch_id: str) -> str:
    """把 batch 内绝对路径转成相对 batch 根的 POSIX 相对路径（发布/迁移友好）。

    用于 manifest/provenance 的 citedSourceRefs / sourceAssetRef / sourcePaths，
    禁止绝对路径进入发布契约。
    """
    base = batch_root(task_id, batch_id).resolve()
    return os.path.relpath(Path(target).resolve(), base).replace(os.sep, "/")


def relative_task_ref(target: Path, task_id: str) -> str:
    """相对 task 根的 POSIX 相对路径（实体成品在 task 根 entities/ 时用）。"""
    base = task_root(task_id).resolve()
    return os.path.relpath(Path(target).resolve(), base).replace(os.sep, "/")


# ─── 对象索引与批次工作区（规格 §14/§15；纯新增，零回归）─────────────
def object_index_path(object_dir: Path) -> Path:
    """对象索引 _object.json（实体过程对象根 / 内容对象根各一份）。"""
    return object_dir / "_object.json"


def batch_source_catalog_path(task_id: str, batch_id: str) -> Path:
    """受控来源类目（批次级共享，唯一真相源）。"""
    return batch_shared_dir(task_id, batch_id) / "source_catalog.json"


def batch_workflow_state_path(task_id: str, batch_id: str) -> Path:
    """workflow 状态属批次工作区，落 _shared（不进对象目录、不进 publish）。"""
    return batch_shared_dir(task_id, batch_id) / "task_workflow_state.json"


def batch_assistant_tasks_dir(task_id: str, batch_id: str) -> Path:
    """会话任务投递（批次工作区，可清理可重投）。"""
    return batch_shared_dir(task_id, batch_id) / "assistant_tasks"


def batch_workflow_packets_dir(task_id: str, batch_id: str) -> Path:
    """workflow 过程 packet 落点（批次工作区，按 stage 分文件）。"""
    return batch_shared_dir(task_id, batch_id) / "workflow_packets"


def batch_workflow_packet_path(task_id: str, batch_id: str, stage: str) -> Path:
    return batch_workflow_packets_dir(task_id, batch_id) / f"{stage}.json"


def batch_entity_page_input_path(
    task_id: str,
    batch_id: str,
    domain: str,
    etype: str,
    name: str,
) -> Path:
    """实体主页输入契约：batch 内对象过程 `3.compose/entity_page_input.json`。"""
    return batch_entity_stage_dir(task_id, batch_id, domain, etype, name, STAGE_COMPOSE) / "entity_page_input.json"


# ─── layout helpers ───────────────────────────────────────────────
def ensure_task_layout(task_id: str) -> Path:
    root = task_root(task_id)
    root.mkdir(parents=True, exist_ok=True)
    task_shared_dir(task_id).mkdir(parents=True, exist_ok=True)
    d = task_data(task_id)
    d.entities_dir().mkdir(exist_ok=True)
    return root


def ensure_batch_layout(task_id: str, batch_id: str, command: str) -> Path:
    cmd_root = batch_command_root(task_id, batch_id, command)
    (cmd_root / "inputs").mkdir(parents=True, exist_ok=True)
    (cmd_root / "results").mkdir(parents=True, exist_ok=True)
    (cmd_root / "assistant_tasks").mkdir(parents=True, exist_ok=True)
    return cmd_root


CREATOR_POOLS_ROOT = RUNTIME_ROOT / "creator_pools"
# user-pool 生成过程根（一次性过程层）；成品经 export 进入 service fixtures / publish。
USER_POOLS_ROOT = RUNTIME_ROOT / "user_pools"


def user_pool_batch_root(batch_id: str) -> Path:
    return USER_POOLS_ROOT / batch_id


def creator_pool_batch_root(vertical: str, batch_id: str) -> Path:
    return CREATOR_POOLS_ROOT / vertical / batch_id


def creator_pool_shared_dir(vertical: str, batch_id: str) -> Path:
    return creator_pool_batch_root(vertical, batch_id) / "_shared"


def creator_pool_object_dir(vertical: str, batch_id: str, creator_ref: str) -> Path:
    return creator_pool_batch_root(vertical, batch_id) / "creators" / creator_ref


def creator_pool_stage_dir(vertical: str, batch_id: str, creator_ref: str, stage: str) -> Path:
    return creator_pool_object_dir(vertical, batch_id, creator_ref) / stage
