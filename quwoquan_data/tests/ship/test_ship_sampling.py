"""采样器 + ship 端到端 + publish_filter 契约。

可直接运行：python3 quwoquan_data/tests/ship/test_ship_sampling.py
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
        self._mods = (paths, sampler, handler)
        self._saved = (paths.PUBLISH_ROOT, sampler.PUBLISH_ROOT, sampler.SAMPLE_BUNDLE_DIR, handler.PUBLISH_ROOT)
        paths.PUBLISH_ROOT = self.root
        sampler.PUBLISH_ROOT = self.root
        sampler.SAMPLE_BUNDLE_DIR = self.root / "sample_bundles"
        handler.PUBLISH_ROOT = self.root
        return self

    def __exit__(self, *exc):
        paths, sampler, handler = self._mods
        paths.PUBLISH_ROOT, sampler.PUBLISH_ROOT, sampler.SAMPLE_BUNDLE_DIR, handler.PUBLISH_ROOT = self._saved
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
