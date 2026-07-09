"""ship rollback 契约（WP6）：用历史 release contract 以 sync+tombstone 幂等重放。"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import pytest  # noqa: E402

import ship.handler as ship_handler  # noqa: E402
from _common.io import read_json, write_json  # noqa: E402


def _seed_publish_root(tmp_path: Path) -> Path:
    publish_root = tmp_path / "publish"
    posts = [
        {"postRef": "posts/travel/route/黄龙一日/001", "entityRefs": ["旅行/地域/黄龙"], "authorId": "creator-a"},
        {"postRef": "posts/travel/route/武侯祠半日/001", "entityRefs": ["旅行/地域/武侯祠"], "authorId": "creator-b"},
    ]
    entities = [
        {"entityRef": "旅行/地域/黄龙"},
        {"entityRef": "旅行/地域/武侯祠"},
    ]
    write_json(publish_root / "index" / "posts.json", {"records": posts})
    write_json(publish_root / "index" / "entities.json", {"records": entities})
    return publish_root


def _seed_release_contract(publish_root: Path, release_id: str, env: str) -> Path:
    contract = {
        "schemaVersion": "quwoquan.data_env_release.v1",
        "releaseId": release_id,
        "environment": env,
        "mode": "sync",
        "deletePolicy": "tombstone",
        "sourceOwner": "qwq_data",
        "sampleBundle": {"sampleRatio": 1.0, "salt": "s1"},
        "desiredRefs": {
            "posts": ["posts/travel/route/黄龙一日/001"],
            "entities": ["旅行/地域/黄龙"],
        },
    }
    path = publish_root / "env_releases" / release_id / f"{env}.json"
    write_json(path, contract)
    return path


class TestBuildRollbackPlan:
    def test_rebuilds_bundle_from_historical_contract(self, tmp_path: Path) -> None:
        publish_root = _seed_publish_root(tmp_path)
        _seed_release_contract(publish_root, "data_gamma_r1", "gamma")
        posts = read_json(publish_root / "index" / "posts.json")["records"]
        entities = read_json(publish_root / "index" / "entities.json")["records"]

        plan = ship_handler.build_rollback_plan(
            "data_gamma_r1",
            "gamma",
            posts=posts,
            entities=entities,
            publish_root=publish_root,
        )
        bundle = plan["bundle"]
        assert bundle["environment"] == "gamma"
        assert bundle["posts"] == ["posts/travel/route/黄龙一日/001"]
        assert bundle["entities"] == ["旅行/地域/黄龙"]
        assert bundle["rollbackOf"] == "data_gamma_r1"
        assert plan["sourceContract"]["releaseId"] == "data_gamma_r1"

    def test_missing_contract_blocks(self, tmp_path: Path) -> None:
        publish_root = _seed_publish_root(tmp_path)
        posts = read_json(publish_root / "index" / "posts.json")["records"]
        entities = read_json(publish_root / "index" / "entities.json")["records"]
        with pytest.raises(SystemExit, match="release contract not found"):
            ship_handler.build_rollback_plan(
                "no_such_release",
                "gamma",
                posts=posts,
                entities=entities,
                publish_root=publish_root,
            )

    def test_refs_missing_from_publish_index_block(self, tmp_path: Path) -> None:
        publish_root = _seed_publish_root(tmp_path)
        contract_path = _seed_release_contract(publish_root, "data_gamma_r2", "gamma")
        contract = read_json(contract_path)
        contract["desiredRefs"]["posts"].append("posts/travel/route/已消失/001")
        write_json(contract_path, contract)
        posts = read_json(publish_root / "index" / "posts.json")["records"]
        entities = read_json(publish_root / "index" / "entities.json")["records"]
        with pytest.raises(SystemExit, match="missing from publish index"):
            ship_handler.build_rollback_plan(
                "data_gamma_r2",
                "gamma",
                posts=posts,
                entities=entities,
                publish_root=publish_root,
            )


class TestHandleShipRollback:
    def test_writes_rollback_contract_and_bundle(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        publish_root = _seed_publish_root(tmp_path)
        _seed_release_contract(publish_root, "data_gamma_r1", "gamma")
        monkeypatch.setattr(ship_handler, "PUBLISH_ROOT", publish_root)
        monkeypatch.setattr(
            ship_handler,
            "load_publish_records",
            lambda: (
                read_json(publish_root / "index" / "posts.json")["records"],
                read_json(publish_root / "index" / "entities.json")["records"],
            ),
        )
        monkeypatch.setattr(ship_handler, "_media_cdn_bases_for_env", lambda env: ("https://img.example", "https://video.example"))
        monkeypatch.setattr(
            ship_handler,
            "materialize_release_media",
            lambda **kwargs: {"schemaVersion": "test", "path": "", "counts": {"assets": 0, "issues": 0}},
        )
        monkeypatch.setattr(
            ship_handler,
            "scan_release_contract",
            lambda contract, publish_root, phase: {"status": "passed", "issues": []},
        )

        args = ship_handler.argparse.Namespace(
            to_release="data_gamma_r1",
            env="gamma",
            data_release_id="rollback_r1_test",
            import_to_db=False,
            mongo_uri=None,
            dry_run=False,
            confirm_prod_apply=False,
        )
        ship_handler.handle_ship_rollback(args)

        rollback_dir = publish_root / "env_releases" / "rollback_r1_test"
        contract = read_json(rollback_dir / "gamma.json")
        assert contract["mode"] == "sync"
        assert contract["deletePolicy"] == "tombstone"
        assert contract["rollbackOf"] == "data_gamma_r1"
        bundle = read_json(rollback_dir / "rollback-bundle-gamma.json")
        assert bundle["posts"] == ["posts/travel/route/黄龙一日/001"]

    def test_prod_apply_requires_confirmation(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        publish_root = _seed_publish_root(tmp_path)
        _seed_release_contract(publish_root, "data_prod_r1", "prod")
        monkeypatch.setattr(ship_handler, "PUBLISH_ROOT", publish_root)
        monkeypatch.setattr(
            ship_handler,
            "load_publish_records",
            lambda: (
                read_json(publish_root / "index" / "posts.json")["records"],
                read_json(publish_root / "index" / "entities.json")["records"],
            ),
        )
        args = ship_handler.argparse.Namespace(
            to_release="data_prod_r1",
            env="prod",
            data_release_id=None,
            import_to_db=True,
            mongo_uri="mongodb://localhost:27017",
            dry_run=False,
            confirm_prod_apply=False,
        )
        with pytest.raises(SystemExit):
            ship_handler.handle_ship_rollback(args)
