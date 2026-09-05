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
from content.release.environment.release_runtime import ReleaseAdmission
from content.release.environment.run_evidence import (
    create_run as create_environment_run,
    write_environment_result,
)
from content.release.environment.readiness import ShipReadinessPhase
from content.release.environment.release_contract import (
    build_release_contract,
    write_release_contract,
)
from content.release.environment.topology import (
    EnvironmentReleaseMode,
    EnvironmentReleaseTarget,
    resolve_environment_release_target,
)
from content.release.model import DeploymentEnvironment, ReleaseKind
from core.io import read_json, write_json
from core.release_layout import payload_digest
from core.source_digest import SourceDefinitionSnapshot, content_source_revision

# The coverage receipt cross-checks the importer's own environment against the
# release run's, so a stub report has to name the environment it ran against.
_ADMISSION_DIGEST = "sha256:" + "0" * 64


def _admission(release_id: str = "release-a") -> ReleaseAdmission:
    return ReleaseAdmission(
        release=Path(f"/admitted/{release_id}"),
        contract={
            "releaseId": release_id,
            "desiredRefs": {"entities": [], "posts": []},
        },
        release_id=release_id,
        manifest_digest=_ADMISSION_DIGEST,
        admission_kind="producer_handoff",
        handoff_ref=f"handoff-ref-v1:sha256:{'1' * 64}:sha256:{'2' * 64}",
        handoff_artifact_ref=f".qwq_output/data/releases/{release_id}/producer_release_handoff.json",
        handoff_artifact_digest=_ADMISSION_DIGEST,
    )


def _fixture_admission(release: Path) -> ReleaseAdmission:
    header = read_json(release / "payload/release.json")
    if header.get("releaseKind") == ReleaseKind.EMPTY_BASELINE:
        return replace(
            _admission(release.name),
            release=release,
            contract=read_json(release / "payload/desired_state.json"),
            manifest_digest=payload_digest(release),
            admission_kind="empty_baseline_attestation",
            handoff_ref="",
            handoff_artifact_ref="",
            handoff_artifact_digest="",
            system_attestation_ref=f"data/releases/{release.name}/attestations/release.json",
            system_attestation_digest=_ADMISSION_DIGEST,
        )
    return replace(
        _admission(release.name),
        release=release,
        contract=read_json(release / "payload/desired_state.json"),
        manifest_digest=payload_digest(release),
    )


HOMEPAGE_IMPORTER_REPORT = {
    "releaseId": "release-a",
    "env": "gamma",
    "dryRun": False,
    "issues": [],
    "skipped": [],
    "entityRefToHomepageId": {},
}


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
        "sourceDigests": [SourceDefinitionSnapshot(digest=source_digest).to_document()],
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


def _isolated_target(
    root: Path,
    environment: DeploymentEnvironment = DeploymentEnvironment.GAMMA,
) -> EnvironmentReleaseTarget:
    return EnvironmentReleaseTarget(
        environment=environment,
        target_name=f"{environment.value}-local",
        mode=EnvironmentReleaseMode.LOCAL_IMPORT,
        mongo_uri="mongodb://topology.test",
        user_postgres_dsn="postgres://topology.test/quwoquan",
        media_sync_root=root / "environment-media",
        media_delivery_base_url=f"https://media.{environment.value}.test",
        api_base_url=f"https://api.{environment.value}.test",
        missing_requirements=(),
        redis_addr="127.0.0.1:6379",
    )


def _write_import_result(
    *,
    root: Path,
    release: Path,
    environment: str,
    import_run_id: str,
    homepage_cases_ref: str,
) -> Path:
    admission = _fixture_admission(release)
    apply_run_id = f"{import_run_id}-apply"
    apply_run = create_environment_run(
        output_root=root,
        environment=environment,
        release_id=release.name,
        run_id=apply_run_id,
        kind="apply",
        valid_environments=frozenset({environment}),
    )
    activation_run = create_environment_run(
        output_root=root,
        environment=environment,
        release_id=release.name,
        run_id=import_run_id,
        kind="activate",
        valid_environments=frozenset({environment}),
    )
    header = read_json(release / "payload/release.json")
    release_class = str(header["releaseClass"])
    candidate = apply_run / "content-candidate-receipt.json"
    write_json(
        candidate,
        {
            "schema": "quwoquan.content_release_candidate_receipt",
            "status": "found",
            "environment": environment,
            "sourceOwner": "qwq_data",
            "releaseId": release.name,
            "manifestDigest": admission.manifest_digest,
            "releaseClass": release_class,
            "releaseKind": str(header["releaseKind"]),
            "mode": "sync",
            "deletePolicy": "tombstone",
            "projectionVersion": 1,
            "verifiedAt": "2026-09-05T00:00:00Z",
            "closureDigests": {
                "posts": "sha256:" + "1" * 64,
                "facts": "sha256:" + "2" * 64,
                "media": "sha256:" + "3" * 64,
            },
            "counts": {
                "postsExpected": 0,
                "postsProjected": 0,
                "outboxExpected": 0,
                "outboxProjected": 0,
                "mediaExpected": 0,
                "mediaProjected": 0,
            },
            "generatedAt": "2026-09-05T00:00:01Z",
        },
    )
    pre = activation_run / "content-active-pre-receipt.json"
    write_json(
        pre,
        {
            "schema": "quwoquan.content_release_active_receipt",
            "status": "not_found",
            "environment": environment,
            "sourceOwner": "qwq_data",
            "generatedAt": "2026-09-05T00:00:02Z",
        },
    )
    expectation = {"found": False, "sourceOwner": "qwq_data", "revision": 0}
    activation = activation_run / "content-activation-receipt.json"
    write_json(
        activation,
        {
            "schema": "quwoquan.content_release_activation_receipt",
            "status": "activated",
            "environment": environment,
            "sourceOwner": "qwq_data",
            "target": {
                "releaseId": release.name,
                "manifestDigest": admission.manifest_digest,
            },
            "expectedActive": expectation,
            "previousActive": expectation,
            "active": {
                "releaseId": release.name,
                "manifestDigest": admission.manifest_digest,
                "releaseClass": release_class,
                "projectionVersion": 2,
                "revision": 1,
                "activatedAt": "2026-09-05T00:00:03Z",
            },
            "counts": {
                "postsMaterialized": 0,
                "postsRemoved": 0,
                "mediaAssetsMaterialized": 0,
                "mediaAssetsRemoved": 0,
                "outboxEventsReady": 0,
                "outboxEventsAppended": 0,
            },
            "generatedAt": "2026-09-05T00:00:03Z",
        },
    )
    post = activation_run / "content-active-post-receipt.json"
    write_json(
        post,
        {
            "schema": "quwoquan.content_release_active_receipt",
            "status": "found",
            "environment": environment,
            "sourceOwner": "qwq_data",
            "releaseId": release.name,
            "manifestDigest": admission.manifest_digest,
            "releaseClass": release_class,
            "projectionVersion": 2,
            "revision": 1,
            "activatedAt": "2026-09-05T00:00:03Z",
            "generatedAt": "2026-09-05T00:00:04Z",
        },
    )
    evidence = {}
    for prefix, receipt in (
        ("contentCandidate", candidate),
        ("contentPreActive", pre),
        ("contentActivation", activation),
        ("contentPostActive", post),
    ):
        evidence[prefix + "ReceiptRef"] = receipt.relative_to(root).as_posix()
        evidence[prefix + "ReceiptDigest"] = (
            "sha256:" + hashlib.sha256(receipt.read_bytes()).hexdigest()
        )
    write_environment_result(
        activation_run / "result.json",
        {
            "schema": "quwoquan_data.environment_release_result",
            "environment": environment,
            "releaseId": release.name,
            "releaseClass": release_class,
            "productLifecycleState": str(header["productLifecycleState"]),
            "containsUnverifiedAssets": bool(header["containsUnverifiedAssets"]),
            "manifestDigest": admission.manifest_digest,
            **admission.result_envelope(),
            "runId": import_run_id,
            "importRunId": apply_run_id,
            "status": "completed",
            **evidence,
            "homepageVerificationCasesRef": homepage_cases_ref,
        },
    )
    return apply_run


def _patch_roots(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(handler, "OUTPUT_ROOT", root)
    monkeypatch.setattr(handler, "RELEASE_ROOT", root / "data" / "releases")
    monkeypatch.setattr(
        handler,
        "resolve_environment_release_target",
        lambda env: _target(root, DeploymentEnvironment(env)),
    )
    monkeypatch.setattr(
        handler, "require_environment_readiness", lambda **_kwargs: None
    )


def test_apply_writes_append_only_environment_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    args = argparse.Namespace(
        env="gamma",
        run_id="apply-1",
        import_to_db=False,
        full_sync=True,
        dry_run=True,
        confirm_prod_apply=False,
        release_admission=_fixture_admission(release),
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
    release = _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)

    handler._apply_release(
        argparse.Namespace(
            env="prod",
            run_id="prepared-1",
            import_to_db=False,
            full_sync=True,
            dry_run=False,
            confirm_prod_apply=False,
            release_admission=_fixture_admission(release),
        )
    )

    run = tmp_path / "env/prod/runs/data-release/release-a/prepared-1"
    assert read_json(run / "result.json")["status"] == "prepared"
    assert not (run / "applied_ref.json").exists()
    assert not (run / "media-sync.json").exists()


def test_apply_dry_run_import_enforces_release_desired_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        handler,
        "_run_tag_importer",
        lambda **kwargs: (
            calls.append({"kind": "tag", **kwargs}) or kwargs["run"] / "tag-import.json"
        ),
    )
    monkeypatch.setattr(
        handler,
        "_run_creator_importer",
        lambda **kwargs: (
            calls.append({"kind": "creator", **kwargs})
            or kwargs["run"] / "creator-import.json"
        ),
    )
    monkeypatch.setattr(
        handler,
        "_run_content_importer",
        lambda **kwargs: (
            calls.append({"kind": "content", **kwargs}) or kwargs["run"] / "import.json"
        ),
    )
    monkeypatch.setattr(
        handler,
        "_run_homepage_importer",
        lambda **kwargs: (
            calls.append({"kind": "homepage", **kwargs})
            or dict(HOMEPAGE_IMPORTER_REPORT)
        ),
    )

    handler._apply_release(
        argparse.Namespace(
            env="gamma",
            run_id="apply-sync",
            import_to_db=True,
            full_sync=True,
            dry_run=True,
            confirm_prod_apply=False,
            release_admission=_fixture_admission(release),
        )
    )

    assert len(calls) == 4
    assert calls[0]["kind"] == "tag"
    assert calls[1]["kind"] == "creator"
    assert calls[1]["postgres_dsn"] == "postgres://topology.test/quwoquan"
    assert calls[2]["kind"] == "content"
    assert calls[2]["mode"] == "sync"
    assert calls[2]["delete_policy"] == "tombstone"
    assert "activation_mode" not in calls[2]
    assert calls[2]["creator_receipt"] == calls[1]["run"] / "creator-import.json"
    assert calls[3]["kind"] == "homepage"
    assert calls[3]["mode"] == "sync"
    assert calls[0]["mongo_uri"] == "mongodb://topology.test"
    target = _target(tmp_path)
    assert calls[1]["media_avatar_base_url"] == target.media_delivery_base_url
    assert calls[2]["media_avatar_base_url"] == target.media_delivery_base_url
    assert calls[2]["media_video_base_url"] == target.media_delivery_base_url
    assert calls[3]["media_image_base_url"] == target.media_delivery_base_url
    run = tmp_path / "env/gamma/runs/data-release/release-a/apply-sync"
    assert read_json(run / "result.json")["status"] == "dry_run"
    assert not (run / "applied_ref.json").exists()


def test_research_apply_blocks_before_readiness_or_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path)
    header_path = release / "payload/release.json"
    header = read_json(header_path)
    header["releaseClass"] = "research"
    header["productLifecycleState"] = "research"
    write_json(header_path, header)
    _patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(
        handler,
        "resolve_environment_release_target",
        lambda _env: _isolated_target(tmp_path),
    )
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        handler,
        "require_environment_readiness",
        lambda **kwargs: observed.update(kwargs),
    )

    monkeypatch.setattr(
        handler,
        "_run_tag_importer",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("tag importer must not run before owner-local staging")
        ),
    )
    with pytest.raises(SystemExit, match="cross-owner live release"):
        handler._apply_release(
            argparse.Namespace(
                env="gamma",
                run_id="research-apply-import-readiness",
                import_to_db=True,
                full_sync=True,
                dry_run=False,
                confirm_prod_apply=False,
                release_admission=_fixture_admission(release),
            )
        )

    assert observed == {}
    run = (
        tmp_path
        / "env/gamma/runs/data-release/release-a/research-apply-import-readiness"
    )
    result = read_json(run / "result.json")
    assert result["status"] == "failed"
    assert result["handoffArtifactRef"].endswith("/producer_release_handoff.json")
    assert result["handoffArtifactDigest"].startswith("sha256:")
    assert result["failedStage"] == "owner_local_staging_admission"
    assert not (run / "applied_ref.json").exists()


def test_research_rollback_import_is_blocked_before_cas_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path)
    header_path = release / "payload/release.json"
    header = read_json(header_path)
    header["releaseClass"] = "research"
    header["productLifecycleState"] = "research"
    write_json(header_path, header)
    _patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(
        handler,
        "resolve_environment_release_target",
        lambda _env: _isolated_target(tmp_path),
    )
    observed: list[object] = []
    monkeypatch.setattr(
        handler,
        "require_environment_readiness",
        lambda **kwargs: observed.append(kwargs),
    )

    monkeypatch.setattr(
        handler,
        "_run_tag_importer",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("tag importer must not run before owner-local staging")
        ),
    )
    with pytest.raises(SystemExit, match="cross-owner live release"):
        handler._rollback_release(
            argparse.Namespace(
                from_release_id="release-current",
                from_manifest_digest="sha256:" + "d" * 64,
                env="gamma",
                run_id="research-rollback-cas-block",
                import_to_db=True,
                dry_run=False,
                confirm_prod_apply=False,
                release_admission=_fixture_admission(release),
            )
        )

    assert observed == []
    run = tmp_path / "env/gamma/runs/data-release/release-a/research-rollback-cas-block"
    assert (run / "run.json").is_file()
    result = read_json(run / "result.json")
    assert result["status"] == "failed"
    assert result["handoffArtifactRef"].endswith("/producer_release_handoff.json")
    assert result["handoffArtifactDigest"].startswith("sha256:")
    assert result["failedStage"] == "owner_local_staging_admission"


def test_apply_rejects_missing_full_sync_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        handler,
        "_run_creator_importer",
        lambda **kwargs: (
            calls.append({"kind": "creator", **kwargs})
            or kwargs["run"] / "creator-import.json"
        ),
    )
    monkeypatch.setattr(
        handler, "_run_content_importer", lambda **kwargs: calls.append(kwargs)
    )
    monkeypatch.setattr(
        handler,
        "_run_homepage_importer",
        lambda **kwargs: calls.append({"kind": "homepage", **kwargs}),
    )

    with pytest.raises(SystemExit, match="immutable release requires --full-sync"):
        handler._apply_release(
            argparse.Namespace(
                env="gamma",
                run_id="apply-without-full-sync",
                import_to_db=True,
                full_sync=False,
                dry_run=False,
                confirm_prod_apply=False,
                release_admission=_fixture_admission(release),
            )
        )

    assert calls == []


def test_rollback_writes_resolvable_release_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    handler._rollback_release(
        argparse.Namespace(
            from_release_id="release-current",
            from_manifest_digest="sha256:" + "d" * 64,
            env="gamma",
            run_id="rollback-1",
            import_to_db=False,
            dry_run=True,
            confirm_prod_apply=False,
            release_admission=_fixture_admission(release),
        )
    )
    ref = read_json(
        tmp_path / "env/gamma/runs/data-release/release-a/rollback-1/rollback_ref.json"
    )
    assert ref["releaseRef"] == "data/releases/release-a"
    assert ref["authority"] == "asserted_intent"
    assert ref["rollbackFromReleaseId"] == "release-current"
    assert (tmp_path / ref["releaseRef"] / "payload" / "desired_state.json").is_file()
    result = read_json(
        tmp_path / "env/gamma/runs/data-release/release-a/rollback-1/result.json"
    )
    assert result["status"] == "dry_run"
    assert result["handoffArtifactRef"].endswith("/producer_release_handoff.json")
    assert result["handoffArtifactDigest"].startswith("sha256:")


def test_rollback_import_is_gate_blocked_before_any_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    mutation_calls: list[str] = []
    monkeypatch.setattr(
        handler,
        "_run_tag_importer",
        lambda **_kwargs: (
            mutation_calls.append("tag")
            or (_ for _ in ()).throw(SystemExit("tag importer unavailable"))
        ),
    )

    with pytest.raises(SystemExit, match="cross-owner live release"):
        handler._rollback_release(
            argparse.Namespace(
                from_release_id="release-current",
                from_manifest_digest="sha256:" + "d" * 64,
                env="gamma",
                run_id="rollback-cas-block",
                import_to_db=True,
                dry_run=False,
                confirm_prod_apply=False,
                release_admission=_fixture_admission(release),
            )
        )

    assert mutation_calls == []
    run = tmp_path / "env/gamma/runs/data-release/release-a/rollback-cas-block"
    assert (run / "run.json").is_file()
    result = read_json(run / "result.json")
    assert result["status"] == "failed"
    assert result["handoffArtifactRef"].endswith("/producer_release_handoff.json")
    assert result["handoffArtifactDigest"].startswith("sha256:")
    assert result["failedStage"] == "owner_local_staging_admission"


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
        write_release_contract(
            {**contract, "environment": "gamma"}, release_root=tmp_path
        )


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
    import_root = _write_import_result(
        root=tmp_path,
        release=release,
        environment=environment.value,
        import_run_id=import_run_id,
        homepage_cases_ref=cases_ref.replace(import_run_id, f"{import_run_id}-apply"),
    )
    cases = import_root / "homepage_verification_cases.json"
    write_json(cases, {"environment": environment.value})
    observed: dict[str, object] = {}

    def _verify(**kwargs: object) -> Path:
        observed.update(kwargs)
        output = Path(str(kwargs["output_path"]))
        write_json(output, {"passed": True})
        return output

    monkeypatch.setattr(handler, "write_homepage_api_verification", _verify)
    handler._verify_release_consumers(
        argparse.Namespace(
            env=environment.value,
            import_run_id=import_run_id,
            run_id="verify-001",
            readiness_phase="consumer",
            lifecycle_exit_ref="",
            release_admission=_fixture_admission(release),
        )
    )

    assert observed["environment"] is environment
    assert observed["api_base_url"] == _target(tmp_path, environment).api_base_url
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
    import_root = (
        tmp_path / "env/gamma/runs/data-release" / release.name / import_run_id
    )
    cases = import_root / "homepage_verification_cases.json"
    import_root = _write_import_result(
        root=tmp_path,
        release=release,
        environment="gamma",
        import_run_id=import_run_id,
        homepage_cases_ref=cases.relative_to(tmp_path)
        .as_posix()
        .replace(import_run_id, f"{import_run_id}-apply"),
    )
    cases = import_root / "homepage_verification_cases.json"
    write_json(cases, {"environment": "gamma"})

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
            env="gamma",
            import_run_id=import_run_id,
            run_id="verify-ready",
            readiness_phase="commercial",
            lifecycle_exit_ref=lifecycle_exit_ref,
            release_admission=_fixture_admission(release),
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
    assert result["releaseReadinessRef"].endswith(
        "/verify-ready/release-readiness.json"
    )
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
    import_root = (
        tmp_path / "env/alpha/runs/data-release" / release.name / import_run_id
    )
    cases = import_root / "homepage_verification_cases.json"
    import_root = _write_import_result(
        root=tmp_path,
        release=release,
        environment="alpha",
        import_run_id=import_run_id,
        homepage_cases_ref=cases.relative_to(tmp_path)
        .as_posix()
        .replace(import_run_id, f"{import_run_id}-apply"),
    )
    cases = import_root / "homepage_verification_cases.json"
    write_json(cases, {"environment": "alpha"})
    monkeypatch.setattr(
        handler,
        "write_homepage_api_verification",
        lambda **_kwargs: (_ for _ in ()).throw(
            handler.HomepageApiVerificationError("public homepage returned 404")
        ),
    )

    with pytest.raises(SystemExit, match="homepage API verification failed"):
        handler._verify_release_consumers(
            argparse.Namespace(
                env="alpha",
                import_run_id=import_run_id,
                run_id="verify-failed",
                readiness_phase="consumer",
                lifecycle_exit_ref="",
                release_admission=_fixture_admission(release),
            )
        )

    result = read_json(
        tmp_path
        / "env/alpha/runs/data-release"
        / release.name
        / "verify-failed/result.json"
    )
    assert result["status"] == "failed"
    assert result["handoffArtifactRef"].endswith("/producer_release_handoff.json")
    assert result["handoffArtifactDigest"].startswith("sha256:")
    assert result["importRunId"] == import_run_id
    assert result["failedStage"] == "homepage_api_verification"
    assert result["error"].endswith("public homepage returned 404")
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
    import_root = (
        tmp_path / "env/gamma/runs/data-release" / release.name / import_run_id
    )
    import_root = _write_import_result(
        root=tmp_path,
        release=release,
        environment="gamma",
        import_run_id=import_run_id,
        homepage_cases_ref="",
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
            env="gamma",
            import_run_id=import_run_id,
            run_id="baseline-verify",
            release_admission=_fixture_admission(release),
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
    assert result["admissionKind"] == "empty_baseline_attestation"
    assert result["systemAttestationRef"].endswith("/attestations/release.json")
