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
import os
from pathlib import Path

DATA_ROOT = Path(os.environ.get("QWQ_DATA_ROOT", Path(__file__).resolve().parents[2]))
RUNTIME_ROOT = Path(os.environ.get("QWQ_RUNTIME_ROOT", DATA_ROOT / "runtime"))
PUBLISH_ROOT = Path(os.environ.get("QWQ_PUBLISH_ROOT", DATA_ROOT / "publish"))
RELEASE_ROOT = Path(os.environ.get("QWQ_RELEASE_ROOT", DATA_ROOT / "release"))
SCHEMA_ROOT = DATA_ROOT / "schema"
SOP_ROOT = DATA_ROOT / "sop"

TASKS_ROOT = RUNTIME_ROOT / "tasks"
# committed 任务规格根（受版本控制；与 runtime/tasks 同 taskId 对应）
COMMITTED_TASKS_ROOT = Path(os.environ.get("QWQ_COMMITTED_TASKS_ROOT", DATA_ROOT / "tasks"))
COMMANDS = ("explore", "build", "download", "produce", "publish")


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
    "batches",
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
# committed: tasks/<taskId>/   runtime: runtime/tasks/<taskId>/（task_root 已支持嵌套）
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


def _task_legacy_root_path(task_id: str, filename: str) -> Path:
    return task_root(task_id) / filename


def resolve_existing_task_shared_path(task_id: str, filename: str) -> Path:
    """读取兼容：优先 `_shared/`，若历史根路径仍存在则回退读取旧位。"""
    canonical = _task_shared_path(task_id, filename)
    if canonical.exists():
        return canonical
    legacy = _task_legacy_root_path(task_id, filename)
    if legacy.exists():
        return legacy
    return canonical


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
def batch_root(task_id: str, batch_id: str) -> Path:
    return task_root(task_id) / "batches" / batch_id


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


def batch_shared_dir(task_id: str, batch_id: str) -> Path:
    """批次级公共产物（跨对象共享，不属于任一对象）。"""
    return batch_root(task_id, batch_id) / "_shared"


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
    """对象的来源单元：{object}/1.download/sources/{NN}.{sourceKind}/（NN 两位补零）。

    来源是自包含单元（source.md + meta.json + assets/ + assets/index.json），
    禁止把图片散落到对象级 images/。
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
