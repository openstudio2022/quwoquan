"""目录与资产证据链静态门 (T1) ——「对象同构 + 来源内聚 + 相对路径 + 文风 + 命名 + 路由同步」收口。

真相源：docs/pipeline_directory_layout_spec.md。扫描批次新布局对象目录：
  batches/{batch}/entities/{domain}/{type}/{name}/   （实体对象）
  batches/{batch}/posts/{contentType}/{angle}/{title}/{seq}/   （内容对象）

阻断（BLOCK）：
1. 对象内出现散落 images/（图片必须在来源单元 assets/ 内）。
2. manifest.json / provenance.json 含绝对路径（citedSourceRefs/sourceAssetRef/sourcePaths/...）。
3. article.md / page.md 出现机械收尾标题（它到底适合谁 等）。
4. 来源单元为无类别 weather_* 普通来源。
5. manifest.assets[].sourceAssetRef 指向的源图缺失（资产闭环断裂）。
6. 【命名门】对象目录层级/命名不符（posts/{type}/{angle}/{title}/{seq}、entities/{domain}/{type}/{name}、
   阶段子目录 ∉ 编号阶段∪assets、来源单元 ∉ {NN}.{kind}）。
7. 【回退门】task_produce stage-first 扁平面被重新写入（task_produce/{posts,inputs,drafts,results,review/*}），
   即 M3/M4 已迁对象根的成品/草稿/brief/阶段报告/账本不得回退。
8. 【同步门】成品对象目录与 `_shared/content_object_index.json` 路由漂移（对象在盘上但未登记）。

旧 stage-first 布局（download/sources）已废弃；若被写入，按回退门直接 BLOCK。

可直接运行：python3 quwoquan_data/scripts/verify/verify_directory_evidence_chain.py [--task T --batch B]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.batch_scan import iter_batch_object_dirs  # noqa: E402
from _common.io import read_json  # noqa: E402
from _common.image_rules import pixel_size_issue, relevance_issue  # noqa: E402
from _common.paths import (  # noqa: E402
    OBJECT_STAGES,
    TASKS_ROOT,
    TASK_ROOT_ALLOWED_ENTRIES,
    TASK_ROOT_LEGACY_COMPAT_ENTRIES,
    TASK_SHARED_LEDGER_FILENAMES,
    batch_root,
    normalize_task_id,
    task_root,
    task_shared_dir,
)
from _common.prose_style import mechanical_ending_title_issues  # noqa: E402
from _common.source_catalog import source_unit_category_issues  # noqa: E402
from verify.verify_asset_id_zero_collision import scan_batch as scan_asset_ids  # noqa: E402

_REF_FIELDS = ("citedSourceRefs", "sourceAssetRef", "sourceRef", "sourcePaths", "citedSourcePaths")
_UNIT_RE = __import__("re").compile(r"^(\d{2})\.(.+)$")
_OBJECT_CHILD_ALLOW = set(OBJECT_STAGES) | {"assets"}
_TASK_SHARED_ALLOW = {
    *TASK_SHARED_LEDGER_FILENAMES,
    "baseline_freeze_packet.json",
    "baseline_report.json",
    "explore_packet.json",
    "discovery_adopt",
}

# 批次顶层允许集（§2/§12 A5）：对象目录 + 批次公共 + 受控 workspace 命令目录。
# workspace 命令目录不得承载对象证据（由回退门 _regression_issues 保证）。
_BATCH_TOP_ALLOW = {
    "entities", "posts", "_shared", "batch_manifest.json",
    "task_workflow", "task_download", "task_build", "task_produce", "task_publish",
    "media",
}

# M3/M4 已迁对象根的 produce 扁平面：若被重新写入（非空）即 stage-first 回退，BLOCK。
_REGRESSION_FACES = (
    ("task_produce/posts", "manifest.json", True, "成品须落对象根 posts/{type}/{angle}/{title}/{seq}"),
    ("task_produce/inputs/compose", "*.json", False, "compose 输入须落对象 3.compose/brief.json"),
    ("task_produce/drafts", "*", True, "草稿须落对象 3.compose/4.draft"),
    ("task_produce/results/compose", "*.json", False, "compose 报告须落对象 5.review"),
    ("task_produce/results/review", "*.json", False, "review 报告须落对象 5.review"),
    ("task_produce/results/quality_analysis", "*.json", False, "quality 报告须落对象 2.quality"),
    ("task_produce/results/media_check", "*.json", False, "media_check 报告须落对象 5.review"),
    ("task_produce/review/ledger", "*.json", False, "复核账本须落对象 5.review/review_ledger.json"),
    ("task_produce/review/entities", "*.json", False, "复核实体边车须落对象 5.review/review_entities.json"),
)


def _task_shared_issues(task_id: str) -> list[str]:
    issues: list[str] = []
    shared_dir = task_shared_dir(task_id)
    if not shared_dir.is_dir():
        return issues
    for entry in sorted(shared_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.name not in _TASK_SHARED_ALLOW:
            issues.append(
                f"task/_shared/{entry.name}: 非法 task 共享条目（仅允许 {sorted(_TASK_SHARED_ALLOW)}）"
            )
    return issues


def scan_task(task_id: str) -> list[str]:
    """task 根目录门：只允许真相源根条目与最小 `_shared/` 账本。"""
    root = task_root(task_id)
    if not root.is_dir():
        return [f"task not found: {root}"]
    issues: list[str] = []
    for entry in sorted(root.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.name in TASK_ROOT_ALLOWED_ENTRIES:
            continue
        if entry.name in TASK_ROOT_LEGACY_COMPAT_ENTRIES:
            issues.append(f"task/{entry.name}: 历史兼容位仍存在，需运行 task cleanup-runtime 清理")
            continue
        issues.append(
            f"task/{entry.name}: 非法 task 顶层条目（仅允许 {sorted(TASK_ROOT_ALLOWED_ENTRIES)}）"
        )
    issues.extend(_task_shared_issues(task_id))
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
                f"{rel}: 非法对象子目录 '{child.name}'（仅允许编号阶段 {list(OBJECT_STAGES)} 或 assets）"
            )
    sources_dir = obj / "1.download" / "sources"
    if sources_dir.is_dir():
        for unit in sorted(sources_dir.iterdir()):
            if unit.is_dir() and not _UNIT_RE.match(unit.name):
                issues.append(f"{rel}: 来源单元命名违规 '{unit.name}'（应为 NN.kind）")
    return issues


def _top_level_issues(batch: Path) -> list[str]:
    """顶层结构门：批次根条目 ⊆ 允许集（§2/§12 A5），拦截漂移/散落文件。"""
    issues: list[str] = []
    for entry in sorted(batch.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.name not in _BATCH_TOP_ALLOW:
            issues.append(
                f"{entry.name}: 非法批次顶层条目（仅允许 {sorted(_BATCH_TOP_ALLOW)}）"
            )
    return issues


def _regression_issues(batch: Path) -> list[str]:
    """回退门：produce 已迁对象根的扁平面被重新写入即 BLOCK。"""
    issues: list[str] = []
    for relpath, pattern, recursive, msg in _REGRESSION_FACES:
        d = batch / Path(relpath)
        if not d.is_dir():
            continue
        matches = d.rglob(pattern) if recursive else d.glob(pattern)
        if any(m.is_file() for m in matches):
            issues.append(f"{relpath}: stage-first 回退禁止 — {msg}")
    return issues


def _sync_issues(task_id: str, batch_id: str, batch: Path) -> list[str]:
    """同步门：盘上成品对象目录必须在 content_object_index 路由中登记（防漂移）。"""
    from _common import content_object  # 延迟导入避免循环依赖

    issues: list[str] = []
    registered: set[str] = set()
    for ref in content_object.iter_content_refs(task_id, batch_id):
        registered.add(content_object.content_object_rel(task_id, batch_id, ref))
    post_root = batch / "posts"
    if not post_root.is_dir():
        return issues
    for manifest in sorted(post_root.rglob("manifest.json")):
        pd = manifest.parent
        if not ((pd / "article.md").exists() or (pd / "gallery.md").exists()):
            continue
        rel = pd.relative_to(batch).as_posix()
        if rel not in registered:
            issues.append(f"{rel}: 成品对象未登记内容路由（content_object_index 漂移）")
    return issues


# 阶段树完整性（opt-in，--require-stage-tree）：每类对象必须物化的过程阶段。
# 内容对象：1.download 证据快照 → 5.review 全链；实体对象：补 2.quality/4.draft/5.review。
_POST_REQUIRED_STAGES = ("1.download", "2.quality", "3.compose", "4.draft", "5.review")
_ENTITY_REQUIRED_STAGES = ("1.download", "2.quality", "3.compose", "4.draft", "5.review")


def _orphan_post_object_issues(task_id: str, batch_id: str, batch: Path) -> list[str]:
    """孤儿内容对象门：posts/ 下出现阶段残骸/manifest/成品，但未登记到当前路由，即 BLOCK。"""
    from _common import content_object  # 延迟导入避免循环依赖

    issues: list[str] = []
    post_root = batch / "posts"
    if not post_root.is_dir():
        return issues
    registered = {
        content_object.content_object_rel(task_id, batch_id, ref)
        for ref in content_object.iter_content_refs(task_id, batch_id)
    }
    for obj in sorted(post_root.rglob("*")):
        if not obj.is_dir():
            continue
        rel = obj.relative_to(batch)
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


def stage_completeness_issues(batch: Path) -> list[str]:
    """阶段树完整性门（opt-in）：成品对象必须物化完整 1-5 过程阶段证据。

    - 内容对象（posts，有 article.md/gallery.md）：补齐 1.download 证据快照等全链。
    - 实体对象（entities，有 page.md/_entity.json）：补齐 2.quality/4.draft/5.review。
    """
    issues: list[str] = []
    for obj in iter_batch_object_dirs(batch):
        rel = obj.relative_to(batch)
        parts = rel.parts
        if parts and parts[0] == "posts":
            if not ((obj / "article.md").exists() or (obj / "gallery.md").exists()):
                continue
            required = _POST_REQUIRED_STAGES
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


def _task_batch_from_path(batch: Path) -> tuple[str, str]:
    """从 batch 目录反推 (task_id, batch_id)：tasks/{task...}/batches/{batch}。"""
    task_root_dir = batch.parent.parent
    task_id = task_root_dir.relative_to(TASKS_ROOT).as_posix()
    return task_id, batch.name


def _scan_object(obj: Path, batch: Path, issues: list[str]) -> None:
    rel = obj.relative_to(batch)
    issues.extend(_naming_issues(obj, rel))
    # 1. 散落 images/
    for images_dir in obj.rglob("images"):
        if images_dir.is_dir():
            issues.append(f"{rel}: 禁止对象级散落 images/（图片必须归属来源单元 assets/）：{images_dir.relative_to(batch)}")
    # 2/5. manifest / provenance 绝对路径 + 资产闭环
    for jname in ("manifest.json", "5.review/provenance.json"):
        jpath = obj / jname
        if jpath.is_file():
            _scan_json_for_absolute(jpath, issues)
    manifest_path = obj / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = read_json(manifest_path)
        except Exception:
            manifest = {}
        for asset in manifest.get("assets") or []:
            ref = str(asset.get("sourceAssetRef") or "")
            if ref and not _is_absolute_ref(ref):
                if not (batch / ref).is_file():
                    issues.append(f"{rel}: sourceAssetRef 源图缺失（证据链断裂）：{ref}")
    # 3. 机械收尾标题
    for mdname in ("article.md", "page.md"):
        mpath = obj / mdname
        if mpath.is_file():
            for issue in mechanical_ending_title_issues(mpath.read_text(encoding="utf-8")):
                issues.append(f"{rel}/{mdname}: {issue}")
    # 4. 无类别 weather_* 来源单元
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


def scan_batch(task_id: str, batch_id: str, *, require_stage_tree: bool = True) -> list[str]:
    batch = batch_root(task_id, batch_id)
    issues: list[str] = []
    if not batch.is_dir():
        return [f"batch not found: {batch}"]
    for obj in iter_batch_object_dirs(batch):
        _scan_object(obj, batch, issues)
    issues.extend(_top_level_issues(batch))
    issues.extend(_regression_issues(batch))
    issues.extend(_sync_issues(task_id, batch_id, batch))
    issues.extend(_orphan_post_object_issues(task_id, batch_id, batch))
    issues.extend(scan_asset_ids(task_id, batch_id))
    if require_stage_tree:
        issues.extend(stage_completeness_issues(batch))
    return issues


def scan_all() -> list[str]:
    issues: list[str] = []
    if not TASKS_ROOT.is_dir():
        return issues
    seen_tasks: set[str] = set()
    for batches_dir in TASKS_ROOT.rglob("batches"):
        task_id = batches_dir.parent.relative_to(TASKS_ROOT).as_posix()
        if task_id not in seen_tasks:
            issues.extend(scan_task(task_id))
            seen_tasks.add(task_id)
        for batch in sorted(p for p in batches_dir.iterdir() if p.is_dir()):
            for obj in iter_batch_object_dirs(batch):
                _scan_object(obj, batch, issues)
            issues.extend(_top_level_issues(batch))
            issues.extend(_regression_issues(batch))
            current_task_id, batch_id = _task_batch_from_path(batch)
            issues.extend(_sync_issues(current_task_id, batch_id, batch))
            issues.extend(_orphan_post_object_issues(current_task_id, batch_id, batch))
            issues.extend(scan_asset_ids(current_task_id, batch_id))
            issues.extend(stage_completeness_issues(batch))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="目录与资产证据链静态门 (T1)")
    parser.add_argument("--task", default="")
    parser.add_argument("--batch", default="")
    parser.add_argument(
        "--no-require-stage-tree",
        action="store_true",
        help="关闭对象 1-5 阶段树完整性校验（默认开启；仅兼容历史批次排障时使用）",
    )
    args = parser.parse_args(argv)
    if args.task and args.batch:
        normalized_task = normalize_task_id(args.task)
        issues = scan_task(normalized_task)
        issues.extend(scan_batch(normalized_task, args.batch, require_stage_tree=not args.no_require_stage_tree))
    elif args.task:
        issues = scan_task(normalize_task_id(args.task))
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
