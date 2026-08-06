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

from content.release.environment._ship_consumer_verification import (  # noqa: E402
    verify_release_consumers,
)
from content.release.environment._ship_operation_dependencies import (  # noqa: E402
    ShipOperationDependencies,
)
from content.release.environment.readiness import ShipReadinessPhase  # noqa: E402
from content.release.environment.release_contract import (  # noqa: E402
    build_release_contract,
)
from content.release.environment.research_isolation_verification import (  # noqa: E402
    write_research_isolation_verification,
)
from content.release.environment.topology import (  # noqa: E402
    resolve_environment_release_target,
)
from content.release.model import DeploymentEnvironment, ReleaseKind  # noqa: E402
from core.io import read_json, write_json  # noqa: E402
from core.release_layout import payload_digest  # noqa: E402
from core.source_digest import SourceDigest, content_source_revision  # noqa: E402

_LIFECYCLE_EXIT_REF = (
    "env/gamma/runs/release-lifecycle-exit/"
    "release-a/exit-001/lifecycle-exit.json"
)
_SOURCE_DIGEST = "sha256:" + "b" * 64
_ENTITY_CATALOG_DIGEST = "sha256:" + "c" * 64
_SOURCE_REVISION = content_source_revision(
    source_digest=_SOURCE_DIGEST,
    entity_catalog_digest=_ENTITY_CATALOG_DIGEST,
)
_SOURCE_DIGEST_DOCUMENT = SourceDigest(_SOURCE_DIGEST).to_document()


def _release(root: Path, *, research: bool = False) -> Path:
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
            "releaseKind": ReleaseKind.CONTENT,
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
            "authorizationRequiredAssetIds": (
                ["research-asset-a"] if research else []
            ),
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
) -> ShipOperationDependencies:
    release = _release(root, research=research)
    contract = build_release_contract(
        release_id="release-a",
        post_refs=[],
        entity_refs=[],
    )
    import_run = root / "env/gamma/runs/data-release/release-a/apply-001"
    cases = import_run / "homepage_verification_cases.json"
    write_json(cases, {"environment": "gamma"})
    write_json(
        import_run / "result.json",
        {
            "environment": "gamma",
            "releaseId": "release-a",
            "status": "completed",
            "homepageVerificationCasesRef": cases.relative_to(root).as_posix(),
        },
    )

    def _write_report(**kwargs: object) -> Path:
        output = Path(str(kwargs["output_path"]))
        write_json(output, {"passed": True})
        return output

    def _require(**kwargs: object) -> None:
        observed.update(kwargs)

    def _write_result(path: Path, result: dict[str, Any]) -> None:
        write_json(path, result)
        observed["result"] = result

    target = replace(
        resolve_environment_release_target("gamma"),
        api_base_url="https://gamma.test/api",
        media_delivery_base_url="https://gamma.test/media",
        missing_requirements=(),
    )

    def _create_run(
        env: str,
        release_id: str,
        run_id: str,
        **_kwargs: object,
    ) -> Path:
        path = root / "env" / env / "runs/data-release" / release_id / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    return ShipOperationDependencies(
        output_root=root,
        load_release=lambda _release_id: (release, contract),
        release_requires_full_sync=lambda _path: True,
        release_has_posts=lambda _contract: True,
        create_run=_create_run,
        run_root=lambda env, release_id, run_id: (
            root / "env" / env / "runs/data-release" / release_id / run_id
        ),
        sync_media=lambda **_kwargs: None,
        write_applied_ref=lambda **_kwargs: None,
        assert_target_action_allowed=lambda **_kwargs: None,
        resolve_environment_release_target=lambda _env: target,
        require_environment_readiness=_require,
        run_tag_importer=lambda **_kwargs: Path("unused"),
        run_creator_importer=lambda **_kwargs: Path("unused"),
        run_content_importer=lambda **_kwargs: None,
        run_homepage_importer=lambda **_kwargs: None,
        write_release_evidence=lambda **_kwargs: None,
        write_verification_result=_write_result,
        write_tag_consumer_verification=_write_report,
        write_homepage_verification_case_manifest=_write_report,
        write_baseline_api_verification=_write_report,
        write_post_api_verification=_write_report,
        write_homepage_api_verification=_write_report,
        write_research_isolation_verification=(
            write_research_isolation_verification
        ),
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
                release_id="release-a",
                env="gamma",
                import_run_id="apply-001",
                run_id="commercial-verify-missing-ref",
                readiness_phase="commercial",
                lifecycle_exit_ref="",
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
            release_id="release-a",
            env="gamma",
            import_run_id="apply-001",
            run_id="commercial-verify-with-ref",
            readiness_phase="commercial",
            lifecycle_exit_ref=_LIFECYCLE_EXIT_REF,
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


def test_ship_verify__research_writes_typed_isolation_blocker_before_post_api(
    tmp_path: Path,
) -> None:
    observed: dict[str, Any] = {}
    dependencies = _dependencies(
        tmp_path,
        observed=observed,
        research=True,
    )

    with pytest.raises(
        SystemExit,
        match="DATA.RESEARCH.IDENTITY_ADAPTER_UNAVAILABLE",
    ):
        verify_release_consumers(
            argparse.Namespace(
                release_id="release-a",
                env="gamma",
                import_run_id="apply-001",
                run_id="research-verify-a",
                readiness_phase="research",
                lifecycle_exit_ref="",
            ),
            dependencies=dependencies,
        )

    result = observed["result"]
    assert result["status"] == "failed"
    assert result["failedStage"] == "research_isolation_verification"
    ref = result["researchIsolationVerificationRef"]
    receipt = read_json(tmp_path / ref)
    assert receipt["outcome"] == "GATE_BLOCK"
    assert (
        receipt["blocker"]["code"]
        == "DATA.RESEARCH.IDENTITY_ADAPTER_UNAVAILABLE"
    )
