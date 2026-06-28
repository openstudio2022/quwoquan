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
from _common.batch_scan import iter_batch_object_dirs  # noqa: E402
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
        except (OSError, ValueError, TypeError):
            issues.append(f"{label}: manifest.json 不可读")
    return issues


def scan_batch(batch_dir: Path, *, task_id: str = "") -> list[str]:
    issues: list[str] = []
    for obj in iter_batch_object_dirs(batch_dir, kind="entity"):
        issues.extend(scan_entity_homepage_issues(obj, batch=batch_dir))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="实体主页 outline 覆盖 + caption 语义门")
    parser.add_argument("--task", default="", help="task id")
    parser.add_argument("--batch", default="", help="batch id")
    parser.add_argument("--root", default="", help="batch 根目录（优先于 task/batch）")
    args = parser.parse_args(argv)

    if args.root:
        batch_dir = Path(args.root).resolve()
    elif args.task and args.batch:
        batch_dir = batch_root(normalize_task_id(args.task), args.batch)
    else:
        parser.error("需要 --root 或 --task + --batch")
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
