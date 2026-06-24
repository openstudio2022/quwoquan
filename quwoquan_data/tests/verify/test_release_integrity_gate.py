"""Release integrity gate regression tests."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
_TMP = Path(tempfile.mkdtemp(prefix="release_integrity_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_RELEASE_ROOT"] = str(_TMP / "release")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common.io import write_json  # noqa: E402
from _common.paths import batch_root, release_root  # noqa: E402
from _common.release_integrity import scan_release_integrity, scan_runtime_batch_integrity  # noqa: E402
from build.homepage import _entity_base_draft  # noqa: E402
from publish.assemble import assemble_release  # noqa: E402
from publish.gate import _quota_issues  # noqa: E402
from task.cleanup_generated import build_cleanup_manifest, execute_cleanup  # noqa: E402


TASK = "旅行/地域/四川省/景区/完整性门"
BATCH = "batch_gate"
RELEASE = "release_gate"


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _reset() -> None:
    shutil.rmtree(_TMP, ignore_errors=True)
    shutil.rmtree(batch_root(TASK, BATCH), ignore_errors=True)
    shutil.rmtree(release_root(RELEASE), ignore_errors=True)
    _TMP.mkdir(parents=True, exist_ok=True)


def _seed_source(entity: str, unit: str, *, kind: str, source_use_mode: str = "licensed_adaptation") -> str:
    root = batch_root(TASK, BATCH)
    source_ref = f"entities/地点/景区/{entity}/1.download/sources/{unit}/source.md"
    unit_dir = root / source_ref
    _write(
        unit_dir,
        "# 来源\n\n"
        f"{entity}位于四川省阿坝藏族羌族自治州，属于高山峡谷型景区。"
        f"{entity}景区海拔跨度较大，游览线路通常围绕湖泊、森林和雪山展开。"
        f"{entity}在秋季以彩林景观受到关注，夏季则适合避暑和观水。"
        f"{entity}周边交通以成都方向进入为主，游客通常需要预留较完整的一天。"
        f"{entity}因自然景观集中，适合实体主页介绍位置、景观类型、季节和交通条件。",
    )
    write_json(
        unit_dir.parent / "meta.json",
        {
            "schemaVersion": "quwoquan_data.source_unit",
            "sourceKind": kind,
            "platform": kind,
            "sourceUseMode": source_use_mode,
            "researchLane": "homepage",
            "authorizationProof": "fixture-proof",
            "licenseSnapshot": "fixture-license",
        },
    )
    asset = unit_dir.parent / "assets" / "001.jpg"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"image-" + unit.encode("utf-8"))
    return source_ref


def _seed_release_post(
    title: str,
    topic: str,
    *,
    base_source: str,
    asset_source: str,
    asset_sha: str = "sha256:abc",
    publish_media_mode: str = "",
    with_assets: bool = True,
    source_use_mode: str = "licensed_adaptation",
    prompt_text: str = "基于授权底稿创作",
) -> None:
    runtime_post = batch_root(TASK, BATCH) / "posts/article/攻略" / title / "1"
    release_post = release_root(RELEASE) / "posts/article/攻略" / title / "1"
    for post in (runtime_post, release_post):
        (post / "assets").mkdir(parents=True, exist_ok=True)
        (post / "assets" / "cover.jpg").write_bytes(b"same-image")
    write_json(
        runtime_post / "1.download" / "source_refs.json",
        {"baseSourceRef": base_source, "sources": [{"sourceRef": base_source}]},
    )
    write_json(
        runtime_post / "3.compose" / "writing_pack.json",
        {
            "baseSourceRef": base_source,
            "sourceUseMode": source_use_mode,
            "baseDraftText": "这是足够长的图文底稿。" * 80,
            "publishMediaMode": publish_media_mode,
        },
    )
    _write(runtime_post / "4.draft" / "prompt.md", prompt_text)
    write_json(
        runtime_post / "5.review" / "review.json",
        {
            "decision": "approved",
            "checks": {name: {"passed": True} for name in [
                "entityCoverage", "provenanceRewrite", "evidenceQuality", "carrierConsistency",
                "proseStyle", "imageGate", "travelogueDensity", "crossArticleSimilarity",
                "sectionShape", "generatorProvenance", "factTraceability", "baseDraftFidelity",
                "writingIntentConsistency", "registerMismatch", "contactInfo", "mechanicalHeading",
            ]},
        },
    )
    assets = [
        {
            "assetId": "cover",
            "fileName": "cover.jpg",
            "sha256": asset_sha,
            "caption": "红叶雪山",
            "sourceRef": asset_source,
            "sourceAssetRef": asset_source.replace("source.md", "assets/001.jpg"),
            "authorizationProof": "fixture-proof",
            "alignmentEvidence": "图片来自同一图文底稿并对应正文中的红叶雪山段落。",
        }
    ] if with_assets else []
    manifest = {
        "topicId": topic,
        "contentType": "article",
        "carrier": "article",
        "publishMediaMode": publish_media_mode,
        "entityRefs": ["/entity/地点/景区/毕棚沟"],
        "assets": assets,
    }
    write_json(runtime_post / "manifest.json", manifest)
    write_json(release_post / "manifest.json", manifest)


def _seed_release_root() -> None:
    write_json(
        release_root(RELEASE) / "release_manifest.json",
        {
            "schemaVersion": "quwoquan_data.release_manifest",
            "releaseId": RELEASE,
            "sourceTaskId": TASK,
            "sourceBatchId": BATCH,
        },
    )
    write_json(
        batch_root(TASK, BATCH) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {}},
    )


def _seed_approved_entity(entity: str) -> None:
    entity_dir = batch_root(TASK, BATCH) / "entities/地点/景区" / entity
    _write(entity_dir / "page.md", f"# {entity}\n\n实体主页。")
    write_json(entity_dir / "_entity.json", {"name": entity, "type": "地点/景区"})
    write_json(entity_dir / "manifest.json", {"entityRef": f"/entity/地点/景区/{entity}"})
    write_json(entity_dir / "5.review" / "review.json", {"decision": "approved"})


def test_release_integrity_allows_cross_post_asset_reuse_but_still_flags_empty_source_ref():
    _reset()
    _seed_release_root()
    base = _seed_source("毕棚沟", "01.base", kind="维基百科")
    _seed_release_post("毕棚沟A", "a", base_source=base, asset_source=base, asset_sha="sha256:abc")
    _seed_release_post("毕棚沟B", "b", base_source=base, asset_source="", asset_sha="sha256:abc")
    write_json(
        batch_root(TASK, BATCH) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {base: "a"}},
    )
    report = scan_release_integrity(RELEASE)
    text = "\n".join(report["issues"])
    assert not report["passed"]
    assert "missing manifest.assets[].sourceRef" in text
    assert "asset sha reused across posts" not in text
    assert "base draft ledger does not map" in text


def test_runtime_integrity_allows_same_asset_contract_before_release():
    _reset()
    _seed_release_root()
    base = _seed_source("毕棚沟", "01.base", kind="维基百科")
    _seed_release_post("毕棚沟A", "a", base_source=base, asset_source=base, asset_sha="sha256:abc")
    _seed_release_post("毕棚沟B", "b", base_source=base, asset_source="", asset_sha="sha256:abc")
    write_json(
        batch_root(TASK, BATCH) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {base: "a"}},
    )

    report = scan_runtime_batch_integrity(TASK, BATCH)
    text = "\n".join(report["issues"])

    assert not report["passed"]
    assert "missing manifest.assets[].sourceRef" in text
    assert "asset sha reused across posts" not in text
    assert "base draft ledger does not map" in text


def test_release_integrity_allows_article_asset_from_independent_source_unit():
    _reset()
    _seed_release_root()
    base = _seed_source("毕棚沟", "01.base", kind="维基百科")
    other = _seed_source("毕棚沟", "02.other", kind="搜狗百科")
    _seed_release_post("毕棚沟C", "c", base_source=base, asset_source=other, asset_sha="sha256:def")
    write_json(
        batch_root(TASK, BATCH) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {base: "c"}},
    )
    report = scan_release_integrity(RELEASE)
    text = "\n".join(report["issues"])
    assert "sourceRef must match article baseSourceRef" not in text
    assert "sourceAssetRef must belong to its declared sourceRef unit" not in text


def test_release_integrity_allows_factual_reference_prompted_as_adaptation():
    """产品裁定 full light-edit：factual_reference_only 以底稿为骨架轻改，不再被 release 门拦截。"""
    _reset()
    _seed_release_root()
    base = _seed_source(
        "毕棚沟",
        "01.base",
        kind="去哪儿攻略",
        source_use_mode="factual_reference_only",
    )
    _seed_release_post(
        "毕棚沟FactOnly",
        "fact-only",
        base_source=base,
        asset_source=base,
        source_use_mode="factual_reference_only",
        prompt_text="在底稿基础上做适度润色，Review Gate 会检查 baseDraftFidelity 55%~99.5%。",
    )
    write_json(
        batch_root(TASK, BATCH) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {base: "fact-only"}},
    )
    report = scan_release_integrity(RELEASE)
    text = "\n".join(report["issues"])
    assert "is prompted as licensed/adaptable base draft" not in text


def test_release_integrity_allows_text_only_article_without_source_asset():
    _reset()
    _seed_release_root()
    base = _seed_source("毕棚沟", "01.base", kind="维基百科")
    _seed_release_post(
        "毕棚沟TextOnly",
        "text-only",
        base_source=base,
        asset_source="",
        publish_media_mode="text_only",
        with_assets=False,
    )
    write_json(
        batch_root(TASK, BATCH) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {base: "text-only"}},
    )

    release_report = scan_release_integrity(RELEASE)
    runtime_report = scan_runtime_batch_integrity(TASK, BATCH)
    combined = "\n".join(release_report["issues"] + runtime_report["issues"])

    assert "article must include at least one sourced image asset" not in combined


def test_release_integrity_still_blocks_unmarked_assetless_article():
    _reset()
    _seed_release_root()
    base = _seed_source("毕棚沟", "01.base", kind="维基百科")
    _seed_release_post("毕棚沟NoAsset", "no-asset", base_source=base, asset_source="", with_assets=False)
    write_json(
        batch_root(TASK, BATCH) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {base: "no-asset"}},
    )
    report = scan_release_integrity(RELEASE)
    assert "article must include at least one sourced image asset" in "\n".join(report["issues"])


def test_release_integrity_flags_article_asset_not_belonging_to_declared_source_unit():
    _reset()
    _seed_release_root()
    base = _seed_source("毕棚沟", "01.base", kind="维基百科")
    other = _seed_source("毕棚沟", "02.other", kind="搜狗百科")
    _seed_release_post("毕棚沟D", "d", base_source=base, asset_source=other, asset_sha="sha256:ghi")
    manifest_path = release_root(RELEASE) / "posts/article/攻略/毕棚沟D/1/manifest.json"
    manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"][0]["sourceAssetRef"] = base.replace("source.md", "assets/001.jpg")
    write_json(manifest_path, manifest)
    write_json(
        batch_root(TASK, BATCH) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {base: "d"}},
    )
    report = scan_release_integrity(RELEASE)
    text = "\n".join(report["issues"])
    assert "sourceAssetRef must belong to its declared sourceRef unit" in text


def test_release_integrity_flags_entity_homepage_using_guide_base():
    _reset()
    _seed_release_root()
    guide = _seed_source("毕棚沟", "05.guide", kind="去哪儿攻略", source_use_mode="factual_reference_only")
    entity_runtime = batch_root(TASK, BATCH) / "entities/地点/景区/毕棚沟"
    entity_release = release_root(RELEASE) / "entities/地点/景区/毕棚沟"
    write_json(entity_runtime / "2.quality" / "quality_analysis.json", {"baseDraft": {"sourceRef": guide}})
    write_json(entity_runtime / "3.compose" / "entity_page_input.json", {"payload": {"baseDraft": {"sourceRef": guide}}})
    write_json(entity_release / "manifest.json", {"assets": []})
    report = scan_release_integrity(RELEASE)
    text = "\n".join(report["issues"])
    assert "entity homepage base draft must be encyclopedia/wiki/official/government source" in text
    assert "must not be author travelogue/guide/comment source" in text


def test_homepage_base_draft_never_falls_back_to_guide_source():
    _reset()
    _seed_source("毕棚沟", "01.guide", kind="去哪儿攻略", source_use_mode="factual_reference_only")
    wiki = _seed_source("毕棚沟", "02.wiki", kind="维基百科", source_use_mode="factual_reference_only")
    chosen = _entity_base_draft(TASK, BATCH, "地点", "景区", "毕棚沟")
    assert chosen["sourceRef"] == wiki

    _reset()
    _seed_source("毕棚沟", "01.guide", kind="去哪儿攻略", source_use_mode="factual_reference_only")
    assert _entity_base_draft(TASK, BATCH, "地点", "景区", "毕棚沟") == {}


def test_release_quota_blocks_entity_homepage_outside_primary_post_refs():
    _reset()
    _seed_release_root()
    root = release_root(RELEASE)
    post = root / "posts/article/攻略/毕棚沟/1"
    write_json(
        post / "manifest.json",
        {
            "topicId": "post-1",
            "contentType": "article",
            "carrier": "article",
            "entityRefs": ["/entity/地点/景区/毕棚沟"],
            "assets": [],
        },
    )
    _write(root / "entities/地点/景区/毕棚沟/page.md", "# 毕棚沟")
    _write(root / "entities/地点/景区/无关替补/page.md", "# 无关替补")

    issues = _quota_issues(root)
    text = "\n".join(issues)

    assert "outside primary post refs" in text
    assert "release entity quota: expected 1, got 2" in text


def test_assemble_release_copies_only_primary_post_entity_homepages():
    _reset()
    runtime_post = batch_root(TASK, BATCH) / "posts/article/攻略/毕棚沟/1"
    _write(runtime_post / "article.md", "# 毕棚沟\n\n正文。")
    write_json(
        runtime_post / "manifest.json",
        {
            "topicId": "post-1",
            "contentType": "article",
            "carrier": "article",
            "entityRefs": ["/entity/地点/景区/毕棚沟"],
            "assets": [],
        },
    )
    _seed_approved_entity("毕棚沟")
    _seed_approved_entity("无关替补")

    release = assemble_release(TASK, RELEASE, batch_id=BATCH)

    assert (release / "entities/地点/景区/毕棚沟/page.md").is_file()
    assert not (release / "entities/地点/景区/无关替补/page.md").exists()


def test_cleanup_generated_is_confirm_required_and_preserves_truth_roots():
    _reset()
    path = batch_root(TASK, BATCH)
    path.mkdir(parents=True, exist_ok=True)
    manifest = build_cleanup_manifest(task_id=TASK, batch_id=BATCH)
    assert manifest["wouldDeleteCount"] == 1
    assert "publish" in manifest["preserved"]
    assert path.exists(), "dry-run must not delete"
    result = execute_cleanup(manifest)
    assert result["deletedCount"] == 1
    assert not path.exists()


def _run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    _run_all()
