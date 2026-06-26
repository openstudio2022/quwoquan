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

from _common.paths import batch_root


_PROVISIONAL_RESIDUE_STAGES = ("1.download", "2.quality", "3.compose", "4.draft", "5.review")


def prune_unregistered_post_residue(task_id: str, batch_id: str) -> list[Path]:
    """剪除未登记到 content_object_index 的死 provisional 残骸目录。

    Agent 在 authoring 期间可能先用临时标题落地阶段证据（如 2.quality/5.review），
    最终登记标题变化（或重组合改派坐标）后，旧坐标目录成为孤儿残骸。带
    manifest/成品的未登记对象属更严重不一致，保留交给孤儿门显式 BLOCK。
    """
    from _common import content_object

    base = batch_root(task_id, batch_id).resolve()
    post_root = base / "posts"
    if not post_root.is_dir():
        return []
    registered = {
        content_object.content_object_rel(task_id, batch_id, ref)
        for ref in content_object.iter_content_refs(task_id, batch_id)
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
