"""Release integrity gate regression tests."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import hashlib
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
_TMP = Path(tempfile.mkdtemp(prefix="release_integrity_"))
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.io import write_json  # noqa: E402
from core import paths as _paths_mod  # noqa: E402
from core.paths import execution_root, release_root  # noqa: E402
from core.release_layout import payload_file  # noqa: E402
from core.tree_integrity import tree_integrity_stats  # noqa: E402
from content.release.canonical.integrity import scan_release_integrity, scan_runtime_batch_integrity  # noqa: E402
from content.source.source_unit import resolve_entity_object_dir, write_source_unit  # noqa: E402
from content.homepage.homepage import _entity_base_draft  # noqa: E402
from content.release.canonical.assemble import assemble_release  # noqa: E402
from content.release.canonical.gate import _quota_issues  # noqa: E402


TASK = "20260711--travel-homepage-integrity--cn-sichuan--canary-901"
RELEASE = "release_gate"


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _retarget_roots() -> None:
    os.environ["QWQ_DATA_ROOT"] = str(_TMP)
    os.environ["QWQ_OUTPUT_ROOT"] = str(_TMP / "output")
    os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")
    _paths_mod.DATA_ROOT = _TMP
    _paths_mod.OUTPUT_ROOT = _TMP / "output"
    _paths_mod.DATA_OUTPUT_ROOT = _paths_mod.OUTPUT_ROOT / "data"
    _paths_mod.DATA_EXECUTIONS_ROOT = _paths_mod.DATA_OUTPUT_ROOT / "tasks"
    _paths_mod.DATA_LOCAL_ROOT = _paths_mod.DATA_OUTPUT_ROOT / "local"
    _paths_mod.RELEASE_ROOT = _paths_mod.DATA_OUTPUT_ROOT / "releases"
    _paths_mod.RUNTIME_ROOT = _paths_mod.DATA_EXECUTIONS_ROOT
    _paths_mod.PUBLISH_ROOT = _TMP / "publish"
    _paths_mod.DATA_EXECUTIONS_ROOT = _paths_mod.DATA_EXECUTIONS_ROOT


def _reset() -> None:
    _retarget_roots()
    shutil.rmtree(_TMP, ignore_errors=True)
    shutil.rmtree(execution_root(TASK), ignore_errors=True)
    shutil.rmtree(release_root(RELEASE), ignore_errors=True)
    _TMP.mkdir(parents=True, exist_ok=True)


def _seed_source(
    entity: str,
    unit: str,
    *,
    kind: str,
    source_use_mode: str = "licensed_adaptation",
    research_lane: str = "article",
) -> str:
    object_dir = resolve_entity_object_dir(TASK, f"/entity/地点/景区/{entity}")
    source_id = unit.split(".", 1)[-1]
    body = (
        "# 来源\n\n"
        f"{entity}位于四川省阿坝藏族羌族自治州，属于高山峡谷型景区。"
        f"{entity}景区海拔跨度较大，游览线路通常围绕湖泊、森林和雪山展开。"
        f"{entity}在秋季以彩林景观受到关注，夏季则适合避暑和观水。"
        f"{entity}周边交通以成都方向进入为主，游客通常需要预留较完整的一天。"
        f"{entity}因自然景观集中，适合实体主页介绍位置、景观类型、季节和交通条件。"
    )
    identities = {
        "维基百科": ("wikipedia", "wikipedia_api", f"https://zh.wikipedia.org/wiki/{entity}"),
        "搜狗百科": ("sogou_baike", "sogou_baike_html", f"https://baike.sogou.com/v{entity}"),
        "百度百科": ("baidu_baike", "baidu_baike_html", f"https://baike.baidu.com/item/{entity}"),
    }
    source_kind, extractor, canonical_url = identities.get(
        kind,
        ("web", "generic_html", f"https://example.test/{entity}/{source_id}"),
    )
    manifest = write_source_unit(
        object_dir,
        ordinal=int(unit.split(".", 1)[0]) if unit.split(".", 1)[0].isdigit() else 1,
        source_id=source_id,
        source_md=body,
        clean_md=body,
        quality={"sourceId": source_id, "quality": "B-fact", "score": 5},
        platform=kind,
        source_category=kind,
        source_kind=source_kind,
        extractor=extractor,
        policy_revision=(
            "encyclopedia-primary-v2" if research_lane == "homepage" else ""
        ),
        source_use_mode=source_use_mode,
        research_lane=research_lane,
        license_value="fixture-license",
        url=canonical_url,
        title=f"{entity} {kind}",
        target_ref=f"/entity/地点/景区/{entity}",
        images=[
            {
                "bytes": b"image-" + unit.encode("utf-8"),
                "ext": ".jpg",
                "slug": "001",
                "license": "CC-BY-SA 4.0",
                "credit": "fixture",
            }
        ],
        execution_id=TASK,
        build_variants=False,
    )
    return manifest["sourceRef"]


def _seed_execution_post(
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
    runtime_post = execution_root(TASK) / "posts/article/攻略" / title / "1"
    (runtime_post / "assets").mkdir(parents=True, exist_ok=True)
    (runtime_post / "assets" / "cover.jpg").write_bytes(b"same-image")
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


def _seed_runtime_image_post(
    title: str,
    *,
    entity: str,
    source_ref: str,
    caption: str,
) -> None:
    runtime_post = execution_root(TASK) / "posts/image/画报" / title / "1"
    asset_bytes = b"image-post-bytes"
    (runtime_post / "assets").mkdir(parents=True, exist_ok=True)
    (runtime_post / "assets" / "cover.jpg").write_bytes(asset_bytes)
    write_json(
        runtime_post / "manifest.json",
        {
            "topicId": title,
            "contentType": "image",
            "carrier": "image",
            "entityRefs": [f"/entity/地点/景区/{entity}"],
            "assets": [
                {
                    "assetId": "cover",
                    "fileName": "cover.jpg",
                    "sha256": hashlib.sha256(asset_bytes).hexdigest(),
                    "caption": caption,
                    "sourceRef": source_ref,
                    "sourceAssetRef": source_ref.replace("source.md", "assets/001.jpg"),
                    "authorizationProof": "fixture-proof",
                    "sourceCollectionId": f"fixture:{entity}:image",
                }
            ],
        },
    )


def _seed_release_root() -> None:
    write_json(
        release_root(RELEASE) / "release_manifest.json",
        {
            "schemaVersion": "quwoquan_data.release_manifest",
            "releaseId": RELEASE,
            "executionId": TASK,
        },
    )
    write_json(
        execution_root(TASK) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {}},
    )


def _seed_v3_creator_only_release(*, broken_profile_ref: bool = False) -> None:
    creator_id = "creator_a"
    creator = _paths_mod.PUBLISH_ROOT / "creators" / creator_id
    write_json(
        creator / "_creator.json",
        {
            "schemaVersion": "quwoquan_data.creator_object/1",
            "creatorId": creator_id,
            "profileRef": "missing.json" if broken_profile_ref else "profile.json",
            "assetsRef": "assets.refs.json",
            "worksRefsRef": "works.refs.ndjson",
            "tagRefs": [],
            "entityRefs": [],
        },
    )
    write_json(creator / "profile.json", {"userId": creator_id})
    write_json(creator / "assets.refs.json", {"assets": []})
    _write(creator / "works.refs.ndjson", "")
    for required in ("entities", "posts", "tags", "media/objects"):
        (_paths_mod.PUBLISH_ROOT / required).mkdir(parents=True, exist_ok=True)
    canonical_merkle = tree_integrity_stats(_paths_mod.PUBLISH_ROOT)["merkleRoot"]
    root = release_root(RELEASE)
    desired = {
        "schemaVersion": "quwoquan_data.release_desired_state/1",
        "releaseId": RELEASE,
        "desiredRefs": {"posts": [], "entities": [], "creators": [creator_id]},
    }
    write_json(
        payload_file(root, "release.json"),
        {
            "schemaVersion": "quwoquan_data.release/3",
            "releaseId": RELEASE,
            "canonicalMerkle": canonical_merkle,
        },
    )
    write_json(payload_file(root, "desired_state.json"), desired)
    write_json(
        payload_file(root, "sample_bundle.json"),
        {
            "schemaVersion": "quwoquan_data.release_sample/1",
            "releaseId": RELEASE,
            "posts": [],
            "entities": [],
        },
    )
    write_json(
        payload_file(root, "media_manifest.json"),
        {
            "schemaVersion": "quwoquan_data.release_media_manifest/1",
            "releaseId": RELEASE,
            "assets": [],
        },
    )
    write_json(
        payload_file(root, "index/objects.json"),
        {
            "schemaVersion": "quwoquan_data.release_object_index/1",
            "posts": [],
            "entities": [],
            "creators": [creator_id],
        },
    )


def test_release_integrity_accepts_v3_creator_only_release_with_real_closure():
    _reset()
    _seed_v3_creator_only_release()

    report = scan_release_integrity(RELEASE)

    assert report["passed"], report
    assert report["stats"]["creatorCount"] == 1
    assert report["stats"]["entityCount"] == 0
    assert report["stats"]["postCount"] == 0


def test_release_integrity_blocks_v3_creator_only_release_with_broken_closure():
    _reset()
    _seed_v3_creator_only_release(broken_profile_ref=True)

    report = scan_release_integrity(RELEASE)

    assert not report["passed"]
    assert "creator_local_ref_missing" in "\n".join(report["issues"])


def _seed_approved_entity(entity: str) -> None:
    entity_dir = execution_root(TASK) / "entities/地点/景区" / entity
    _write(entity_dir / "page.md", f"# {entity}\n\n实体主页。")
    write_json(entity_dir / "_entity.json", {"name": entity, "type": "地点/景区"})
    write_json(entity_dir / "manifest.json", {"entityRef": f"/entity/地点/景区/{entity}"})
    write_json(entity_dir / "5.review" / "review.json", {"decision": "approved"})
    write_json(entity_dir / "5.review" / "attestation.json", {"decision": "approved"})
    write_json(entity_dir / "5.review" / "evidence_index.json", {"refs": ["runtime"]})


def test_runtime_integrity_allows_same_asset_contract_before_release():
    _reset()
    base = _seed_source("毕棚沟", "01.base", kind="维基百科")
    _seed_execution_post("毕棚沟A", "a", base_source=base, asset_source=base, asset_sha="sha256:abc")
    _seed_execution_post("毕棚沟B", "b", base_source=base, asset_source="", asset_sha="sha256:abc")
    write_json(
        execution_root(TASK) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {base: "a"}},
    )

    report = scan_runtime_batch_integrity(TASK)
    text = "\n".join(report["issues"])

    assert not report["passed"]
    assert "missing manifest.assets[].sourceRef" in text
    assert "asset sha reused across posts" not in text
    assert "base draft ledger does not map" in text


def test_runtime_integrity_blocks_garbled_caption_for_image_post():
    _reset()
    source_ref = _seed_source("光雾山", "01.image", kind="维基百科")
    _seed_runtime_image_post(
        "光雾山乱码图",
        entity="光雾山",
        source_ref=source_ref,
        caption="500px provided description: ???????????????????????????????? [#?? ,#??]",
    )

    report = scan_runtime_batch_integrity(TASK)
    text = "\n".join(report["issues"])

    assert not report["passed"]
    assert "imageCaption" in text


def test_runtime_integrity_blocks_known_wrong_place_image():
    _reset()
    source_ref = _seed_source("剑门关", "01.image", kind="维基百科")
    title = "剑门关·20120430杭州临安浙西大峡谷剑门关水库"
    runtime_post = execution_root(TASK) / "posts/image/画报" / title / "1"
    asset_bytes = b"wrong-place-image"
    asset_sha = hashlib.sha256(asset_bytes).hexdigest()
    (runtime_post / "assets").mkdir(parents=True, exist_ok=True)
    (runtime_post / "assets" / "cover.jpg").write_bytes(asset_bytes)
    source_fields = {
        "sourceCollectionId": "fixture:wrong-place",
        "creator": "fixture",
        "collectionPageUrl": "https://example.test/wrong-place",
        "license": "CC-BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "fixture-proof",
    }
    write_json(
        runtime_post / "manifest.json",
        {
            "topicId": title,
            "contentType": "image",
            "carrier": "image",
            "title": title,
            "caption": "20120430杭州临安浙西大峡谷剑门关水库",
            "entityRefs": [],
            **source_fields,
            "assets": [
                {
                    "assetId": "cover",
                    "fileName": "cover.jpg",
                    "sha256": asset_sha,
                    "caption": "20120430杭州临安浙西大峡谷剑门关水库",
                    "sourceRef": source_ref,
                    "sourceAssetRef": source_ref.replace("source.md", "assets/001.jpg"),
                    **source_fields,
                }
            ],
        },
    )

    report = scan_runtime_batch_integrity(TASK)
    text = "\n".join(report["issues"])

    assert not report["passed"]
    assert "已知错位图片词" in text


def test_runtime_integrity_allows_article_asset_from_independent_source_unit():
    _reset()
    base = _seed_source("毕棚沟", "01.base", kind="维基百科")
    other = _seed_source("毕棚沟", "02.other", kind="搜狗百科")
    _seed_execution_post("毕棚沟C", "c", base_source=base, asset_source=other, asset_sha="sha256:def")
    write_json(
        execution_root(TASK) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {base: "c"}},
    )
    report = scan_runtime_batch_integrity(TASK)
    text = "\n".join(report["issues"])
    assert "sourceRef must match article baseSourceRef" not in text
    assert "sourceAssetRef must belong to its declared sourceRef unit" not in text


def test_runtime_integrity_allows_factual_reference_prompted_as_adaptation():
    """factual_reference_only 以底稿为骨架轻改，执行期完整性门不得误拦截。"""
    _reset()
    base = _seed_source(
        "毕棚沟",
        "01.base",
        kind="去哪儿攻略",
        source_use_mode="factual_reference_only",
    )
    _seed_execution_post(
        "毕棚沟FactOnly",
        "fact-only",
        base_source=base,
        asset_source=base,
        source_use_mode="factual_reference_only",
        prompt_text="在底稿基础上做适度润色，Review Gate 会检查 baseDraftFidelity 55%~99.5%。",
    )
    write_json(
        execution_root(TASK) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {base: "fact-only"}},
    )
    report = scan_runtime_batch_integrity(TASK)
    text = "\n".join(report["issues"])
    assert "is prompted as licensed/adaptable base draft" not in text


def test_runtime_integrity_allows_text_only_article_without_source_asset():
    _reset()
    base = _seed_source("毕棚沟", "01.base", kind="维基百科")
    _seed_execution_post(
        "毕棚沟TextOnly",
        "text-only",
        base_source=base,
        asset_source="",
        publish_media_mode="text_only",
        with_assets=False,
    )
    write_json(
        execution_root(TASK) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {base: "text-only"}},
    )

    runtime_report = scan_runtime_batch_integrity(TASK)
    combined = "\n".join(runtime_report["issues"])

    assert "article must include at least one sourced image asset" not in combined


def test_runtime_integrity_still_blocks_unmarked_assetless_article():
    _reset()
    base = _seed_source("毕棚沟", "01.base", kind="维基百科")
    _seed_execution_post("毕棚沟NoAsset", "no-asset", base_source=base, asset_source="", with_assets=False)
    write_json(
        execution_root(TASK) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {base: "no-asset"}},
    )
    report = scan_runtime_batch_integrity(TASK)
    assert "article must include at least one sourced image asset" in "\n".join(report["issues"])


def test_runtime_integrity_flags_article_asset_not_belonging_to_declared_source_unit():
    _reset()
    base = _seed_source("毕棚沟", "01.base", kind="维基百科")
    other = _seed_source("毕棚沟", "02.other", kind="搜狗百科")
    _seed_execution_post("毕棚沟D", "d", base_source=base, asset_source=other, asset_sha="sha256:ghi")
    manifest_path = execution_root(TASK) / "posts/article/攻略/毕棚沟D/1/manifest.json"
    manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"][0]["sourceAssetRef"] = base.replace("source.md", "assets/001.jpg")
    write_json(manifest_path, manifest)
    write_json(
        execution_root(TASK) / "_shared" / "base_draft_ledger.json",
        {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {base: "d"}},
    )
    report = scan_runtime_batch_integrity(TASK)
    text = "\n".join(report["issues"])
    assert "sourceAssetRef must belong to its declared sourceRef unit" in text


def test_runtime_integrity_flags_entity_homepage_using_guide_base():
    _reset()
    guide = _seed_source("毕棚沟", "05.guide", kind="去哪儿攻略", source_use_mode="factual_reference_only")
    entity_runtime = execution_root(TASK) / "entities/地点/景区/毕棚沟"
    write_json(entity_runtime / "2.quality" / "quality_analysis.json", {"baseDraft": {"sourceRef": guide}})
    write_json(entity_runtime / "3.compose" / "entity_page_input.json", {"payload": {"baseDraft": {"sourceRef": guide}}})
    write_json(entity_runtime / "manifest.json", {"assets": []})
    report = scan_runtime_batch_integrity(TASK)
    text = "\n".join(report["issues"])
    assert "entity homepage base draft must be homepage primary authority source" in text


def test_homepage_base_draft_never_falls_back_to_guide_source():
    _reset()
    _seed_source("毕棚沟", "01.guide", kind="去哪儿攻略", source_use_mode="factual_reference_only")
    wiki = _seed_source(
        "毕棚沟",
        "02.wiki",
        kind="维基百科",
        source_use_mode="factual_reference_only",
        research_lane="homepage",
    )
    chosen = _entity_base_draft(TASK, "地点", "景区", "毕棚沟")
    assert chosen["sourceRef"] == wiki

    _reset()
    _seed_source("毕棚沟", "01.guide", kind="去哪儿攻略", source_use_mode="factual_reference_only")
    assert _entity_base_draft(TASK, "地点", "景区", "毕棚沟") == {}


def test_homepage_base_draft_picks_best_single_baike_no_cross_source():
    """主权威百科单源择优：主页三件套必须同源，不允许跨源拼接。"""
    _reset()
    sogou = _seed_source(
        "毕棚沟", "01.sogou", kind="搜狗百科",
        source_use_mode="factual_reference_only", research_lane="homepage",
    )
    baidu = _seed_source(
        "毕棚沟", "02.baidu", kind="百度百科",
        source_use_mode="factual_reference_only", research_lane="homepage",
    )
    wiki = _seed_source(
        "毕棚沟", "03.wiki", kind="维基百科",
        source_use_mode="factual_reference_only", research_lane="homepage",
    )
    chosen = _entity_base_draft(TASK, "地点", "景区", "毕棚沟")
    # registry authority 顺序与质量共同裁决；当前应稳定选到维基百科，且三件套同源。
    assert chosen["sourceRef"] == wiki, chosen
    assert chosen["primaryEvidenceRef"] == wiki
    assert chosen["sourceRef"] not in (baidu, sogou)
    assert chosen.get("text")

    # 去掉维基后退而求其次取百度（仍是单一最佳源，绝不跨源拼接）。
    _reset()
    _seed_source(
        "毕棚沟", "01.sogou", kind="搜狗百科",
        source_use_mode="factual_reference_only", research_lane="homepage",
    )
    baidu_only = _seed_source(
        "毕棚沟", "02.baidu", kind="百度百科",
        source_use_mode="factual_reference_only", research_lane="homepage",
    )
    chosen_baidu = _entity_base_draft(TASK, "地点", "景区", "毕棚沟")
    assert chosen_baidu["sourceRef"] == baidu_only, chosen_baidu


def test_release_quota_blocks_entity_homepage_outside_primary_post_refs():
    _reset()
    _seed_release_root()
    root = release_root(RELEASE)
    write_json(
        root / "release_manifest.json",
        {
            "schemaVersion": "quwoquan_data.release_manifest",
            "releaseId": RELEASE,
            "executionId": TASK,
        },
    )
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
    runtime_post = execution_root(TASK) / "posts/article/攻略/毕棚沟/1"
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
    write_json(runtime_post / "5.review/attestation.json", {"decision": "approved"})
    write_json(runtime_post / "5.review/evidence_index.json", {"refs": ["runtime"]})
    _seed_approved_entity("毕棚沟")
    _seed_approved_entity("无关替补")

    release = assemble_release(TASK, RELEASE)

    assert (release / "entities/地点/景区/毕棚沟/page.md").is_file()
    assert not (release / "entities/地点/景区/无关替补/page.md").exists()


def _run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    _run_all()
