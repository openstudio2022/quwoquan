"""实体主页结构 + 配图语义验收门（新批次 opt-in，不卡存量 s10）。

校验：
- 来源 source.md 关键章节是否在 page.md 保留为同级小标题（outline 覆盖）。
- manifest.assets caption 是否具有中文语义（非文件名退化）。

用法：
  python3 quwoquan_data/scripts/verify/verify_homepage_structure_and_assets.py --task T --batch B
  python3 quwoquan_data/scripts/verify/verify_homepage_structure_and_assets.py --root /path/to/batch
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.asset_placement import caption_semantic_issues  # noqa: E402
from _common.io import read_json  # noqa: E402
from _common.paths import batch_root, batches_root, normalize_task_id  # noqa: E402
from _common.section_outline import (  # noqa: E402
    outline_coverage_issues,
    outline_required_sections,
    parse_section_outline,
)

_HOMEPAGE_SECTION_MIN_CHARS = 120


def _entity_label(obj: Path, batch: Path) -> str:
    return obj.relative_to(batch).as_posix()


def _required_titles_from_source(obj: Path) -> list[str]:
    """从实体对象 1.download 主来源 source.md 解析关键章节标题。"""
    sources = obj / "1.download" / "sources"
    if not sources.is_dir():
        return []
    for unit in sorted(sources.iterdir()):
        if not unit.is_dir():
            continue
        raw_path = unit / "source.md"
        if not raw_path.is_file():
            continue
        try:
            text = raw_path.read_text(encoding="utf-8")
        except OSError:
            continue
        nodes = outline_required_sections(
            parse_section_outline(text),
            min_body_chars=_HOMEPAGE_SECTION_MIN_CHARS,
        )
        if nodes:
            return [n.title for n in nodes]
    return []


def scan_entity_homepage_issues(obj: Path, *, batch: Path) -> list[str]:
    """单实体对象的结构 + caption 语义 issue 列表。"""
    label = _entity_label(obj, batch)
    issues: list[str] = []
    page_path = obj / "page.md"
    if not page_path.is_file():
        return [f"{label}: page.md 缺失"]
    try:
        page_text = page_path.read_text(encoding="utf-8")
    except OSError:
        return [f"{label}: page.md 不可读"]

    required = _required_titles_from_source(obj)
    if required:
        issues.extend(
            outline_coverage_issues(required, page_text, label=label)
        )

    manifest_path = obj / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = read_json(manifest_path)
            assets = manifest.get("assets") if isinstance(manifest, dict) else []
            if isinstance(assets, list):
                issues.extend(caption_semantic_issues(assets, label=label))
            # 主页三段结构门：frontmatter 封面唯一、正文块级 figure、gallery 仅页尾、
            # roles 收敛 cover/inline/related、零占位符残留。
            from build.homepage_validation import homepage_structure_issues

            if isinstance(manifest, dict):
                issues.extend(homepage_structure_issues(obj, manifest, label))
        except (OSError, ValueError, TypeError):
            issues.append(f"{label}: manifest.json 不可读")
    return issues


def scan_batch(batch_dir: Path, *, task_id: str = "") -> list[str]:
    issues: list[str] = []
    ent_root = batch_dir / "entities"
    if ent_root.is_dir():
        for entity_json in sorted(ent_root.rglob("_entity.json")):
            issues.extend(scan_entity_homepage_issues(entity_json.parent, batch=batch_dir))
    return issues


def _batch_opts_in(batch_dir: Path) -> bool:
    """批次是否显式 opt-in 本结构/配图门（batch_manifest.homepageStructureGate==true）。

    新批次 opt-in：只对显式声明的批次强制，避免回卡未迁移的存量批次。
    """
    manifest_path = batch_dir / "batch_manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = read_json(manifest_path)
    except (OSError, ValueError, TypeError):
        return False
    return bool(isinstance(manifest, dict) and manifest.get("homepageStructureGate") is True)


def scan_runtime_opt_in_batches() -> tuple[list[str], int]:
    """扫描所有 runtime 批次中显式 opt-in 的批次，返回 (issues, opted_in_count)。

    无 opt-in 批次时返回空 issues（CI/干净检出安全通过）。
    """
    issues: list[str] = []
    opted_in = 0
    root = batches_root()
    if not root.is_dir():
        return issues, opted_in
    for batch_dir in sorted(root.iterdir()):
        if not batch_dir.is_dir() or not _batch_opts_in(batch_dir):
            continue
        opted_in += 1
        issues.extend(scan_batch(batch_dir))
    return issues, opted_in


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="实体主页 outline 覆盖 + caption 语义门")
    parser.add_argument("--task", default="", help="task id")
    parser.add_argument("--batch", default="", help="batch id")
    parser.add_argument("--root", default="", help="batch 根目录（优先于 task/batch）")
    parser.add_argument(
        "--all-runtime-opt-in",
        action="store_true",
        help="扫描所有 runtime 批次中显式 opt-in（batch_manifest.homepageStructureGate=true）的批次",
    )
    args = parser.parse_args(argv)

    if args.all_runtime_opt_in:
        issues, opted_in = scan_runtime_opt_in_batches()
        if issues:
            print(f"FAIL: {len(issues)} homepage structure/asset issues across {opted_in} opt-in batch(es)")
            for issue in issues[:50]:
                print(f"  - {issue}")
            if len(issues) > 50:
                print(f"  ... and {len(issues) - 50} more")
            return 1
        print(f"OK: homepage structure + caption gate passed ({opted_in} opt-in batch(es))")
        return 0

    if args.root:
        batch_dir = Path(args.root).resolve()
    elif args.task and args.batch:
        batch_dir = batch_root(normalize_task_id(args.task), args.batch)
    else:
        parser.error("需要 --root 或 --task + --batch 或 --all-runtime-opt-in")
        return 2

    if not batch_dir.is_dir():
        print(f"FAIL: batch 目录不存在: {batch_dir}", file=sys.stderr)
        return 1

    issues = scan_batch(batch_dir, task_id=args.task)
    if issues:
        print(f"FAIL: {len(issues)} homepage structure/asset issues in {batch_dir}")
        for issue in issues[:50]:
            print(f"  - {issue}")
        if len(issues) > 50:
            print(f"  ... and {len(issues) - 50} more")
        return 1
    print(f"OK: homepage structure + caption semantic gate passed ({batch_dir})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
