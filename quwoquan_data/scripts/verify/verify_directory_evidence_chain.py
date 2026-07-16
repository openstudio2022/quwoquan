"""Execution 工作包与资产证据链静态门。

扫描唯一工作包：
  tasks/{executionId}/entities/{domain}/{type}/{name}/
  tasks/{executionId}/posts/{contentType}/{angle}/{title}/{seq}/

阻断（BLOCK）：
1. 对象内出现散落 images/（图片必须在来源单元 assets/ 内）。
2. manifest.json / provenance.json 含绝对路径（citedSourceRefs/sourceAssetRef/sourcePaths/...）。
3. article.md / page.md 出现机械收尾标题（它到底适合谁 等）。
4. 来源单元为无类别 weather_* 普通来源。
5. manifest.assets[].sourceAssetRef 指向的源图缺失（资产闭环断裂）。
6. 【命名门】对象目录层级/命名不符（posts/{type}/{angle}/{title}/{seq}、entities/{domain}/{type}/{name}、
   阶段子目录 ∉ 编号阶段∪assets、来源单元 ∉ {NN}.{kind}）。
7. 【回退门】`_shared/workspace/post` 的 stage-first 扁平面被重新写入，
   即 M3/M4 已迁对象根的成品/草稿/brief/阶段报告/账本不得回退。
8. 【同步门】成品对象目录与 `_shared/content_object_index.json` 路由漂移（对象在盘上但未登记）。
9. 【证据面门】execution/_shared 出现未登记条目（不属于 paths.EXECUTION_SHARED_AUTHORITATIVE_ENTRIES
   权威证据，也不属于 EXECUTION_SHARED_RECLAIMABLE_ENTRIES / `tmp_*` 可清理层）。

旧 stage-first 布局（download/sources）已废弃；若被写入，按回退门直接 BLOCK。

可直接运行：python3 quwoquan_data/scripts/verify/verify_directory_evidence_chain.py [--execution-id ID]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from content.execution.object_scan import iter_execution_object_dirs  # noqa: E402
from core.article_package import compute_document_sha256  # noqa: E402
from core.io import read_json  # noqa: E402
from core.image_rules import pixel_size_issue, relevance_issue  # noqa: E402
from core.paths import (  # noqa: E402
    OBJECT_STAGES,
    DATA_EXECUTIONS_ROOT,
    EXECUTION_ROOT_ALLOWED_ENTRIES,
    execution_root,
    execution_shared_entry_role,
    execution_id_from_dir,
    iter_all_execution_dirs,
    normalize_execution_id,
)
from core.asset_identity import parse_post_asset_id  # noqa: E402
from core.prose_style import mechanical_ending_title_issues  # noqa: E402
from core.source_catalog import source_unit_category_issues  # noqa: E402
from core.entity_object import execution_entity_type_conflicts  # noqa: E402
from verify.verify_asset_id_zero_collision import scan_execution as scan_asset_ids  # noqa: E402

_REF_FIELDS = (
    "baseSourceRef",
    "citedSourceRefs",
    "sourceAssetRef",
    "sourceRef",
    "sourcePaths",
    "citedSourcePaths",
    "sourceUnitRef",
    "metaRef",
    "qualityRef",
    "cleanSourceRef",
    "objectRef",
    "draftArticleRef",
    "finalArticleRef",
    "composeSnapshotRef",
)
_UNIT_RE = __import__("re").compile(r"^(\d{2})\.(.+)$")
_OBJECT_CHILD_ALLOW = set(OBJECT_STAGES) | {"assets", "evidence"}
# execution 顶层只允许稳定工作包合同；内部命令临时面统一在 `_shared/workspace/`。
_EXECUTION_TOP_ALLOW = set(EXECUTION_ROOT_ALLOWED_ENTRIES)

# M3/M4 已迁对象根的 post 扁平面：若被重新写入（非空）即 stage-first 回退，BLOCK。
_REGRESSION_FACES = (
    ("_shared/workspace/post/posts", "manifest.json", True, "成品须落对象根 posts/{type}/{angle}/{title}/{seq}"),
    ("_shared/workspace/post/inputs/compose", "*.json", False, "compose 输入须落对象 3.compose/brief.json"),
    ("_shared/workspace/post/drafts", "*", True, "草稿须落对象 3.compose/4.draft"),
    ("_shared/workspace/post/results/compose", "*.json", False, "compose 报告须落对象 5.review"),
    ("_shared/workspace/post/results/review", "*.json", False, "review 报告须落对象 5.review"),
    ("_shared/workspace/post/results/quality_analysis", "*.json", False, "quality 报告须落对象 2.quality"),
    ("_shared/workspace/post/results/media_check", "*.json", False, "media_check 报告须落对象 5.review"),
    ("_shared/workspace/post/review/ledger", "*.json", False, "复核账本须落对象 5.review/review_ledger.json"),
    ("_shared/workspace/post/review/entities", "*.json", False, "复核实体边车须落对象 5.review/review_entities.json"),
)


def scan_execution_root(execution_id: str) -> list[str]:
    """Execution 根目录只允许稳定工作包条目。"""
    root = execution_root(execution_id)
    if not root.is_dir():
        return [f"execution not found: {root}"]
    issues: list[str] = []
    for entry in sorted(root.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.name in EXECUTION_ROOT_ALLOWED_ENTRIES:
            continue
        issues.append(
            f"execution/{entry.name}: 非法顶层条目（仅允许 {sorted(EXECUTION_ROOT_ALLOWED_ENTRIES)}）"
        )
    return issues


def _is_absolute_ref(value: str) -> bool:
    s = str(value or "")
    return s.startswith("/") or "/Users/" in s or (len(s) > 1 and s[1] == ":")


def _scan_json_for_absolute(path: Path, issues: list[str]) -> None:
    try:
        data = read_json(path)
    except Exception as exc:  # noqa: BLE001
        issues.append(f"{path}: unreadable ({exc})")
        return

    def walk(node, key=""):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, str):
            if key in _REF_FIELDS or key in ("path", "objectKey"):
                if key == "objectKey":
                    return
                if _is_absolute_ref(node):
                    issues.append(f"{path}: 绝对路径进入发布契约 [{key}]={node}")

    walk(data)


def _source_refs_issues(obj: Path, execution: Path) -> list[str]:
    """post `1.download/source_refs.json` 必须满足单底稿零参考宪法 v2：

    - `sources` 长度恒为 1（唯一底稿来源单元，`role == base`）。
    - `baseSourceRef` 非空且与该唯一来源一致，源文件/来源单元可回查。
    - 禁止 `citedSourceRefs` / `sourcePaths` / `referenceSourceRefs` 等第二来源或全量索引。
    - 禁止内联 `sourceMarkdown` / `sourceCleanMarkdown` 原文镜像（只留 sha256）。
    - 文件体积受限（避免回归到全文镜像的臃肿索引）。
    """
    from core.post_evidence_chain import SOURCE_REFS_MAX_BYTES

    rel = obj.relative_to(execution)
    has_final = (obj / "article.md").is_file() or (obj / "gallery.md").is_file()
    if not has_final:
        return []
    snapshot_path = obj / "1.download" / "source_refs.json"
    if not snapshot_path.is_file():
        return [f"{rel}: 内容对象缺 `1.download/source_refs.json`（post 必须自持来源索引）"]
    try:
        data = read_json(snapshot_path)
    except Exception as exc:  # noqa: BLE001
        return [f"{rel}: source_refs.json unreadable ({exc})"]
    if not isinstance(data, dict):
        # agent 产物是外部输入：顶层写成数组/标量属于契约违规，必须报 issue 而非崩溃。
        return [
            f"{rel}: source_refs.json 顶层必须是 object（实得 {type(data).__name__}）"
        ]
    issues: list[str] = []
    if snapshot_path.stat().st_size > SOURCE_REFS_MAX_BYTES:
        issues.append(
            f"{rel}: source_refs.json 过大（{snapshot_path.stat().st_size}B > {SOURCE_REFS_MAX_BYTES}B），"
            "疑似回归到全文镜像/多源索引"
        )
    for banned in ("citedSourceRefs", "referenceSourceRefs", "sourcePaths"):
        if data.get(banned):
            issues.append(
                f"{rel}: source_refs.json 禁止出现 `{banned}`（单底稿零参考宪法：无第二来源/全量索引）"
            )
    sources = data.get("sources") or []
    if not isinstance(sources, list) or len(sources) != 1:
        issues.append(
            f"{rel}: source_refs.json.sources 长度必须为 1（单底稿），实得 {len(sources) if isinstance(sources, list) else '非法'}"
        )
        return issues
    entry = sources[0]
    if not isinstance(entry, dict):
        return [f"{rel}: source_refs.json.sources 含非法条目"]
    source_ref = str(entry.get("sourceRef") or "")
    unit_ref = str(entry.get("sourceUnitRef") or "")
    base_source_ref = str(data.get("baseSourceRef") or "")
    if not base_source_ref:
        issues.append(f"{rel}: source_refs.json.baseSourceRef 为空（必须声明唯一底稿）")
    if not source_ref:
        issues.append(f"{rel}: source_refs.json.sources[0] 缺 sourceRef")
        return issues
    if base_source_ref and base_source_ref != source_ref:
        issues.append(
            f"{rel}: baseSourceRef 与唯一来源不一致：{base_source_ref} != {source_ref}"
        )
    role = str(entry.get("role") or "base")
    if role != "base":
        issues.append(f"{rel}: source_refs.json.sources[0].role 必须为 base，实得 {role}")
    if entry.get("sourceMarkdown") is not None or entry.get("sourceCleanMarkdown") is not None:
        issues.append(f"{rel}: source_refs.json 禁止内联 sourceMarkdown 原文镜像（只留 sha256）")
    source_path = execution / source_ref
    if not source_path.is_file():
        issues.append(f"{rel}: sourceRef 源文件缺失（证据链断裂）：{source_ref}")
    elif unit_ref and not (execution / unit_ref).is_dir():
        issues.append(f"{rel}: sourceUnitRef 源单元缺失（不可回查）：{unit_ref}")
    return issues


def _object_source_unit_records(obj: Path, execution: Path) -> list[tuple[str, str]]:
    """Return (sourceId, sourceKind) pairs from canonical object source refs."""
    snapshot_path = obj / "1.download" / "source_refs.json"
    if not snapshot_path.is_file():
        return []
    try:
        data = read_json(snapshot_path)
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(data, dict):
        # 顶层坏类型（agent 写成数组等）：无可提取记录；契约违规由
        # _source_refs_issues / download gate 负责报 issue，这里不得崩溃。
        return []
    rows = data.get("sources") or []
    if not isinstance(rows, list):
        return []
    records: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("sourceId") or "").strip()
        meta_ref = str(row.get("metaRef") or "").strip()
        unit_ref = str(row.get("sourceUnitRef") or "").strip()
        source_ref = str(row.get("sourceRef") or "").strip()
        meta_path = execution / meta_ref if meta_ref else Path()
        if not meta_path.is_file() and unit_ref:
            meta_path = execution / unit_ref / "meta.json"
        if not meta_path.is_file() and source_ref:
            meta_path = execution / source_ref
            meta_path = meta_path.parent / "meta.json"
        category = ""
        if meta_path.is_file():
            try:
                meta = read_json(meta_path)
                category = str(meta.get("sourceKind") or meta.get("category") or "")
                source_id = source_id or str(meta.get("sourceId") or "")
            except Exception:  # noqa: BLE001
                category = ""
        records.append((source_id, category))
    return records


def _finalization_report_issues(obj: Path, execution: Path) -> list[str]:
    rel = obj.relative_to(execution)
    has_final = (obj / "article.md").is_file() or (obj / "gallery.md").is_file()
    if not has_final:
        return []
    report_path = obj / "5.review" / "finalization_report.json"
    if not report_path.is_file():
        return [f"{rel}: 缺 `5.review/finalization_report.json`（draft->final 差异报告必须落盘）"]
    try:
        data = read_json(report_path)
    except Exception as exc:  # noqa: BLE001
        return [f"{rel}: finalization_report.json unreadable ({exc})"]
    issues: list[str] = []
    draft_ref = str(data.get("draftArticleRef") or "")
    final_ref = str(data.get("finalArticleRef") or "")
    if draft_ref != "4.draft/draft.article.md":
        issues.append(f"{rel}: finalization_report.draftArticleRef 非法：{draft_ref}")
    if final_ref != "article.md":
        issues.append(f"{rel}: finalization_report.finalArticleRef 非法：{final_ref}")
    draft_path = obj / "4.draft" / "draft.article.md"
    final_path = obj / "article.md"
    if not draft_path.is_file():
        issues.append(f"{rel}: finalization_report 引用的 draft.article.md 缺失")
        return issues
    if not final_path.is_file():
        issues.append(f"{rel}: finalization_report 引用的 article.md 缺失")
        return issues
    draft_text = draft_path.read_text(encoding="utf-8")
    final_text = final_path.read_text(encoding="utf-8")
    if str(data.get("draftSha256") or "") != compute_document_sha256(draft_text):
        issues.append(f"{rel}: finalization_report.draftSha256 与 draft.article.md 不一致")
    if str(data.get("finalSha256") or "") != compute_document_sha256(final_text):
        issues.append(f"{rel}: finalization_report.finalSha256 与 article.md 不一致")
    return issues


def _entity_quality_stage_issues(obj: Path, execution: Path) -> list[str]:
    rel = obj.relative_to(execution)
    if not ((obj / "page.md").is_file() or (obj / "_entity.json").is_file()):
        return []
    path = obj / "2.quality" / "quality_analysis.json"
    if not path.is_file():
        return [f"{rel}: 缺 `2.quality/quality_analysis.json`（实体主页必须显式记录底稿选择/来源准备度）"]
    try:
        data = read_json(path)
    except Exception as exc:  # noqa: BLE001
        return [f"{rel}: quality_analysis.json unreadable ({exc})"]
    issues: list[str] = []
    source_paths = data.get("sourcePaths") or []
    if not isinstance(source_paths, list) or not source_paths:
        issues.append(f"{rel}: quality_analysis.sourcePaths 为空（实体主页必须声明可回查来源）")
    recommendation = str(data.get("recommendation") or "")
    if recommendation not in {"proceed", "needs_source_repair"}:
        issues.append(f"{rel}: quality_analysis.recommendation 非法：{recommendation}")
    base_draft = data.get("baseDraft")
    if recommendation == "proceed":
        if not isinstance(base_draft, dict):
            issues.append(f"{rel}: quality_analysis.recommendation=proceed 但 baseDraft 缺失")
        elif not str(base_draft.get("sourceRef") or "").strip():
            issues.append(f"{rel}: quality_analysis.baseDraft.sourceRef 缺失")
    return issues


def _entity_review_sidecar_issues(obj: Path, execution: Path) -> list[str]:
    rel = obj.relative_to(execution)
    if not ((obj / "page.md").is_file() or (obj / "_entity.json").is_file()):
        return []
    review_dir = obj / "5.review"
    review_path = review_dir / "review.json"
    provenance_path = review_dir / "provenance.json"
    finalization_path = review_dir / "finalization_report.json"
    draft_path = obj / "4.draft" / "page.md"
    issues: list[str] = []
    if not draft_path.is_file():
        issues.append(f"{rel}: 缺 `4.draft/page.md`（实体主页 draft→final 必须留档）")
    review: dict[str, Any] | None = None
    if not review_path.is_file():
        issues.append(f"{rel}: 缺 `5.review/review.json`（实体主页必须有独立审校结果）")
    else:
        try:
            review = read_json(review_path)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{rel}: review.json unreadable ({exc})")
        else:
            decision = str(review.get("decision") or "")
            if decision not in {"approved", "revision_needed"}:
                issues.append(f"{rel}: review.decision 非法：{decision}")
            checks = review.get("checks") or {}
            if not isinstance(checks, dict):
                issues.append(f"{rel}: review.checks 须为对象")
            else:
                source_qualification = checks.get("sourceQualification") or {}
                if not isinstance(source_qualification, dict):
                    issues.append(f"{rel}: review.checks.sourceQualification 须为对象")
                elif "passed" not in source_qualification:
                    issues.append(f"{rel}: review.checks.sourceQualification.passed 缺失")
                page_quality = checks.get("entityPageQuality") or {}
                if not isinstance(page_quality, dict):
                    issues.append(f"{rel}: review.checks.entityPageQuality 须为对象")
                elif "passed" not in page_quality:
                    issues.append(f"{rel}: review.checks.entityPageQuality.passed 缺失")
    if not provenance_path.is_file():
        issues.append(f"{rel}: 缺 `5.review/provenance.json`（实体主页必须可追责原始来源与 agent 输入）")
    else:
        try:
            provenance = read_json(provenance_path)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{rel}: provenance.json unreadable ({exc})")
        else:
            originals = provenance.get("originalSources") or []
            if not isinstance(originals, list) or not originals:
                issues.append(f"{rel}: provenance.originalSources 为空（实体主页来源不可追责）")
            final = provenance.get("final") or {}
            if str(final.get("generator") or "") != "agent":
                issues.append(f"{rel}: provenance.final.generator 必须为 agent")
            if not str((provenance.get("agentInput") or {}).get("writingPack") or "").strip():
                issues.append(f"{rel}: provenance.agentInput.writingPack 缺失")
    if not finalization_path.is_file():
        issues.append(f"{rel}: 缺 `5.review/finalization_report.json`（实体主页 draft->final 差异报告必须落盘）")
    else:
        try:
            finalization = read_json(finalization_path)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{rel}: finalization_report.json unreadable ({exc})")
        else:
            if str(finalization.get("draftArticleRef") or "") != "4.draft/page.md":
                issues.append(f"{rel}: finalization_report.draftArticleRef 非法：{finalization.get('draftArticleRef')}")
            if str(finalization.get("finalArticleRef") or "") != "page.md":
                issues.append(f"{rel}: finalization_report.finalArticleRef 非法：{finalization.get('finalArticleRef')}")
            if not str(finalization.get("draftSha256") or "").strip():
                issues.append(f"{rel}: finalization_report.draftSha256 缺失")
            if not str(finalization.get("finalSha256") or "").strip():
                issues.append(f"{rel}: finalization_report.finalSha256 缺失")
    return issues


def _naming_issues(obj: Path, rel: Path) -> list[str]:
    """命名门：对象层级 + 阶段子目录 + 来源单元命名（规格 §2.4/§3）。"""
    issues: list[str] = []
    parts = rel.parts
    if parts and parts[0] == "posts":
        if len(parts) != 5 or not parts[4].isdigit():
            issues.append(f"{rel}: 内容对象命名违规（应为 posts/{{type}}/{{angle}}/{{title}}/{{seq}}，seq 为数字）")
    elif parts and parts[0] == "entities":
        if len(parts) != 4:
            issues.append(f"{rel}: 实体对象命名违规（应为 entities/{{domain}}/{{type}}/{{name}}）")
    for child in sorted(obj.iterdir()):
        if child.is_dir() and child.name not in _OBJECT_CHILD_ALLOW:
            issues.append(
                f"{rel}: 非法对象子目录 '{child.name}'（仅允许编号阶段 {list(OBJECT_STAGES)}、assets 或 evidence）"
            )
    sources_dir = obj / "1.download" / "sources"
    if sources_dir.is_dir():
        for unit in sorted(sources_dir.iterdir()):
            if unit.is_dir() and not _UNIT_RE.match(unit.name):
                issues.append(f"{rel}: 来源单元命名违规 '{unit.name}'（应为 NN.kind）")
    return issues


def _execution_shared_issues(execution: Path) -> list[str]:
    """证据面门：execution/_shared 条目 ⊆ 权威证据 ∪ 可清理层（真相源 paths）。

    - authoritative：不可重算真相源，readiness/审计只认这些条目。
    - reclaimable（含 `tmp_*`）：调试/过程层，允许存在、可随时清理，不算证据。
    - unknown：未登记条目直接 BLOCK，防止证据面无限膨胀出第二真相源。
    """
    issues: list[str] = []
    shared_dir = execution / "_shared"
    if not shared_dir.is_dir():
        return issues
    for entry in sorted(shared_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        if execution_shared_entry_role(entry.name) == "unknown":
            issues.append(
                f"_shared/{entry.name}: 未登记的 execution 共享条目"
                "（须先在 paths.EXECUTION_SHARED_AUTHORITATIVE_ENTRIES 或 "
                "EXECUTION_SHARED_RECLAIMABLE_ENTRIES 登记角色）"
            )
    return issues


def _top_level_issues(execution: Path) -> list[str]:
    """顶层结构门：execution 根条目 ⊆ 允许集，拦截漂移/散落文件。"""
    issues: list[str] = []
    for entry in sorted(execution.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.name not in _EXECUTION_TOP_ALLOW:
            issues.append(
                f"{entry.name}: 非法 execution 顶层条目（仅允许 {sorted(_EXECUTION_TOP_ALLOW)}）"
            )
    return issues


def _regression_issues(execution: Path) -> list[str]:
    """回退门：post 已迁对象根的扁平面被重新写入即 BLOCK。"""
    issues: list[str] = []
    for relpath, pattern, recursive, msg in _REGRESSION_FACES:
        d = execution / Path(relpath)
        if not d.is_dir():
            continue
        matches = d.rglob(pattern) if recursive else d.glob(pattern)
        if any(m.is_file() for m in matches):
            issues.append(f"{relpath}: stage-first 回退禁止 — {msg}")
    return issues


# 批次级来源单元可读命名（spec §3）：{实体名}__{sourceKind}__{hash8}。
_SOURCE_UNIT_READABLE_RE = re.compile(r"^.+__[A-Za-z0-9_\-]+__[0-9a-f]{8}$")
_SOURCE_UNIT_LEGACY_HASH_RE = re.compile(r"^su_[0-9a-f]{20}$")

# 成品资产命名门允许的图片扩展（对象 assets/ 下的成品图）。
_PRODUCT_ASSET_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _execution_assets_naming_issues(execution: Path) -> list[str]:
    """命名门：对象 assets/ 成品图片文件名必须是 v2 assetId
    （实体_角色_图注_批次号_hash，见 asset_id_zero_collision_spec §3）。

    与 sources 命名门平级：旧 v1 四段格式（无图注段）在新批次成品中禁止回归。
    """
    issues: list[str] = []
    for obj in iter_execution_object_dirs(execution):
        assets_dir = obj / "assets"
        if not assets_dir.is_dir():
            continue
        rel = obj.relative_to(execution)
        for item in sorted(assets_dir.iterdir()):
            if not item.is_file() or item.suffix.lower() not in _PRODUCT_ASSET_EXTS:
                continue
            stem = item.stem
            try:
                parsed = parse_post_asset_id(stem)
            except ValueError:
                issues.append(
                    f"{rel}: 成品资产文件名不可解析为 assetId：assets/{item.name}"
                    "（须为 实体_角色_图注_批次号_hash，spec §4.1）"
                )
                continue
            if parsed.get("format") != "v2":
                issues.append(
                    f"{rel}: 成品资产命名缺图注段（v1 已废弃）：assets/{item.name}"
                    "（须为 实体_角色_图注_批次号_hash，spec §4.1）"
                )
    return issues


def _execution_sources_naming_issues(execution: Path) -> list[str]:
    """命名门：批次级 sources/ 目录必须用可读命名，禁止回归纯哈希 su_ 目录。"""
    issues: list[str] = []
    sources_root = execution / "sources"
    if not sources_root.is_dir():
        return issues
    for unit in sorted(sources_root.iterdir()):
        if not unit.is_dir():
            continue
        name = unit.name
        if _SOURCE_UNIT_LEGACY_HASH_RE.match(name):
            issues.append(
                f"sources/{name}: 纯哈希来源单元目录名已废弃，"
                "必须使用可读命名 {实体名}__{sourceKind}__{hash8}（spec §3）"
            )
            continue
        if not _SOURCE_UNIT_READABLE_RE.match(name):
            issues.append(
                f"sources/{name}: 来源单元目录名不符可读命名契约 "
                "{实体名}__{sourceKind}__{hash8}（spec §3）"
            )
    return issues


def _sync_issues(execution_id: str, execution: Path) -> list[str]:
    """同步门：盘上成品对象目录必须在 content_object_index 路由中登记（防漂移）。"""
    from content.post import object_index as content_object  # 延迟导入避免循环依赖

    issues: list[str] = []
    registered: set[str] = set()
    for ref in content_object.iter_content_refs(execution_id):
        registered.add(content_object.content_object_rel(execution_id, ref))
    post_root = execution / "posts"
    if not post_root.is_dir():
        return issues
    for manifest in sorted(post_root.rglob("manifest.json")):
        pd = manifest.parent
        if not ((pd / "article.md").exists() or (pd / "gallery.md").exists()):
            continue
        rel = pd.relative_to(execution).as_posix()
        if rel not in registered:
            issues.append(f"{rel}: 成品对象未登记内容路由（content_object_index 漂移）")
    return issues


# 阶段树完整性（opt-in，--require-stage-tree）：每类对象必须物化的过程阶段。
# 内容对象：1.download 证据快照 → 5.review 全链；实体对象：补 2.quality/4.draft/5.review。
_POST_REQUIRED_STAGES = ("1.download", "2.quality", "3.compose", "4.draft", "5.review")
_ENTITY_REQUIRED_STAGES = ("1.download", "2.quality", "3.compose", "4.draft", "5.review")


def _orphan_post_object_issues(execution_id: str, execution: Path) -> list[str]:
    """孤儿内容对象门：posts/ 下出现阶段残骸/manifest/成品，但未登记到当前路由，即 BLOCK。"""
    from content.post import object_index as content_object  # 延迟导入避免循环依赖

    issues: list[str] = []
    post_root = execution / "posts"
    if not post_root.is_dir():
        return issues
    registered = {
        content_object.content_object_rel(execution_id, ref)
        for ref in content_object.iter_content_refs(execution_id)
    }
    for obj in sorted(post_root.rglob("*")):
        if not obj.is_dir():
            continue
        rel = obj.relative_to(execution)
        parts = rel.parts
        if not parts or parts[0] != "posts":
            continue
        if len(parts) < 4:
            continue
        has_stage = any((obj / stage).is_dir() for stage in OBJECT_STAGES)
        has_manifest = (obj / "manifest.json").is_file()
        has_final = (obj / "article.md").is_file() or (obj / "gallery.md").is_file()
        if not (has_stage or has_manifest or has_final):
            continue
        if len(parts) != 5 or not parts[4].isdigit():
            issues.append(
                f"{rel}: 孤儿内容对象残骸（含阶段/manifest/成品，但不符合 posts/{{type}}/{{angle}}/{{title}}/{{seq}} 命名）"
            )
            continue
        rel_posix = rel.as_posix()
        if rel_posix not in registered:
            issues.append(
                f"{rel}: 孤儿内容对象残骸（当前 content_object_index 未登记该对象，需清理旧坐标/旧批次残留）"
            )
    return issues


_STAGE_TREE_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _post_object_carrier(obj: Path) -> str:
    """读取内容对象 manifest 的 carrier（article/image…）；读不到返回空串。"""
    manifest_path = obj / "manifest.json"
    if not manifest_path.is_file():
        return ""
    try:
        return str(read_json(manifest_path).get("carrier") or "")
    except Exception:
        return ""


def _has_image_asset(obj: Path) -> bool:
    assets_dir = obj / "assets"
    if not assets_dir.is_dir():
        return False
    return any(
        p.is_file() and p.suffix.lower() in _STAGE_TREE_IMAGE_EXTS
        for p in assets_dir.iterdir()
    )


def stage_completeness_issues(execution: Path) -> list[str]:
    """阶段树完整性门（opt-in）：成品对象必须物化完整 1-5 过程阶段证据。

    成品判定以 `manifest.json` 为准（图片作品没有 article.md/gallery.md，旧口径会漏判）。
    并按内容类型校验关键成品文件：
    - 文章/主页：必须有 article.md（实体主页为 page.md）。
    - 图片作品（manifest.carrier==image）：必须有至少一张落盘资产 assets/<image>。
    - 全部成品：必须物化 1.download→5.review 全链过程阶段。
    """
    issues: list[str] = []
    for obj in iter_execution_object_dirs(execution):
        rel = obj.relative_to(execution)
        parts = rel.parts
        if parts and parts[0] == "posts":
            manifest_present = (obj / "manifest.json").is_file()
            has_article = (obj / "article.md").exists()
            has_gallery = (obj / "gallery.md").exists()
            if not (manifest_present or has_article or has_gallery):
                continue
            required = _POST_REQUIRED_STAGES
            is_image = _post_object_carrier(obj) == "image"
            if is_image:
                if not _has_image_asset(obj):
                    issues.append(f"{rel}: 图片作品成品缺关键资产 assets/<image>")
            elif not has_article:
                issues.append(f"{rel}: 文章成品缺关键文件 article.md")
        elif parts and parts[0] == "entities":
            if not ((obj / "page.md").exists() or (obj / "_entity.json").exists()):
                continue
            required = _ENTITY_REQUIRED_STAGES
        else:
            continue
        missing = [stage for stage in required if not (obj / stage).is_dir()]
        if missing:
            issues.append(f"{rel}: 阶段树不完整，缺过程阶段 {missing}（须物化 1-5 全链证据）")
    return issues


def _scan_object(obj: Path, execution: Path, issues: list[str]) -> None:
    rel = obj.relative_to(execution)
    issues.extend(_naming_issues(obj, rel))
    # 1. 散落 images/
    for images_dir in obj.rglob("images"):
        if images_dir.is_dir():
            issues.append(f"{rel}: 禁止对象级散落 images/（图片必须归属来源单元 assets/）：{images_dir.relative_to(execution)}")
    # 2/5. manifest / provenance 绝对路径 + 资产闭环
    for jname in (
        "manifest.json",
        "1.download/source_refs.json",
        "5.review/provenance.json",
        "5.review/finalization_report.json",
    ):
        jpath = obj / jname
        if jpath.is_file():
            _scan_json_for_absolute(jpath, issues)
    issues.extend(_source_refs_issues(obj, execution))
    issues.extend(_finalization_report_issues(obj, execution))
    issues.extend(_entity_quality_stage_issues(obj, execution))
    issues.extend(_entity_review_sidecar_issues(obj, execution))
    manifest_path = obj / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = read_json(manifest_path)
        except Exception:
            manifest = {}
        for asset in manifest.get("assets") or []:
            ref = str(asset.get("sourceAssetRef") or "")
            if ref and not _is_absolute_ref(ref):
                if not (execution / ref).is_file():
                    issues.append(f"{rel}: sourceAssetRef 源图缺失（证据链断裂）：{ref}")
    # 3. 机械收尾标题
    for mdname in ("article.md", "page.md"):
        mpath = obj / mdname
        if mpath.is_file():
            for issue in mechanical_ending_title_issues(mpath.read_text(encoding="utf-8")):
                issues.append(f"{rel}/{mdname}: {issue}")
    # 4. 无类别 weather_* 来源单元
    for source_id, category in _object_source_unit_records(obj, execution):
        for issue in source_unit_category_issues(source_id, category):
            issues.append(f"{rel}: {issue}")
    sources_dir = obj / "1.download" / "sources"
    if sources_dir.is_dir():
        for unit in sorted(sources_dir.iterdir()):
            if not unit.is_dir() or not _UNIT_RE.match(unit.name):
                continue
            m = _UNIT_RE.match(unit.name)
            source_id = m.group(2) if m else unit.name
            category = ""
            umani = unit / "meta.json"
            if umani.is_file():
                try:
                    category = str(read_json(umani).get("sourceKind") or "")
                except Exception:
                    category = ""
            for issue in source_unit_category_issues(source_id, category):
                issues.append(f"{rel}: {issue}")
            # 6. 来源图片：相关性必填(非模板) + 像素尺寸门（来源单元 assets/index.json）。
            aidx = unit / "assets" / "index.json"
            if aidx.is_file():
                try:
                    assets = read_json(aidx).get("assets") or []
                except Exception:
                    assets = []
                for asset in assets:
                    if not isinstance(asset, dict):
                        continue
                    aid = str(asset.get("sourceAssetId") or asset.get("fileName") or "?")
                    rel_issue = relevance_issue(
                        str(asset.get("relevance") or ""), entity_id=obj.name, asset_id=aid
                    )
                    if rel_issue:
                        issues.append(f"{rel}: {rel_issue}")
                    px = pixel_size_issue(
                        asset.get("width"), asset.get("height"), asset_id=aid
                    )
                    if px:
                        issues.append(f"{rel}: {px}")


def scan_execution(execution_id: str, *, require_stage_tree: bool = True) -> list[str]:
    execution = execution_root(execution_id)
    issues: list[str] = []
    if not execution.is_dir():
        return [f"execution not found: {execution}"]
    for conflict in execution_entity_type_conflicts(execution_id):
        issues.append(
            "entity type drift: same execution contains dual scenic-location trees "
            f"for {conflict['domain']}/{conflict['name']} -> {conflict['paths']}"
        )
    for obj in iter_execution_object_dirs(execution):
        _scan_object(obj, execution, issues)
    issues.extend(_top_level_issues(execution))
    issues.extend(_execution_shared_issues(execution))
    issues.extend(_regression_issues(execution))
    issues.extend(_execution_sources_naming_issues(execution))
    issues.extend(_execution_assets_naming_issues(execution))
    issues.extend(_sync_issues(execution_id, execution))
    issues.extend(_orphan_post_object_issues(execution_id, execution))
    issues.extend(scan_asset_ids(execution_id))
    if require_stage_tree:
        issues.extend(stage_completeness_issues(execution))
    return issues


def scan_all() -> list[str]:
    issues: list[str] = []
    for execution in iter_all_execution_dirs():
        issues.extend(scan_execution(execution.name))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="目录与资产证据链静态门 (T1)")
    parser.add_argument("--execution-id", default="")
    parser.add_argument(
        "--no-require-stage-tree",
        action="store_true",
        help="关闭对象 1-5 阶段树完整性校验（默认开启）",
    )
    args = parser.parse_args(argv)
    if args.execution_id:
        execution_id = normalize_execution_id(args.execution_id)
        issues = scan_execution_root(execution_id)
        issues.extend(scan_execution(execution_id, require_stage_tree=not args.no_require_stage_tree))
    else:
        issues = scan_all()
    if issues:
        print("FAIL verify_directory_evidence_chain:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("PASS verify_directory_evidence_chain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
