"""materialize 文章目录布局契约 ——「文章标题写在 article 之下、序号默认 1、标题可重复递增」。

覆盖：
- post 目录为 posts/<type>/<发布标题>/<seq>/（标题在 article 之下，再下是序号目录）。
- seq 默认 1；同一发布标题多篇按 ref 稳定递增（支持标题重复）。
- manifest.publishSeq 与目录序号一致。
- promote 以 rglob(manifest.json)+正文存在性定位 post 的口径，对新三层结构成立。

可直接运行：python3 quwoquan_data/tests/test_post_dir_layout.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

from _common.io import read_json, write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    batch_command_root,
    ensure_batch_layout,
    ensure_task_layout,
)
from produce.materialize import materialize_posts  # noqa: E402

TASK = "目录布局_gwt"
BATCH = "pilot"


def _seed_post(produce_root: Path, ref: str, publish_title: str) -> None:
    review_dir = produce_root / "results" / "review"
    compose_dir = produce_root / "results" / "compose"
    review_dir.mkdir(parents=True, exist_ok=True)
    compose_dir.mkdir(parents=True, exist_ok=True)
    write_json(review_dir / f"{ref}.json", {"ref": ref, "payload": {"decision": "approved"}})
    write_json(
        compose_dir / f"{ref}.json",
        {
            "payload": {
                "generator": "agent",
                "articleMarkdown": f"# {publish_title}\n\n正文：{ref} 的真实内容展开。",
                "title": publish_title,
                "publishTitle": publish_title,
                "carrier": "article",
                "entityRefs": [],
                "tagRefs": ["Topic/旅行", "Format/内容角度/攻略"],
                "assets": [],
            }
        },
    )


def _materialize() -> tuple[Path, list[Path]]:
    ensure_task_layout(TASK)
    ensure_batch_layout(TASK, BATCH, "produce")
    produce_root = batch_command_root(TASK, BATCH, "produce")
    posts = produce_root / "posts"
    import shutil

    if posts.exists():
        shutil.rmtree(posts)
    # 同一标题两篇（ref 排序 a<b → 1,2），另一标题一篇。
    _seed_post(produce_root, "露营地_a", "成都周边小众露营地实测")
    _seed_post(produce_root, "露营地_b", "成都周边小众露营地实测")
    _seed_post(produce_root, "都江堰_a", "都江堰一日游怎么玩")
    materialized = materialize_posts(TASK, BATCH, "article")
    return posts, materialized


def test_post_dir_is_title_then_seq():
    posts, materialized = _materialize()
    assert len(materialized) == 3, materialized
    dup1 = posts / "article" / "成都周边小众露营地实测" / "1"
    dup2 = posts / "article" / "成都周边小众露营地实测" / "2"
    solo = posts / "article" / "都江堰一日游怎么玩" / "1"
    assert dup1.is_dir() and (dup1 / "manifest.json").exists(), posts
    assert dup2.is_dir() and (dup2 / "manifest.json").exists(), posts
    assert solo.is_dir() and (solo / "manifest.json").exists(), posts


def test_seq_increments_for_duplicate_title():
    posts, _ = _materialize()
    seq1 = read_json(posts / "article" / "成都周边小众露营地实测" / "1" / "manifest.json")["publishSeq"]
    seq2 = read_json(posts / "article" / "成都周边小众露营地实测" / "2" / "manifest.json")["publishSeq"]
    solo_seq = read_json(posts / "article" / "都江堰一日游怎么玩" / "1" / "manifest.json")["publishSeq"]
    assert {seq1, seq2} == {1, 2}
    assert solo_seq == 1


def test_promote_rglob_locates_new_layout():
    posts, _ = _materialize()
    # 复刻 promote_from_posts_root 的定位口径：rglob(manifest) + 正文存在性。
    leaves = [
        m.parent
        for m in sorted(posts.rglob("manifest.json"))
        if (m.parent / "article.md").exists() or (m.parent / "gallery.md").exists()
    ]
    assert len(leaves) == 3
    for leaf in leaves:
        rel = leaf.relative_to(posts)
        assert rel.parts[0] == "article", rel
        assert len(rel.parts) == 3, rel  # <type>/<title>/<seq>
        assert rel.parts[2].isdigit(), rel


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"post dir layout tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
