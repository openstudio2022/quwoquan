"""Strict stackctl content-api-consumer authority and 4×4 evidence tests.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/
multi-carrier-release/spec.md#gwt-034
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from quwoquan_ops.cli.lib import content_api_consumer as subject
from quwoquan_ops.cli.lib import environment_acceptance_fact as acceptance
from quwoquan_ops.cli.lib.readiness_case_result import validate_readiness_case_result

RELEASE_ID = "release-m1"
IMPORT_RUN_ID = "import-m1"
VERIFY_RUN_ID = "verify-m1"
RELEASE_DIGEST = "sha256:" + "1" * 64
MANIFEST_DIGEST = "sha256:" + "2" * 64
SOURCE_SHA = "a" * 40
SPEC_REF = subject.SPEC_REF
BEARER_FIXTURE = "research-bearer-fixture-never-persist"
ATTESTATION = "research-attestation-fixture-never-persist"


def _write(root: Path, ref: str, value: Mapping[str, Any]) -> tuple[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
        encoding="utf-8",
    )
    return ref, subject._digest_bytes(path.read_bytes())


def _authorities(root: Path) -> dict[str, str]:
    samples = [
        {
            "sampleId": f"baseline-{carrier}-001",
            "carrier": carrier,
            "objectId": (
                "/entity/travel/place/dali"
                if carrier == "homepage"
                else f"content-{carrier}"
            ),
            "objectRef": (
                "objects/entities/travel/place/dali"
                if carrier == "homepage"
                else f"objects/posts/{carrier}/m1-{carrier}"
            ),
            "objectDigest": "sha256:" + str(index) * 64,
        }
        for index, carrier in enumerate(subject.CARRIERS, 3)
    ]
    plan = {
        "schema": "quwoquan_data.release_uat_sample_plan",
        "releaseId": RELEASE_ID,
        "releaseDigest": RELEASE_DIGEST,
        "milestone": None,
        "selectionEvidence": {},
        "eligiblePopulationCounts": dict.fromkeys(subject.CARRIERS, 1),
        "exactCohortCounts": dict.fromkeys(subject.CARRIERS, 1),
        "entryCarrierCells": [
            {
                "entry": entry,
                "carrier": carrier,
                "applicability": "required",
                "specRef": SPEC_REF,
                "runnerClass": f"qwq.content_consumer.{entry}.{carrier}.v1",
            }
            for entry in subject.ENTRY_SURFACES
            for carrier in subject.CARRIERS
        ],
        "sampleStrategy": {},
        "sampleCount": 4,
        "samples": samples,
    }
    sample_ref, sample_digest = _write(
        root, f"data/releases/{RELEASE_ID}/payload/uat/sample_plan.json", plan
    )

    import_prefix = f"env/alpha/runs/data-release/{RELEASE_ID}/{IMPORT_RUN_ID}"
    cases = {
        "schema": "quwoquan_data.homepage_verification_case_manifest",
        "environment": "alpha",
        "releaseId": RELEASE_ID,
        "runId": IMPORT_RUN_ID,
        "importerReportRef": f"{import_prefix}/homepage-import.json",
        "generatedAt": "2026-09-03T01:00:00Z",
        "cases": [
            {
                "entityRef": "/entity/travel/place/dali",
                "homepageId": "homepage-runtime-dali",
                "title": "大理",
            }
        ],
    }
    _write(root, f"{import_prefix}/homepage_verification_cases.json", cases)
    post_bindings = [
        {
            "contentId": f"content-{carrier}",
            "postRef": f"{carrier}/m1-{carrier}",
            "postId": f"post-runtime-{carrier}",
            "contentVersion": 1,
            "usageScope": "research",
            "contentType": carrier,
            "authorId": "author-m1",
        }
        for carrier in ("article", "image", "video")
    ]
    import_report = {
        "schema": "quwoquan.content_import_report",
        "status": "imported",
        "environment": "alpha",
        "releaseId": RELEASE_ID,
        "sourceOwner": "qwq_data",
        "manifestDigest": MANIFEST_DIGEST,
        "mode": "upsert",
        "deletePolicy": "none",
        "counts": {"postsLoaded": 3, "entitiesLoaded": 1},
        "postBindings": post_bindings,
        "auditEvents": [],
    }
    import_ref, _ = _write(root, f"{import_prefix}/import.json", import_report)

    verify_prefix = f"env/alpha/runs/data-release/{RELEASE_ID}/{VERIFY_RUN_ID}"
    homepage = {
        "schema": "quwoquan_data.homepage_api_verification",
        "environment": "alpha",
        "releaseId": RELEASE_ID,
        "runId": VERIFY_RUN_ID,
        "sourceCasesRef": f"{import_prefix}/homepage_verification_cases.json",
        "apiBaseUrl": "https://api.alpha.quwoquan.com",
        "verifiedAt": "2026-09-03T01:01:00Z",
        "passed": True,
        "entities": [
            {
                "entityRef": "/entity/travel/place/dali",
                "homepageId": "homepage-runtime-dali",
                "title": "大理",
                "detailStatus": 200,
                "introductionStatus": 200,
                "coverUrl": "media/objects/sha256/cover",
                "sectionCount": 1,
            }
        ],
        "issues": [],
    }
    homepage_ref, _ = _write(
        root, f"{verify_prefix}/homepage-api-verification.json", homepage
    )
    _write(root, f"{verify_prefix}/post-api-verification.json", {"passed": True})
    readiness = {
        "schema": "quwoquan_data.environment_release_readiness",
        "environment": "alpha",
        "releaseId": RELEASE_ID,
        "releaseKind": "content",
        "releaseClass": "research",
        "productLifecycleState": "research",
        "sourceOwner": "qwq_data",
        "readinessPhase": "research",
        "manifestDigest": MANIFEST_DIGEST,
        "importRunId": IMPORT_RUN_ID,
        "verifyRunId": VERIFY_RUN_ID,
        "entityRefs": ["/entity/travel/place/dali"],
        "postIds": [row["postId"] for row in post_bindings],
        "contentImportReportRef": import_ref,
        "homepageApiVerificationRef": homepage_ref,
        "postApiVerificationRef": f"{verify_prefix}/post-api-verification.json",
        "passed": True,
    }
    readiness_ref, readiness_digest = _write(
        root, f"{verify_prefix}/release-readiness.json", readiness
    )

    health = {
        "command": "health",
        "target": "alpha-local",
        "scope": "content-consumer",
        "environment": "alpha",
        "deploymentTarget": "alpha-local",
        "releaseId": RELEASE_ID,
        "releaseDigest": RELEASE_DIGEST,
        "manifestDigest": MANIFEST_DIGEST,
        "importRunId": IMPORT_RUN_ID,
        "verifyRunId": VERIFY_RUN_ID,
        "findings": [],
        "generationIssues": [],
        "checks": [{"name": "content-feed", "ok": True, "skipped": False}],
        "userAvailability": [
            {"name": name, "status": "ready", "issues": []}
            for name in sorted(subject._REQUIRED_HEALTH_LAYERS)
        ],
        "userAvailabilityReport": {
            "evidence": {
                "candidate": {
                    "baselineId": "sha256:" + "b" * 64,
                    "packageDigest": "sha256:" + "c" * 64,
                    "sourceRevision": SOURCE_SHA,
                    "candidateDir": "",
                },
                "runtime": {
                    "startupReceipt": {
                        "configurationDigest": "sha256:" + "d" * 64,
                    }
                },
                "content": {
                    "releaseId": RELEASE_ID,
                    "manifestDigest": MANIFEST_DIGEST,
                    "readinessReceiptRef": readiness_ref,
                    "readinessReceiptDigest": readiness_digest,
                    "releaseActive": True,
                    "exactQueriesReady": True,
                    "generationMatch": True,
                },
            }
        },
    }
    health_ref, health_digest = _write(
        root, "env/alpha/runs/health/content-consumer/report.json", health
    )
    return {
        "sample_plan_ref": sample_ref,
        "sample_plan_digest": sample_digest,
        "data_readiness_ref": readiness_ref,
        "data_readiness_digest": readiness_digest,
        "consumer_health_ref": health_ref,
        "consumer_health_digest": health_digest,
    }


def _credential(ca: Path) -> dict[str, str]:
    return {
        "apiBaseUrl": "https://api.alpha.quwoquan.com",
        "sslCaFile": str(ca),
        "bearerToken": BEARER_FIXTURE,
        "attestationToken": ATTESTATION,
        "subjectHash": "sha256:" + "e" * 64,
        "expiresAt": "2026-09-03T02:00:00Z",
    }


def _http(**kwargs: Any) -> subject.HttpObservation:
    path = "/" + str(kwargs["path"]).lstrip("/")
    body = kwargs.get("body") or {}
    now = "2026-09-03T01:10:00Z"
    if path == "/content/feed":
        payload: dict[str, Any] = {
            "releaseId": RELEASE_ID,
            "manifestDigest": MANIFEST_DIGEST,
            "items": [
                {
                    "postId": f"post-runtime-{carrier}",
                    "contentType": carrier,
                    "primaryHomepageId": "homepage-runtime-dali",
                }
                for carrier in ("article", "image", "video")
            ],
            "objectCards": [
                {"objectId": "homepage-runtime-dali", "objectKind": "entity_homepage"}
            ],
        }
    elif path == "/search":
        object_id = body["ids"][0]
        carrier = ""
        if object_id.startswith("post-runtime-"):
            carrier = object_id.removeprefix("post-runtime-")
        payload = {
            "hits": [
                {
                    "objectId": object_id,
                    "objectType": (
                        "entity.homepage" if not carrier else "content.post"
                    ),
                    **({"contentType": carrier} if carrier else {}),
                }
            ]
        }
    elif path.startswith("/homepages/"):
        payload = {"homepageId": path.rsplit("/", 1)[-1], "title": "大理"}
    else:
        carrier = path.rsplit("-", 1)[-1]
        payload = {
            "postId": path.rsplit("/", 1)[-1],
            "contentType": carrier,
            "contentIdentity": "work",
        }
    return subject.HttpObservation(
        method=str(kwargs["method"]),
        path=path,
        status=200,
        payload=payload,
        request_id="request-" + path.replace("/", "-"),
        trace_id="trace-" + path.replace("/", "-"),
        started_at=now,
        completed_at=now,
        duration_ms=1,
    )


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    http: Any = _http,
) -> tuple[dict[str, Any], Path, dict[str, str]]:
    root = tmp_path / "output"
    root.mkdir()
    refs = _authorities(root)
    ca = tmp_path / "root.crt"
    ca.write_text("test CA", encoding="utf-8")
    monkeypatch.setattr(
        subject, "_topology_api_base", lambda _target: "https://api.alpha.quwoquan.com"
    )
    monkeypatch.setattr(subject, "_tls_ca_file", lambda _target: ca)
    parent = root / "env/alpha/runs/content-api-consumer"
    parent.mkdir(parents=True)
    report_dir = parent / "run-001"
    result = subject.run_content_api_consumer(
        target="alpha-local",
        release_id=RELEASE_ID,
        import_run_id=IMPORT_RUN_ID,
        verify_run_id=VERIFY_RUN_ID,
        manifest_digest=MANIFEST_DIGEST,
        report_dir=report_dir,
        output_root=root,
        http_request=http,
        credential_issuer=lambda **_kwargs: _credential(ca),
        **refs,
    )
    return result, report_dir, refs


def test_matrix_writes_sixteen_observations_and_canonical_raw_without_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, report_dir, _refs = _run(tmp_path, monkeypatch)

    assert result["exitCode"] == 0
    assert result["releaseDigest"] == RELEASE_DIGEST
    assert result["manifestDigest"] == MANIFEST_DIGEST
    assert result["releaseDigest"] != result["manifestDigest"]
    observations = sorted((report_dir / "observations").glob("*/*.json"))
    raw_paths = sorted((report_dir / "raw").glob("*/*.json"))
    assert len(observations) == len(raw_paths) == 16
    raw = [json.loads(path.read_text(encoding="utf-8")) for path in raw_paths]
    assert {(row["entrySurface"], row["carrier"]) for row in raw} == {
        (entry, carrier)
        for entry in subject.ENTRY_SURFACES
        for carrier in subject.CARRIERS
    }
    assert {row["status"] for row in raw} == {"passed"}
    assert all(
        row["producer"] == "service" and row["layer"] == "api_integration"
        for row in raw
    )
    assert all("platform" not in row and "deviceClass" not in row for row in raw)
    assert all(
        validate_readiness_case_result(row, generated_at=row["completedAt"]) == row
        for row in raw
    )
    persisted = b"".join(path.read_bytes() for path in report_dir.rglob("*.json"))
    assert BEARER_FIXTURE.encode() not in persisted
    assert ATTESTATION.encode() not in persisted
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert "status" not in report and "verdict" not in report
    assert report["releaseDigest"] == RELEASE_DIGEST
    assert report["manifestDigest"] == MANIFEST_DIGEST
    assert report["consumerHealth"] == result["consumerHealth"]
    health_binding = json.loads(
        (report_dir / "consumer-health.json").read_text(encoding="utf-8")
    )
    assert health_binding["requiredLayers"] == list(subject._REQUIRED_HEALTH_LAYERS)
    assert "provider_ready" not in health_binding["requiredLayers"]
    assert health_binding["sourceHealth"]["ref"] == report["sourceHealth"]["ref"]
    assert len(report["observations"]) == len(report["requiredRawResults"]) == 16
    homepage = next(
        json.loads(path.read_text(encoding="utf-8"))
        for path in observations
        if path.parts[-2:] == ("recommendation", "homepage.json")
    )
    assert homepage["assertion"]["matchedRuntimeObjectId"] == "homepage-runtime-dali"


def test_failed_http_assertion_still_retains_all_raw_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_http(**kwargs: Any) -> subject.HttpObservation:
        observation = _http(**kwargs)
        if kwargs["path"] == "search" and (kwargs.get("body") or {}).get("ids") == [
            "post-runtime-video"
        ]:
            return subject.HttpObservation(**{**observation.__dict__, "status": 503})
        return observation

    result, report_dir, _refs = _run(tmp_path, monkeypatch, http=failing_http)

    assert result["exitCode"] == 1
    raw_paths = sorted((report_dir / "raw").glob("*/*.json"))
    assert len(raw_paths) == 16
    failed = json.loads(
        (report_dir / "raw/search/video.json").read_text(encoding="utf-8")
    )
    assert failed["status"] == "failed"
    assert failed["reasonCode"] == "SERVICE.CONTENT_API_CONSUMER.failed"


def test_credential_failure_retains_sixteen_blocked_raw_without_exception_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "output"
    root.mkdir()
    refs = _authorities(root)
    ca = tmp_path / "root.crt"
    ca.write_text("test CA", encoding="utf-8")
    monkeypatch.setattr(
        subject, "_topology_api_base", lambda _target: "https://api.alpha.quwoquan.com"
    )
    monkeypatch.setattr(subject, "_tls_ca_file", lambda _target: ca)
    parent = root / "env/alpha/runs/content-api-consumer"
    parent.mkdir(parents=True)
    report_dir = parent / "blocked"

    result = subject.run_content_api_consumer(
        target="alpha-local",
        release_id=RELEASE_ID,
        import_run_id=IMPORT_RUN_ID,
        verify_run_id=VERIFY_RUN_ID,
        manifest_digest=MANIFEST_DIGEST,
        report_dir=report_dir,
        output_root=root,
        http_request=lambda **_kwargs: pytest.fail("HTTP must not run"),
        credential_issuer=lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("credential failed " + BEARER_FIXTURE)
        ),
        **refs,
    )

    assert result["exitCode"] == 2
    raw = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (report_dir / "raw").glob("*/*.json")
    ]
    assert len(raw) == 16 and {row["status"] for row in raw} == {"blocked"}
    assert BEARER_FIXTURE.encode() not in b"".join(
        path.read_bytes() for path in report_dir.rglob("*.json")
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda refs: refs.update(sample_plan_digest="sha256:" + "f" * 64),
            "digest drifted",
        ),
        (
            lambda refs: refs.update(data_readiness_ref="../release-readiness.json"),
            "relative",
        ),
        (
            lambda refs: refs.update(consumer_health_digest="not-a-digest"),
            "canonical sha256",
        ),
    ],
)
def test_explicit_authority_digest_and_ref_drift_is_rejected_before_http(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: Any,
    message: str,
) -> None:
    root = tmp_path / "output"
    root.mkdir()
    refs = _authorities(root)
    mutation(refs)
    ca = tmp_path / "root.crt"
    ca.write_text("test CA", encoding="utf-8")
    monkeypatch.setattr(
        subject, "_topology_api_base", lambda _target: "https://api.alpha.quwoquan.com"
    )
    monkeypatch.setattr(subject, "_tls_ca_file", lambda _target: ca)
    parent = root / "env/alpha/runs/content-api-consumer"
    parent.mkdir(parents=True)

    with pytest.raises(subject.ContentApiConsumerError, match=message):
        subject.run_content_api_consumer(
            target="alpha-local",
            release_id=RELEASE_ID,
            import_run_id=IMPORT_RUN_ID,
            verify_run_id=VERIFY_RUN_ID,
            manifest_digest=MANIFEST_DIGEST,
            report_dir=parent / "rejected",
            output_root=root,
            http_request=lambda **_kwargs: pytest.fail("HTTP must not run"),
            credential_issuer=lambda **_kwargs: _credential(ca),
            **refs,
        )


def test_stackctl_parser_exposes_only_explicit_authority_surface() -> None:
    from quwoquan_ops.cli import stackctl

    parser = stackctl.build_parser()
    command = parser.parse_args(
        [
            "content-api-consumer",
            "--target",
            "alpha-local",
            "--release-id",
            RELEASE_ID,
            "--import-run-id",
            IMPORT_RUN_ID,
            "--verify-run-id",
            VERIFY_RUN_ID,
            "--manifest-digest",
            MANIFEST_DIGEST,
            "--sample-plan-ref",
            "plan.json",
            "--sample-plan-digest",
            RELEASE_DIGEST,
            "--data-readiness-ref",
            "readiness.json",
            "--data-readiness-digest",
            RELEASE_DIGEST,
            "--consumer-health-ref",
            "health.json",
            "--consumer-health-digest",
            RELEASE_DIGEST,
            "--report-dir",
            "report",
        ]
    )
    assert command.command == "content-api-consumer"
    assert not {"base_url", "insecure", "token"}.intersection(vars(command))
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "content-api-consumer",
                "--target",
                "alpha-local",
                "--base-url",
                "https://attacker.invalid",
            ]
        )


def test_nonrequired_health_layers_do_not_block_m1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "output"
    root.mkdir()
    refs = _authorities(root)
    health_path = root / refs["consumer_health_ref"]
    health = json.loads(health_path.read_text(encoding="utf-8"))
    health["userAvailability"].extend(
        [
            {"name": "provider_ready", "status": "blocked", "issues": ["not M1"]},
            {"name": "device_bound", "status": "blocked", "issues": ["not M1"]},
            {"name": "content_live_passed", "status": "blocked", "issues": ["not M1"]},
        ]
    )
    health_path.write_text(
        json.dumps(health, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    refs["consumer_health_digest"] = subject._digest_bytes(health_path.read_bytes())
    ca = tmp_path / "root.crt"
    ca.write_text("test CA", encoding="utf-8")
    monkeypatch.setattr(
        subject, "_topology_api_base", lambda _target: "https://api.alpha.quwoquan.com"
    )
    monkeypatch.setattr(subject, "_tls_ca_file", lambda _target: ca)
    parent = root / "env/alpha/runs/content-api-consumer"
    parent.mkdir(parents=True)
    result = subject.run_content_api_consumer(
        target="alpha-local",
        release_id=RELEASE_ID,
        import_run_id=IMPORT_RUN_ID,
        verify_run_id=VERIFY_RUN_ID,
        manifest_digest=MANIFEST_DIGEST,
        report_dir=parent / "nonrequired-blocked",
        output_root=root,
        http_request=_http,
        credential_issuer=lambda **_kwargs: _credential(ca),
        **refs,
    )
    assert result["exitCode"] == 0


def test_explicit_manifest_digest_must_match_data_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "output"
    root.mkdir()
    refs = _authorities(root)
    ca = tmp_path / "root.crt"
    ca.write_text("test CA", encoding="utf-8")
    monkeypatch.setattr(
        subject, "_topology_api_base", lambda _target: "https://api.alpha.quwoquan.com"
    )
    monkeypatch.setattr(subject, "_tls_ca_file", lambda _target: ca)
    parent = root / "env/alpha/runs/content-api-consumer"
    parent.mkdir(parents=True)
    with pytest.raises(subject.ContentApiConsumerError, match="manifestDigest drifted"):
        subject.run_content_api_consumer(
            target="alpha-local",
            release_id=RELEASE_ID,
            import_run_id=IMPORT_RUN_ID,
            verify_run_id=VERIFY_RUN_ID,
            manifest_digest=RELEASE_DIGEST,
            report_dir=parent / "wrong-manifest",
            output_root=root,
            http_request=lambda **_kwargs: pytest.fail("HTTP must not run"),
            credential_issuer=lambda **_kwargs: _credential(ca),
            **refs,
        )


def test_runner_outputs_build_a_real_m1_eaf_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, report_dir, refs = _run(tmp_path, monkeypatch)
    root = tmp_path / "output"
    fact = acceptance.build_environment_acceptance_fact(
        evidence_root=root,
        acceptance_profile="m1_api_consumer",
        environment="alpha",
        target="alpha-local",
        release_id=RELEASE_ID,
        release_digest=RELEASE_DIGEST,
        manifest_digest=MANIFEST_DIGEST,
        import_run_id=IMPORT_RUN_ID,
        verify_run_id=VERIFY_RUN_ID,
        sample_plan_ref=refs["sample_plan_ref"],
        sample_plan_digest=refs["sample_plan_digest"],
        target_binding_refs=[],
        required_raw_results=result["requiredRawResults"],
        required_target_profiles=[],
        data_readiness={
            "ref": refs["data_readiness_ref"],
            "digest": refs["data_readiness_digest"],
        },
        consumer_health=result["consumerHealth"],
        created_at="2026-09-03T01:10:00Z",
        source_fingerprint=result["sourceFingerprint"],
    )
    assert fact["sourceFingerprint"] == result["sourceFingerprint"]
    assert fact["consumerHealth"] == result["consumerHealth"]
    assert fact["releaseDigest"] == RELEASE_DIGEST
    assert fact["manifestDigest"] == MANIFEST_DIGEST
    store = root / "environment-acceptance-facts"
    store.mkdir()
    written = acceptance.write_environment_acceptance_fact(
        root=store,
        fact=fact,
        evidence_root=root,
        required_target_profiles=[],
    )
    assert written.is_file()
    assert (report_dir / "consumer-health.json").is_file()
