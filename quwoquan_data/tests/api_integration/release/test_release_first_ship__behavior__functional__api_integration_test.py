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
        "sourceDigests": [
            SourceDefinitionSnapshot(digest=source_digest).to_document()
        ],
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
        expected_revision=0,
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
            expected_revision=0,
        )
    )

    run = tmp_path / "env/prod/runs/data-release/release-a/prepared-1"
    assert read_json(run / "result.json")["status"] == "prepared"
    assert not (run / "applied_ref.json").exists()
    assert not (run / "media-sync.json").exists()


CANDIDATE_REVISION = 1788678560042


def _fake_content_importer(calls: list[dict[str, object]]):
    """Emulate the three-phase Go importer: stage/verify/activate reports."""

    def _run(**kwargs: object) -> dict[str, object]:
        calls.append({"kind": "content", **kwargs})
        phase = str(kwargs.get("phase", "stage"))
        if phase == "stage":
            write_json(
                Path(str(kwargs["run"])) / "import.json",
                {
                    "schema": "quwoquan.content_import_report",
                    "status": "staged", "phase": "stage",
                    "candidateRevision": CANDIDATE_REVISION,
                    "environment": "gamma", "releaseId": "release-a",
                    "sourceOwner": "qwq_data",
                    "manifestDigest": payload_digest(
                        Path(str(kwargs["release"]))
                    ),
                    "mode": kwargs["mode"], "deletePolicy": kwargs["delete_policy"],
                    "counts": {"postsLoaded": 0, "entitiesLoaded": 0, "postsStaged": 0},
                    "postBindings": [], "auditEvents": ["DataReleasePrepared"],
                    "previousReleaseId": "", "previousManifestDigest": "",
                    "previousRevision": 0,
                },
            )
            return {"status": "staged", "phase": "stage", "candidateRevision": CANDIDATE_REVISION}
        if phase == "verify":
            return {
                "status": "verified", "phase": "verify",
                "candidateRevision": kwargs["candidate_revision"],
                "candidatePostIds": [], "candidateSourceHashes": [],
            }
        return {
            "status": "active", "phase": "activate",
            "candidateRevision": kwargs["candidate_revision"],
            "revision": int(kwargs["expected_revision"]) + 1, "sourceVersion": 1,
            "auditEvents": [],
        }

    return _run


def _patch_reference_importers(
    monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, object]]
) -> None:
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
    monkeypatch.setattr(handler, "_run_content_importer", _fake_content_importer(calls))
    monkeypatch.setattr(
        handler,
        "_run_homepage_importer",
        lambda **kwargs: (
            calls.append({"kind": "homepage", **kwargs})
            or dict(HOMEPAGE_IMPORTER_REPORT)
        ),
    )


def test_apply_stages_only_and_activate_owns_pointer_switch_and_destructive_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []
    _patch_reference_importers(monkeypatch, calls)

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

    # Stage：引用型对象只允许 additive upsert；Content 只写候选，不带 expected revision。
    assert [call["kind"] for call in calls] == ["tag", "creator", "homepage", "content"]
    assert calls[1]["postgres_dsn"] == "postgres://topology.test/quwoquan"
    assert calls[1]["mode"] == "upsert"
    assert calls[2]["mode"] == "upsert"
    assert calls[3]["phase"] == "stage"
    assert calls[3]["mode"] == "sync"
    assert calls[3]["delete_policy"] == "tombstone"
    assert "expected_revision" not in calls[3]
    assert calls[3]["creator_receipt"] == calls[1]["run"] / "creator-import.json"
    target = _target(tmp_path)
    assert calls[3]["media_video_base_url"] == target.media_delivery_base_url
    stage_run = tmp_path / "env/gamma/runs/data-release/release-a/apply-sync"
    stage_result = read_json(stage_run / "result.json")
    assert stage_result["status"] == "completed"
    assert stage_result["contentPhase"] == "stage"
    assert stage_result["candidateRevision"] == CANDIDATE_REVISION
    assert stage_result["fullSync"] is True
    assert not (stage_run / "applied_ref.json").exists()

    # Activate 必须绑定已通过的候选 verify run；缺失即 fail closed，且不触碰 importer。
    calls.clear()
    with pytest.raises(SystemExit, match="verify run"):
        handler._activate_release(
            argparse.Namespace(
                release_id="release-a", env="gamma", import_run_id="apply-sync",
                verify_run_id="missing-verify", run_id="activate-early",
                expected_revision=0, confirm_prod_apply=False,
            )
        )
    assert calls == []

    handler._verify_release_consumers(
        argparse.Namespace(
            release_id="release-a", env="gamma", import_run_id="apply-sync",
            run_id="candidate-verify",
        )
    )
    assert [call["kind"] for call in calls] == ["content"]
    assert calls[0]["phase"] == "verify"
    assert calls[0]["candidate_revision"] == CANDIDATE_REVISION
    verify_result = read_json(
        tmp_path / "env/gamma/runs/data-release/release-a/candidate-verify/result.json"
    )
    assert verify_result["contentPhase"] == "verify"
    assert verify_result["importRunId"] == "apply-sync"
    assert verify_result["candidateRevision"] == CANDIDATE_REVISION

    calls.clear()
    handler._activate_release(
        argparse.Namespace(
            release_id="release-a", env="gamma", import_run_id="apply-sync",
            verify_run_id="candidate-verify", run_id="activate-1",
            expected_revision=0, confirm_prod_apply=False,
        )
    )
    # Activate：先切 Content pointer，pointer 切换成功之后才允许 sync 删除/下线。
    assert [call["kind"] for call in calls] == ["content", "tag", "creator", "homepage"]
    assert calls[0]["phase"] == "activate"
    assert calls[0]["candidate_revision"] == CANDIDATE_REVISION
    assert calls[0]["expected_revision"] == 0
    assert calls[0]["creator_receipt"] == stage_run / "creator-import.json"
    assert calls[2]["mode"] == "sync"
    assert calls[3]["mode"] == "sync"
    activate_run = tmp_path / "env/gamma/runs/data-release/release-a/activate-1"
    applied = read_json(activate_run / "applied_ref.json")
    assert applied["releaseId"] == "release-a"
    assert applied["releaseRef"] == "data/releases/release-a"
    activate_result = read_json(activate_run / "result.json")
    assert activate_result["contentPhase"] == "activate"
    assert activate_result["revision"] == 1
    assert activate_result["verifyRunId"] == "candidate-verify"
    assert read_json(activate_run / "media-prune.json")["pruned"] == 0


def test_research_apply_uses_import_readiness_before_import(
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

    class StopAfterReadiness(RuntimeError):
        pass

    def _require_import_readiness(**kwargs: object) -> None:
        observed.update(kwargs)
        raise StopAfterReadiness

    monkeypatch.setattr(
        handler,
        "require_environment_readiness",
        _require_import_readiness,
    )

    with pytest.raises(StopAfterReadiness):
        handler._apply_release(
            argparse.Namespace(
                release_id="release-a",
                env="gamma",
                run_id="research-apply-import-readiness",
                import_to_db=True,
                full_sync=True,
                dry_run=False,
                confirm_prod_apply=False,
                expected_revision=0,
            )
        )

    assert observed["phase"] is ShipReadinessPhase.IMPORT
    assert observed["environment"] is DeploymentEnvironment.GAMMA
    assert observed["release_id"] == "release-a"
    assert observed["manifest_digest"] == payload_digest(release)


def test_research_rollback_uses_import_readiness_before_import(
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

    class StopAfterReadiness(RuntimeError):
        pass

    def _require_import_readiness(**kwargs: object) -> None:
        observed.update(kwargs)
        raise StopAfterReadiness

    monkeypatch.setattr(
        handler,
        "require_environment_readiness",
        _require_import_readiness,
    )

    # fresh rollback 的 stage 子 run 在 readiness 处中断；任何非 SystemExit 异常都
    # 必须收敛为 typed rollback_failed，而不是裸异常逃逸。
    with pytest.raises(SystemExit, match="DATA.DELIVERY.ROLLBACK_FAILED.*failedStage=stage"):
        handler._rollback_release(
            argparse.Namespace(
                to_release="release-a",
                from_release_id="release-current",
                env="gamma",
                run_id="research-rollback-import-readiness",
                import_to_db=True,
                dry_run=False,
                confirm_prod_apply=False,
                expected_revision=0,
            )
        )

    assert observed["phase"] is ShipReadinessPhase.IMPORT
    assert observed["environment"] is DeploymentEnvironment.GAMMA
    assert observed["release_id"] == "release-a"
    assert observed["manifest_digest"] == payload_digest(release)


def test_activate_rejects_negative_content_revision_before_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(handler, "_run_content_importer", lambda **kwargs: calls.append(kwargs))

    with pytest.raises(SystemExit, match="expected-revision"):
        handler._activate_release(
            argparse.Namespace(
                release_id="release-a",
                env="gamma",
                import_run_id="apply-sync",
                verify_run_id="candidate-verify",
                run_id="negative-revision",
                expected_revision=-1,
                confirm_prod_apply=False,
            )
        )

    assert calls == []


def test_apply_rejects_multiple_environments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(handler, "_run_content_importer", lambda **kwargs: calls.append(kwargs))

    with pytest.raises(SystemExit, match="单个 --env"):
        handler._apply_release(
            argparse.Namespace(
                release_id="release-a",
                env="alpha,gamma",
                run_id="multi-env",
                import_to_db=True,
                full_sync=True,
                dry_run=False,
                confirm_prod_apply=False,
            )
        )

    assert calls == []


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
                expected_revision=0,
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
            expected_revision=0,
        )
    )
    ref = read_json(tmp_path / "env/gamma/runs/data-release/release-a/rollback-1/rollback_ref.json")
    assert ref["releaseRef"] == "data/releases/release-a"
    assert ref["rollbackFromReleaseId"] == "release-current"
    assert (tmp_path / ref["releaseRef"] / "payload" / "desired_state.json").is_file()
    result = read_json(tmp_path / "env/gamma/runs/data-release/release-a/rollback-1/result.json")
    assert result["status"] == "dry_run"


def test_rollback_runs_fresh_stage_verify_activate_and_binds_homepage_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []
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
    _patch_reference_importers(monkeypatch, calls)

    def _write_homepage_cases(**kwargs: object) -> Path:
        calls.append({"kind": "homepage-cases"})
        assert kwargs["importer_report"] == HOMEPAGE_IMPORTER_REPORT
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
            expected_revision=4,
        )
    )

    # fresh stage(additive) → candidate verify → activate(pointer) → destructive sync。
    assert [(call["kind"], call.get("phase"), call.get("mode")) for call in calls] == [
        ("tag", None, None),
        ("creator", None, "upsert"),
        ("homepage", None, "upsert"),
        ("homepage-cases", None, None),
        ("content", "stage", "sync"),
        ("content", "verify", "sync"),
        ("content", "activate", "sync"),
        ("tag", None, None),
        ("creator", None, "sync"),
        ("homepage", None, "sync"),
        ("homepage-cases", None, None),
    ]
    activate_call = next(call for call in calls if call.get("phase") == "activate")
    assert activate_call["expected_revision"] == 4
    assert activate_call["candidate_revision"] == CANDIDATE_REVISION
    runs = tmp_path / "env/gamma/runs/data-release/release-a"
    result = read_json(runs / "rollback-reload/result.json")
    assert result["status"] == "completed"
    assert result["contentPhase"] == "activate"
    assert result["revision"] == 5
    assert result["stageRunId"] == "rollback-reload-stage"
    assert result["verifyRunId"] == "rollback-reload-verify"
    assert result["activateRunId"] == "rollback-reload-activate"
    activate_result = read_json(runs / "rollback-reload-activate/result.json")
    assert activate_result["homepageVerificationCasesRef"].endswith(
        "/rollback-reload-activate/homepage_verification_cases.json"
    )
    assert read_json(runs / "rollback-reload-activate/rollback_ref.json")[
        "rollbackFromReleaseId"
    ] == "release-current"
    assert (runs / "rollback-reload-activate/applied_ref.json").is_file()
    assert not (runs / "rollback-reload-stage/applied_ref.json").exists()


def test_rollback_failure_before_activation_is_typed_and_leaves_no_applied_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []
    _patch_reference_importers(monkeypatch, calls)
    fake_content = _fake_content_importer(calls)

    def _failing_verify(**kwargs: object) -> dict[str, object]:
        if kwargs.get("phase") == "verify":
            calls.append({"kind": "content", **kwargs})
            raise SystemExit("[ship] importer failed: exit=1")
        return fake_content(**kwargs)

    monkeypatch.setattr(handler, "_run_content_importer", _failing_verify)

    with pytest.raises(SystemExit, match="DATA.DELIVERY.ROLLBACK_FAILED.*failedStage=verify"):
        handler._rollback_release(
            argparse.Namespace(
                to_release="release-a",
                from_release_id="release-current",
                env="gamma",
                run_id="rollback-broken",
                import_to_db=True,
                dry_run=False,
                confirm_prod_apply=False,
                expected_revision=0,
            )
        )

    assert [call.get("phase") for call in calls if call["kind"] == "content"] == ["stage", "verify"]
    runs = tmp_path / "env/gamma/runs/data-release/release-a"
    result = read_json(runs / "rollback-broken/result.json")
    assert result["status"] == "failed"
    assert result["failedStage"] == "verify"
    assert result["error"].startswith("DATA.DELIVERY.ROLLBACK_FAILED")
    assert result["stageRunId"] == "rollback-broken-stage"
    assert "activateRunId" not in result
    assert not (runs / "rollback-broken-stage/applied_ref.json").exists()
    assert not (runs / "rollback-broken-activate").exists()


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
    previous_active = destination / "media/image/s/release-old/post-old/v1/cover.jpg"
    previous_active.parent.mkdir(parents=True)
    previous_active.write_bytes(b"previous-active")

    handler._sync_media(release=release, destination=str(destination), run=run)

    assert (destination / source.relative_to(payload_root)).read_bytes() == payload
    assert not (destination / unrelated.relative_to(payload_root)).exists()
    assert previous_active.read_bytes() == b"previous-active"
    report = read_json(run / "media-sync.json")
    assert report["failed"] == 0
    assert report["pruned"] == 0


def _media_release(root: Path, release_id: str, slice_key: str, payload: bytes) -> Path:
    """One commercial release whose manifest ships exactly one public slice."""

    release = _release(root, release_id=release_id)
    payload_root = release / "payload"
    source = payload_root / slice_key
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(payload)
    write_json(
        release / "payload" / "media_manifest.json",
        {
            "schema": "quwoquan_data.release_media_manifest",
            "releaseId": release_id,
            "assets": [
                {
                    "assetId": f"{release_id}-image",
                    "publicSliceKey": slice_key,
                    "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
                    "bytes": len(payload),
                }
            ],
        },
    )
    return release


def test_post_activate_prune_keeps_new_and_previous_active_closures(
    tmp_path: Path,
) -> None:
    previous = _media_release(
        tmp_path, "release-prev", "media/image/s/asset/prev-image/v1/source.webp", b"prev-bytes"
    )
    current = _media_release(
        tmp_path, "release-next", "media/image/s/asset/next-image/v1/source.webp", b"next-bytes"
    )
    destination = tmp_path / "environment-media"
    for key, payload in (
        ("media/image/s/asset/prev-image/v1/source.webp", b"prev-bytes"),
        ("media/image/s/asset/next-image/v1/source.webp", b"next-bytes"),
        ("media/image/s/asset/stale-image/v1/source.webp", b"stale-bytes"),
        ("media/objects/sha256/aa/bb/" + "a" * 64 + ".bin", b"cas-body"),
    ):
        path = destination / key
        path.parent.mkdir(parents=True)
        path.write_bytes(payload)
    run = tmp_path / "runs/activate-1"
    run.mkdir(parents=True)

    handler._prune_media(
        release=current, previous_release=previous, destination=str(destination), run=run,
    )

    # 回滚窗口内 previous 与 new 都必须可服务；只回收两者之外的公开 slice，
    # 且永不触及 CAS 根。
    assert (destination / "media/image/s/asset/prev-image/v1/source.webp").read_bytes() == b"prev-bytes"
    assert (destination / "media/image/s/asset/next-image/v1/source.webp").read_bytes() == b"next-bytes"
    assert not (destination / "media/image/s/asset/stale-image/v1/source.webp").exists()
    assert (destination / ("media/objects/sha256/aa/bb/" + "a" * 64 + ".bin")).exists()
    report = read_json(run / "media-prune.json")
    assert report["pruned"] == 1
    assert report["keptKeys"] == 2


def test_post_activate_prune_skips_when_previous_release_is_unavailable_locally(
    tmp_path: Path,
) -> None:
    current = _media_release(
        tmp_path, "release-next", "media/image/s/asset/next-image/v1/source.webp", b"next-bytes"
    )
    destination = tmp_path / "environment-media"
    stale = destination / "media/image/s/asset/stale-image/v1/source.webp"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale-bytes")
    run = tmp_path / "runs/activate-2"
    run.mkdir(parents=True)

    handler._prune_media(
        release=current,
        previous_release=tmp_path / "data/releases/release-missing",
        destination=str(destination),
        run=run,
    )

    # previous release 身份已知但本机不可得：保留多余字节永远比删掉回滚仍需
    # 服务的字节安全。
    assert stale.read_bytes() == b"stale-bytes"
    report = read_json(run / "media-prune.json")
    assert report["pruned"] == 0
    assert "unavailable" in report["skipped"]


def test_first_activation_prune_keeps_only_new_closure(
    tmp_path: Path,
) -> None:
    current = _media_release(
        tmp_path, "release-next", "media/image/s/asset/next-image/v1/source.webp", b"next-bytes"
    )
    destination = tmp_path / "environment-media"
    for key, payload in (
        ("media/image/s/asset/next-image/v1/source.webp", b"next-bytes"),
        ("media/image/s/asset/fixture-image/v1/source.webp", b"fixture-bytes"),
    ):
        path = destination / key
        path.parent.mkdir(parents=True)
        path.write_bytes(payload)
    run = tmp_path / "runs/activate-3"
    run.mkdir(parents=True)

    handler._prune_media(
        release=current, previous_release=None, destination=str(destination), run=run,
    )

    assert (destination / "media/image/s/asset/next-image/v1/source.webp").exists()
    assert not (destination / "media/image/s/asset/fixture-image/v1/source.webp").exists()
    assert read_json(run / "media-prune.json")["pruned"] == 1


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


def test_activate_post_switch_failure_leaves_typed_failed_result_with_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []
    _patch_reference_importers(monkeypatch, calls)
    handler._apply_release(
        argparse.Namespace(
            release_id="release-a", env="gamma", run_id="apply-sync", import_to_db=True,
            full_sync=True, dry_run=False, confirm_prod_apply=False,
        )
    )
    handler._verify_release_consumers(
        argparse.Namespace(
            release_id="release-a", env="gamma", import_run_id="apply-sync",
            run_id="candidate-verify",
        )
    )

    def _broken_homepage(**kwargs: object) -> dict[str, object]:
        calls.append({"kind": "homepage", **kwargs})
        raise SystemExit("[ship] homepage importer failed: exit=1")

    monkeypatch.setattr(handler, "_run_homepage_importer", _broken_homepage)
    calls.clear()
    with pytest.raises(SystemExit, match="DATA.DELIVERY.POST_ACTIVATE_FAILED.*revision=1"):
        handler._activate_release(
            argparse.Namespace(
                release_id="release-a", env="gamma", import_run_id="apply-sync",
                verify_run_id="candidate-verify", run_id="activate-broken",
                expected_revision=0, confirm_prod_apply=False,
            )
        )

    # pointer 已切换（content activate 已执行），收尾失败必须留下可观测终态。
    assert [call["kind"] for call in calls] == ["content", "tag", "creator", "homepage"]
    run = tmp_path / "env/gamma/runs/data-release/release-a/activate-broken"
    result = read_json(run / "result.json")
    assert result["status"] == "failed"
    assert result["failedStage"] == "post_activate_reference_sync"
    assert result["revision"] == 1
    assert result["candidateRevision"] == CANDIDATE_REVISION
    assert result["contentPhase"] == "activate"
    assert result["error"].startswith("DATA.DELIVERY.POST_ACTIVATE_FAILED")
    assert not (run / "applied_ref.json").exists()


def test_consumer_verify_argument_error_never_triggers_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _release(tmp_path)
    _patch_roots(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []
    _patch_reference_importers(monkeypatch, calls)
    handler._apply_release(
        argparse.Namespace(
            release_id="release-a", env="gamma", run_id="apply-sync", import_to_db=True,
            full_sync=True, dry_run=False, confirm_prod_apply=False,
        )
    )
    handler._verify_release_consumers(
        argparse.Namespace(
            release_id="release-a", env="gamma", import_run_id="apply-sync",
            run_id="candidate-verify",
        )
    )
    handler._activate_release(
        argparse.Namespace(
            release_id="release-a", env="gamma", import_run_id="apply-sync",
            verify_run_id="candidate-verify", run_id="activate-1",
            expected_revision=0, confirm_prod_apply=False,
        )
    )
    restores: list[dict[str, object]] = []
    monkeypatch.setattr(
        handler,
        "_restore_previous_release",
        lambda **kwargs: restores.append(kwargs) or "restore-x-activate",
    )
    monkeypatch.setattr(
        handler,
        "_write_tag_consumer_verification",
        _stub_tag_consumer_verification,
    )

    # --readiness-phase 非法是参数错误，发生在任何 verifier 之前；它不能变成回滚。
    with pytest.raises(SystemExit, match="--readiness-phase"):
        handler._verify_release_consumers(
            argparse.Namespace(
                release_id="release-a", env="gamma", import_run_id="activate-1",
                run_id="consumer-bad-args", readiness_phase="not-a-phase",
                lifecycle_exit_ref="", previous_environment_readiness="",
            )
        )
    assert restores == []
