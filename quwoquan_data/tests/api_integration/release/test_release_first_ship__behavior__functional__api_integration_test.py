from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.io import read_json, write_json
from content.release.environment import handler
from content.release.environment.activation import write_activation_smoke_report
from content.release.environment.release_contract import build_release_contract, write_release_contract


def _release(root: Path, release_id: str = "release-a") -> Path:
    release = root / "data" / "releases" / release_id
    desired = build_release_contract(
        release_id=release_id,
        post_refs=[],
        entity_refs=[],
    )
    write_json(release / "payload" / "release.json", {
        "schemaVersion": "quwoquan_data.release/3",
        "releaseId": release_id,
        "releaseKind": "content",
        "executionIds": ["20260715--travel-homepage-coverage--cn-zhejiang--m1-001"],
    })
    write_json(release / "payload" / "desired_state.json", desired)
    write_json(release / "payload" / "sample_bundle.json", {
        "schemaVersion": "quwoquan_data.release_sample/1",
        "releaseId": release_id,
        "posts": [],
        "entities": [],
    })
    write_json(release / "payload" / "media_manifest.json", {
        "schemaVersion": "quwoquan_data.release_media_manifest/1",
        "releaseId": release_id,
        "assets": [],
    })
    write_json(release / "payload" / "index/objects.json", {
        "schemaVersion": "quwoquan_data.release_object_index/1",
        "releaseId": release_id,
        "posts": [],
        "entities": [],
    })
    return release


def _patch_roots(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    canonical = root / "publish"
    canonical.mkdir(parents=True)
    monkeypatch.setattr(handler, "OUTPUT_ROOT", root)
    monkeypatch.setattr(handler, "RELEASE_ROOT", root / "data" / "releases")
    monkeypatch.setattr(handler, "PUBLISH_ROOT", canonical)


def test_apply_writes_append_only_environment_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    args = argparse.Namespace(
        release_id="release-a",
        env="gamma",
        run_id="apply-1",
        import_to_db=False,
        mongo_uri=None,
        sync_media_root=None,
        media_base_url="",
        entity_reload_url=None,
        full_sync=False,
        dry_run=True,
        confirm_prod_apply=False,
    )
    handler._apply_release(args)
    run = tmp_path / "env/gamma/runs/data-release/release-a/apply-1"
    assert read_json(run / "result.json")["status"] == "dry_run"
    assert read_json(run / "consistency-preflight.json")["status"] == "passed"
    with pytest.raises(SystemExit, match="append-only run"):
        handler._apply_release(args)


def test_apply_import_enforces_release_desired_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(handler, "_run_content_importer", lambda **kwargs: calls.append({"kind": "content", **kwargs}))
    monkeypatch.setattr(
        handler,
        "_run_homepage_importer",
        lambda **kwargs: calls.append({"kind": "homepage", **kwargs}) or {
            "releaseId": "release-a",
            "env": "gamma",
            "dryRun": False,
            "issues": [],
            "skipped": [],
            "entityRefToHomepageId": {},
        },
    )

    handler._apply_release(argparse.Namespace(
        release_id="release-a",
        env="gamma",
        run_id="apply-sync",
        import_to_db=True,
        mongo_uri="mongodb://unused",
        sync_media_root=None,
        media_base_url="https://media.gamma.test",
        entity_reload_url=None,
        full_sync=False,
        dry_run=False,
        confirm_prod_apply=False,
    ))

    assert len(calls) == 2
    assert calls[0]["kind"] == "content"
    assert calls[0]["mode"] == "upsert"
    assert calls[0]["delete_policy"] == "none"
    assert calls[1]["kind"] == "homepage"
    assert calls[1]["mode"] == "upsert"
    assert calls[1]["media_base_url"] == "https://media.gamma.test"
    applied = read_json(
        tmp_path / "env/gamma/runs/data-release/release-a/apply-sync/applied_ref.json"
    )
    assert applied["releaseId"] == "release-a"
    assert applied["releaseRef"] == "data/releases/release-a"


def test_apply_full_sync_requires_explicit_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(handler, "_run_content_importer", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(handler, "_run_homepage_importer", lambda **kwargs: calls.append({"kind": "homepage", **kwargs}))

    handler._apply_release(argparse.Namespace(
        release_id="release-a",
        env="gamma",
        run_id="apply-full-sync",
        import_to_db=True,
        mongo_uri="mongodb://unused",
        sync_media_root=None,
        media_base_url="https://media.gamma.test",
        entity_reload_url=None,
        full_sync=True,
        dry_run=False,
        confirm_prod_apply=False,
    ))

    assert calls[0]["mode"] == "sync"
    assert calls[0]["delete_policy"] == "tombstone"
    assert calls[1]["mode"] == "sync"


def test_rollback_writes_resolvable_release_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    handler._rollback_release(argparse.Namespace(
        to_release="release-a",
        from_release_id="release-current",
        env="gamma",
        run_id="rollback-1",
        import_to_db=False,
        mongo_uri=None,
        media_base_url="",
        dry_run=True,
        confirm_prod_apply=False,
    ))
    ref = read_json(
        tmp_path
        / "env/gamma/runs/data-release/release-a/rollback-1/rollback_ref.json"
    )
    assert ref["releaseRef"] == "data/releases/release-a"
    assert ref["rollbackFromReleaseId"] == "release-current"
    assert (tmp_path / ref["releaseRef"] / "payload" / "desired_state.json").is_file()
    result = read_json(
        tmp_path
        / "env/gamma/runs/data-release/release-a/rollback-1/result.json"
    )
    assert result["status"] == "dry_run"


def test_rollback_import_reloads_entity_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        handler,
        "_run_content_importer",
        lambda **_kwargs: calls.append("content"),
    )
    monkeypatch.setattr(
        handler,
        "_run_homepage_importer",
        lambda **_kwargs: calls.append("homepage"),
    )

    def _reload(url: str, *, release_id: str, run: Path) -> Path:
        calls.append(f"reload:{url}:{release_id}")
        report = run / "entity-reload.json"
        write_json(report, {"ok": True})
        return report

    monkeypatch.setattr(handler, "_trigger_entity_reload", _reload)

    handler._rollback_release(argparse.Namespace(
        to_release="release-a",
        from_release_id="release-current",
        env="gamma",
        run_id="rollback-reload",
        import_to_db=True,
        mongo_uri="mongodb://unused",
        sync_media_root=None,
        media_base_url="https://media.gamma.test",
        entity_reload_url="https://entity.gamma.test/internal/reload",
        dry_run=False,
        confirm_prod_apply=False,
    ))

    assert calls == [
        "content",
        "homepage",
        "reload:https://entity.gamma.test/internal/reload:release-a",
    ]
    assert read_json(
        tmp_path
        / "env/gamma/runs/data-release/release-a/rollback-reload/entity-reload.json"
    )["ok"] is True


def test_release_contract_is_environment_neutral_and_create_once(tmp_path: Path) -> None:
    contract = build_release_contract(
        release_id="release-a",
        post_refs=["posts/article/攻略/甲/1"],
        entity_refs=["地点/景区/甲"],
    )
    path = write_release_contract(contract, release_root=tmp_path)
    assert path == tmp_path / "release-a/payload/desired_state.json"
    assert write_release_contract(contract, release_root=tmp_path) == path
    changed = {**contract, "desiredRefs": {"posts": [], "entities": []}}
    with pytest.raises(FileExistsError, match="create-once"):
        write_release_contract(changed, release_root=tmp_path)
    with pytest.raises(ValueError, match="environment-neutral"):
        write_release_contract({**contract, "environment": "gamma"}, release_root=tmp_path)


def test_activation_evidence_is_append_only(tmp_path: Path) -> None:
    contract = build_release_contract(
        release_id="release-a",
        post_refs=[],
        entity_refs=[],
    )
    path = write_activation_smoke_report(
        contract,
        environment="gamma",
        run_id="apply-1",
        active_release_id="release-a",
        output_root=tmp_path,
    )
    assert path == (
        tmp_path
        / "env/gamma/runs/data-release/release-a/apply-1/activation-smoke.json"
    )
    with pytest.raises(FileExistsError, match="append-only"):
        write_activation_smoke_report(
            contract,
            environment="gamma",
            run_id="apply-1",
            active_release_id="release-a",
            output_root=tmp_path,
        )


def test_media_sync_reads_only_release_media_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"release-first-cas"
    digest = hashlib.sha256(payload).hexdigest()
    release = _release(tmp_path)
    canonical = tmp_path / "publish"
    source = canonical / f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.bin"
    source.parent.mkdir(parents=True)
    source.write_bytes(payload)
    unrelated = canonical / "media/objects/sha256/aa/bb" / ("a" * 64 + ".bin")
    unrelated.parent.mkdir(parents=True)
    unrelated.write_bytes(b"unrelated")
    write_json(release / "payload" / "media_manifest.json", {
        "schemaVersion": "quwoquan_data.release_media_manifest/1",
        "releaseId": "release-a",
        "assets": [{
            "objectKey": source.relative_to(canonical).as_posix(),
            "sha256": "sha256:" + digest,
            "bytes": len(payload),
        }],
    })
    monkeypatch.setattr(handler, "PUBLISH_ROOT", canonical)
    run = tmp_path / "env/gamma/runs/data-release/release-a/apply-1"
    run.mkdir(parents=True)
    destination = tmp_path / "media"
    handler._sync_media(release=release, destination=str(destination), run=run)
    assert (destination / source.relative_to(canonical)).read_bytes() == payload
    assert not (destination / unrelated.relative_to(canonical)).exists()
    assert read_json(run / "media-sync.json")["failed"] == 0
