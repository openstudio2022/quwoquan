"""materialize 内容对象目录布局契约 ——「成品落对象根 posts/{type}/{angle}/{title}/{seq}」。

覆盖（对象优先，§2.4/§2.5）：
- post 成品落 batch 根 `posts/<type>/<angle>/<标题>/<seq>/`（含 angle 必选层）。
- 对象坐标（angle/title/seq）= `_shared/content_object_index.json` 路由真相；seq 默认 1，同
  (type,angle,title) 组多 ref 按 ref 稳定递增（支持标题重复）。
- manifest.publishSeq/publishAngle/publishTitle 与对象目录坐标一致。
- promote 以 rglob(manifest.json)+正文存在性定位 post，对四层对象结构成立（type/angle/title/seq）。

可直接运行：python3 quwoquan_data/tests/produce/test_post_dir_layout.py
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
import sys
import tempfile
from pathlib import Path
import json
import shutil

sys.path.insert(0, str(SCRIPTS_ROOT))

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

from _common.content_object import register_content_object  # noqa: E402
from _common.draft_io import write_agent_draft  # noqa: E402
from _common.io import read_json, write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    PUBLISH_ROOT,
    batch_entity_object_dir,
    batch_command_root,
    batch_root,
    ensure_batch_layout,
    ensure_task_layout,
)
from _common.stage_reports import write_stage_result  # noqa: E402
from produce.materialize import _materialized_asset_refs, materialize_posts  # noqa: E402
from publish_ops.promote_to_publish import promote_task_batch, promote_task_entities  # noqa: E402

TASK = "目录布局_gwt"
BATCH = "pilot"
ANGLE = "攻略"


def _seed_post(ref: str, publish_title: str) -> None:
    article = f"# {publish_title}\n\n正文：{ref} 的真实内容展开。"
    register_content_object(TASK, BATCH, ref, content_type="article", angle=ANGLE, title=publish_title)
    write_stage_result(TASK, BATCH, "produce", "review", ref, {"decision": "approved"})
    write_stage_result(
        TASK, BATCH, "produce", "compose", ref,
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
        TASK,
        BATCH,
        ref,
        article,
        model="test-agent/post-dir-layout",
        cited_source_paths=[],
        covered_facts=[],
        agent_run_id=f"run-{ref}",
        agent_id="agent-post-dir-layout",
    )


def _posts_root() -> Path:
    return batch_root(TASK, BATCH) / "posts"


def _materialize() -> tuple[Path, list[Path]]:
    ensure_task_layout(TASK)
    ensure_batch_layout(TASK, BATCH, "produce")
    import shutil

    # 清理对象树 + 路由，保证可重复运行。
    batch = batch_root(TASK, BATCH)
    for sub in (batch / "posts", batch / "_shared"):
        if sub.exists():
            shutil.rmtree(sub)
    legacy = batch_command_root(TASK, BATCH, "produce") / "results"
    if legacy.exists():
        shutil.rmtree(legacy)
    # 同一 (type,angle,title) 两篇（ref 排序 a<b → 1,2），另一标题一篇。
    _seed_post("露营地_a", "成都周边小众露营地实测")
    _seed_post("露营地_b", "成都周边小众露营地实测")
    _seed_post("都江堰_a", "都江堰一日游怎么玩")
    materialized = materialize_posts(TASK, BATCH, "article")
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
        batch_root(TASK, BATCH)
        / "entities/地点/景区/毕棚沟/1.download/sources/03.article_base/assets/001.jpg"
    )
    source_ref, source_asset_ref = _materialized_asset_refs(
        {"sourcePath": str(source_path)},
        task_id=TASK,
        batch_id=BATCH,
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


def test_publish_angle_derives_category_from_carrier_and_intent():
    """底稿中心：angle 为底稿派生类目（载体 + writingIntent 标签），不再用 templateId 模板。"""
    from produce.route_workflow import _publish_angle

    # 图片/画报作品落「画报」类目。
    assert _publish_angle({"carrier": "image"}) == "画报"
    assert _publish_angle({"carrier": "gallery"}) == "画报"
    # 文章按底稿派生的 writingIntent 标签归类。
    assert _publish_angle({"carrier": "article", "writingIntent": "planning_consultation"}) == "攻略"
    assert _publish_angle({"carrier": "article", "writingIntent": "decision_experience"}) == "体验"
    assert _publish_angle({"carrier": "article", "writingIntent": "post_trip_journal"}) == "游记"
    # 缺失/未知 intent 回退「攻略」，templateId 不再影响 angle。
    assert _publish_angle({"carrier": "article"}) == "攻略"
    assert _publish_angle({"templateId": "线路_自驾路书"}) == "攻略"


def test_promote_rglob_locates_object_layout():
    posts, _ = _materialize()
    # 复刻 promote_from_posts_root 的定位口径：rglob(manifest) + 正文存在性。
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


def test_promote_injects_and_preserves_published_at():
    posts, _ = _materialize()
    manifest_path = posts / "article" / ANGLE / "都江堰一日游怎么玩" / "1" / "manifest.json"
    raw = read_json(manifest_path)
    assert "publishedAt" not in raw

    count, skipped = promote_task_batch(TASK, BATCH, dry_run=False)
    assert count == 3
    assert skipped == 0

    publish_manifest = PUBLISH_ROOT / "posts" / "article" / ANGLE / "都江堰一日游怎么玩" / "1" / "manifest.json"
    first = json.loads(publish_manifest.read_text(encoding="utf-8"))
    assert first["publishedAt"]

    count2, skipped2 = promote_task_batch(TASK, BATCH, dry_run=False)
    assert count2 == 3
    assert skipped2 == 0
    second = json.loads(publish_manifest.read_text(encoding="utf-8"))
    assert second["publishedAt"] == first["publishedAt"]


def test_promote_task_entities_only_copies_approved_homepages():
    approved_name = "都江堰_approved_only"
    rejected_name = "青城山_rejected_only"
    ensure_task_layout(TASK)
    shutil.rmtree(PUBLISH_ROOT / "entities" / "地点" / "景区" / approved_name, ignore_errors=True)
    shutil.rmtree(PUBLISH_ROOT / "entities" / "地点" / "景区" / rejected_name, ignore_errors=True)
    approved = batch_entity_object_dir(TASK, BATCH, "地点", "景区", approved_name)
    approved.mkdir(parents=True, exist_ok=True)
    (approved / "page.md").write_text(f"# {approved_name}\n\n主页。", encoding="utf-8")
    write_json(approved / "_entity.json", {"label": approved_name, "domain": "地点", "type": "景区"})
    write_json(approved / "manifest.json", {"assets": []})
    (approved / "5.review").mkdir(parents=True, exist_ok=True)
    write_json(approved / "5.review" / "review.json", {"decision": "approved"})

    rejected = batch_entity_object_dir(TASK, BATCH, "地点", "景区", rejected_name)
    rejected.mkdir(parents=True, exist_ok=True)
    (rejected / "page.md").write_text(f"# {rejected_name}\n\n主页。", encoding="utf-8")
    write_json(rejected / "_entity.json", {"label": rejected_name, "domain": "地点", "type": "景区"})
    write_json(rejected / "manifest.json", {"assets": []})
    (rejected / "5.review").mkdir(parents=True, exist_ok=True)
    write_json(rejected / "5.review" / "review.json", {"decision": "rejected"})

    count = promote_task_entities(TASK, dry_run=False)
    assert count >= 1
    assert (PUBLISH_ROOT / "entities" / "地点" / "景区" / approved_name / "page.md").is_file()
    assert not (PUBLISH_ROOT / "entities" / "地点" / "景区" / rejected_name / "page.md").exists()


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"post dir layout tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
