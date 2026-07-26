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
from content.release.environment.topology import EnvironmentReleaseMode, EnvironmentReleaseTarget
from content.release.model import DeploymentEnvironment, ReleaseKind


def _release(
    root: Path,
    release_id: str = "release-a",
    release_kind: ReleaseKind = ReleaseKind.CONTENT,
) -> Path:
    release = root / "data" / "releases" / release_id
    desired = build_release_contract(
        release_id=release_id,
        post_refs=[],
        entity_refs=[],
    )
    write_json(release / "payload" / "release.json", {
        "schema": "quwoquan_data.release",
        "releaseId": release_id,
        "releaseKind": release_kind,
        "executionIds": ["20260715--travel-homepage-coverage--test-region-a--scale-001"],
    })
    write_json(release / "payload" / "desired_state.json", desired)
    write_json(release / "payload" / "sample_bundle.json", {
        "schema": "quwoquan_data.release_sample",
        "releaseId": release_id,
        "posts": [],
        "entities": [],
    })
    write_json(release / "payload" / "media_manifest.json", {
        "schema": "quwoquan_data.release_media_manifest",
        "releaseId": release_id,
        "assets": [],
    })
    write_json(release / "payload" / "index/objects.json", {
        "schema": "quwoquan_data.release_object_index",
        "releaseId": release_id,
        "posts": [],
        "entities": [],
    })
    return release


def _target(
    root: Path,
    env: DeploymentEnvironment = DeploymentEnvironment.GAMMA,
) -> EnvironmentReleaseTarget:
    return EnvironmentReleaseTarget(
        environment=env,
        target_name=f"{env.value}-test",
        mode=EnvironmentReleaseMode.LOCAL_IMPORT,
        mongo_uri="mongodb://topology.test",
        user_postgres_dsn="postgres://topology.test/quwoquan",
        media_sync_root=root / "environment-media",
        media_base_url=f"https://{env.value}-image.quwoquan-env.test",
        api_base_url=f"https://{env.value}-api.quwoquan-env.test",
        missing_requirements=(),
    )


def _patch_roots(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(handler, "OUTPUT_ROOT", root)
    monkeypatch.setattr(handler, "RELEASE_ROOT", root / "data" / "releases")
    monkeypatch.setattr(
        handler,
        "resolve_environment_release_target",
        lambda env: _target(root, DeploymentEnvironment(env)),
    )
    monkeypatch.setattr(handler, "require_environment_readiness", lambda **_kwargs: None)


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
        full_sync=True,
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
    monkeypatch.setattr(
        handler,
        "_run_creator_importer",
        lambda **kwargs: calls.append({"kind": "creator", **kwargs}) or kwargs["run"] / "creator-import.json",
    )
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
        full_sync=True,
        dry_run=False,
        confirm_prod_apply=False,
    ))

    assert len(calls) == 3
    assert calls[0]["kind"] == "creator"
    assert calls[1]["kind"] == "content"
    assert calls[1]["mode"] == "sync"
    assert calls[1]["delete_policy"] == "tombstone"
    assert calls[1]["creator_receipt"] == calls[0]["run"] / "creator-import.json"
    assert calls[2]["kind"] == "homepage"
    assert calls[2]["mode"] == "sync"
    assert calls[0]["mongo_uri"] == "mongodb://topology.test"
    assert calls[2]["media_base_url"] == "https://gamma-image.quwoquan-env.test"
    applied = read_json(
        tmp_path / "env/gamma/runs/data-release/release-a/apply-sync/applied_ref.json"
    )
    assert applied["releaseId"] == "release-a"
    assert applied["releaseRef"] == "data/releases/release-a"


def test_apply_rejects_missing_full_sync_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(handler, "_run_creator_importer", lambda **kwargs: calls.append({"kind": "creator", **kwargs}) or kwargs["run"] / "creator-import.json")
    monkeypatch.setattr(handler, "_run_content_importer", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(handler, "_run_homepage_importer", lambda **kwargs: calls.append({"kind": "homepage", **kwargs}))

    with pytest.raises(SystemExit, match="immutable release requires --full-sync"):
        handler._apply_release(argparse.Namespace(
            release_id="release-a",
            env="gamma",
            run_id="apply-without-full-sync",
            import_to_db=True,
            full_sync=False,
            dry_run=False,
            confirm_prod_apply=False,
        ))

    assert calls == []


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


def test_rollback_import_applies_all_release_owners(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        handler,
        "_run_creator_importer",
        lambda **_kwargs: calls.append("creator") or tmp_path / "creator-import.json",
    )
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

    handler._rollback_release(argparse.Namespace(
        to_release="release-a",
        from_release_id="release-current",
        env="gamma",
        run_id="rollback-reload",
        import_to_db=True,
        dry_run=False,
        confirm_prod_apply=False,
    ))

    assert calls == [
        "creator",
        "content",
        "homepage",
    ]


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
    payload_root = release / "payload"
    source = payload_root / f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.bin"
    source.parent.mkdir(parents=True)
    source.write_bytes(payload)
    unrelated = payload_root / "media/objects/sha256/aa/bb" / ("a" * 64 + ".bin")
    unrelated.parent.mkdir(parents=True)
    unrelated.write_bytes(b"unrelated")
    write_json(release / "payload" / "media_manifest.json", {
        "schema": "quwoquan_data.release_media_manifest",
        "releaseId": "release-a",
        "assets": [{
            "objectKey": source.relative_to(payload_root).as_posix(),
            "sha256": "sha256:" + digest,
            "bytes": len(payload),
        }],
    })
    run = tmp_path / "env/gamma/runs/data-release/release-a/apply-1"
    run.mkdir(parents=True)
    destination = tmp_path / "media"
    handler._sync_media(release=release, destination=str(destination), run=run)
    assert (destination / source.relative_to(payload_root)).read_bytes() == payload
    assert not (destination / unrelated.relative_to(payload_root)).exists()
    assert read_json(run / "media-sync.json")["failed"] == 0


@pytest.mark.parametrize(
    "environment",
    [
        DeploymentEnvironment.ALPHA,
        DeploymentEnvironment.BETA,
        DeploymentEnvironment.GAMMA,
    ],
)
def test_ship_verify_uses_environment_topology_without_manual_network_arguments(
    environment: DeploymentEnvironment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    import_run_id = "apply-verified"
    import_root = (
        tmp_path
        / "env"
        / environment.value
        / "runs/data-release"
        / release.name
        / import_run_id
    )
    cases = import_root / "homepage_verification_cases.json"
    cases_ref = cases.relative_to(tmp_path).as_posix()
    write_json(cases, {"environment": environment.value})
    write_json(
        import_root / "result.json",
        {
            "environment": environment.value,
            "releaseId": release.name,
            "status": "completed",
            "homepageVerificationCasesRef": cases_ref,
        },
    )
    observed: dict[str, object] = {}

    def _verify(**kwargs: object) -> Path:
        observed.update(kwargs)
        output = Path(str(kwargs["output_path"]))
        write_json(output, {"passed": True})
        return output

    monkeypatch.setattr(handler, "write_homepage_api_verification", _verify)
    handler._verify_release_consumers(
        argparse.Namespace(
            release_id=release.name,
            env=environment.value,
            import_run_id=import_run_id,
            run_id="verify-001",
        )
    )

    assert observed["environment"] is environment
    assert observed["api_base_url"] == f"https://{environment.value}-api.quwoquan-env.test"
    assert observed["resolve_host"] == "127.0.0.1"
    assert observed["insecure_tls"] is True
    result = read_json(
        tmp_path
        / "env"
        / environment.value
        / "runs/data-release"
        / release.name
        / "verify-001/result.json"
    )
    assert result["homepageApiVerificationRef"].endswith(
        "/verify-001/homepage-api-verification.json"
    )


def test_ship_verify_empty_baseline_proves_isolated_removal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path, release_kind=ReleaseKind.EMPTY_BASELINE)
    _patch_roots(monkeypatch, tmp_path)
    import_run_id = "baseline-import"
    import_root = (
        tmp_path
        / "env/gamma/runs/data-release"
        / release.name
        / import_run_id
    )
    write_json(
        import_root / "result.json",
        {
            "environment": "gamma",
            "releaseId": release.name,
            "status": "completed",
            "homepageVerificationCasesRef": "",
        },
    )
    write_json(import_root / "homepage-import.json", {"offlined": ["homepage-old"]})
    observed: dict[str, object] = {}

    def _verify_baseline(**kwargs: object) -> Path:
        observed.update(kwargs)
        output = Path(str(kwargs["output_path"]))
        write_json(output, {"passed": True})
        return output

    monkeypatch.setattr(handler, "write_baseline_api_verification", _verify_baseline)
    handler._verify_release_consumers(
        argparse.Namespace(
            release_id=release.name,
            env="gamma",
            import_run_id=import_run_id,
            run_id="baseline-verify",
        )
    )

    assert observed["importer_report_path"] == import_root / "homepage-import.json"
    result = read_json(
        tmp_path
        / "env/gamma/runs/data-release"
        / release.name
        / "baseline-verify/result.json"
    )
    assert result["baselineApiVerificationRef"].endswith(
        "/baseline-verify/baseline-api-verification.json"
    )
