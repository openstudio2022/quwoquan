"""ship verify forwards --lifecycle-exit-ref into commercial readiness."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.environment.release_runtime import ReleaseAdmission  # noqa: E402
from content.release.environment._ship_consumer_verification import (  # noqa: E402
    verify_release_consumers,
)
from content.release.environment._ship_operation_dependencies import (  # noqa: E402
    ShipOperationDependencies,
)
from content.release.environment.readiness import ShipReadinessPhase  # noqa: E402
from content.release.environment.run_evidence import (  # noqa: E402
    create_run,
    write_environment_result,
)
from content.release.environment.release_contract import (  # noqa: E402
    build_release_contract,
)
from content.release.environment.research_isolation_verification import (  # noqa: E402
    write_research_isolation_verification,
)
from content.release.environment.topology import (  # noqa: E402
    EnvironmentReleaseMode,
    EnvironmentReleaseTarget,
)
from content.release.model import DeploymentEnvironment, ReleaseKind  # noqa: E402
from core.control_types import ReleaseRunKind  # noqa: E402
from core.io import read_json, write_json  # noqa: E402
from core.release_layout import payload_digest  # noqa: E402
from core.source_digest import (  # noqa: E402
    SourceDefinitionSnapshot,
    content_source_revision,
)

_LIFECYCLE_EXIT_REF = (
    "env/gamma/runs/release-lifecycle-exit/release-a/exit-001/lifecycle-exit.json"
)
_SOURCE_DIGEST = "sha256:" + "b" * 64
_ENTITY_CATALOG_DIGEST = "sha256:" + "c" * 64
_SOURCE_REVISION = content_source_revision(
    source_digest=_SOURCE_DIGEST,
    entity_catalog_digest=_ENTITY_CATALOG_DIGEST,
)
_SOURCE_DIGEST_DOCUMENT = SourceDefinitionSnapshot(_SOURCE_DIGEST).to_document()
_ADMISSION = ReleaseAdmission(
    release=Path("/admitted/release-a"),
    contract={"releaseId": "release-a", "desiredRefs": {"entities": [], "posts": []}},
    release_id="release-a",
    manifest_digest="sha256:" + "0" * 64,
    admission_kind="producer_handoff",
    handoff_ref=f"handoff-ref-v1:sha256:{'1' * 64}:sha256:{'2' * 64}",
    handoff_artifact_ref=".qwq_output/data/releases/release-a/producer_release_handoff.json",
    handoff_artifact_digest="sha256:" + "0" * 64,
)


def _release(
    root: Path,
    *,
    research: bool = False,
    release_kind: ReleaseKind = ReleaseKind.CONTENT,
) -> Path:
    release = root / "data" / "releases" / "release-a"
    desired = build_release_contract(
        release_id="release-a",
        post_refs=[],
        entity_refs=[],
    )
    write_json(
        release / "payload" / "release.json",
        {
            "schema": "quwoquan_data.release",
            "releaseId": "release-a",
            "sourceOwner": "qwq_data",
            "releaseKind": release_kind,
            "sourceRevision": _SOURCE_REVISION,
            "sourceDigest": _SOURCE_DIGEST,
            "entityCatalogDigest": _ENTITY_CATALOG_DIGEST,
            "releaseClass": "research" if research else "commercial",
            "productLifecycleState": "research" if research else "commercial",
            "containsUnverifiedAssets": research,
            "rightsStatusCounts": {
                "verified": 0,
                "unverified": 1 if research else 0,
                "restricted": 0,
                "unknown": 0,
            },
            "authorizationRequiredAssetIds": (["research-asset-a"] if research else []),
            "researchAcceptedCount": 1 if research else 0,
            "commercialAcceptedCount": 0,
            "canonicalMerkle": "sha256:" + "a" * 64,
            "executionIds": [
                "20260804--travel-commercial-rights-closure--china--pilot-003"
            ],
            "sourceDigests": [_SOURCE_DIGEST_DOCUMENT],
        },
    )
    write_json(release / "payload" / "desired_state.json", desired)
    write_json(
        release / "payload" / "sample_bundle.json",
        {
            "schema": "quwoquan_data.release_sample",
            "releaseId": "release-a",
            "posts": [],
            "entities": [],
        },
    )
    write_json(
        release / "payload" / "media_manifest.json",
        {
            "schema": "quwoquan_data.release_media_manifest",
            "releaseId": "release-a",
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
            "releaseId": "release-a",
            "posts": [],
            "entities": [],
        },
    )
    return release


def _dependencies(
    root: Path,
    *,
    observed: dict[str, Any],
    research: bool = False,
    release_kind: ReleaseKind = ReleaseKind.CONTENT,
    create_homepage_cases: bool = True,
    homepage_cases_ref: str | None = None,
    predecessor_overrides: dict[str, Any] | None = None,
) -> ShipOperationDependencies:
    release = _release(root, research=research, release_kind=release_kind)
    contract = build_release_contract(
        release_id="release-a",
        post_refs=[],
        entity_refs=[],
    )
    manifest_digest = payload_digest(release)
    admission = ReleaseAdmission(
        release=release,
        contract=contract,
        release_id=release.name,
        manifest_digest=manifest_digest,
        admission_kind=(
            "empty_baseline_attestation"
            if release_kind is ReleaseKind.EMPTY_BASELINE
            else "producer_handoff"
        ),
        system_attestation_ref=(
            f"data/releases/{release.name}/attestations/release.json"
            if release_kind is ReleaseKind.EMPTY_BASELINE
            else ""
        ),
        system_attestation_digest=(
            "sha256:" + "0" * 64 if release_kind is ReleaseKind.EMPTY_BASELINE else ""
        ),
        handoff_ref=(
            ""
            if release_kind is ReleaseKind.EMPTY_BASELINE
            else f"handoff-ref-v1:sha256:{'1' * 64}:sha256:{'2' * 64}"
        ),
        handoff_artifact_ref=(
            ""
            if release_kind is ReleaseKind.EMPTY_BASELINE
            else f".qwq_output/data/releases/{release.name}/producer_release_handoff.json"
        ),
        handoff_artifact_digest=(
            "" if release_kind is ReleaseKind.EMPTY_BASELINE else "sha256:" + "0" * 64
        ),
    )
    apply_run = create_run(
        output_root=root,
        environment="gamma",
        release_id=release.name,
        run_id="apply-001",
        kind=ReleaseRunKind.APPLY,
        valid_environments=frozenset({"gamma"}),
    )
    import_run = create_run(
        output_root=root,
        environment="gamma",
        release_id=release.name,
        run_id="activate-001",
        kind=ReleaseRunKind.ACTIVATE,
        valid_environments=frozenset({"gamma"}),
    )
    cases = apply_run / "homepage_verification_cases.json"
    if create_homepage_cases:
        write_json(cases, {"environment": "gamma"})
    if homepage_cases_ref is None:
        homepage_cases_ref = (
            ""
            if release_kind is ReleaseKind.EMPTY_BASELINE
            else cases.relative_to(root).as_posix()
        )
    candidate = apply_run / "content-candidate-receipt.json"
    pre_active = import_run / "content-active-pre-receipt.json"
    activation = import_run / "content-activation-receipt.json"
    post_active = import_run / "content-active-post-receipt.json"
    write_json(
        candidate,
        {
            "schema": "quwoquan.content_release_candidate_receipt",
            "status": "found",
            "environment": "gamma",
            "sourceOwner": "qwq_data",
            "releaseId": release.name,
            "manifestDigest": manifest_digest,
            "releaseClass": "research" if research else "commercial",
            "releaseKind": str(release_kind),
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
    write_json(
        pre_active,
        {
            "schema": "quwoquan.content_release_active_receipt",
            "status": "not_found",
            "environment": "gamma",
            "sourceOwner": "qwq_data",
            "generatedAt": "2026-09-05T00:00:02Z",
        },
    )
    expected = {"found": False, "sourceOwner": "qwq_data", "revision": 0}
    write_json(
        activation,
        {
            "schema": "quwoquan.content_release_activation_receipt",
            "status": "activated",
            "environment": "gamma",
            "sourceOwner": "qwq_data",
            "target": {"releaseId": release.name, "manifestDigest": manifest_digest},
            "expectedActive": expected,
            "previousActive": expected,
            "active": {
                "releaseId": release.name,
                "manifestDigest": manifest_digest,
                "releaseClass": "research" if research else "commercial",
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
    write_json(
        post_active,
        {
            "schema": "quwoquan.content_release_active_receipt",
            "status": "found",
            "environment": "gamma",
            "sourceOwner": "qwq_data",
            "releaseId": release.name,
            "manifestDigest": manifest_digest,
            "releaseClass": "research" if research else "commercial",
            "projectionVersion": 2,
            "revision": 1,
            "activatedAt": "2026-09-05T00:00:03Z",
            "generatedAt": "2026-09-05T00:00:04Z",
        },
    )
    evidence_fields = {
        "contentCandidateReceiptRef": candidate.relative_to(root).as_posix(),
        "contentCandidateReceiptDigest": "sha256:"
        + __import__("hashlib").sha256(candidate.read_bytes()).hexdigest(),
        "contentPreActiveReceiptRef": pre_active.relative_to(root).as_posix(),
        "contentPreActiveReceiptDigest": "sha256:"
        + __import__("hashlib").sha256(pre_active.read_bytes()).hexdigest(),
        "contentActivationReceiptRef": activation.relative_to(root).as_posix(),
        "contentActivationReceiptDigest": "sha256:"
        + __import__("hashlib").sha256(activation.read_bytes()).hexdigest(),
        "contentPostActiveReceiptRef": post_active.relative_to(root).as_posix(),
        "contentPostActiveReceiptDigest": "sha256:"
        + __import__("hashlib").sha256(post_active.read_bytes()).hexdigest(),
    }
    overrides = dict(predecessor_overrides or {})
    predecessor_admission = admission.result_envelope()
    if overrides.get("admissionKind") == "empty_baseline_attestation":
        predecessor_admission.pop("handoffRef", None)
        predecessor_admission.pop("handoffArtifactRef", None)
        predecessor_admission.pop("handoffArtifactDigest", None)
    predecessor = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": "gamma",
        "releaseId": release.name,
        "releaseClass": "research" if research else "commercial",
        "productLifecycleState": "research" if research else "commercial",
        "containsUnverifiedAssets": research,
        "manifestDigest": manifest_digest,
        **predecessor_admission,
        "runId": "activate-001",
        "importRunId": "apply-001",
        "status": "completed",
        **evidence_fields,
        "homepageVerificationCasesRef": homepage_cases_ref,
        **overrides,
    }
    write_environment_result(import_run / "result.json", predecessor)
    observed["admission"] = admission

    def _write_report(**kwargs: object) -> Path:
        output = Path(str(kwargs["output_path"]))
        write_json(output, {"passed": True})
        return output

    def _require(**kwargs: object) -> None:
        observed.update(kwargs)

    def _write_result(path: Path, result: dict[str, Any]) -> None:
        write_environment_result(path, result)
        written = read_json(path)
        observed.setdefault("results", []).append(written)
        observed["result"] = written

    target = EnvironmentReleaseTarget(
        environment=DeploymentEnvironment.GAMMA,
        target_name="gamma-test",
        mode=EnvironmentReleaseMode.LOCAL_IMPORT,
        mongo_uri="mongodb://gamma.test",
        user_postgres_dsn="postgres://gamma.test/quwoquan",
        media_sync_root=root / "environment-media",
        media_delivery_base_url="https://gamma.test/media",
        api_base_url="https://gamma.test/api",
        missing_requirements=(),
        ssl_cafile="/test/gamma-local/root.crt",
        redis_addr="gamma.test:6379",
        redis_database=1,
    )

    def _create_run(
        env: str,
        release_id: str,
        run_id: str,
        **kwargs: object,
    ) -> Path:
        observed.setdefault("created_runs", []).append(run_id)
        return create_run(
            output_root=root,
            environment=env,
            release_id=release_id,
            run_id=run_id,
            kind=str(kwargs["kind"]),
            valid_environments=frozenset({"gamma"}),
        )

    return ShipOperationDependencies(
        output_root=root,
        admit_release=lambda _args: admission,
        release_requires_full_sync=lambda _path: True,
        release_has_posts=lambda _contract: True,
        create_run=_create_run,
        run_root=lambda env, release_id, run_id: (
            root / "env" / env / "runs/data-release" / release_id / run_id
        ),
        sync_media=lambda **_kwargs: None,
        write_applied_ref=lambda **_kwargs: None,
        assert_target_action_allowed=lambda **_kwargs: None,
        assert_environment_release_policy=lambda **_kwargs: None,
        resolve_environment_release_target=lambda _env: target,
        require_environment_readiness=_require,
        run_tag_importer=lambda **_kwargs: Path("unused"),
        run_creator_importer=lambda **_kwargs: Path("unused"),
        run_content_importer=lambda **_kwargs: None,
        run_homepage_importer=lambda **_kwargs: None,
        write_environment_coverage_receipt=lambda **_kwargs: Path("unused"),
        write_release_evidence=lambda **_kwargs: None,
        write_verification_result=_write_result,
        write_tag_consumer_verification=_write_report,
        write_homepage_verification_case_manifest=_write_report,
        write_baseline_api_verification=_write_report,
        write_post_api_verification=_write_report,
        write_homepage_api_verification=_write_report,
        write_research_isolation_verification=(write_research_isolation_verification),
        write_environment_release_readiness=_write_report,
        now_compact=lambda: "20260804T000000Z",
    )


def test_ship_verify__commercial_fails_closed_without_lifecycle_exit_ref(
    tmp_path: Path,
) -> None:
    observed: dict[str, Any] = {}
    dependencies = _dependencies(tmp_path, observed=observed)

    with pytest.raises(SystemExit, match="lifecycleExitRef is required"):
        verify_release_consumers(
            argparse.Namespace(
                env="gamma",
                import_run_id="activate-001",
                run_id="commercial-verify-missing-ref",
                readiness_phase="commercial",
                lifecycle_exit_ref="",
                release_admission=replace(
                    _ADMISSION,
                    release=tmp_path / "data/releases/release-a",
                    contract=read_json(
                        tmp_path / "data/releases/release-a/payload/desired_state.json"
                    ),
                    manifest_digest=payload_digest(
                        tmp_path / "data/releases/release-a"
                    ),
                ),
            ),
            dependencies=dependencies,
        )

    assert "phase" not in observed


def test_ship_verify__commercial_forwards_lifecycle_exit_ref(
    tmp_path: Path,
) -> None:
    observed: dict[str, Any] = {}
    dependencies = _dependencies(tmp_path, observed=observed)
    release = tmp_path / "data/releases/release-a"

    verify_release_consumers(
        argparse.Namespace(
            env="gamma",
            import_run_id="activate-001",
            run_id="commercial-verify-with-ref",
            readiness_phase="commercial",
            lifecycle_exit_ref=_LIFECYCLE_EXIT_REF,
            release_admission=replace(
                _ADMISSION,
                release=tmp_path / "data/releases/release-a",
                contract=read_json(
                    tmp_path / "data/releases/release-a/payload/desired_state.json"
                ),
                manifest_digest=payload_digest(tmp_path / "data/releases/release-a"),
            ),
        ),
        dependencies=dependencies,
    )

    assert observed["environment"] is DeploymentEnvironment.GAMMA
    assert observed["phase"] is ShipReadinessPhase.COMMERCIAL
    assert observed["lifecycle_exit_ref"] == _LIFECYCLE_EXIT_REF
    assert observed["release_id"] == "release-a"
    assert observed["verify_run_id"] == "commercial-verify-with-ref"
    assert observed["manifest_digest"] == payload_digest(release)
    result = observed["result"]
    assert result["lifecycleExitRef"] == _LIFECYCLE_EXIT_REF
    assert result["readinessPhase"] == "commercial"
    assert result["status"] == "completed"
    assert result["handoffArtifactRef"].endswith("/producer_release_handoff.json")
    assert result["handoffArtifactDigest"].startswith("sha256:")


def test_ship_verify__research_writes_typed_isolation_blocker_before_post_api(
    tmp_path: Path,
) -> None:
    observed: dict[str, Any] = {}
    dependencies = _dependencies(
        tmp_path,
        observed=observed,
        research=True,
    )
    original_writer = dependencies.write_research_isolation_verification

    def _write_isolation(**kwargs: object) -> Path:
        observed["runtime_proof_path"] = kwargs.get("runtime_proof_path")
        return original_writer(**kwargs)

    dependencies = replace(
        dependencies,
        write_research_isolation_verification=_write_isolation,
    )

    with pytest.raises(
        SystemExit,
        match="DATA.RESEARCH.RUNTIME_PROOF_INCOMPLETE",
    ):
        verify_release_consumers(
            argparse.Namespace(
                env="gamma",
                import_run_id="activate-001",
                run_id="research-verify-a",
                readiness_phase="research",
                lifecycle_exit_ref="",
                release_admission=replace(
                    _ADMISSION,
                    release=tmp_path / "data/releases/release-a",
                    contract=read_json(
                        tmp_path / "data/releases/release-a/payload/desired_state.json"
                    ),
                    manifest_digest=payload_digest(
                        tmp_path / "data/releases/release-a"
                    ),
                ),
            ),
            dependencies=dependencies,
        )

    result = observed["result"]
    assert result["status"] == "failed"
    assert result["handoffArtifactRef"].endswith("/producer_release_handoff.json")
    assert result["handoffArtifactDigest"].startswith("sha256:")
    assert result["failedStage"] == "research_isolation_verification"
    ref = result["researchIsolationVerificationRef"]
    receipt = read_json(tmp_path / ref)
    assert receipt["outcome"] == "GATE_BLOCK"
    assert receipt["blocker"]["code"] == "DATA.RESEARCH.RUNTIME_PROOF_INCOMPLETE"
    assert observed["runtime_proof_path"] == (
        tmp_path / "env/gamma/runs/data-release/release-a/research-verify-a/"
        "research-isolation-runtime-proof.json"
    )


_PREDECESSOR_DRIFT_CASES = [
    ("environment", {"environment": "alpha"}),
    ("runId", {"runId": "apply-other"}),
    ("releaseId", {"releaseId": "release-other"}),
    ("manifestDigest", {"manifestDigest": "sha256:" + "9" * 64}),
    (
        "admissionKind",
        {
            "admissionKind": "empty_baseline_attestation",
            "admissionKind": "empty_baseline_attestation",
            "systemAttestationRef": "data/releases/release-a/attestations/release.json",
            "systemAttestationDigest": "sha256:" + "7" * 64,
        },
    ),
    (
        "handoffArtifactRef",
        {
            "handoffArtifactRef": ".qwq_output/data/releases/release-other/producer_release_handoff.json"
        },
    ),
    ("handoffArtifactDigest", {"handoffArtifactDigest": "sha256:" + "8" * 64}),
]


@pytest.mark.parametrize(("field", "overrides"), _PREDECESSOR_DRIFT_CASES)
def test_ship_verify__rejects_import_predecessor_identity_drift_before_consumer(
    tmp_path: Path,
    field: str,
    overrides: dict[str, Any],
) -> None:
    observed: dict[str, Any] = {}
    dependencies = _dependencies(
        tmp_path,
        observed=observed,
        predecessor_overrides=overrides,
    )

    with pytest.raises(SystemExit, match=field):
        verify_release_consumers(
            argparse.Namespace(
                env="gamma",
                import_run_id="activate-001",
                run_id="verify-predecessor-drift",
                readiness_phase="consumer",
                lifecycle_exit_ref="",
                release_admission=observed["admission"],
            ),
            dependencies=dependencies,
        )

    assert observed.get("created_runs") is None
    assert observed.get("results") is None


def test_ship_verify__rejects_revision_chain_drift_before_consumer(
    tmp_path: Path,
) -> None:
    observed: dict[str, Any] = {}
    dependencies = _dependencies(tmp_path, observed=observed)
    activation_path = (
        tmp_path
        / "env/gamma/runs/data-release/release-a/activate-001/content-activation-receipt.json"
    )
    activation = read_json(activation_path)
    activation["expectedActive"] = {
        "found": True,
        "sourceOwner": "qwq_data",
        "releaseId": "release-old",
        "manifestDigest": "sha256:" + "7" * 64,
        "revision": 7,
    }
    write_json(activation_path, activation)
    predecessor_path = (
        tmp_path / "env/gamma/runs/data-release/release-a/activate-001/result.json"
    )
    predecessor = read_json(predecessor_path)
    predecessor["contentActivationReceiptDigest"] = (
        "sha256:" + __import__("hashlib").sha256(activation_path.read_bytes()).hexdigest()
    )
    write_environment_result(
        predecessor_path.with_name("rewritten-result.json"),
        predecessor,
    )
    predecessor_path.unlink()
    predecessor_path.with_name("rewritten-result.json").replace(predecessor_path)

    with pytest.raises(SystemExit, match="revision-bearing evidence chain"):
        verify_release_consumers(
            argparse.Namespace(
                env="gamma",
                import_run_id="activate-001",
                run_id="verify-revision-drift",
                readiness_phase="consumer",
                lifecycle_exit_ref="",
                release_admission=observed["admission"],
            ),
            dependencies=dependencies,
        )

    assert observed.get("created_runs") is None


def test_ship_verify__rejects_import_predecessor_checksum_drift_before_consumer(
    tmp_path: Path,
) -> None:
    observed: dict[str, Any] = {}
    dependencies = _dependencies(tmp_path, observed=observed)
    predecessor_path = (
        tmp_path / "env/gamma/runs/data-release/release-a/activate-001/result.json"
    )
    predecessor = read_json(predecessor_path)
    predecessor["manifestDigest"] = "sha256:" + "9" * 64
    write_json(predecessor_path, predecessor)

    with pytest.raises(SystemExit, match="verificationChecksum drift"):
        verify_release_consumers(
            argparse.Namespace(
                env="gamma",
                import_run_id="activate-001",
                run_id="verify-checksum-drift",
                readiness_phase="consumer",
                lifecycle_exit_ref="",
                release_admission=observed["admission"],
            ),
            dependencies=dependencies,
        )

    assert observed.get("created_runs") is None


@pytest.mark.parametrize(
    "import_run_id", ["../activate-001", "nested/activate-001", "activate\\001"]
)
def test_ship_verify__rejects_unsafe_import_run_id_before_consumer(
    tmp_path: Path,
    import_run_id: str,
) -> None:
    observed: dict[str, Any] = {}
    dependencies = _dependencies(tmp_path, observed=observed)

    with pytest.raises(SystemExit, match="单一安全路径段"):
        verify_release_consumers(
            argparse.Namespace(
                env="gamma",
                import_run_id=import_run_id,
                run_id="verify-unsafe-import-run",
                readiness_phase="consumer",
                lifecycle_exit_ref="",
                release_admission=observed["admission"],
            ),
            dependencies=dependencies,
        )

    assert observed.get("created_runs") is None
    assert observed.get("results") is None


def _verify_args(
    admission: ReleaseAdmission, *, run_id: str, **overrides: Any
) -> argparse.Namespace:
    values: dict[str, Any] = {
        "env": "gamma",
        "import_run_id": "activate-001",
        "run_id": run_id,
        "readiness_phase": "consumer",
        "lifecycle_exit_ref": "",
        "previous_environment_readiness": "",
        "release_admission": admission,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.mark.parametrize(
    ("case", "expected_stage", "message"),
    [
        ("invalid_phase", "readiness_phase", "readiness-phase"),
        ("missing_lifecycle", "lifecycle_exit_ref", "lifecycleExitRef is required"),
        ("missing_homepage", "homepage_verification_cases", "cases missing"),
        ("drifted_homepage", "homepage_verification_cases", "does not bind"),
        (
            "unsafe_previous_readiness",
            "previous_environment_readiness",
            "safe output-relative ref",
        ),
    ],
)
def test_ship_verify__post_create_direct_failures_write_one_typed_result(
    tmp_path: Path,
    case: str,
    expected_stage: str,
    message: str,
) -> None:
    observed: dict[str, Any] = {}
    dependencies = _dependencies(tmp_path, observed=observed)
    args = _verify_args(observed["admission"], run_id=f"verify-{case}")
    if case == "invalid_phase":
        args.readiness_phase = "invalid"
    elif case == "missing_lifecycle":
        args.readiness_phase = "commercial"
    elif case == "missing_homepage":
        (
            tmp_path / "env/gamma/runs/data-release/release-a/apply-001/"
            "homepage_verification_cases.json"
        ).unlink()
    elif case == "drifted_homepage":
        observed = {}
        dependencies = _dependencies(
            tmp_path / "drifted",
            observed=observed,
            homepage_cases_ref=(
                "env/gamma/runs/data-release/release-a/apply-001/other-cases.json"
            ),
        )
        args = _verify_args(observed["admission"], run_id=f"verify-{case}")
    elif case == "unsafe_previous_readiness":
        dependencies = replace(
            dependencies,
            release_has_posts=lambda _contract: True,
        )
        args.previous_environment_readiness = "../outside.json"

    with pytest.raises(SystemExit, match=message):
        verify_release_consumers(args, dependencies=dependencies)

    assert len(observed["results"]) == 1
    result = observed["results"][0]
    assert result["status"] == "failed"
    assert result["failedStage"] == expected_stage
    assert result["error"]


def test_ship_verify__empty_baseline_positive_case_drift_writes_failed_result(
    tmp_path: Path,
) -> None:
    observed: dict[str, Any] = {}
    dependencies = _dependencies(
        tmp_path,
        observed=observed,
        release_kind=ReleaseKind.EMPTY_BASELINE,
        homepage_cases_ref=(
            "env/gamma/runs/data-release/release-a/apply-001/"
            "homepage_verification_cases.json"
        ),
    )

    with pytest.raises(SystemExit, match="must not bind positive homepage cases"):
        verify_release_consumers(
            _verify_args(observed["admission"], run_id="verify-empty-drift"),
            dependencies=dependencies,
        )

    assert len(observed["results"]) == 1
    assert observed["result"]["status"] == "failed"
    assert observed["result"]["failedStage"] == "empty_baseline_import_binding"


def test_ship_verify__failed_receipt_error_does_not_replace_operation_error(
    tmp_path: Path,
) -> None:
    observed: dict[str, Any] = {}
    dependencies = _dependencies(tmp_path, observed=observed)

    def _fail_result(_path: Path, _result: dict[str, Any]) -> None:
        raise OSError("receipt sink unavailable")

    dependencies = replace(dependencies, write_verification_result=_fail_result)
    with pytest.raises(SystemExit, match="readiness-phase") as exc:
        verify_release_consumers(
            _verify_args(
                observed["admission"],
                run_id="verify-receipt-write-failure",
                readiness_phase="invalid",
            ),
            dependencies=dependencies,
        )

    assert any("receipt sink unavailable" in note for note in exc.value.__notes__)


def test_ship_verify__tag_failure_writes_redacted_bounded_result(
    tmp_path: Path,
) -> None:
    observed: dict[str, Any] = {}
    dependencies = _dependencies(tmp_path, observed=observed)
    secret = "top-secret-password"
    dependencies = replace(
        dependencies,
        write_tag_consumer_verification=lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError(f"tag unavailable password={secret} " + "x" * 2000)
        ),
    )

    with pytest.raises(SystemExit, match="tag consumer verification failed"):
        verify_release_consumers(
            _verify_args(observed["admission"], run_id="verify-tag-failure"),
            dependencies=dependencies,
        )

    assert len(observed["results"]) == 1
    result = observed["result"]
    assert result["failedStage"] == "tag_consumer_verification"
    assert secret not in result["error"]
    assert "[REDACTED]" in result["error"]
    assert len(result["error"]) <= 1024
