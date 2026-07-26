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
7. 【回退门】`_shared/workspace/post` 的 retired stage-first 扁平面被重新写入，
   已归位对象根的成品/草稿/brief/阶段报告/账本不得回退。
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
from verify.evidence_source_checks import (  # noqa: E402
    _entity_quality_stage_issues,
    _entity_review_sidecar_issues,
    _execution_assets_naming_issues,
    _execution_shared_issues,
    _execution_sources_naming_issues,
    _finalization_report_issues,
    _is_absolute_ref,
    _naming_issues,
    _object_source_unit_records,
    _regression_issues,
    _scan_json_for_absolute,
    _source_refs_issues,
    _sync_issues,
    _top_level_issues,
    scan_execution_root,
)

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

# 已归位对象根的 post 扁平面：若被重新写入（非空）即 stage-first 回退，BLOCK。
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


























# 批次级来源单元可读命名（spec §3）：{实体名}__{sourceKind}__{hash8}。
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
        has_final = (
            (obj / "article.md").is_file()
            or (obj / "gallery.md").is_file()
            or (obj / "assets" / "video.mp4").is_file()
        )
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


def _has_video_asset(obj: Path) -> bool:
    return (obj / "assets" / "video.mp4").is_file()


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
            carrier = _post_object_carrier(obj)
            is_image = carrier == "image"
            is_video = carrier == "video"
            if is_image:
                if not _has_image_asset(obj):
                    issues.append(f"{rel}: 图片作品成品缺关键资产 assets/<image>")
            elif is_video:
                if not _has_video_asset(obj):
                    issues.append(f"{rel}: 视频作品成品缺关键资产 assets/video.mp4")
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
