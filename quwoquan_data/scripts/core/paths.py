"""源码、execution 输出和独立内容仓的根路径。

execution 保持冻结的过程目录；publish 按 publish_layout 定位，身份显式存储。
媒体和采用来源随对象，taxonomy authoring 仍属源码 control plane。
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from core.control_types import OBJECT_STAGE_SEQUENCE, ReceiptStage
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
# 源码仓保留可复用输入契约，内容在独立 publish 仓。可重跑执行物只有
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
RELEASE_IDENTITY_INCIDENTS_ROOT = DATA_WORKSPACE_ROOT / "release-identity-incidents"
RELEASE_IDENTITY_INCIDENT_MIGRATIONS_ROOT = (
    DATA_WORKSPACE_ROOT / "release-identity-incident-migrations"
)
DATA_GC_WORKSPACE_ROOT = DATA_WORKSPACE_ROOT / "gc"
DATA_QUARANTINE_ROOT = DATA_WORKSPACE_ROOT / "quarantine"
RELEASE_ROOT = DATA_OUTPUT_ROOT / "releases"

# 采集复用库保持仓外 CAS；execution 可引用它，完整发布包不依赖它存在。
# 原始未采用媒体不能从源码再生，因此仍不属于可任意删除的运行输出。
# publish 与 release 的最终采用媒体为独立随体字节，不共享可写 inode。
def _default_library_root() -> Path:
    xdg_data_home = str(os.environ.get("XDG_DATA_HOME") or "").strip()
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base / "quwoquan" / "content_library"


LIBRARY_ROOT = Path(
    os.environ.get("QWQ_LIBRARY_ROOT") or _default_library_root()
).expanduser()
# 来源阶段下载一次入库；发布事务从核验后的原件生成独立随体包。
LIBRARY_MEDIA_CAS_ROOT = LIBRARY_ROOT / "_media_cas"
# 受治理代码/输入字节：source capsule 与 execution bundle 共享同一份入库字节。
LIBRARY_SOURCE_CAS_ROOT = LIBRARY_ROOT / "_source_cas"
LIBRARY_CAS_ROOT_BY_KIND = {
    "media": LIBRARY_MEDIA_CAS_ROOT,
    "source": LIBRARY_SOURCE_CAS_ROOT,
}
# golden_media 是对象随体媒体的独立摘要备份，不进 Git。派生视频等不能按
# sourceUrl 原样重取；缺失报告来源只为溯源，不作可重建承诺。
# QWQ_CARRIED_MEDIA_ROOT 可指向异卷备份；同机同卷两目录不代表抗磁盘故障。
def default_carried_media_root() -> Path:
    xdg_data_home = str(os.environ.get("XDG_DATA_HOME") or "").strip()
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base / "quwoquan" / "golden_media"


def carried_media_root() -> Path:
    override = str(os.environ.get("QWQ_CARRIED_MEDIA_ROOT") or "").strip()
    if override:
        return Path(override).expanduser()
    return default_carried_media_root()

# canonical publish 根的逻辑身份。物理位置是环境事实（QWQ_PUBLISH_ROOT / DATA_ROOT），
# 只由本模块解析；receipt 文档记录这个与位置无关的身份，不再内嵌仓库相对路径。
CANONICAL_PUBLISH_ROOT_REF = "canonical-publish"

# 独立内容仓与源码 worktree 平级；实际入口须核验 repository.json，不能自动建空池。
# QWQ_DATA_ROOT / OUTPUT_ROOT 不再决定 canonical 根；测试必须显式注入隔离发布仓。
PUBLISH_ROOT = Path(os.environ.get("QWQ_PUBLISH_ROOT") or REPO_ROOT.parent / "publish").expanduser()
# terminal producer 事实随内容仓持久保存，不在源码仓再维护一份发布事实。
REFERENCE_RELEASES_ROOT = PUBLISH_ROOT / "releases"
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
    "0.plan",
    "sources",
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
    """所有源码工作树共享内容仓的锁和可重建索引，不随 OUTPUT_ROOT 漂移。"""
    from core.publish_repository import repository_sidecar_root

    return repository_sidecar_root(publish_root or PUBLISH_ROOT)


def publish_lock_path(publish_root: Path | None = None) -> Path:
    """Return one process lock shared by every clone of the same publish root."""

    return canonical_publish_sidecar_root(publish_root) / "publish.lock"


# 发布仓身份由 repository.json 声明；不另存 publish_meta 最新指针。


# ─── release 输出（供服务端 bulk import 消费）─────────────────────










_LABEL_STRIP_RE = re.compile(r"[\s/\\:]+")
_INTENT_LABEL_MAX = 64






















# execution 对象保留冻结的 targetRef 及过程阶段；不得由发布分区反推其身份。
# 最终包由 publisher 定位到独立内容仓，不再与 execution 同名直拷。
STAGE_DOWNLOAD = ReceiptStage.DOWNLOAD.value
STAGE_DRAFT = ReceiptStage.DRAFT.value
STAGE_REVIEW = ReceiptStage.REVIEW.value
# 实体/内容共享同一阶段骨架，差异只体现在阶段产物内容；阶段名来自 receipt 协议闭集。
OBJECT_STAGES = tuple(stage.value for stage in OBJECT_STAGE_SEQUENCE)




































# ─── 对象索引与批次工作区（规格 §14/§15；纯新增，零回归）─────────────














# ─── layout helpers ───────────────────────────────────────────────
from core.execution_paths import (  # noqa: F401
    ensure_execution_layout,
    ensure_object_stages,
    env_data_release_evidence_ref,
    env_data_release_run_root,
    execution_data,
    execution_entity_object_dir,
    execution_entity_stage_dir,
    execution_id_from_dir,
    execution_manifest_path,
    execution_post_object_dir,
    execution_post_roots,
    execution_post_stage_dir,
    execution_posts_root,
    execution_root_entry,
    execution_shared_dir,
    execution_source_unit_dir,
    execution_sources_root,
    executions_root,
    iter_all_execution_dirs,
    iter_execution_ids,
    object_index_path,
    object_source_unit_dir,
    relative_execution_ref,
    release_manifest,
    release_ref,
    release_root,
    sanitize_intent_label,
)
