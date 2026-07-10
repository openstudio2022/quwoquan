"""采样器 + ship 端到端 + publish_filter 契约。

可直接运行：python3 quwoquan_data/tests/api_integration/ship/test_ship_sampling__api_integration_test.py
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

from _common.io import read_json, write_json  # noqa: E402
from ship.sampler import (  # noqa: E402
    build_sample_bundle,
    rank01,
    sample_records,
)


class _PatchedPublishRoot:
    """临时把 PUBLISH_ROOT 指向隔离目录，结束后恢复（避免污染真实 publish/ 与会话内其他用例）。"""

    def __init__(self, root: Path):
        self.root = root

    def __enter__(self):
        import _common.paths as paths
        import ship.sampler as sampler
        import ship.handler as handler
        import publish_ops.build_publish_lookup_indexes as lookup
        self._mods = (paths, sampler, handler, lookup)
        self._saved = (
            paths.PUBLISH_ROOT,
            sampler.PUBLISH_ROOT,
            sampler.SAMPLE_BUNDLE_DIR,
            handler.PUBLISH_ROOT,
            lookup.PUBLISH_MAINLINE,
            lookup.INDEX_ROOT,
            lookup.ENTITY_INDEX_ROOT,
            lookup.POST_INDEX_ROOT,
            lookup.LINK_TARGET_ROOT,
            lookup.COVERAGE_INDEX_ROOT,
        )
        paths.PUBLISH_ROOT = self.root
        sampler.PUBLISH_ROOT = self.root
        sampler.SAMPLE_BUNDLE_DIR = self.root / "sample_bundles"
        handler.PUBLISH_ROOT = self.root
        lookup.PUBLISH_MAINLINE = self.root
        lookup.INDEX_ROOT = self.root / "index"
        lookup.ENTITY_INDEX_ROOT = lookup.INDEX_ROOT / "entities"
        lookup.POST_INDEX_ROOT = lookup.INDEX_ROOT / "posts"
        lookup.LINK_TARGET_ROOT = lookup.INDEX_ROOT / "link_targets"
        lookup.COVERAGE_INDEX_ROOT = lookup.INDEX_ROOT / "coverage"
        return self

    def __exit__(self, *exc):
        paths, sampler, handler, lookup = self._mods
        (
            paths.PUBLISH_ROOT,
            sampler.PUBLISH_ROOT,
            sampler.SAMPLE_BUNDLE_DIR,
            handler.PUBLISH_ROOT,
            lookup.PUBLISH_MAINLINE,
            lookup.INDEX_ROOT,
            lookup.ENTITY_INDEX_ROOT,
            lookup.POST_INDEX_ROOT,
            lookup.LINK_TARGET_ROOT,
            lookup.COVERAGE_INDEX_ROOT,
        ) = self._saved
        return False

MANIFEST = {
    "salt": "test-salt",
    "environments": {
        "prod": {"sampleRatio": 1.0, "postCapPerBucket": 0, "entityCapPerBucket": 0, "maxPosts": 0, "maxEntities": 0},
        "alpha": {"sampleRatio": 0.5, "postCapPerBucket": 2, "entityCapPerBucket": 0, "maxPosts": 0, "maxEntities": 0},
    },
}


def _posts(n: int) -> list[dict]:
    out = []
    for i in range(n):
        out.append({"postRef": f"posts/article/体验/t{i}/1", "contentType": "article", "angle": "体验"})
    return out


def _entities(n: int) -> list[dict]:
    return [{"entityRef": f"地点/景区/e{i}", "domain": "地点", "etype": "景区"} for i in range(n)]


def test_rank_is_deterministic_and_bounded():
    a = rank01("s", "ref-x")
    b = rank01("s", "ref-x")
    assert a == b
    assert 0.0 <= a < 1.0
    assert rank01("s", "ref-x") != rank01("s", "ref-y")


def test_prod_full_sampling():
    bundle = build_sample_bundle("prod", MANIFEST, _posts(20), _entities(10))
    assert bundle["counts"]["posts"] == 20
    assert bundle["counts"]["entities"] == 10


def test_alpha_ratio_and_cap():
    bundle = build_sample_bundle("alpha", MANIFEST, _posts(40), _entities(10))
    # ratio 0.5 → 约半量；cap 2 per bucket(体验) → 最多 2
    assert bundle["counts"]["posts"] <= 2, "postCapPerBucket 应生效"
    # 重跑确定性
    again = build_sample_bundle("alpha", MANIFEST, _posts(40), _entities(10))
    assert bundle["posts"] == again["posts"]


def test_forced_posts_bypass_sampling_ratio_and_cap():
    posts = _posts(40)
    forced_ref = "posts/article/体验/t39/1"
    bundle = build_sample_bundle("alpha", MANIFEST, posts, _entities(10), forced_post_refs=[forced_ref])
    assert forced_ref in bundle["posts"]
    assert forced_ref in bundle["forcedPosts"]
    assert bundle["counts"]["posts"] >= 1


def test_isolated_forced_sample_excludes_default_environment_sample():
    posts = _posts(40)
    forced_ref = "posts/article/体验/t39/1"
    bundle = build_sample_bundle(
        "alpha",
        MANIFEST,
        posts,
        _entities(10),
        forced_post_refs=[forced_ref],
        isolate_forced_sample=True,
    )
    assert bundle["posts"] == [forced_ref]
    assert bundle["forcedPosts"] == [forced_ref]
    assert bundle["isolatedForcedSample"] is True


def test_forced_post_entity_closure_accepts_singular_entity_ref():
    forced_ref = "posts/article/体验/t0/1"
    entity_ref = "地点/景区/e0"
    posts = [{"postRef": forced_ref, "contentType": "article", "angle": "体验", "entityRef": f"/entity/{entity_ref}"}]
    bundle = build_sample_bundle("alpha", MANIFEST, posts, _entities(1), forced_post_refs=[forced_ref])

    assert entity_ref in bundle["entities"]


def test_ship_e2e_writes_bundle_and_meta():
    tmp_publish = Path(tempfile.mkdtemp(prefix="ship_pub_"))
    posts_dir = tmp_publish / "index" / "posts"
    ent_dir = tmp_publish / "index" / "entities"
    posts_dir.mkdir(parents=True, exist_ok=True)
    ent_dir.mkdir(parents=True, exist_ok=True)
    import json
    with open(posts_dir / "article__体验__四川省.ndjson", "w", encoding="utf-8") as f:
        for i in range(30):
            f.write(json.dumps({"postRef": f"posts/article/体验/t{i}/1", "contentType": "article", "angle": "体验"}, ensure_ascii=False) + "\n")
            write_json(
                tmp_publish / "posts" / "article" / "体验" / f"t{i}" / "1" / "manifest.json",
                {"contentType": "article", "assets": []},
            )
    with open(ent_dir / "地点__景区__四川省.ndjson", "w", encoding="utf-8") as f:
        for i in range(20):
            f.write(json.dumps({"entityRef": f"地点/景区/e{i}", "domain": "地点", "etype": "景区"}, ensure_ascii=False) + "\n")

    from ship.handler import handle_ship

    args = argparse.Namespace(
        release_id=None, task=None, batch=None, copy_entities=False,
        env="alpha", skip_promote=True, skip_index=True,
        import_to_db=False, mongo_uri=None,
    )
    with _PatchedPublishRoot(tmp_publish):
        handle_ship(args)

        bundle_path = tmp_publish / "sample_bundles" / "alpha.json"
        assert bundle_path.is_file(), "ship 应写出 alpha sample bundle"
        bundle = read_json(bundle_path)
        assert bundle["environment"] == "alpha"
        assert bundle["counts"]["postsTotal"] == 30

        meta = read_json(tmp_publish / "publish_meta.json")
        assert meta["lastShip"] is not None, "ship 应更新 publish_meta.lastShip"
        assert meta["lastDataReleaseId"], "ship 应记录数据 releaseId"
        assert (tmp_publish / "env_releases" / meta["lastDataReleaseId"] / "alpha.json").is_file()


def test_ship_writes_source_batch_ship_and_import_evidence():
    tmp_publish = Path(tempfile.mkdtemp(prefix="ship_batch_evidence_pub_"))
    tmp_shared = Path(tempfile.mkdtemp(prefix="ship_batch_evidence_shared_"))
    posts_dir = tmp_publish / "index" / "posts"
    ent_dir = tmp_publish / "index" / "entities"
    posts_dir.mkdir(parents=True, exist_ok=True)
    ent_dir.mkdir(parents=True, exist_ok=True)
    import json
    with open(posts_dir / "article__体验__四川省.ndjson", "w", encoding="utf-8") as f:
        f.write(json.dumps({"postRef": "posts/article/体验/t0/1", "contentType": "article", "angle": "体验"}, ensure_ascii=False) + "\n")
    write_json(
        tmp_publish / "posts" / "article" / "体验" / "t0" / "1" / "manifest.json",
        {"contentType": "article", "assets": []},
    )

    from ship.handler import handle_ship
    import ship.handler as handler

    saved_run_importer = handler._run_importer
    saved_batch_shared_dir = handler.batch_shared_dir

    def fake_run_importer(mongo_uri, bundles, *, release_id, mode, delete_policy, source_owner, dry_run):
        reports = []
        for bundle in bundles:
            report = tmp_publish / "env_releases" / release_id / f"import-{bundle.stem}.json"
            write_json(report, {"schemaVersion": "test.import", "status": "dry-run", "environment": bundle.stem})
            reports.append(report)
        return reports

    try:
        handler._run_importer = fake_run_importer
        handler.batch_shared_dir = lambda task_id, batch_id: tmp_shared
        args = argparse.Namespace(
            release_id=None, task="旅行/地域/测试省/景区/试跑", batch="batch_1", copy_entities=False,
            env="alpha", skip_promote=True, skip_index=True,
            import_to_db=True, mongo_uri="mongodb://example.invalid",
            data_release_id="test_release", mode="upsert", delete_policy="none",
            source_owner="qwq_data", approved_by=None, dry_run=True, confirm_prod_apply=False,
        )
        with _PatchedPublishRoot(tmp_publish):
            handle_ship(args)
    finally:
        handler._run_importer = saved_run_importer
        handler.batch_shared_dir = saved_batch_shared_dir

    ship_report = read_json(tmp_shared / "ship_report.json")
    assert ship_report["taskId"] == "旅行/地域/测试省/景区/试跑"
    assert ship_report["batchId"] == "batch_1"
    assert ship_report["importRequested"] is True
    assert ship_report["importReports"]
    import_report = read_json(tmp_shared / "alpha_import_report.json")
    assert import_report["status"] == "dry-run"
    assert import_report["sourceReportPath"].endswith("import-alpha.json")


def test_ship_importer_uses_code_anchored_service_root_for_isolated_publish():
    tmp_publish = Path(tempfile.mkdtemp(prefix="ship_import_isolated_pub_"))
    bundle = tmp_publish / "sample_bundles" / "gamma.json"
    write_json(bundle, {"environment": "gamma", "postRefs": [], "entityRefs": []})

    import ship.handler as handler

    calls = []
    saved_run = handler.subprocess.run
    try:
        def fake_run(cmd, *, cwd, check):
            calls.append({"cmd": cmd, "cwd": Path(cwd), "check": check})

        handler.subprocess.run = fake_run
        with _PatchedPublishRoot(tmp_publish):
            reports = handler._run_importer(
                "mongodb://example.invalid",
                [bundle],
                release_id="test_release",
                mode="sync",
                delete_policy="tombstone",
                source_owner="test",
                dry_run=True,
            )
    finally:
        handler.subprocess.run = saved_run

    assert reports == [
        tmp_publish / "env_releases" / "test_release" / "import-gamma.json",
        tmp_publish / "env_releases" / "test_release" / "import-homepage-gamma.json",
    ]
    # 同一 --import 通道两段式：content importer + homepage 投影 importer。
    assert len(calls) == 2 and all(c["check"] is True for c in calls)
    assert calls[0]["cwd"] == handler.REPO_ROOT / "quwoquan_service"
    assert "--publish-root" in calls[0]["cmd"]
    assert str(tmp_publish) in calls[0]["cmd"]
    assert calls[1]["cwd"] == handler.REPO_ROOT / "quwoquan_service" / "services" / "entity-service"
    assert "./cmd/homepage-import" in calls[1]["cmd"]
    assert "--sample-bundle" in calls[1]["cmd"]


def test_ship_can_force_current_batch_into_sample_bundle():
    tmp_publish = Path(tempfile.mkdtemp(prefix="ship_force_batch_pub_"))
    tmp_shared = Path(tempfile.mkdtemp(prefix="ship_force_batch_shared_"))
    tmp_batch_root = Path(tempfile.mkdtemp(prefix="ship_force_batch_runtime_"))
    posts_dir = tmp_publish / "index" / "posts"
    ent_dir = tmp_publish / "index" / "entities"
    posts_dir.mkdir(parents=True, exist_ok=True)
    ent_dir.mkdir(parents=True, exist_ok=True)
    import json
    forced_ref = "posts/article/体验/forced-title/1"
    forced_entity = "地点/景区/forced-entity"
    rows = _posts(30) + [{"postRef": forced_ref, "contentType": "article", "angle": "体验", "entityRef": forced_entity}]
    with open(posts_dir / "article__体验__四川省.ndjson", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(ent_dir / "地点__景区__四川省.ndjson", "w", encoding="utf-8") as f:
        f.write(json.dumps({"entityRef": forced_entity, "domain": "地点", "etype": "景区"}, ensure_ascii=False) + "\n")
    (tmp_publish / "entities" / "地点" / "景区" / "forced-entity").mkdir(parents=True, exist_ok=True)
    (tmp_publish / "entities" / "地点" / "景区" / "forced-entity" / "page.md").write_text(
        "# forced-entity\n\nforced-entity fixture homepage.",
        encoding="utf-8",
    )
    for row in rows:
        post_ref = row["postRef"]
        rel = Path(post_ref).relative_to("posts")
        write_json(tmp_publish / "posts" / rel / "manifest.json", {"contentType": "article", "assets": []})
    write_json(tmp_batch_root / forced_ref / "manifest.json", {"contentType": "article", "assets": []})
    write_json(tmp_batch_root / "entities" / "地点" / "景区" / "forced-entity" / "_entity.json", {})
    write_json(
        tmp_shared / "content_object_index.json",
        {
            "schemaVersion": "quwoquan_data.content_object_index",
            "refs": {"candidate": {"contentType": "article", "angle": "体验", "title": "forced-title", "seq": 1}},
        },
    )

    from ship.handler import handle_ship
    import ship.handler as handler

    saved_batch_shared_dir = handler.batch_shared_dir
    saved_batch_root = handler.batch_root
    try:
        handler.batch_shared_dir = lambda task_id, batch_id: tmp_shared
        handler.batch_root = lambda task_id, batch_id: tmp_batch_root
        args = argparse.Namespace(
            release_id=None, task="旅行/测试/受控发布", batch="batch_force", copy_entities=False,
            env="alpha", skip_promote=True, skip_index=True,
            import_to_db=False, mongo_uri=None,
            data_release_id="test_force_release", mode="upsert", delete_policy="none",
            source_owner="qwq_data", approved_by=None, dry_run=False, confirm_prod_apply=False,
            force_current_batch_sample=True,
        )
        with _PatchedPublishRoot(tmp_publish):
            handle_ship(args)
            bundle = read_json(tmp_publish / "sample_bundles" / "alpha.json")
    finally:
        handler.batch_shared_dir = saved_batch_shared_dir
        handler.batch_root = saved_batch_root

    assert forced_ref in bundle["posts"]
    assert forced_entity in bundle["entities"]
    assert bundle["forcedPosts"] == [forced_ref]
    assert bundle["forcedEntities"] == [forced_entity]


def test_force_current_batch_sample_skips_abandoned_unmaterialized_refs():
    tmp_publish = Path(tempfile.mkdtemp(prefix="ship_force_active_pub_"))
    tmp_shared = Path(tempfile.mkdtemp(prefix="ship_force_active_shared_"))
    tmp_batch_root = Path(tempfile.mkdtemp(prefix="ship_force_active_runtime_"))
    posts_dir = tmp_publish / "index" / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    import json

    active_ref = "posts/article/攻略/active-title/1"
    abandoned_ref = "posts/article/攻略/abandoned-title/1"
    with open(posts_dir / "article__攻略__测试.ndjson", "w", encoding="utf-8") as f:
        f.write(json.dumps({"postRef": active_ref, "contentType": "article", "angle": "攻略"}, ensure_ascii=False) + "\n")
    write_json(tmp_publish / active_ref / "manifest.json", {"contentType": "article", "assets": []})
    write_json(tmp_batch_root / active_ref / "manifest.json", {"contentType": "article", "assets": []})
    write_json(
        tmp_shared / "content_object_index.json",
        {
            "schemaVersion": "quwoquan_data.content_object_index",
            "refs": {
                "active_candidate": {"contentType": "article", "angle": "攻略", "title": "active-title", "seq": 1},
                "abandoned_candidate": {"contentType": "article", "angle": "攻略", "title": "abandoned-title", "seq": 1},
            },
        },
    )
    write_json(
        tmp_shared / "task_workflow_state.json",
        {
            "abandonedContentObjects": [
                {"ref": "abandoned_candidate", "status": "abandoned", "reason": "source too short"}
            ]
        },
    )

    from ship.handler import handle_ship
    import ship.handler as handler

    saved_batch_shared_dir = handler.batch_shared_dir
    saved_batch_root = handler.batch_root
    try:
        handler.batch_shared_dir = lambda task_id, batch_id: tmp_shared
        handler.batch_root = lambda task_id, batch_id: tmp_batch_root
        args = argparse.Namespace(
            release_id=None, task="旅行/测试/受控发布", batch="batch_force_active", copy_entities=False,
            env="alpha", skip_promote=True, skip_index=True,
            import_to_db=False, mongo_uri=None,
            data_release_id="test_force_active_release", mode="upsert", delete_policy="none",
            source_owner="qwq_data", approved_by=None, dry_run=False, confirm_prod_apply=False,
            force_current_batch_sample=True, force_post_refs=None, force_post_refs_file=None,
            isolate_forced_sample=True,
        )
        with _PatchedPublishRoot(tmp_publish):
            handle_ship(args)
            bundle = read_json(tmp_publish / "sample_bundles" / "alpha.json")
    finally:
        handler.batch_shared_dir = saved_batch_shared_dir
        handler.batch_root = saved_batch_root

    assert bundle["posts"] == [active_ref]
    assert bundle["forcedPosts"] == [active_ref]
    assert abandoned_ref not in bundle["posts"]


def test_ship_blocks_forced_refs_missing_from_publish_index():
    tmp_publish = Path(tempfile.mkdtemp(prefix="ship_force_missing_pub_"))
    (tmp_publish / "index" / "posts").mkdir(parents=True, exist_ok=True)

    from ship.handler import handle_ship

    missing_ref = "posts/article/攻略/missing-title/1"
    args = argparse.Namespace(
        release_id=None, task=None, batch=None, copy_entities=False,
        env="alpha", skip_promote=True, skip_index=True,
        import_to_db=False, mongo_uri=None,
        data_release_id="test_force_missing_release", mode="upsert", delete_policy="none",
        source_owner="qwq_data", approved_by=None, dry_run=False, confirm_prod_apply=False,
        force_current_batch_sample=False, force_post_refs=missing_ref,
        force_post_refs_file=None, isolate_forced_sample=True,
    )
    with _PatchedPublishRoot(tmp_publish):
        try:
            handle_ship(args)
        except SystemExit as exc:
            assert exc.code != 0
            assert "forced post refs missing from publish index" in str(exc)
        else:
            raise AssertionError("missing forced post ref must block ship")


def test_ship_can_force_explicit_post_refs_into_sample_bundle():
    tmp_publish = Path(tempfile.mkdtemp(prefix="ship_force_refs_pub_"))
    posts_dir = tmp_publish / "index" / "posts"
    ent_dir = tmp_publish / "index" / "entities"
    posts_dir.mkdir(parents=True, exist_ok=True)
    ent_dir.mkdir(parents=True, exist_ok=True)
    import json
    forced_ref = "posts/article/体验/manual-ref/1"
    rows = _posts(20) + [{"postRef": forced_ref, "contentType": "article", "angle": "体验"}]
    with open(posts_dir / "article__体验__四川省.ndjson", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    for row in rows:
        rel = Path(row["postRef"]).relative_to("posts")
        write_json(tmp_publish / "posts" / rel / "manifest.json", {"contentType": "article", "assets": []})

    from ship.handler import handle_ship

    args = argparse.Namespace(
        release_id=None, task=None, batch=None, copy_entities=False,
        env="alpha", skip_promote=True, skip_index=True,
        import_to_db=False, mongo_uri=None,
        data_release_id="test_force_refs_release", mode="upsert", delete_policy="none",
        source_owner="qwq_data", approved_by=None, dry_run=False, confirm_prod_apply=False,
        force_current_batch_sample=False, force_post_refs=forced_ref,
    )
    with _PatchedPublishRoot(tmp_publish):
        handle_ship(args)
        bundle = read_json(tmp_publish / "sample_bundles" / "alpha.json")

    assert forced_ref in bundle["posts"]
    assert forced_ref in bundle["forcedPosts"]


def test_ship_can_force_explicit_entity_refs_into_sample_bundle():
    tmp_publish = Path(tempfile.mkdtemp(prefix="ship_force_entity_refs_pub_"))
    posts_dir = tmp_publish / "index" / "posts"
    ent_dir = tmp_publish / "index" / "entities"
    posts_dir.mkdir(parents=True, exist_ok=True)
    ent_dir.mkdir(parents=True, exist_ok=True)
    import json
    forced_entity = "地点/古镇/强制古镇"
    rows = _entities(20) + [{"entityRef": forced_entity, "domain": "地点", "etype": "古镇"}]
    with open(ent_dir / "地点__混合__测试.ndjson", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (tmp_publish / "entities" / "地点" / "古镇" / "强制古镇").mkdir(
        parents=True,
        exist_ok=True,
    )
    (tmp_publish / "entities" / "地点" / "古镇" / "强制古镇" / "page.md").write_text(
        "# 强制古镇\n\n强制实体采样测试主页。",
        encoding="utf-8",
    )

    from ship.handler import handle_ship

    args = argparse.Namespace(
        release_id=None, task=None, batch=None, copy_entities=False,
        env="alpha", skip_promote=True, skip_index=True,
        import_to_db=False, mongo_uri=None,
        data_release_id="test_force_entity_refs_release", mode="upsert", delete_policy="none",
        source_owner="qwq_data", approved_by=None, dry_run=False, confirm_prod_apply=False,
        force_current_batch_sample=False, force_post_refs=None,
        force_post_refs_file=None, force_entity_refs=forced_entity,
        isolate_forced_sample=True,
    )
    with _PatchedPublishRoot(tmp_publish):
        handle_ship(args)
        bundle = read_json(tmp_publish / "sample_bundles" / "alpha.json")

    assert bundle["entities"] == [forced_entity]
    assert bundle["forcedEntities"] == [forced_entity]


def test_ship_blocks_forced_entity_refs_missing_from_publish_index():
    tmp_publish = Path(tempfile.mkdtemp(prefix="ship_force_entity_missing_pub_"))
    (tmp_publish / "index" / "posts").mkdir(parents=True, exist_ok=True)
    (tmp_publish / "index" / "entities").mkdir(parents=True, exist_ok=True)

    from ship.handler import handle_ship

    args = argparse.Namespace(
        release_id=None, task=None, batch=None, copy_entities=False,
        env="alpha", skip_promote=True, skip_index=True,
        import_to_db=False, mongo_uri=None,
        data_release_id="test_force_entity_missing_release", mode="upsert", delete_policy="none",
        source_owner="qwq_data", approved_by=None, dry_run=False, confirm_prod_apply=False,
        force_current_batch_sample=False, force_post_refs=None,
        force_post_refs_file=None, force_entity_refs="地点/景区/不存在实体",
        isolate_forced_sample=True,
    )
    with _PatchedPublishRoot(tmp_publish):
        try:
            handle_ship(args)
        except SystemExit as exc:
            assert exc.code != 0
            assert "forced entity refs missing from publish index" in str(exc)
        else:
            raise AssertionError("missing forced entity ref must block ship")


def test_ship_force_post_refs_file_preserves_comma_refs_and_can_isolate():
    tmp_publish = Path(tempfile.mkdtemp(prefix="ship_force_refs_file_pub_"))
    posts_dir = tmp_publish / "index" / "posts"
    ent_dir = tmp_publish / "index" / "entities"
    posts_dir.mkdir(parents=True, exist_ok=True)
    ent_dir.mkdir(parents=True, exist_ok=True)
    import json
    forced_ref = "posts/article/攻略/华山风景区·行前指南：西安,常德5日游/1"
    other_ref = "posts/article/攻略/普通标题/1"
    rows = [
        {"postRef": forced_ref, "contentType": "article", "angle": "攻略"},
        {"postRef": other_ref, "contentType": "article", "angle": "攻略"},
    ]
    with open(posts_dir / "article__攻略__测试.ndjson", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    for row in rows:
        rel = Path(row["postRef"]).relative_to("posts")
        write_json(tmp_publish / "posts" / rel / "manifest.json", {"contentType": "article", "assets": []})
    refs_file = tmp_publish / "forced_refs.txt"
    refs_file.write_text(forced_ref + "\n", encoding="utf-8")

    from ship.handler import handle_ship

    args = argparse.Namespace(
        release_id=None, task=None, batch=None, copy_entities=False,
        env="alpha", skip_promote=True, skip_index=True,
        import_to_db=False, mongo_uri=None,
        data_release_id="test_force_refs_file_release", mode="upsert", delete_policy="none",
        source_owner="qwq_data", approved_by=None, dry_run=False, confirm_prod_apply=False,
        force_current_batch_sample=False, force_post_refs=None,
        force_post_refs_file=str(refs_file), isolate_forced_sample=True,
    )
    with _PatchedPublishRoot(tmp_publish):
        handle_ship(args)
        bundle = read_json(tmp_publish / "sample_bundles" / "alpha.json")

    assert bundle["posts"] == [forced_ref]
    assert bundle["forcedPosts"] == [forced_ref]


def test_promote_release_preserves_image_post_packages_in_publish_index():
    tmp_publish = Path(tempfile.mkdtemp(prefix="ship_image_promote_pub_"))
    posts_root = Path(tempfile.mkdtemp(prefix="ship_image_promote_posts_"))
    image_dir = posts_root / "image" / "攻略" / "九寨沟图集" / "1"
    write_json(
        image_dir / "manifest.json",
        {
            "contentType": "image",
            "publishAngle": "攻略",
            "publishTitle": "九寨沟图集",
            "publishSeq": 1,
            "reviewDecision": "approved",
            "entityRefs": [],
            "tagRefs": ["Format/内容角度/攻略"],
            "assets": [
                {
                    "assetId": "asset_001",
                    "fileName": "asset_001.jpg",
                    "license": "CC BY 2.0",
                    "credit": "Example",
                    "sourceUrl": "https://commons.wikimedia.org/wiki/File:Example.jpg",
                    "termsUrl": "https://creativecommons.org/licenses/by/2.0/",
                    "usageScope": "app_publish",
                }
            ],
        },
    )
    (image_dir / "assets").mkdir(parents=True, exist_ok=True)
    (image_dir / "assets" / "asset_001.jpg").write_bytes(b"fake-image")

    from publish_ops.promote_to_publish import promote_from_posts_root
    from publish_ops.build_publish_lookup_indexes import build_publish_lookup_indexes

    with _PatchedPublishRoot(tmp_publish):
        count, skipped = promote_from_posts_root(posts_root, dry_run=False)
        counts = build_publish_lookup_indexes()
        promoted = tmp_publish / "posts" / "image" / "攻略" / "九寨沟图集" / "1" / "manifest.json"
        index_file = tmp_publish / "index" / "posts" / "image__攻略__unknown.ndjson"

    assert (count, skipped) == (1, 0)
    assert promoted.is_file()
    assert counts["posts"] == 1
    assert index_file.is_file()
    assert "posts/image/攻略/九寨沟图集/1" in index_file.read_text(encoding="utf-8")


def test_promote_release_copies_entities_before_filtering_posts():
    tmp_publish = Path(tempfile.mkdtemp(prefix="ship_release_entity_pub_"))
    release_dir = Path(tempfile.mkdtemp(prefix="ship_release_entity_release_"))
    entity_dir = release_dir / "entities" / "地点" / "景区" / "九寨沟"
    post_dir = release_dir / "posts" / "article" / "攻略" / "九寨沟攻略" / "1"
    entity_dir.mkdir(parents=True, exist_ok=True)
    post_dir.mkdir(parents=True, exist_ok=True)
    (entity_dir / "page.md").write_text("# 九寨沟\n\n九寨沟主页。", encoding="utf-8")
    write_json(entity_dir / "_entity.json", {"entityRef": "/entity/地点/景区/九寨沟", "label": "九寨沟"})
    write_json(entity_dir / "manifest.json", {"entityRef": "/entity/地点/景区/九寨沟"})
    (post_dir / "article.md").write_text("# 九寨沟攻略\n\n正文。", encoding="utf-8")
    write_json(
        post_dir / "manifest.json",
        {
            "contentType": "article",
            "publishAngle": "攻略",
            "publishTitle": "九寨沟攻略",
            "publishSeq": 1,
            "reviewDecision": "approved",
            "entityRefs": ["/entity/地点/景区/九寨沟"],
            "tagRefs": ["Format/内容角度/攻略"],
            "assets": [],
        },
    )

    from publish_ops import promote_to_publish as promote_mod

    original_release_root = promote_mod.release_root
    promote_mod.release_root = lambda _release_id: release_dir
    try:
        with _PatchedPublishRoot(tmp_publish):
            count, skipped, entity_count = promote_mod.promote_release("rel_entity_closure", dry_run=False)
            promoted_manifest = read_json(
                tmp_publish / "posts" / "article" / "攻略" / "九寨沟攻略" / "1" / "manifest.json"
            )
    finally:
        promote_mod.release_root = original_release_root

    assert (count, skipped, entity_count) == (1, 0, 1)
    assert (tmp_publish / "entities" / "地点" / "景区" / "九寨沟" / "page.md").is_file()
    assert promoted_manifest["entityRefs"] == ["/entity/地点/景区/九寨沟"]


def test_ship_blocks_prod_apply_without_explicit_confirmation():
    tmp_publish = Path(tempfile.mkdtemp(prefix="ship_prod_guard_"))
    posts_dir = tmp_publish / "index" / "posts"
    ent_dir = tmp_publish / "index" / "entities"
    posts_dir.mkdir(parents=True, exist_ok=True)
    ent_dir.mkdir(parents=True, exist_ok=True)
    import json
    with open(posts_dir / "article__体验__prod.ndjson", "w", encoding="utf-8") as f:
        f.write(json.dumps({"postRef": "posts/article/体验/prod/1", "contentType": "article", "angle": "体验"}, ensure_ascii=False) + "\n")
    write_json(
        tmp_publish / "posts" / "article" / "体验" / "prod" / "1" / "manifest.json",
        {"contentType": "article", "assets": []},
    )

    from ship.handler import handle_ship

    args = argparse.Namespace(
        release_id=None, task=None, batch=None, copy_entities=False,
        env="prod", skip_promote=True, skip_index=True,
        import_to_db=True, mongo_uri="mongodb://prod.example.invalid:27017",
        data_release_id="rel_prod_guard", mode="upsert", delete_policy="none",
        source_owner="qwq_data", approved_by=None, dry_run=False, confirm_prod_apply=False,
    )
    with _PatchedPublishRoot(tmp_publish):
        try:
            handle_ship(args)
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("prod apply without --confirm-prod-apply must be blocked")


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"ship/sampling tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
