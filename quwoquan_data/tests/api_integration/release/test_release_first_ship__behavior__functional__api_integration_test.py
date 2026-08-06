from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import replace
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.environment import _ship_operations, handler
from content.release.environment.release_contract import (
    build_release_contract,
    write_release_contract,
)
from content.release.environment.topology import (
    EnvironmentReleaseTarget,
    resolve_environment_release_target,
)
from content.release.model import DeploymentEnvironment, ReleaseKind
from core.io import read_json, write_json
from core.release_layout import payload_digest
from core.source_digest import SourceDigest, content_source_revision


def _stub_tag_consumer_verification(**kwargs: object) -> Path:
    output = Path(str(kwargs["output_path"]))
    write_json(output, {"passed": True})
    return output


def _release(
    root: Path,
    release_id: str = "release-a",
    release_kind: ReleaseKind = ReleaseKind.CONTENT,
) -> Path:
    release = root / "data" / "releases" / release_id
    source_digest = "sha256:" + "b" * 64
    entity_catalog_digest = "sha256:" + "c" * 64
    is_empty = release_kind is ReleaseKind.EMPTY_BASELINE
    desired = build_release_contract(
        release_id=release_id,
        post_refs=[],
        entity_refs=[],
    )
    header = {
        "schema": "quwoquan_data.release",
        "releaseId": release_id,
        "sourceOwner": "qwq_data",
        "releaseKind": release_kind,
        "releaseClass": "commercial",
        "productLifecycleState": "commercial",
        "containsUnverifiedAssets": False,
        "rightsStatusCounts": {
            "verified": 0,
            "unverified": 0,
            "restricted": 0,
            "unknown": 0,
        },
        "authorizationRequiredAssetIds": [],
        "researchAcceptedCount": 0,
        "commercialAcceptedCount": 0,
        "canonicalMerkle": "sha256:" + "a" * 64,
        "executionIds": (
            []
            if is_empty
            else ["20260715--travel-homepage-coverage--test-region-a--scale-001"]
        ),
        "sourceDigests": [SourceDigest(digest=source_digest).to_document()],
    }
    if not is_empty:
        header.update(
            {
                "sourceRevision": content_source_revision(
                    source_digest=source_digest,
                    entity_catalog_digest=entity_catalog_digest,
                ),
                "sourceDigest": source_digest,
                "entityCatalogDigest": entity_catalog_digest,
            }
        )
    write_json(release / "payload" / "release.json", header)
    write_json(release / "payload" / "desired_state.json", desired)
    write_json(
        release / "payload" / "sample_bundle.json",
        {
            "schema": "quwoquan_data.release_sample",
            "releaseId": release_id,
            "posts": [],
            "entities": [],
        },
    )
    write_json(
        release / "payload" / "media_manifest.json",
        {
            "schema": "quwoquan_data.release_media_manifest",
            "releaseId": release_id,
            "sourceOwner": "qwq_data",
            "assets": [],
            "issues": [],
            "counts": {"assets": 0, "issues": 0},
        },
    )
    write_json(
        release / "payload" / "index/objects.json",
        {
            "schema": "quwoquan_data.release_object_index",
            "releaseId": release_id,
            "posts": [],
            "entities": [],
        },
    )
    return release


def _target(
    root: Path,
    env: DeploymentEnvironment = DeploymentEnvironment.GAMMA,
) -> EnvironmentReleaseTarget:
    return replace(
        resolve_environment_release_target(env.value),
        mongo_uri="mongodb://topology.test",
        user_postgres_dsn="postgres://topology.test/quwoquan",
        media_sync_root=root / "environment-media",
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


def test_prod_apply_without_import_is_prepared_not_activated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)

    handler._apply_release(
        argparse.Namespace(
            release_id="release-a",
            env="prod",
            run_id="prepared-1",
            import_to_db=False,
            full_sync=True,
            dry_run=False,
            confirm_prod_apply=False,
        )
    )

    run = tmp_path / "env/prod/runs/data-release/release-a/prepared-1"
    assert read_json(run / "result.json")["status"] == "prepared"
    assert not (run / "applied_ref.json").exists()
    assert not (run / "media-sync.json").exists()


def test_apply_import_enforces_release_desired_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        handler,
        "_run_tag_importer",
        lambda **kwargs: calls.append({"kind": "tag", **kwargs}) or kwargs["run"] / "tag-import.json",
    )
    monkeypatch.setattr(
        handler,
        "_run_creator_importer",
        lambda **kwargs: calls.append({"kind": "creator", **kwargs}) or kwargs["run"] / "creator-import.json",
    )
    monkeypatch.setattr(
        handler,
        "_run_content_importer",
        lambda **kwargs: calls.append({"kind": "content", **kwargs}),
    )
    monkeypatch.setattr(
        handler,
        "_run_homepage_importer",
        lambda **kwargs: (
            calls.append({"kind": "homepage", **kwargs})
            or {
                "releaseId": "release-a",
                "env": "gamma",
                "dryRun": False,
                "issues": [],
                "skipped": [],
                "entityRefToHomepageId": {},
            }
        ),
    )

    handler._apply_release(
        argparse.Namespace(
            release_id="release-a",
            env="gamma",
            run_id="apply-sync",
            import_to_db=True,
            full_sync=True,
            dry_run=False,
            confirm_prod_apply=False,
        )
    )

    assert len(calls) == 4
    assert calls[0]["kind"] == "tag"
    assert calls[1]["kind"] == "creator"
    assert calls[1]["postgres_dsn"] == "postgres://topology.test/quwoquan"
    assert calls[2]["kind"] == "content"
    assert calls[2]["mode"] == "sync"
    assert calls[2]["delete_policy"] == "tombstone"
    assert calls[2]["creator_receipt"] == calls[1]["run"] / "creator-import.json"
    assert calls[3]["kind"] == "homepage"
    assert calls[3]["mode"] == "sync"
    assert calls[0]["mongo_uri"] == "mongodb://topology.test"
    target = _target(tmp_path)
    assert calls[1]["media_avatar_base_url"] == target.media_delivery_base_url
    assert calls[2]["media_video_base_url"] == target.media_delivery_base_url
    assert calls[3]["media_image_base_url"] == target.media_delivery_base_url
    applied = read_json(tmp_path / "env/gamma/runs/data-release/release-a/apply-sync/applied_ref.json")
    assert applied["releaseId"] == "release-a"
    assert applied["releaseRef"] == "data/releases/release-a"


def test_apply_rejects_missing_full_sync_flag(
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
    monkeypatch.setattr(handler, "_run_content_importer", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(
        handler,
        "_run_homepage_importer",
        lambda **kwargs: calls.append({"kind": "homepage", **kwargs}),
    )

    with pytest.raises(SystemExit, match="immutable release requires --full-sync"):
        handler._apply_release(
            argparse.Namespace(
                release_id="release-a",
                env="gamma",
                run_id="apply-without-full-sync",
                import_to_db=True,
                full_sync=False,
                dry_run=False,
                confirm_prod_apply=False,
            )
        )

    assert calls == []


def test_rollback_writes_resolvable_release_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    handler._rollback_release(
        argparse.Namespace(
            to_release="release-a",
            from_release_id="release-current",
            env="gamma",
            run_id="rollback-1",
            import_to_db=False,
            dry_run=True,
            confirm_prod_apply=False,
        )
    )
    ref = read_json(tmp_path / "env/gamma/runs/data-release/release-a/rollback-1/rollback_ref.json")
    assert ref["releaseRef"] == "data/releases/release-a"
    assert ref["rollbackFromReleaseId"] == "release-current"
    assert (tmp_path / ref["releaseRef"] / "payload" / "desired_state.json").is_file()
    result = read_json(tmp_path / "env/gamma/runs/data-release/release-a/rollback-1/result.json")
    assert result["status"] == "dry_run"


def test_rollback_import_applies_all_release_owners_and_binds_homepage_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[str] = []
    contract = read_json(release / "payload" / "desired_state.json")
    contract["desiredRefs"]["entities"] = ["地点/景区/甲"]
    monkeypatch.setattr(
        handler,
        "_load_release",
        lambda _release_id: (release, contract),
    )
    monkeypatch.setattr(
        _ship_operations,
        "scan_release_contract",
        lambda *_args, **_kwargs: {"status": "passed"},
    )
    monkeypatch.setattr(
        handler,
        "_run_tag_importer",
        lambda **_kwargs: calls.append("tag") or tmp_path / "tag-import.json",
    )
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
        lambda **_kwargs: calls.append("homepage") or {"entities": 1},
    )

    def _write_homepage_cases(**kwargs: object) -> Path:
        calls.append("homepage-cases")
        assert kwargs["importer_report"] == {"entities": 1}
        output = Path(str(kwargs["run_root"])) / "homepage_verification_cases.json"
        write_json(output, {"schema": "test.homepage_cases"})
        return output

    monkeypatch.setattr(
        handler,
        "write_homepage_verification_case_manifest",
        _write_homepage_cases,
    )

    handler._rollback_release(
        argparse.Namespace(
            to_release="release-a",
            from_release_id="release-current",
            env="gamma",
            run_id="rollback-reload",
            import_to_db=True,
            dry_run=False,
            confirm_prod_apply=False,
        )
    )

    assert calls == [
        "tag",
        "creator",
        "content",
        "homepage",
        "homepage-cases",
    ]
    result = read_json(
        tmp_path
        / "env/gamma/runs/data-release/release-a/rollback-reload/result.json"
    )
    assert result["homepageVerificationCasesRef"].endswith(
        "/rollback-reload/homepage_verification_cases.json"
    )


def test_release_contract_is_environment_neutral_and_create_once(
    tmp_path: Path,
) -> None:
    contract = build_release_contract(
        release_id="release-a",
        post_refs=["posts/article/攻略/甲/1"],
        entity_refs=["地点/景区/甲"],
    )
    path = write_release_contract(contract, release_root=tmp_path)
    assert path == tmp_path / "release-a/payload/desired_state.json"
    assert write_release_contract(contract, release_root=tmp_path) == path
    changed = {
        **contract,
        "desiredRefs": {
            **contract["desiredRefs"],
            "posts": [],
            "entities": [],
        },
    }
    with pytest.raises(FileExistsError, match="create-once"):
        write_release_contract(changed, release_root=tmp_path)
    with pytest.raises(ValueError, match="environment-neutral"):
        write_release_contract({**contract, "environment": "gamma"}, release_root=tmp_path)


def test_media_sync_reads_only_release_media_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"release-first-cas"
    digest = hashlib.sha256(payload).hexdigest()
    release = _release(tmp_path)
    payload_root = release / "payload"
    public_slice_key = "media/image/s/asset/release-image/v1/source.webp"
    source = payload_root / public_slice_key
    source.parent.mkdir(parents=True)
    source.write_bytes(payload)
    unrelated = payload_root / "media/objects/sha256/aa/bb" / ("a" * 64 + ".bin")
    unrelated.parent.mkdir(parents=True)
    unrelated.write_bytes(b"unrelated")
    write_json(
        release / "payload" / "media_manifest.json",
        {
            "schema": "quwoquan_data.release_media_manifest",
            "releaseId": "release-a",
            "assets": [
                {
                    "assetId": "release-image",
                    "publicSliceKey": public_slice_key,
                    "sha256": "sha256:" + digest,
                    "bytes": len(payload),
                }
            ],
        },
    )
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
    monkeypatch.setattr(
        handler,
        "_write_tag_consumer_verification",
        _stub_tag_consumer_verification,
    )
    import_run_id = "apply-verified"
    import_root = tmp_path / "env" / environment.value / "runs/data-release" / release.name / import_run_id
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
            readiness_phase="consumer",
            lifecycle_exit_ref="",
        )
    )

    assert observed["environment"] is environment
    assert observed["api_base_url"] == _target(tmp_path, environment).api_base_url
    result = read_json(
        tmp_path / "env" / environment.value / "runs/data-release" / release.name / "verify-001/result.json"
    )
    assert result["homepageApiVerificationRef"].endswith("/verify-001/homepage-api-verification.json")


def test_ship_verify_binds_consumer_readiness_to_verified_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(handler, "_release_has_posts", lambda _contract: True)
    monkeypatch.setattr(
        handler,
        "_write_tag_consumer_verification",
        _stub_tag_consumer_verification,
    )
    import_run_id = "apply-ready"
    import_root = tmp_path / "env/gamma/runs/data-release" / release.name / import_run_id
    cases = import_root / "homepage_verification_cases.json"
    write_json(cases, {"environment": "gamma"})
    write_json(
        import_root / "result.json",
        {
            "environment": "gamma",
            "releaseId": release.name,
            "status": "completed",
            "homepageVerificationCasesRef": cases.relative_to(tmp_path).as_posix(),
        },
    )

    def _write_report(**kwargs: object) -> Path:
        output = Path(str(kwargs["output_path"]))
        write_json(output, {"passed": True})
        return output

    observed: dict[str, object] = {}
    monkeypatch.setattr(handler, "write_post_api_verification", _write_report)
    monkeypatch.setattr(handler, "write_homepage_api_verification", _write_report)
    monkeypatch.setattr(handler, "write_environment_release_readiness", _write_report)
    monkeypatch.setattr(
        handler,
        "require_environment_readiness",
        lambda **kwargs: observed.update(kwargs),
    )

    lifecycle_exit_ref = (
        "env/gamma/runs/release-lifecycle-exit/"
        f"{release.name}/exit-001/lifecycle-exit.json"
    )
    handler._verify_release_consumers(
        argparse.Namespace(
            release_id=release.name,
            env="gamma",
            import_run_id=import_run_id,
            run_id="verify-ready",
            readiness_phase="commercial",
            lifecycle_exit_ref=lifecycle_exit_ref,
        )
    )

    assert observed["environment"] is DeploymentEnvironment.GAMMA
    assert observed["phase"].value == "commercial"
    assert observed["lifecycle_exit_ref"] == lifecycle_exit_ref
    assert observed["release_id"] == release.name
    assert observed["verify_run_id"] == "verify-ready"
    assert observed["manifest_digest"] == payload_digest(release)
    assert observed["run"] == (
        tmp_path / "env/gamma/runs/data-release" / release.name / "verify-ready"
    )
    result = read_json(Path(str(observed["run"])) / "result.json")
    assert result["releaseReadinessRef"].endswith("/verify-ready/release-readiness.json")
    assert result["lifecycleExitRef"] == lifecycle_exit_ref


def test_ship_verify_preserves_failed_consumer_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(
        handler,
        "_write_tag_consumer_verification",
        _stub_tag_consumer_verification,
    )
    import_run_id = "apply-before-failure"
    import_root = tmp_path / "env/alpha/runs/data-release" / release.name / import_run_id
    cases = import_root / "homepage_verification_cases.json"
    write_json(cases, {"environment": "alpha"})
    write_json(
        import_root / "result.json",
        {
            "environment": "alpha",
            "releaseId": release.name,
            "status": "completed",
            "homepageVerificationCasesRef": cases.relative_to(tmp_path).as_posix(),
        },
    )
    monkeypatch.setattr(
        handler,
        "write_homepage_api_verification",
        lambda **_kwargs: (_ for _ in ()).throw(handler.HomepageApiVerificationError("public homepage returned 404")),
    )

    with pytest.raises(SystemExit, match="homepage API verification failed"):
        handler._verify_release_consumers(
            argparse.Namespace(
                release_id=release.name,
                env="alpha",
                import_run_id=import_run_id,
                run_id="verify-failed",
                readiness_phase="consumer",
                lifecycle_exit_ref="",
            )
        )

    result = read_json(tmp_path / "env/alpha/runs/data-release" / release.name / "verify-failed/result.json")
    assert result["status"] == "failed"
    assert result["importRunId"] == import_run_id
    assert result["failedStage"] == "homepage_api_verification"
    assert result["error"] == "public homepage returned 404"
    assert result["verificationChecksum"].startswith("sha256:")


def test_ship_verify_empty_baseline_proves_isolated_removal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path, release_kind=ReleaseKind.EMPTY_BASELINE)
    _patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(
        handler,
        "_write_tag_consumer_verification",
        _stub_tag_consumer_verification,
    )
    import_run_id = "baseline-import"
    import_root = tmp_path / "env/gamma/runs/data-release" / release.name / import_run_id
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
    result = read_json(tmp_path / "env/gamma/runs/data-release" / release.name / "baseline-verify/result.json")
    assert result["baselineApiVerificationRef"].endswith("/baseline-verify/baseline-api-verification.json")
