"""materialize 内容对象目录布局契约 ——「成品落对象根 posts/{type}/{angle}/{title}/{seq}」。

覆盖（对象优先，§2.4/§2.5）：
- post 成品落 execution 根 `posts/<type>/<angle>/<标题>/<seq>/`（含 angle 必选层）。
- 对象坐标（angle/title/seq）= `_shared/content_object_index.json` 路由真相；seq 默认 1，同
  (type,angle,title) 组多 ref 按 ref 稳定递增（支持标题重复）。
- manifest.publishSeq/publishAngle/publishTitle 与对象目录坐标一致。

可直接运行：python3 quwoquan_data/tests/local_contract/post/test_post_dir_layout__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os
import tempfile

sys.path.insert(0, str(SCRIPTS_ROOT))

_OUTPUT_ROOT = Path(tempfile.mkdtemp(prefix="post_dir_layout_output_"))

from content.post.object_index import register_content_object  # noqa: E402
from content.post.draft_io import write_agent_draft  # noqa: E402
from core.io import read_json  # noqa: E402
from core.paths import (  # noqa: E402
    execution_command_root,
    execution_root,
    ensure_execution_command_layout,
    ensure_execution_layout,
)
from content.execution.stage_reports import write_stage_result  # noqa: E402
from content.post.materialize_apply import materialize_posts  # noqa: E402
from content.post.materialize_contract import _materialized_asset_refs  # noqa: E402
from content.post.materialize_residue_cleanup import prune_materialized_post_refs  # noqa: E402
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402

EXECUTION_ID = "20260711--travel-article-layout--cn-sichuan--canary-001"
ANGLE = "攻略"


def _retarget_roots() -> None:
    os.environ["QWQ_OUTPUT_ROOT"] = str(_OUTPUT_ROOT)


def _seed_post(ref: str, publish_title: str) -> None:
    article = f"# {publish_title}\n\n正文：{ref} 的真实内容展开。"
    register_content_object(EXECUTION_ID, ref, content_type="article", angle=ANGLE, title=publish_title)
    write_stage_result(EXECUTION_ID, "post", "review", ref, {"decision": "approved"})
    write_stage_result(
        EXECUTION_ID, "post", "compose", ref,
        {
            "generator": "agent",
            "articleMarkdown": article,
            "title": publish_title,
            "publishTitle": publish_title,
            "carrier": "article",
            "entityRefs": [],
            "tagRefs": ["Topic/旅行", "Format/内容角度/攻略"],
            "assets": [],
        },
    )
    write_agent_draft(
        EXECUTION_ID,
        ref,
        article,
        model="test-agent/post-dir-layout",
        cited_source_paths=[],
        covered_facts=[],
        agent_run_id=f"run-{ref}",
        agent_id="agent-post-dir-layout",
    )


def _posts_root() -> Path:
    return execution_root(EXECUTION_ID) / "posts"


def _materialize() -> tuple[Path, list[Path]]:
    _retarget_roots()
    ensure_execution_layout(EXECUTION_ID)
    ensure_execution_command_layout(EXECUTION_ID, "post")
    import shutil

    # 清理对象树 + 路由，保证可重复运行。
    execution_dir = execution_root(EXECUTION_ID)
    for sub in (execution_dir / "posts", execution_dir / "_shared"):
        if sub.exists():
            shutil.rmtree(sub)
    post_results = execution_command_root(EXECUTION_ID, "post") / "results"
    if post_results.exists():
        shutil.rmtree(post_results)
    build_execution_fixture(EXECUTION_ID)
    # 同一 (type,angle,title) 两篇（ref 排序 a<b → 1,2），另一标题一篇。
    _seed_post("露营地_a", "成都周边小众露营地实测")
    _seed_post("露营地_b", "成都周边小众露营地实测")
    _seed_post("都江堰_a", "都江堰一日游怎么玩")
    materialized = materialize_posts(EXECUTION_ID, "article")
    return _posts_root(), materialized


def test_post_dir_is_type_angle_title_seq():
    posts, materialized = _materialize()
    assert len(materialized) == 3, materialized
    dup1 = posts / "article" / ANGLE / "成都周边小众露营地实测" / "1"
    dup2 = posts / "article" / ANGLE / "成都周边小众露营地实测" / "2"
    solo = posts / "article" / ANGLE / "都江堰一日游怎么玩" / "1"
    assert dup1.is_dir() and (dup1 / "manifest.json").exists(), posts
    assert dup2.is_dir() and (dup2 / "manifest.json").exists(), posts
    assert solo.is_dir() and (solo / "manifest.json").exists(), posts


def test_materialized_manifest_has_required_times():
    posts, _ = _materialize()
    for manifest_path in posts.rglob("manifest.json"):
        manifest = read_json(manifest_path)
        assert manifest.get("createdAt"), manifest_path
        assert manifest.get("updatedAt"), manifest_path


def test_materialized_asset_refs_infer_source_ref_from_source_path():
    source_path = (
        execution_root(EXECUTION_ID)
        / "entities/地点/景区/毕棚沟/1.download/sources/03.article_base/assets/001.jpg"
    )
    source_ref, source_asset_ref = _materialized_asset_refs(
        {"sourcePath": str(source_path)},
        execution_id=EXECUTION_ID,
    )

    assert source_asset_ref == "entities/地点/景区/毕棚沟/1.download/sources/03.article_base/assets/001.jpg"
    assert source_ref == "entities/地点/景区/毕棚沟/1.download/sources/03.article_base/source.md"


def test_seq_increments_for_duplicate_title():
    posts, _ = _materialize()
    seq1 = read_json(posts / "article" / ANGLE / "成都周边小众露营地实测" / "1" / "manifest.json")["publishSeq"]
    seq2 = read_json(posts / "article" / ANGLE / "成都周边小众露营地实测" / "2" / "manifest.json")["publishSeq"]
    solo_seq = read_json(posts / "article" / ANGLE / "都江堰一日游怎么玩" / "1" / "manifest.json")["publishSeq"]
    assert {seq1, seq2} == {1, 2}
    assert solo_seq == 1


def test_manifest_angle_matches_object_dir():
    posts, _ = _materialize()
    m = read_json(posts / "article" / ANGLE / "都江堰一日游怎么玩" / "1" / "manifest.json")
    assert m["publishAngle"] == ANGLE, m["publishAngle"]
    assert m["publishTitle"] == "都江堰一日游怎么玩", m["publishTitle"]


def test_object_index_written_per_object():
    posts, _ = _materialize()
    idx = read_json(posts / "article" / ANGLE / "都江堰一日游怎么玩" / "1" / "_object.json")
    assert idx["objectKind"] == "content"
    assert idx["publishTargetRef"] == "posts/article/攻略/都江堰一日游怎么玩/1", idx["publishTargetRef"]


def test_prune_materialized_post_refs_removes_only_final_surface():
    posts, _ = _materialize()
    target = posts / "article" / ANGLE / "成都周边小众露营地实测" / "1"
    sibling = posts / "article" / ANGLE / "成都周边小众露营地实测" / "2"
    evidence = target / "5.review" / "review_evidence.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("{}", encoding="utf-8")

    removed = prune_materialized_post_refs(EXECUTION_ID, ["露营地_a"])

    assert removed
    for name in ("manifest.json", "_object.json", "article.md", "gallery.md", "assets"):
        assert not (target / name).exists(), name
    assert evidence.is_file()
    assert (sibling / "manifest.json").is_file()


def test_publish_angle_derives_category_from_carrier_and_intent():
    """底稿中心：angle 为底稿派生类目（载体 + writingIntent 标签），不再用 templateId 模板。"""
    from content.post.route_core import _publish_angle

    # 图片/画报作品落「画报」类目。
    assert _publish_angle({"carrier": "image"}) == "画报"
    assert _publish_angle({"carrier": "image"}) == "画报"
    # 文章按底稿派生的 writingIntent 标签归类。
    assert _publish_angle({"carrier": "article", "writingIntent": "planning_consultation"}) == "攻略"
    assert _publish_angle({"carrier": "article", "writingIntent": "decision_experience"}) == "体验"
    assert _publish_angle({"carrier": "article", "writingIntent": "post_trip_journal"}) == "游记"
    # 缺失/未知 intent 回退「攻略」，templateId 不再影响 angle。
    assert _publish_angle({"carrier": "article"}) == "攻略"
    assert _publish_angle({"templateId": "线路_自驾路书"}) == "攻略"


def test_promote_rglob_locates_object_layout():
    posts, _ = _materialize()
    # 发布装配定位口径：rglob(manifest) + 正文存在性。
    leaves = [
        m.parent
        for m in sorted(posts.rglob("manifest.json"))
        if (m.parent / "article.md").exists() or (m.parent / "gallery.md").exists()
    ]
    assert len(leaves) == 3, leaves
    for leaf in leaves:
        rel = leaf.relative_to(posts)
        assert rel.parts[0] == "article", rel
        assert len(rel.parts) == 4, rel  # <type>/<angle>/<title>/<seq>
        assert rel.parts[1] == ANGLE, rel
        assert rel.parts[3].isdigit(), rel


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"post dir layout tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
