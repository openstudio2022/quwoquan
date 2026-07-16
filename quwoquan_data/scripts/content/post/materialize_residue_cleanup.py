"""Clean up provisional post residue after materialization."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.paths import execution_root


_PROVISIONAL_RESIDUE_STAGES = ("1.download", "2.quality", "3.compose", "4.draft", "5.review")
_MATERIALIZED_POST_ENTRIES = ("manifest.json", "_object.json", "article.md", "gallery.md", "assets")


def prune_materialized_post_refs(
    execution_id: str,
    refs: list[str] | set[str] | tuple[str, ...],
) -> list[Path]:
    """Remove only the final materialization surface for isolated post refs.

    Source, drafting, and review evidence remains in the execution work package
    for audit and controlled retry. Object coordinates are resolved only through
    the content-object index, never inferred from a ref string.
    """
    from content.post import object_index as content_object

    removed: list[Path] = []
    for ref in sorted({str(item).strip() for item in refs if str(item).strip()}):
        try:
            object_dir = content_object.content_object_dir(execution_id, ref)
        except KeyError:
            continue
        for name in _MATERIALIZED_POST_ENTRIES:
            path = object_dir / name
            if path.is_dir():
                shutil.rmtree(path)
                removed.append(path)
            elif path.is_file() or path.is_symlink():
                path.unlink()
                removed.append(path)
    return removed


def prune_unregistered_post_residue(execution_id: str) -> list[Path]:
    """剪除未登记到 content_object_index 的死 provisional 残骸目录。

    Agent 在 authoring 期间可能先用临时标题落地阶段证据（如 2.quality/5.review），
    最终登记标题变化（或重组合改派坐标）后，旧坐标目录成为孤儿残骸。带
    manifest/成品的未登记对象属更严重不一致，保留交给孤儿门显式 BLOCK。
    """
    from content.post import object_index as content_object

    base = execution_root(execution_id).resolve()
    post_root = base / "posts"
    if not post_root.is_dir():
        return []
    registered = {
        content_object.content_object_rel(execution_id, ref)
        for ref in content_object.iter_content_refs(execution_id)
    }
    removed: list[Path] = []
    for obj in sorted(post_root.rglob("*")):
        if not obj.is_dir():
            continue
        rel = obj.relative_to(base)
        parts = rel.parts
        if len(parts) != 5 or parts[0] != "posts" or not parts[4].isdigit():
            continue
        if rel.as_posix() in registered:
            continue
        has_manifest = (obj / "manifest.json").is_file()
        has_final = (obj / "article.md").is_file() or (obj / "gallery.md").is_file()
        if has_manifest or has_final:
            continue
        has_stage = any((obj / stage).is_dir() for stage in _PROVISIONAL_RESIDUE_STAGES)
        if not has_stage:
            continue
        shutil.rmtree(obj)
        removed.append(obj)
    return removed
