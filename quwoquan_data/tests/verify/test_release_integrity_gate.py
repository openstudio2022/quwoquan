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
    _write(unit_dir, "# 来源\n\n" + "这是一个足够长的实体或图文底稿。" * 80)
    write_json(
        unit_dir.parent / "meta.json",
        {
            "schemaVersion": "quwoquan_data.source_unit",
            "sourceKind": kind,
            "platform": kind,
            "sourceUseMode": source_use_mode,
            "authorizationProof": "fixture-proof",
            "licenseSnapshot": "fixture-license",
        },
    )
    asset = unit_dir.parent / "assets" / "001.jpg"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"image-" + unit.encode("utf-8"))
    return source_ref


def _seed_release_post(title: str, topic: str, *, base_source: str, asset_source: str, asset_sha: str = "sha256:abc") -> None:
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
            "sourceUseMode": "licensed_adaptation",
            "baseDraftText": "这是足够长的图文底稿。" * 80,
        },
    )
    _write(runtime_post / "4.draft" / "prompt.md", "基于授权底稿创作")
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
    manifest = {
        "topicId": topic,
        "contentType": "article",
        "carrier": "article",
        "entityRefs": ["/entity/地点/景区/毕棚沟"],
        "assets": [
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
        ],
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


def test_release_integrity_flags_cross_post_asset_reuse_and_empty_source_ref():
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
    assert "asset sha reused across posts" in text
    assert "base draft ledger does not map" in text


def test_runtime_integrity_flags_same_asset_contract_before_release():
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
    assert "asset sha reused across posts" in text
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
