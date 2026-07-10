"""annotate CLI + publish_filter 发布门契约。

可直接运行：python3 quwoquan_data/tests/local_contract/annotate/test_annotate_publish_filter__local_contract_test.py
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

import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(SCRIPTS_ROOT))
os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp(prefix="anno_rt_")

from _common.io import read_json, write_json  # noqa: E402
from _common.article_package import compute_document_sha256  # noqa: E402
from _common.paths import ensure_batch_layout  # noqa: E402
from _common import content_object  # noqa: E402
from _common.review_ledger import (  # noqa: E402
    ReviewItem,
    ReviewLedger,
    JUDGE_DOUBTFUL,
    KIND_ARTICLE,
    KIND_IMAGE,
    STATE_PUBLISHABLE,
    STATE_DISCARD,
    load_ledger,
    resolve_publish_state,
    save_ledger,
)
from _common.publish_filter import apply_publish_filter  # noqa: E402
from annotate.handler import handle_annotate  # noqa: E402

TASK = "anno_task"
BATCH = "b1"
REF = "topic_x"


def _seed_ledger() -> None:
    ensure_batch_layout(TASK, BATCH, "produce")
    content_object.register_content_object(TASK, BATCH, REF, content_type="article", angle="体验", title=REF)
    ledger = ReviewLedger(
        taskId=TASK,
        batchId=BATCH,
        ref=REF,
        article=ReviewItem(kind=KIND_ARTICLE, target=REF, agentJudgment="credible", agentScore=4),
        images=[
            ReviewItem(kind=KIND_IMAGE, target="img_safe", agentJudgment="credible", agentScore=4),
            ReviewItem(kind=KIND_IMAGE, target="img_face", agentJudgment=JUDGE_DOUBTFUL, agentScore=2, reasons=["face"]),
        ],
    )
    save_ledger(ledger)


def _args(**kw) -> argparse.Namespace:
    base = dict(
        task=TASK, batch=BATCH, list=False, ref=None, kind=None, target=None,
        judgment=None, score=None, override=None, reprocess=False, note=None,
    )
    base.update(kw)
    return argparse.Namespace(**base)


def test_doubtful_image_blocks_until_human():
    _seed_ledger()
    ledger = load_ledger(TASK, BATCH, REF)
    face = ledger.find_item(KIND_IMAGE, "img_face")
    # agent 存疑 + 默认 requireHumanWhenDoubtful → fix（必须人确认）
    assert resolve_publish_state(face, ledger.policy) != STATE_PUBLISHABLE


def test_annotate_human_publishable():
    _seed_ledger()
    handle_annotate(_args(ref=REF, kind=KIND_IMAGE, target="img_face", judgment="credible", score=4))
    ledger = load_ledger(TASK, BATCH, REF)
    face = ledger.find_item(KIND_IMAGE, "img_face")
    assert resolve_publish_state(face, ledger.policy) == STATE_PUBLISHABLE


def test_annotate_override_discard():
    _seed_ledger()
    handle_annotate(_args(ref=REF, kind=KIND_IMAGE, target="img_face", override="discard"))
    ledger = load_ledger(TASK, BATCH, REF)
    face = ledger.find_item(KIND_IMAGE, "img_face")
    assert resolve_publish_state(face, ledger.policy) == STATE_DISCARD


def test_annotate_reprocess_count():
    _seed_ledger()
    handle_annotate(_args(ref=REF, kind=KIND_IMAGE, target="img_face", reprocess=True))
    handle_annotate(_args(ref=REF, kind=KIND_IMAGE, target="img_face", reprocess=True))
    ledger = load_ledger(TASK, BATCH, REF)
    assert ledger.find_item(KIND_IMAGE, "img_face").reprocessCount == 2


def test_publish_filter_discard_and_homepage(tmp_path_factory=None):
    publish_root = Path(tempfile.mkdtemp(prefix="pf_pub_"))
    # 一个实体有主页，一个没有
    (publish_root / "entities" / "地点" / "景区" / "有主页" ).mkdir(parents=True, exist_ok=True)
    (publish_root / "entities" / "地点" / "景区" / "有主页" / "page.md").write_text("# 有主页\n", encoding="utf-8")

    topic = Path(tempfile.mkdtemp(prefix="pf_topic_"))
    (topic / "assets").mkdir(parents=True, exist_ok=True)
    (topic / "assets" / "bad.jpg").write_bytes(b"x")
    write_json(topic / "manifest.json", {
        "topicId": REF,
        "entityRefs": ["/entity/地点/景区/有主页", "/entity/地点/景区/无主页"],
        "assets": [
            {"assetId": "ok", "fileName": "ok.jpg"},
            {"assetId": "bad", "fileName": "bad.jpg"},
        ],
    })
    (topic / "article.md").write_text(
        "# t\n\n:::figure\n![x](asset://bad)\nbad\n:::\n\n"
        "正文提到[无主页](/entity/地点/景区/无主页)。\n",
        encoding="utf-8",
    )
    # 账本：文章可发布，bad 图 discard
    ledger = ReviewLedger(
        taskId=TASK, batchId=BATCH, ref=REF,
        article=ReviewItem(kind=KIND_ARTICLE, target=REF, agentJudgment="credible", agentScore=4),
        images=[
            ReviewItem(kind=KIND_IMAGE, target="ok", agentJudgment="credible", agentScore=4),
            ReviewItem(kind=KIND_IMAGE, target="bad", humanOverride="discard"),
        ],
    )
    (topic / "5.review").mkdir(parents=True, exist_ok=True)
    write_json(topic / "5.review" / "review_ledger.json", ledger.to_dict())

    verdict = apply_publish_filter(topic, publish_root)
    assert verdict.publishable is True
    assert "bad" in verdict.discarded_assets
    assert "无主页" in "".join(verdict.filtered_entities)
    assert verdict.manifest["pendingEntityMentions"][0]["status"] == "pending_review"
    assert verdict.manifest["pendingEntityMentions"][0]["surface"] == "无主页"
    # discard 图从 manifest.assets 剔除
    asset_ids = {a["assetId"] for a in verdict.manifest["assets"]}
    assert "bad" not in asset_ids and "ok" in asset_ids
    # 无主页实体被过滤
    assert all("无主页" not in r for r in verdict.manifest["entityRefs"])
    # 正文 figure 引用 bad 被剔除
    assert "asset://bad" not in verdict.article_md
    # 无主页实体链接被降级为普通文本，避免发布可点击实体引用
    assert "[无主页](/entity/地点/景区/无主页)" not in verdict.article_md
    assert "正文提到无主页" in verdict.article_md


def test_publish_filter_accepts_release_entities_root():
    release_root = Path(tempfile.mkdtemp(prefix="pf_release_"))
    entities_root = release_root / "entities"
    (entities_root / "地点" / "景区" / "有主页").mkdir(parents=True, exist_ok=True)
    (entities_root / "地点" / "景区" / "有主页" / "page.md").write_text("# 有主页\n", encoding="utf-8")

    topic = Path(tempfile.mkdtemp(prefix="pf_topic_release_"))
    write_json(topic / "manifest.json", {
        "topicId": REF,
        "entityRefs": ["/entity/地点/景区/有主页", "/entity/地点/景区/无主页"],
        "assets": [],
    })
    (topic / "article.md").write_text("# t\n\n正文。\n", encoding="utf-8")

    verdict = apply_publish_filter(topic, release_root, entity_homepage_root=entities_root)
    assert verdict.publishable is True
    assert verdict.filtered_entities == ["/entity/地点/景区/无主页"]
    assert verdict.manifest["entityRefs"] == ["/entity/地点/景区/有主页"]
    assert verdict.manifest["pendingEntityMentions"][0]["sourceEntityRef"] == "/entity/地点/景区/无主页"


def test_publish_filter_syncs_readonly_ref_projections_after_entity_filter():
    publish_root = Path(tempfile.mkdtemp(prefix="pf_projection_pub_"))
    (publish_root / "entities" / "地点" / "景区" / "有主页").mkdir(parents=True, exist_ok=True)
    (publish_root / "entities" / "地点" / "景区" / "有主页" / "page.md").write_text("# 有主页\n", encoding="utf-8")

    topic = Path(tempfile.mkdtemp(prefix="pf_projection_topic_"))
    write_json(topic / "manifest.json", {
        "topicId": REF,
        "entityRefs": ["/entity/地点/景区/有主页", "/entity/地点/景区/无主页"],
        "normalizedEntityRefs": ["entity:景区:有主页", "entity:景区:无主页"],
        "semanticMentions": [],
        "intersectionHints": [
            {"source": "entityRef", "actionTargetId": "entity:景区:有主页"},
            {"source": "entityRef", "actionTargetId": "entity:景区:无主页"},
            {"source": "tagRef", "actionTargetId": "Topic/旅行"},
        ],
        "assets": [],
    })
    (topic / "article.md").write_text("# t\n\n正文。\n", encoding="utf-8")

    verdict = apply_publish_filter(topic, publish_root)

    assert "semanticMentions" not in verdict.manifest
    assert verdict.manifest["entityRefs"] == ["/entity/地点/景区/有主页"]
    assert verdict.manifest["normalizedEntityRefs"] == ["entity:景区:有主页"]
    assert verdict.manifest["pendingEntityMentions"][0]["candidateId"].startswith("entity_candidate_")
    action_targets = [item.get("actionTargetId") for item in verdict.manifest["intersectionHints"]]
    assert "entity:景区:无主页" not in action_targets
    assert "entity:景区:有主页" in action_targets
    assert "Topic/旅行" in action_targets


def test_publish_filter_syncs_article_digest_and_provenance_after_filter():
    publish_root = Path(tempfile.mkdtemp(prefix="pf_digest_pub_"))
    topic = Path(tempfile.mkdtemp(prefix="pf_digest_topic_"))
    article = (
        "# t\n\n"
        "正文提到[无主页](/entity/地点/景区/无主页)，发布过滤后链接会降级为普通文本。\n"
    )
    original_digest = compute_document_sha256(article)
    write_json(topic / "manifest.json", {
        "topicId": REF,
        "contentType": "article",
        "entityRefs": ["/entity/地点/景区/无主页"],
        "normalizedEntityRefs": ["entity:景区:无主页"],
        "tagRefs": ["Topic/旅行/玩法/观光游览", "Format/内容角度/攻略"],
        "assets": [],
    })
    (topic / "article.md").write_text(article, encoding="utf-8")
    (topic / "5.review").mkdir(parents=True, exist_ok=True)
    write_json(topic / "5.review" / "provenance.json", {
        "schemaVersion": "quwoquan_data.provenance",
        "final": {"contentType": "article", "generator": "agent", "articleDigest": original_digest},
    })

    verdict = apply_publish_filter(topic, publish_root)
    verdict.write_into(topic)

    filtered_article = (topic / "article.md").read_text(encoding="utf-8")
    filtered_digest = compute_document_sha256(filtered_article)
    manifest = read_json(topic / "manifest.json")
    provenance = read_json(topic / "5.review" / "provenance.json")
    assert "[无主页](/entity/地点/景区/无主页)" not in filtered_article
    assert manifest["articleMarkdownDigest"] == filtered_digest
    assert manifest["documentSha256"] == filtered_digest
    assert provenance["final"]["articleDigest"] == filtered_digest
    assert filtered_digest != original_digest


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"annotate/publish_filter tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
