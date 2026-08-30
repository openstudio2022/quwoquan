"""Immutable release lifecycle is anchored by one aggregate attestation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.baseline_release import build_empty_baseline_release
from core.release_layout import payload_digest
from core.source_digest import (
    content_source_revision,
    current_source_definition_snapshot,
)
from verify import verify_release_lifecycle as lifecycle

RELEASE_ID = "20260715--travel-homepage-coverage--test-release-a--003"
EXECUTION_IDS = [
    "20260715--travel-homepage-coverage--test-region-b--pilot-007",
    "20260715--travel-homepage-coverage--test-region-a--pilot-004",
]
ENTITY_CATALOG_DIGEST = "sha256:" + "e" * 64


def _content_identity(source_digest: dict[str, object]) -> dict[str, object]:
    digest = str(source_digest["digest"])
    return {
        "sourceRevision": content_source_revision(
            source_digest=digest,
            entity_catalog_digest=ENTITY_CATALOG_DIGEST,
        ),
        "sourceDigest": digest,
        "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
    }


def _research_lifecycle() -> dict[str, object]:
    return {
        "releaseClass": "research",
        "productLifecycleState": "research",
        "containsUnverifiedAssets": False,
        "rightsStatusCounts": {
            "verified": 1,
            "unverified": 0,
            "restricted": 0,
            "unknown": 0,
        },
        "authorizationRequiredAssetIds": [],
        "researchAcceptedCount": 1,
        "commercialAcceptedCount": 0,
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _fixture(tmp_path: Path) -> Path:
    release = tmp_path / RELEASE_ID
    source_digest = current_source_definition_snapshot().to_document()
    _write_json(
        release / "payload/release.json",
        {
            "schema": "quwoquan_data.release",
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "releaseKind": "content",
            **_research_lifecycle(),
            "canonicalMerkle": "sha256:" + "a" * 64,
            "executionIds": EXECUTION_IDS,
            **_content_identity(source_digest),
            "sourceDigests": [source_digest],
        },
    )
    _write_json(
        release / "payload/desired_state.json",
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": RELEASE_ID,
            "desiredRefs": {
                "creators": [],
                "entities": ["地点/景区/测试实体甲"],
                "posts": [],
                "tags": ["Topic/旅行"],
            },
        },
    )
    _write_json(
        release / "attestations/release.json",
        {
            "schema": "quwoquan_data.release_attestation",
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "releaseKind": "content",
            **_research_lifecycle(),
            "executionIds": EXECUTION_IDS,
            "entityCount": 1,
            "postCount": 0,
            "creatorCount": 0,
            "tagCount": 1,
            "canonicalMerkle": "sha256:" + "a" * 64,
            **_content_identity(source_digest),
            "sourceDigests": [source_digest],
            "payloadSha256": payload_digest(release),
            "recordedAt": "2026-07-15T00:00:00Z",
        },
    )
    return release


def _rewrite_with_frozen_source_digest(release: Path) -> None:
    header_path = release / "payload/release.json"
    attestation_path = release / "attestations/release.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    source_digest = dict(header["sourceDigests"][0])
    source_digest["inputs"] = ["quwoquan_data/historical/pre-contract-source"]
    for document in (header, attestation):
        document["sourceDigests"] = [source_digest]
    _write_json(header_path, header)
    attestation["payloadSha256"] = payload_digest(release)
    _write_json(attestation_path, attestation)


def _environment_fixture(
    root: Path,
    *,
    manifest_digest: str,
    environment: str,
    import_run_id: str,
    verify_run_id: str | None,
    status: str,
    kind: str = "apply",
    rollback_from: str = "",
) -> None:
    run = root / "env" / environment / "runs/data-release" / RELEASE_ID / import_run_id
    dry_run = status == "dry_run"
    # Tag/creator projections and the content import report spell the same
    # applied state with different literals, so each receipt takes the value its
    # own schema admits.
    receipt_status = "dry-run" if dry_run else "active"
    content_receipt_status = "dry-run" if dry_run else "imported"
    _write_json(
        run / "run.json",
        {
            "schema": "quwoquan_data.environment_release_run",
            "environment": environment,
            "releaseId": RELEASE_ID,
            "runId": import_run_id,
            "kind": kind,
            "startedAt": "2026-07-28T00:00:00Z",
        },
    )
    result = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": environment,
        "releaseId": RELEASE_ID,
        "runId": import_run_id,
        "status": status,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "containsUnverifiedAssets": False,
        "manifestDigest": manifest_digest,
        "homepageVerificationCasesRef": "",
        "tagImportReportRef": f"{run.relative_to(root).as_posix()}/tag-import.json",
        "creatorImportReportRef": f"{run.relative_to(root).as_posix()}/creator-import.json",
        "contentImportReportRef": f"{run.relative_to(root).as_posix()}/import.json",
        "homepageImportReportRef": f"{run.relative_to(root).as_posix()}/homepage-import.json",
    }
    if status == "prepared":
        for field in tuple(result):
            if field.endswith("ImportReportRef"):
                result[field] = ""
    _write_json(run / "result.json", result)
    if kind == "rollback":
        _write_json(
            run / "rollback_ref.json",
            {
                "schema": "quwoquan_data.rollback_release_ref",
                "rollbackTo": RELEASE_ID,
                "rollbackFromReleaseId": rollback_from,
                "releaseRef": f"data/releases/{RELEASE_ID}",
            },
        )
    if status == "prepared":
        return
    _write_json(
        run / "tag-import.json",
        {
            "schema": "quwoquan.tag_import_report",
            "status": receipt_status,
            "environment": environment,
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "canonicalDigest": "a" * 64,
            "releaseKind": "content",
            "previousReleaseId": rollback_from,
            "nodeCount": 1,
            "tagRefs": ["Topic/旅行"],
            "generatedAt": "2026-07-28T00:00:00Z",
        },
    )
    _write_json(
        run / "creator-import.json",
        {
            "schema": "quwoquan.user_creator_import_report",
            "status": receipt_status,
            "environment": environment,
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "mode": "sync",
            "projectionDatabase": "quwoquan_user",
            "counts": {
                "creatorsLoaded": 0,
                "usersUpserted": 0,
                "creatorsUpserted": 0,
                "usersRemoved": 0,
                "creatorsRemoved": 0,
            },
            "authorIds": [],
            "verifiedCreatorIds": [],
            "generatedAt": "2026-07-28T00:00:00Z",
        },
    )
    _write_json(
        run / "import.json",
        {
            "schema": "quwoquan.content_import_report",
            "status": content_receipt_status,
            "environment": environment,
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "manifestDigest": manifest_digest,
            "mode": "sync",
            "deletePolicy": "tombstone",
            "counts": {"postsLoaded": 0, "entitiesLoaded": 1},
            "postBindings": [],
            "auditEvents": [],
        },
    )
    _write_json(
        run / "homepage-import.json",
        {
            "schema": "quwoquan_service.homepage_import_report",
            "releaseId": RELEASE_ID,
            "env": environment,
            "dryRun": dry_run,
            "mode": "sync",
            "sourceOwner": "qwq_data",
            "projected": 1,
            "created": [],
            "updated": [],
            "offlined": [],
            "skipped": [],
            "entityRefToHomepageId": {"地点/景区/测试实体甲": "homepage-a"},
            "issues": [],
            "finishedAt": "2026-07-28T00:00:00Z",
        },
    )
    if status == "completed":
        _write_json(
            run / "applied_ref.json",
            {
                "schema": "quwoquan_data.applied_release_ref",
                "environment": environment,
                "releaseId": RELEASE_ID,
                "releaseRef": f"data/releases/{RELEASE_ID}",
                "evidenceRef": run.relative_to(root).as_posix(),
            },
        )
    if not verify_run_id:
        return
    verify = run.parent / verify_run_id
    _write_json(
        verify / "run.json",
        {
            "schema": "quwoquan_data.environment_release_run",
            "environment": environment,
            "releaseId": RELEASE_ID,
            "runId": verify_run_id,
            "kind": "verify",
            "startedAt": "2026-07-28T00:10:00Z",
        },
    )
    homepage_ref = (
        f"{verify.relative_to(root).as_posix()}/homepage-api-verification.json"
    )
    _write_json(
        verify / "result.json",
        {
            "schema": "quwoquan_data.environment_release_result",
            "environment": environment,
            "releaseId": RELEASE_ID,
            "runId": verify_run_id,
            "importRunId": import_run_id,
            "status": "completed",
            "releaseClass": "research",
            "productLifecycleState": "research",
            "containsUnverifiedAssets": False,
            "manifestDigest": manifest_digest,
            "homepageApiVerificationRef": homepage_ref,
        },
    )
    _write_json(
        verify / "homepage-api-verification.json",
        {
            "schema": "quwoquan_data.homepage_api_verification",
            "environment": environment,
            "releaseId": RELEASE_ID,
            "runId": verify_run_id,
            "sourceCasesRef": (
                f"env/{environment}/runs/data-release/{RELEASE_ID}/"
                f"{import_run_id}/homepage_verification_cases.json"
            ),
            "apiBaseUrl": f"https://{environment}.example.test",
            "verifiedAt": "2026-07-28T00:11:00Z",
            "passed": True,
            "entities": [
                {
                    "entityRef": "地点/景区/测试实体甲",
                    "homepageId": "homepage-a",
                    "title": "测试实体甲",
                    "detailStatus": 200,
                    "introductionStatus": 200,
                    "coverUrl": "https://media.example.test/cover.jpg",
                    "sectionCount": 1,
                }
            ],
            "issues": [],
        },
    )


def test_release_lifecycle__accepts_schema_bound_aggregate_attestation__local_contract(
    monkeypatch, tmp_path: Path
) -> None:
    _fixture(tmp_path)
    monkeypatch.setattr(lifecycle, "RELEASE_ROOT", tmp_path)

    assert lifecycle.release_lifecycle_issues(RELEASE_ID) == []


def test_release_lifecycle__rejects_frozen_source_digest__local_contract(
    monkeypatch, tmp_path: Path
) -> None:
    release = _fixture(tmp_path)
    _rewrite_with_frozen_source_digest(release)
    monkeypatch.setattr(lifecycle, "RELEASE_ROOT", tmp_path)

    issues = lifecycle.release_lifecycle_issues(RELEASE_ID)

    assert any("$.sourceDigests[0].inputs" in issue for issue in issues)


def test_release_lifecycle__rejects_attestation_payload_drift__local_contract(
    monkeypatch, tmp_path: Path
) -> None:
    release = _fixture(tmp_path)
    monkeypatch.setattr(lifecycle, "RELEASE_ROOT", tmp_path)
    path = release / "attestations/release.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["payloadSha256"] = "sha256:" + "0" * 64
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    assert lifecycle.release_lifecycle_issues(RELEASE_ID) == [
        f"{path}: payloadSha256 drift from immutable payload"
    ]


def test_release_lifecycle__accepts_create_once_empty_baseline__local_contract(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    publish_root.mkdir()
    release_root = tmp_path / "releases"
    baseline_id = "20260715--travel-homepage-coverage--test-baseline-a--001"

    created = build_empty_baseline_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=baseline_id,
        release_class="research",
    )
    repeated = build_empty_baseline_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=baseline_id,
        release_class="research",
    )

    assert created["releaseKind"] == "empty_baseline"
    assert created["idempotent"] is False
    assert repeated["idempotent"] is True
    assert json.loads(
        (release_root / baseline_id / "payload/release.json").read_text(
            encoding="utf-8"
        )
    )["sourceOwner"] == "qwq_data"
    assert (
        lifecycle.release_lifecycle_issues(baseline_id, release_root=release_root) == []
    )

    desired = json.loads(
        (release_root / baseline_id / "payload/desired_state.json").read_text(
            encoding="utf-8"
        )
    )
    assert desired["desiredRefs"] == {
        "creators": [],
        "entities": [],
        "posts": [],
        "tags": [],
    }


def test_environment_lifecycle__consumes_real_import_and_api_evidence__local_contract(
    tmp_path: Path,
) -> None:
    releases = tmp_path / "releases"
    _fixture(releases)
    output = tmp_path / "output"
    _environment_fixture(
        output,
        manifest_digest=payload_digest(releases / RELEASE_ID),
        environment="alpha",
        import_run_id="apply-001",
        verify_run_id="verify-001",
        status="completed",
    )
    assert (
        lifecycle.environment_lifecycle_issues(
            RELEASE_ID,
            environment="alpha",
            import_run_id="apply-001",
            verify_run_id="verify-001",
            release_root=releases,
            output_root=output,
        )
        == []
    )


def test_environment_lifecycle__rejects_import_manifest_digest_drift__local_contract(
    tmp_path: Path,
) -> None:
    releases = tmp_path / "releases"
    _fixture(releases)
    output = tmp_path / "output"
    _environment_fixture(
        output,
        manifest_digest=payload_digest(releases / RELEASE_ID),
        environment="alpha",
        import_run_id="apply-001",
        verify_run_id="verify-001",
        status="completed",
    )
    report_path = (
        output
        / "env/alpha/runs/data-release"
        / RELEASE_ID
        / "apply-001/import.json"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["manifestDigest"] = "sha256:" + "0" * 64
    _write_json(report_path, report)

    issues = lifecycle.environment_lifecycle_issues(
        RELEASE_ID,
        environment="alpha",
        import_run_id="apply-001",
        verify_run_id="verify-001",
        release_root=releases,
        output_root=output,
    )

    assert issues == [
        f"{report_path}: manifestDigest drift from immutable payload"
    ]


def test_environment_lifecycle__supports_prod_prepared_and_dry_run_without_activation(
    tmp_path: Path,
) -> None:
    releases = tmp_path / "releases"
    _fixture(releases)
    output = tmp_path / "output"
    _environment_fixture(
        output,
        manifest_digest=payload_digest(releases / RELEASE_ID),
        environment="prod",
        import_run_id="dry-run-001",
        verify_run_id=None,
        status="dry_run",
    )

    assert (
        lifecycle.environment_lifecycle_issues(
            RELEASE_ID,
            environment="prod",
            import_run_id=None,
            prod_mode="prepared",
            release_root=releases,
            output_root=output,
        )
        == []
    )
    assert (
        lifecycle.environment_lifecycle_issues(
            RELEASE_ID,
            environment="prod",
            import_run_id="dry-run-001",
            prod_mode="dry-run",
            release_root=releases,
            output_root=output,
        )
        == []
    )


def test_environment_lifecycle__binds_rollback_source_and_replay__local_contract(
    tmp_path: Path,
) -> None:
    releases = tmp_path / "releases"
    _fixture(releases)
    output = tmp_path / "output"
    _environment_fixture(
        output,
        manifest_digest=payload_digest(releases / RELEASE_ID),
        environment="gamma",
        import_run_id="rollback-001",
        verify_run_id="verify-replay-001",
        status="completed",
        kind="rollback",
        rollback_from="baseline-001",
    )

    assert (
        lifecycle.environment_lifecycle_issues(
            RELEASE_ID,
            environment="gamma",
            import_run_id="rollback-001",
            verify_run_id="verify-replay-001",
            rollback_from_release_id="baseline-001",
            release_root=releases,
            output_root=output,
        )
        == []
    )
