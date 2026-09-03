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

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from core.control_types import OBJECT_STAGE_SEQUENCE, ReceiptStage
from core.data_root import DataRoot

# 代码仓库 data 根：schema 是受版本控制、不可手改的契约真相源，必须跟代码走，
# 不随运行时 QWQ_DATA_ROOT 漂移；隔离/多环境只覆盖运行时数据根，不应丢失契约。
_REPO_DATA_ROOT = Path(__file__).resolve().parents[2]
REPO_DATA_ROOT = _REPO_DATA_ROOT
# 仓库根（quwoquan_data 的上级）：服务侧 contracts/metadata 等跨工程契约真相源都挂在这里，
# 同样受版本控制、跟代码走，禁止用 DATA_ROOT.parent 推导（隔离根下会漂移到 /tmp/quwoquan_service）。
REPO_ROOT = _REPO_DATA_ROOT.parent
# 服务契约由每个领域服务自治；Data 只能按服务名读取其 contracts，不再读取已删除的
# 根级 metadata 聚合目录，也不接受运行环境覆盖仓内契约真相源。
SERVICE_DOMAINS_ROOT = REPO_ROOT / "quwoquan_service" / "services"


def service_contracts_root(service_name: str) -> Path:
    normalized = str(service_name or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9-]*-service", normalized):
        raise ValueError(f"invalid service contract owner: {service_name}")
    return SERVICE_DOMAINS_ROOT / normalized / "contracts"
DATA_ROOT = Path(os.environ.get("QWQ_DATA_ROOT", _REPO_DATA_ROOT))

# ─── 统一输出根（版本控制之外、工程目录之内）────────────────────────
# 仓内只保留可复用的输入契约与 canonical publish/**。所有可重跑执行物只有
# `.qwq_output/data/` 一个根：tasks/<executionId>、releases/<releaseId>、local/。
# 不再支持 QWQ_RUNTIME_ROOT、runtime/batches 或第二个 state 根。
_DEFAULT_OUTPUT_ROOT = REPO_ROOT / ".qwq_output"
OUTPUT_ROOT = Path(os.environ.get("QWQ_OUTPUT_ROOT") or _DEFAULT_OUTPUT_ROOT)

DATA_OUTPUT_ROOT = OUTPUT_ROOT / "data"
DATA_EXECUTIONS_ROOT = DATA_OUTPUT_ROOT / "tasks"
DATA_LOCAL_ROOT = DATA_OUTPUT_ROOT / "local"
DATA_CACHE_ROOT = DATA_LOCAL_ROOT / "cache"
DATA_WORKSPACE_ROOT = DATA_LOCAL_ROOT / "workspace"
RUNTIME_ROOT = DATA_WORKSPACE_ROOT
CANONICAL_PUBLISH_SIDECAR_ROOT = DATA_CACHE_ROOT / "canonical-publish"
SOURCE_ACQUISITION_ROOT = DATA_WORKSPACE_ROOT / "source-acquisition"
RELEASE_IDENTITY_INCIDENTS_ROOT = DATA_WORKSPACE_ROOT / "release-identity-incidents"
RELEASE_IDENTITY_INCIDENT_MIGRATIONS_ROOT = (
    DATA_WORKSPACE_ROOT / "release-identity-incident-migrations"
)
DATA_GC_WORKSPACE_ROOT = DATA_WORKSPACE_ROOT / "gc"
DATA_QUARANTINE_ROOT = DATA_WORKSPACE_ROOT / "quarantine"
RELEASE_ROOT = DATA_OUTPUT_ROOT / "releases"

# ─── content_library：内容字节的唯一物理归属 ──────────────────────────
# 库把「每个阶段复制一份字节」换成「一次入库、多处引用」：入库条目按 sha256 内容
# 寻址，一旦写入即不可变，任何阶段只保存指向库内条目的引用。
#
# 库根必须落在仓库工作树之外。媒体原始字节已刻意移出 Git（release 用 holdings
# 引用而非复制字节），库因此是这些字节的唯一持有者、无法从受版本控制真相源重建。
# 而 `.qwq_output/` 的契约恰恰是「随时可整个删除并重建」，仓库工作树内的其他
# gitignored 目录同样在 `git clean -xdf` 射程内——把不可重建资产放进任一处，都会
# 让一次例行清理静默销毁唯一副本。QWQ_LIBRARY_ROOT 覆盖默认位置（例如挂到独立
# 卷）；库与其引用方必须同卷，跨卷由 reference_library_entry 显式 fail-closed。
def _default_library_root() -> Path:
    xdg_data_home = str(os.environ.get("XDG_DATA_HOME") or "").strip()
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base / "quwoquan" / "content_library"


LIBRARY_ROOT = Path(
    os.environ.get("QWQ_LIBRARY_ROOT") or _default_library_root()
).expanduser()
# 媒体字节：source 阶段下载一次入库，成品与 publish 只引用同一条目。
LIBRARY_MEDIA_CAS_ROOT = LIBRARY_ROOT / "_media_cas"
# 受治理代码/输入字节：campaign capsule 与 execution bundle 共享同一份入库字节。
LIBRARY_SOURCE_CAS_ROOT = LIBRARY_ROOT / "_source_cas"
LIBRARY_CAS_ROOT_BY_KIND = {
    "media": LIBRARY_MEDIA_CAS_ROOT,
    "source": LIBRARY_SOURCE_CAS_ROOT,
}
# carried media：canonical 引用字节的受版本控制随体，不是库镜像。库落在仓外且不可
# 从版本控制重建，而 canonical 引用的编码视频、poster 与头像都是无上游可逐字节复现
# 的派生物——库一丢，已 approved 的对象就永久不可交付，所以这个子集随树受控。
# 按调用解析而非导入即冻结：它是发布事务的写入目标，冻结成模块常量会让「默认写真
# 仓库」对任何执行 apply 的进程生效。QWQ_CARRIED_MEDIA_ROOT 把随体指向临时根。
def carried_media_root() -> Path:
    override = str(os.environ.get("QWQ_CARRIED_MEDIA_ROOT") or "").strip()
    if override:
        return Path(override).expanduser()
    return _REPO_DATA_ROOT / "reference" / "golden_media"

# canonical publish 根的逻辑身份。物理位置是环境事实（QWQ_PUBLISH_ROOT / DATA_ROOT），
# 只由本模块解析；receipt 文档记录这个与位置无关的身份，不再内嵌仓库相对路径。
CANONICAL_PUBLISH_ROOT_REF = "canonical-publish"

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
EXECUTION_ROOT_DIRECTORIES = (
    ReceiptStage.PLAN.value,
    ReceiptStage.SOURCES.value,
    "entities",
    "posts",
    "_shared",
    "evidence",
)
EXECUTION_ROOT_FILES = ("execution_manifest.json", "publish_ref.json")
EXECUTION_ROOT_ALLOWED_ENTRIES = frozenset(
    (*EXECUTION_ROOT_DIRECTORIES, *EXECUTION_ROOT_FILES)
)

# Discovery and deduplication facts remain execution evidence.  They are not
# provider accounting and must stay distinct from any billing concern.
EXECUTION_SHARED_ALLOWED_ENTRIES = frozenset({
    "asset_id_registry.json",
    "receipts",
    "stage-open",
})
EXECUTION_SHARED_AUTHORITATIVE_ENTRIES = EXECUTION_SHARED_ALLOWED_ENTRIES
EXECUTION_SHARED_RECLAIMABLE_ENTRIES = frozenset({"workspace"})

def execution_shared_entry_role(name: str) -> str:
    if name in EXECUTION_SHARED_AUTHORITATIVE_ENTRIES:
        return "authoritative"
    if name in EXECUTION_SHARED_RECLAIMABLE_ENTRIES or name.startswith("tmp_"):
        return "reclaimable"
    return "unknown"

WORKSPACE_ROOT_BY_COMMAND = {
    "source": "source",
    "homepage": "homepage",
    "post": "post",
    "release": "release",
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
    r"[a-z][a-z0-9-]*--[a-z0-9][a-z0-9-]*--(pilot|scale|full)-\d{3,}$"
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


def canonical_publish_sidecar_root(publish_root: Path | None = None) -> Path:
    """Return the governed disposable sidecar directory for one publish root.

    The process fence and the inventory index are derived state: both are
    rebuilt from the canonical tree whenever they are absent. They still cannot
    live inside canonical ``publish/`` (that tree is audited and version
    controlled) nor inside one execution work package, so they belong in
    the disposable cache under the governed output root. Anywhere outside
    ``.qwq_output`` — the system temporary directory in particular — they are
    exempt from the output budget, invisible to ``release gc``, outside the
    pytest isolation root, and free to accumulate across repositories and
    sessions. A stable digest of the resolved publish root keeps every clone of
    the same tree on one fence and one index.
    """

    resolved_root = (publish_root or PUBLISH_ROOT).resolve()
    digest = hashlib.sha256(str(resolved_root).encode("utf-8")).hexdigest()
    return CANONICAL_PUBLISH_SIDECAR_ROOT / digest[:20]


def publish_lock_path(publish_root: Path | None = None) -> Path:
    """Return one process lock shared by every clone of the same publish root."""

    return canonical_publish_sidecar_root(publish_root) / "publish.lock"


# ─── publish 单一主线（已去版本化）───────────────────────────────
def publish_meta_path() -> Path:
    return PUBLISH_ROOT / "publish_meta.json"


# ─── 同构路径（runtime task 与 publish 共用）─────────────────────
# ─── publish 同构（单一主线）─────────────────────────────────────


# ─── release 输出（供服务端 bulk import 消费）─────────────────────










_LABEL_STRIP_RE = re.compile(r"[\s/\\:]+")
_INTENT_LABEL_MAX = 64






















# ─── 对象同构目录（与 publish DataRoot 同构 + 过程阶段编号）─────────
# 实体对象 = tasks/{executionId}/entities/{domain}/{type}/{name}/
# 内容对象 = tasks/{executionId}/posts/{contentType}/{angle}/{title}/{seq}/
# 对象目录下过程阶段统一编号；成品落对象根（promote 时与 publish 同名直拷）。
STAGE_DOWNLOAD = ReceiptStage.DOWNLOAD.value
STAGE_QUALITY = ReceiptStage.QUALITY.value
STAGE_COMPOSE = ReceiptStage.COMPOSE.value
STAGE_DRAFT = ReceiptStage.DRAFT.value
STAGE_REVIEW = ReceiptStage.REVIEW.value
# 实体/内容共享同一阶段骨架，差异只体现在阶段产物内容；阶段名来自 receipt 协议闭集。
OBJECT_STAGES = tuple(stage.value for stage in OBJECT_STAGE_SEQUENCE)




































# ─── 对象索引与批次工作区（规格 §14/§15；纯新增，零回归）─────────────














# ─── layout helpers ───────────────────────────────────────────────
from core.execution_paths import (  # noqa: F401
    ensure_execution_command_layout,
    ensure_execution_layout,
    ensure_object_stages,
    env_data_release_evidence_ref,
    env_data_release_run_root,
    execution_assistant_task,
    execution_command_root,
    execution_data,
    execution_entity_object_dir,
    execution_entity_page_input_path,
    execution_entity_stage_dir,
    execution_id_from_dir,
    execution_inputs_dir,
    execution_manifest_path,
    execution_post_object_dir,
    execution_post_roots,
    execution_post_stage_dir,
    execution_posts_root,
    execution_results_dir,
    execution_root_entry,
    execution_shared_dir,
    execution_source_unit_dir,
    execution_sources_dir,
    execution_sources_root,
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
    sanitize_intent_label,
)
