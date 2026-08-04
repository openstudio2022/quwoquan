"""The release policy selects one minimal capability slice, never all environments."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.content_release_readiness import (
    ProbeSource,
    ReadinessCapability,
    ReadinessPhase,
    VerificationProfile,
    load_content_release_readiness_policy,
)


def _operation_evidence(path: str, page_id: str, *, suffix: str) -> dict[str, object]:
    return {
        "path": path,
        "pageId": page_id,
        "status": 200,
        "requestId": f"DATA.{page_id}.{suffix}",
        "traceId": f"DATA.readiness.{page_id}.{suffix}",
        "startedAt": "2026-07-28T00:00:00.000Z",
        "endedAt": "2026-07-28T00:00:00.001Z",
        "durationMs": 1,
    }


def test_content_release_readiness__maps_phase_to_environment_capabilities__local_contract() -> (
    None
):
    policy = load_content_release_readiness_policy()

    alpha_import = policy.requirement_for(
        phase=ReadinessPhase.IMPORT,
        environment="alpha",
    )
    beta_import = policy.requirement_for(
        phase=ReadinessPhase.IMPORT,
        environment="beta",
    )
    gamma_consumer = policy.requirement_for(
        phase=ReadinessPhase.CONSUMER,
        environment="gamma",
    )
    alpha_consumer = policy.requirement_for(
        phase=ReadinessPhase.CONSUMER,
        environment="alpha",
    )
    prod_consumer = policy.requirement_for(
        phase=ReadinessPhase.CONSUMER,
        environment="prod",
    )
    gamma_commercial = policy.requirement_for(
        phase=ReadinessPhase.COMMERCIAL,
        environment="gamma",
    )
    alpha_commercial = policy.requirement_for(
        phase=ReadinessPhase.COMMERCIAL,
        environment="alpha",
    )
    beta_commercial = policy.requirement_for(
        phase=ReadinessPhase.COMMERCIAL,
        environment="beta",
    )

    assert alpha_import.workload == "content-release"
    assert beta_import.workload == "content-release"
    assert alpha_consumer.target == "alpha-local"
    assert gamma_consumer.health_scope == "content-consumer"
    assert prod_consumer.target == "prod-hosted"
    assert ReadinessCapability.TELEMETRY_LOG_SINK not in beta_import.capabilities
    assert ReadinessCapability.TELEMETRY_LOG_SINK in gamma_commercial.capabilities
    assert alpha_commercial.workload == "full"
    assert beta_commercial.workload == "full"


def test_content_release_readiness__binds_probe_for_every_capability__local_contract() -> (
    None
):
    policy = load_content_release_readiness_policy()

    for capability in ReadinessCapability:
        binding = policy.probe_binding_for(capability)
        if binding.source is ProbeSource.HEALTH_SCOPE:
            assert binding.health_scope
        elif binding.source is ProbeSource.COMMERCIAL_DOCTOR:
            assert binding.source is ProbeSource.COMMERCIAL_DOCTOR
            assert binding.health_scope is None
        elif binding.source is ProbeSource.RESEARCH_ISOLATION:
            assert capability is ReadinessCapability.RESEARCH_ACCESS_ISOLATION
            assert binding.health_scope is None
            assert binding.control_action is None
        else:
            assert binding.source is ProbeSource.LOG_SINK_CONTROL
            assert binding.control_action == "all"

    assert (
        policy.probe_binding_for(ReadinessCapability.CONTENT_SERVICES).health_scope
        == "content-import"
    )
    assert (
        policy.probe_binding_for(ReadinessCapability.TELEMETRY_LOG_SINK).source
        is ProbeSource.LOG_SINK_CONTROL
    )


def test_content_release_readiness__doctor_bound_capabilities_are_commercial_only__local_contract() -> (
    None
):
    policy = load_content_release_readiness_policy()

    for requirement in policy.requirements:
        for capability in requirement.capabilities:
            binding = policy.probe_binding_for(capability)
            if requirement.phase is ReadinessPhase.COMMERCIAL:
                continue
            if requirement.phase is ReadinessPhase.RESEARCH:
                assert binding.source in {
                    ProbeSource.HEALTH_SCOPE,
                    ProbeSource.RESEARCH_ISOLATION,
                }
            else:
                assert binding.source is ProbeSource.HEALTH_SCOPE


def test_content_release_readiness__rejects_undefined_phase_environment__local_contract() -> (
    None
):
    policy = load_content_release_readiness_policy()
    try:
        policy.requirement_for(phase=ReadinessPhase.IMPORT, environment="prod")
    except ValueError as exc:
        assert "does not define" in str(exc)
    else:
        raise AssertionError("undefined phase/environment must be rejected")


def test_prod_hosted_content_service_has_a_real_import_scope_probe__local_contract() -> (
    None
):
    checks = stackctl._content_data_plane_health_checks("prod-hosted")

    assert checks == [
        {
            "name": "content-service-public",
            "scope": "content-import",
            "url": "https://api.quwoquan.com/healthz",
        }
    ]


def test_media_edge_health_uses_edge_root_not_carrier_path_base__local_contract() -> (
    None
):
    topology = stackctl.load_environment_topology()
    for target_name in ("alpha-local", "beta-local", "gamma-local"):
        checks = stackctl._health_checks_for_target(
            topology,
            target_name,
            "content-import",
            workload="content-release",
        )
        media = next(item for item in checks if item["name"] == "media-edge-health")
        assert media["url"].endswith("/healthz")
        assert not media["url"].endswith("/media/image/healthz")
        assert "/media/image/" not in media["url"]
        assert "/media/avatar/" not in media["url"]
        assert "/media/video/" not in media["url"]


def test_content_release_import_plane_excludes_tag_and_search__local_contract() -> (
    None
):
    topology = stackctl.load_environment_topology()
    checks = stackctl._health_checks_for_target(
        topology,
        "alpha-local",
        "content-import",
        workload="content-release",
    )
    names = {str(item["name"]) for item in checks}
    assert "content-service" in names
    assert "entity-service" in names
    assert "tag-service" not in names
    assert "search-service" not in names

    full_plane = {
        str(item["name"])
        for item in stackctl._content_data_plane_health_checks(
            "alpha-local",
            workload="full",
        )
    }
    assert "tag-service" in full_plane
    assert "search-service" in full_plane


def test_content_consumer_feed_health_includes_session_id__local_contract() -> None:
    topology = stackctl.load_environment_topology()
    checks = stackctl._health_checks_for_target(
        topology,
        "alpha-local",
        "content-consumer",
        workload="content-release",
    )
    feed = next(item for item in checks if item["name"] == "content-feed")
    assert "sessionId=" in str(feed["url"])
    assert str(feed["url"]).endswith("sessionId=stackctl-content-consumer-health") or (
        "sessionId=stackctl-content-consumer-health" in str(feed["url"])
    )


def test_content_commercial_health_adds_product_ops_without_full_plane__local_contract() -> (
    None
):
    topology = stackctl.load_environment_topology()
    checks = stackctl._health_checks_for_target(
        topology,
        "alpha-local",
        "content-commercial",
        workload="content-commercial",
    )
    names = {str(item["name"]) for item in checks}

    assert {
        "api-health",
        "product-ops-health",
        "media-edge-health",
        "content-service",
        "entity-service",
        "app-config",
        "content-feed",
        "product-ops-service",
    }.issubset(names)
    assert "assistant-service" not in names
    assert "platform-ops-service" not in names
    assert "integration-service" not in names


def test_content_consumer_nonempty_feed_probe_skips_commercial_checks__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def _fake_probe(
        topology,
        target_name,
        report_dir,
        *,
        require_non_empty_content_feed=False,
        release_post_expectations=None,
        release_readiness_path=None,
        only_checks=(),
        probe_name="integration-readonly",
        timeout_seconds=None,
    ):
        captured["only_checks"] = only_checks
        captured["require_non_empty_content_feed"] = require_non_empty_content_feed
        return (
            {"name": probe_name, "ok": True, "scope": "content-consumer"},
            "ok",
            [],
        )

    monkeypatch.setattr(stackctl, "_run_environment_integration_probe", _fake_probe)
    topology = stackctl.load_environment_topology()
    statuses, _, findings = stackctl._script_probes_for_target(
        topology,
        "alpha-local",
        "content-consumer",
        tmp_path,
        require_non_empty_content_feed=True,
    )
    assert findings == []
    assert statuses
    assert captured["require_non_empty_content_feed"] is True
    assert captured["only_checks"] == (
        "content_feed",
        "video_book_feed",
    )
    assert "premium_feed" not in captured["only_checks"]
    assert "global_search" not in captured["only_checks"]


def test_baseline_verify__does_not_read_disposable_release_output__local_contract() -> (
    None
):
    commands = stackctl._selected_verify_commands(
        "all",
        profile=VerificationProfile.BASELINE,
    )

    rendered = "\n".join(" ".join(command) for command in commands)
    assert "verify_environment_packaging_contract.py" not in rendered
    assert "verify_env_artifact_isolation.py" not in rendered


def test_non_prod_verify__binds_prod_purity_to_prod_target__local_contract() -> None:
    commands = stackctl._selected_verify_commands(
        "all",
        env_name="alpha",
        target_name="alpha-local",
        profile=VerificationProfile.SMOKE,
    )

    purity_command = next(
        command
        for command in commands
        if any(part.endswith("verify_prod_package_purity.py") for part in command)
    )
    assert purity_command[-2:] == ["--target", "prod-hosted"]


def test_prod_verify__passes_prod_target_to_prod_purity__local_contract() -> None:
    commands = stackctl._selected_verify_commands(
        "all",
        env_name="prod",
        target_name="prod-hosted",
        profile=VerificationProfile.RELEASE,
    )

    purity_command = next(
        command
        for command in commands
        if any(part.endswith("verify_prod_package_purity.py") for part in command)
    )
    assert purity_command[-2:] == ["--target", "prod-hosted"]


_IMPORT_SCOPE_CHECKS = [
    {"name": "api-health", "scope": "edge"},
    {"name": "media-edge-health", "scope": "media"},
    {"name": "entity-service", "scope": "content-import"},
]


def test_content_release_readiness__import_ignores_commercial_doctor__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {"exitCode": 0, "details": [], "reportDir": "health"},
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {"checks": list(_IMPORT_SCOPE_CHECKS)},
    )
    monkeypatch.setattr(
        stackctl,
        "command_doctor",
        lambda _args: (_ for _ in ()).throw(
            AssertionError("import must not call doctor")
        ),
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="import",
            env="beta",
            report_dir=str(tmp_path),
            output_format="json",
        )
    )

    assert result["exitCode"] == 0
    assert result["outcome"] == "PASS"
    assert result["phase"] == "import"
    assert result["schema"] == "quwoquan_ops.ship_readiness_receipt"


def test_content_release_readiness__missing_declared_probe_is_gate_block__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """健康门绿但缺少能力声明的探针时必须 fail-closed，不得凭空 PASS。"""
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {"exitCode": 0, "details": [], "reportDir": "health"},
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {"checks": [{"name": "api-health", "scope": "edge"}]},
    )
    monkeypatch.setattr(
        stackctl,
        "command_doctor",
        lambda _args: (_ for _ in ()).throw(
            AssertionError("import must not call doctor")
        ),
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="import",
            env="beta",
            report_dir=str(tmp_path),
            output_format="json",
        )
    )

    assert result["exitCode"] == 2
    assert result["outcome"] == "GATE_BLOCK"
    assert any("content_services" in item for item in result["details"])


def test_content_release_readiness__commercial_missing_capability_is_gate_block(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {"exitCode": 0, "details": [], "reportDir": "health"},
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {
            "checks": list(_IMPORT_SCOPE_CHECKS)
            + [{"name": "content-feed", "scope": "content-consumer"}]
        },
    )
    monkeypatch.setattr(
        stackctl,
        "command_doctor",
        lambda _args: {"exitCode": 1, "details": ["Elasticsearch is unavailable"]},
    )
    monkeypatch.setattr(
        stackctl,
        "command_product_telemetry_log_sink",
        lambda _args: {
            "exitCode": 2,
            "details": ["Elasticsearch log sink is unavailable"],
        },
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="commercial",
            env="gamma",
            report_dir=str(tmp_path),
            output_format="json",
        )
    )

    assert result["exitCode"] == 2
    assert result["outcome"] == "GATE_BLOCK"
    assert any("telemetry_log_sink" in item for item in result["details"])


def test_content_release_readiness__gamma_controls_elasticsearch_log_sink(
    monkeypatch,
    tmp_path: Path,
) -> None:
    control_calls: list[argparse.Namespace] = []
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {"exitCode": 0, "details": [], "reportDir": "health"},
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {
            "checks": list(_IMPORT_SCOPE_CHECKS)
            + [{"name": "content-feed", "scope": "content-consumer"}]
        },
    )
    monkeypatch.setattr(
        stackctl,
        "command_product_telemetry_log_sink",
        lambda args: control_calls.append(args) or {"exitCode": 0, "details": []},
    )
    monkeypatch.setattr(
        stackctl,
        "command_doctor",
        lambda _args: {"exitCode": 0, "details": []},
    )
    monkeypatch.setattr(
        stackctl,
        "_load_data_release_readiness",
        lambda **_kwargs: (
            {
                "schema": "quwoquan_data.environment_release_readiness",
                "releaseId": "release-001",
                "manifestDigest": "sha256:" + "1" * 64,
                "passed": True,
            },
            tmp_path / "release-readiness.json",
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "_run_release_feed_readback_probe",
        lambda **_kwargs: (
            {
                "schema": "environment-integration-probe-report",
                "status": "passed",
                "checks": [],
            },
            tmp_path / "feed-readback" / "integration-probe.json",
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "_run_release_video_delivery_probe",
        lambda **_kwargs: (
            {
                "schema": "quwoquan_ops.release_video_delivery_evidence",
                "status": "passed",
                "release": {"releaseId": "release-001"},
            },
            tmp_path / "video-delivery" / "report.json",
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "_load_data_release_lifecycle_exit",
        lambda **_kwargs: (
            {
                "schema": "quwoquan_data.environment_release_lifecycle_exit",
                "passed": True,
            },
            tmp_path / "lifecycle-exit.json",
        ),
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="commercial",
            env="gamma",
            report_dir=str(tmp_path),
            output_format="json",
            lifecycle_exit_ref=(
                "env/gamma/runs/release-lifecycle-exit/"
                "release-001/exit-001/lifecycle-exit.json"
            ),
        )
    )

    assert result["exitCode"] == 0
    assert result["outcome"] == "PASS"
    assert result["probes"][-1] == "product-telemetry-log-sink:all"
    assert "release-bound-feed-readback" in result["probes"]
    assert "release-video-delivery" in result["probes"]
    assert "canonical-data-release-lifecycle-exit" in result["probes"]
    assert result["dataRelease"]["feedReadbackEvidenceRef"]
    assert result["dataRelease"]["videoDeliveryEvidenceRef"]
    assert [(item.target, item.action) for item in control_calls] == [
        ("gamma-local", "all")
    ]


def test_content_release_readiness__consumer_skips_commercial_video_delivery(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {"exitCode": 0, "details": [], "reportDir": "health"},
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {
            "checks": list(_IMPORT_SCOPE_CHECKS)
            + [{"name": "content-feed", "scope": "content-consumer"}]
        },
    )
    monkeypatch.setattr(
        stackctl,
        "_load_data_release_readiness",
        lambda **_kwargs: (
            {
                "schema": "quwoquan_data.environment_release_readiness",
                "releaseId": "release-001",
                "readinessPhase": "consumer",
                "passed": True,
            },
            tmp_path / "release-readiness.json",
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "_run_release_feed_readback_probe",
        lambda **_kwargs: (
            {
                "schema": "environment-integration-probe-report",
                "status": "passed",
                "checks": [],
            },
            tmp_path / "feed-readback" / "integration-probe.json",
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "_run_release_video_delivery_probe",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("consumer must not require commercial video delivery")
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "command_doctor",
        lambda _args: (_ for _ in ()).throw(
            AssertionError("consumer must not call commercial doctor")
        ),
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="consumer",
            env="alpha",
            release_id="release-001",
            verify_run_id="verify-001",
            manifest_digest="sha256:" + "1" * 64,
            report_dir=str(tmp_path),
            output_format="json",
        )
    )

    assert result["exitCode"] == 0
    assert "release-bound-feed-readback" in result["probes"]
    assert "release-video-delivery" not in result["probes"]
    assert result["dataRelease"]["videoDeliveryEvidenceRef"] == ""
    assert result["dataRelease"]["videoDelivery"] is None


def _write_data_readiness_fixture(
    *,
    output_root: Path,
    environment: str = "gamma",
    release_id: str = "pilot-002",
    verify_run_id: str = "verify-001",
) -> tuple[Path, str]:
    release_root = output_root / "data" / "releases" / release_id
    media_path = release_root / "payload" / "media_manifest.json"
    media_path.parent.mkdir(parents=True)
    media_path.write_text('{"assets":[{"assetId":"video-asset"}]}\n', encoding="utf-8")
    manifest_digest = "sha256:" + "2" * 64
    attestation_path = release_root / "attestations" / "release.json"
    attestation_path.parent.mkdir(parents=True)
    attestation_path.write_text(
        json.dumps(
            {
                "releaseId": release_id,
                "sourceOwner": "qwq_data",
                "payloadSha256": manifest_digest,
            }
        ),
        encoding="utf-8",
    )
    evidence_root = (
        output_root
        / "env"
        / environment
        / "runs"
        / "data-release"
        / release_id
        / verify_run_id
    )
    evidence_root.mkdir(parents=True)
    refs: dict[str, str] = {}
    for key, filename in (
        ("contentImportReportRef", "content-import-report.json"),
        ("creatorAttributionRef", "creator-attribution.json"),
        ("tagAttributionRef", "tag-attribution.json"),
        ("homepageApiVerificationRef", "homepage-api-verification.json"),
        ("postApiVerificationRef", "post-api-verification.json"),
    ):
        path = evidence_root / filename
        if key != "postApiVerificationRef":
            path.write_text("{}\n", encoding="utf-8")
        refs[key] = path.relative_to(output_root).as_posix()
    feed_queries = [
        (
            "discovery_work",
            "identity=work&limit=20",
            ["post-article", "post-image", "post-video"],
        ),
        ("typed_article", "identity=work&type=article&limit=20", ["post-article"]),
        ("typed_image", "identity=work&type=image&limit=20", ["post-image"]),
        ("typed_video", "identity=work&type=video&limit=20", ["post-video"]),
        (
            "homepage_recommend",
            "sort=recommend&channelId=recommend&limit=20",
            ["post-video"],
        ),
        (
            "premium_stream",
            "sort=recommend&channelId=premium_stream&limit=20",
            ["post-video"],
        ),
    ]
    guest_login = _operation_evidence(
        "/auth/login/anonymous",
        "user.login.anonymous",
        suffix="login",
    )
    feed_query_evidence = [
        {
            "name": name,
            "path": "/content/feed",
            "query": query,
            "status": 200,
            "releaseBound": True,
            "matchedPostIds": post_ids,
            "requests": [
                _operation_evidence(
                    "/content/feed",
                    "content.feed.list",
                    suffix=name,
                )
            ],
        }
        for name, query, post_ids in feed_queries
    ]
    guest_actor_hash = "sha256:" + "3" * 64
    post_verification_path = output_root / refs["postApiVerificationRef"]
    post_verification_path.write_text(
        json.dumps(
            {
                "guestActorHash": guest_actor_hash,
                "guestLogin": guest_login,
                "feedQueries": feed_query_evidence,
                "creators": [
                    {
                        "creatorRef": f"creator-{index}",
                        "avatarAssetId": f"creator-avatar-{index}",
                        "profileStatus": 200,
                        "avatarMediaReady": True,
                        "avatarProbeCount": 1,
                        "avatarUrl": (
                            "https://cdn.gamma.quwoquan.com/media/avatar/s/asset/"
                            f"creator-avatar-{index}/v1/source.jpg"
                        ),
                        "avatarProbe": {
                            "publicUrl": (
                                "https://cdn.gamma.quwoquan.com/media/avatar/s/asset/"
                                f"creator-avatar-{index}/v1/source.jpg"
                            ),
                            "status": 200,
                            "mimeType": "image/jpeg",
                            "bytes": 64,
                            "sha256": "sha256:" + f"{index}" * 64,
                            "etag": f'"creator-avatar-{index}"',
                            "hashVerified": True,
                        },
                    }
                    for index in range(1, 5)
                ],
                "posts": [
                    {
                        "mediaProbeCount": 1,
                        "mediaProbes": [
                            {
                                "assetId": "image-asset",
                                "kind": "image",
                                "status": 200,
                                "mimeType": "image/jpeg",
                                "bytes": 64,
                                "expectedBytes": 64,
                                "sha256": "sha256:" + "8" * 64,
                                "expectedSha256": "sha256:" + "8" * 64,
                                "hashVerified": True,
                            }
                        ]
                    }
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    receipt = {
        "schema": "quwoquan_data.environment_release_readiness",
        "environment": environment,
        "releaseId": release_id,
        "releaseKind": "content",
        "sourceOwner": "qwq_data",
        "releaseClass": "commercial",
        "productLifecycleState": "commercial",
        "containsUnverifiedAssets": False,
        "rightsStatusCounts": {
            "verified": 3,
            "unverified": 0,
            "restricted": 0,
            "unknown": 0,
        },
        "authorizationRequiredAssetIds": [],
        "researchAcceptedCount": 3,
        "commercialAcceptedCount": 3,
        "readinessPhase": "commercial",
        "manifestDigest": manifest_digest,
        "mediaManifestDigest": "sha256:"
        + hashlib.sha256(media_path.read_bytes()).hexdigest(),
        "importRunId": "import-001",
        "verifyRunId": verify_run_id,
        "guestActorHash": guest_actor_hash,
        "guestLogin": guest_login,
        "counts": {
            "entities": 1,
            "posts": 3,
            "creators": 4,
            "avatarAssets": 4,
            "imageAssets": 1,
            "tags": 2,
            "mediaAssets": 3,
            "discoveryPosts": 3,
            "premiumPlayableVideos": 1,
        },
        "entityRefs": ["entities/west-lake"],
        "postIds": ["post-article", "post-image", "post-video"],
        "creatorIds": ["creator-1", "creator-2", "creator-3", "creator-4"],
        "tagRefs": ["tag/hangzhou", "tag/west-lake"],
        "mediaAssetIds": ["article-cover", "image-asset", "video-asset"],
        "feedQueries": feed_query_evidence,
        **refs,
        "mediaManifestRef": media_path.relative_to(output_root).as_posix(),
        "verifiedAt": "2026-07-28T00:00:00Z",
        "passed": True,
    }
    receipt["verificationChecksum"] = stackctl._canonical_document_checksum(receipt)
    receipt_path = evidence_root / "release-readiness.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt_path, manifest_digest


def test_data_release_readiness__binds_digest_exact_queries_and_evidence__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    receipt_path, manifest_digest = _write_data_readiness_fixture(output_root=tmp_path)

    receipt, loaded_path = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
    )

    assert loaded_path == receipt_path
    assert receipt["counts"]["premiumPlayableVideos"] == 1
    assert receipt["sourceOwner"] == "qwq_data"


def test_data_release_readiness__rejects_tampered_receipt__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    receipt_path, manifest_digest = _write_data_readiness_fixture(output_root=tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["feedQueries"][-1]["matchedPostIds"] = ["post-article"]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    try:
        stackctl._load_data_release_readiness(
            environment="gamma",
            release_id="pilot-002",
            verify_run_id="verify-001",
            manifest_digest=manifest_digest,
            readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
        )
    except ValueError as exc:
        assert "verificationChecksum" in str(exc)
        assert "playable video" in str(exc)
    else:
        raise AssertionError("tampered readiness receipt must be rejected")


def test_data_release_readiness__projects_live_exact_query_expectations__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    _receipt_path, manifest_digest = _write_data_readiness_fixture(output_root=tmp_path)
    receipt, _loaded_path = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
    )

    assert stackctl._release_feed_post_expectations(
        receipt,
        readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
    ) == {
        "content_feed": {"post-article", "post-image", "post-video"},
        "video_book_feed": {"post-video"},
        "premium_feed": {"post-video"},
    }


def test_data_release_readiness__consumer_does_not_require_premium_supply(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    receipt_path, manifest_digest = _write_data_readiness_fixture(
        output_root=tmp_path
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["readinessPhase"] = "consumer"
    receipt["feedQueries"] = [
        row
        for row in receipt["feedQueries"]
        if row["name"] != "premium_stream"
    ]
    receipt["counts"]["premiumPlayableVideos"] = 0
    post_path = tmp_path / receipt["postApiVerificationRef"]
    post = json.loads(post_path.read_text(encoding="utf-8"))
    post["feedQueries"] = list(receipt["feedQueries"])
    post_path.write_text(json.dumps(post), encoding="utf-8")
    unsigned = dict(receipt)
    unsigned.pop("verificationChecksum")
    receipt["verificationChecksum"] = stackctl._canonical_document_checksum(
        unsigned
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    loaded, _ = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.CONSUMER,
    )

    assert stackctl._release_feed_post_expectations(
        loaded,
        readiness_phase=stackctl.ReadinessPhase.CONSUMER,
    ) == {
        "content_feed": {"post-article", "post-image", "post-video"},
        "video_book_feed": {"post-video"},
    }


def _write_lifecycle_exit_fixture(
    *,
    output_root: Path,
    readiness: dict,
) -> str:
    environment = readiness["environment"]
    release_id = readiness["releaseId"]
    rollback_release_id = "empty-baseline-001"
    rollback_digest = "sha256:" + "4" * 64
    rollback_attestation = (
        output_root
        / "data/releases"
        / rollback_release_id
        / "attestations/release.json"
    )
    rollback_attestation.parent.mkdir(parents=True)
    rollback_attestation.write_text(
        json.dumps(
            {
                "releaseId": rollback_release_id,
                "sourceOwner": "qwq_data",
                "payloadSha256": rollback_digest,
            }
        ),
        encoding="utf-8",
    )
    run_bindings = (
        (release_id, readiness["importRunId"]),
        (release_id, readiness["verifyRunId"]),
        (rollback_release_id, "rollback-001"),
        (rollback_release_id, "rollback-verify-001"),
        (release_id, "replay-001"),
        (release_id, "replay-verify-001"),
    )
    for bound_release_id, run_id in run_bindings:
        result = (
            output_root
            / "env"
            / environment
            / "runs/data-release"
            / bound_release_id
            / run_id
            / "result.json"
        )
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text("{}\n", encoding="utf-8")

    def result_ref(bound_release_id: str, run_id: str) -> str:
        return (
            Path("env")
            / environment
            / "runs/data-release"
            / bound_release_id
            / run_id
            / "result.json"
        ).as_posix()

    exit_run_id = "exit-001"
    receipt = {
        "schema": "quwoquan_data.environment_release_lifecycle_exit",
        "environment": environment,
        "sourceOwner": "qwq_data",
        "exitRunId": exit_run_id,
        "originalReleaseId": release_id,
        "originalManifestDigest": readiness["manifestDigest"],
        "originalImportRunId": readiness["importRunId"],
        "originalVerifyRunId": readiness["verifyRunId"],
        "originalImportResultRef": result_ref(
            release_id,
            readiness["importRunId"],
        ),
        "originalVerifyResultRef": result_ref(
            release_id,
            readiness["verifyRunId"],
        ),
        "rollbackToReleaseId": rollback_release_id,
        "rollbackToManifestDigest": rollback_digest,
        "rollbackRunId": "rollback-001",
        "rollbackVerifyRunId": "rollback-verify-001",
        "rollbackResultRef": result_ref(rollback_release_id, "rollback-001"),
        "rollbackVerifyResultRef": result_ref(
            rollback_release_id,
            "rollback-verify-001",
        ),
        "replayImportRunId": "replay-001",
        "replayVerifyRunId": "replay-verify-001",
        "replayManifestDigest": readiness["manifestDigest"],
        "replayImportResultRef": result_ref(release_id, "replay-001"),
        "replayVerifyResultRef": result_ref(release_id, "replay-verify-001"),
        "recordedAt": "2026-07-28T00:05:00Z",
        "passed": True,
    }
    receipt["verificationChecksum"] = stackctl._canonical_document_checksum(receipt)
    ref = (
        Path("env")
        / environment
        / "runs/release-lifecycle-exit"
        / release_id
        / exit_run_id
        / "lifecycle-exit.json"
    ).as_posix()
    path = output_root / ref
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    return ref


def test_data_lifecycle_exit__binds_original_readiness_and_same_digest_replay(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    _receipt_path, manifest_digest = _write_data_readiness_fixture(
        output_root=tmp_path
    )
    readiness, _ = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
    )
    ref = _write_lifecycle_exit_fixture(
        output_root=tmp_path,
        readiness=readiness,
    )

    receipt, path = stackctl._load_data_release_lifecycle_exit(
        environment="gamma",
        release_id="pilot-002",
        manifest_digest=manifest_digest,
        readiness=readiness,
        lifecycle_exit_ref=ref,
    )

    assert path == tmp_path / ref
    assert receipt["originalImportRunId"] == readiness["importRunId"]
    assert receipt["replayManifestDigest"] == manifest_digest



def test_data_lifecycle_exit__allows_commercial_readiness_on_replay_import(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Commercial verify after lifecycle binds via replayImportRunId."""
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    _receipt_path, manifest_digest = _write_data_readiness_fixture(
        output_root=tmp_path
    )
    readiness, _ = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
    )
    ref = _write_lifecycle_exit_fixture(
        output_root=tmp_path,
        readiness=readiness,
    )
    # Simulate post-lifecycle commercial verify on the replayed import.
    readiness = dict(readiness)
    readiness["importRunId"] = "replay-001"
    readiness["verifyRunId"] = "commercial-verify-001"
    commercial_result = (
        tmp_path
        / "env/gamma/runs/data-release/pilot-002/commercial-verify-001/result.json"
    )
    commercial_result.parent.mkdir(parents=True, exist_ok=True)
    commercial_result.write_text("{}
", encoding="utf-8")

    receipt, path = stackctl._load_data_release_lifecycle_exit(
        environment="gamma",
        release_id="pilot-002",
        manifest_digest=manifest_digest,
        readiness=readiness,
        lifecycle_exit_ref=ref,
    )

    assert path == tmp_path / ref
    assert receipt["replayImportRunId"] == readiness["importRunId"]
    assert receipt["originalImportRunId"] != readiness["importRunId"]


def test_data_lifecycle_exit__rejects_replay_digest_drift(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    _receipt_path, manifest_digest = _write_data_readiness_fixture(
        output_root=tmp_path
    )
    readiness, _ = stackctl._load_data_release_readiness(
        environment="gamma",
        release_id="pilot-002",
        verify_run_id="verify-001",
        manifest_digest=manifest_digest,
        readiness_phase=stackctl.ReadinessPhase.COMMERCIAL,
    )
    ref = _write_lifecycle_exit_fixture(
        output_root=tmp_path,
        readiness=readiness,
    )
    path = tmp_path / ref
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["replayManifestDigest"] = "sha256:" + "9" * 64
    unsigned = dict(receipt)
    unsigned.pop("verificationChecksum")
    receipt["verificationChecksum"] = stackctl._canonical_document_checksum(unsigned)
    path.write_text(json.dumps(receipt), encoding="utf-8")

    try:
        stackctl._load_data_release_lifecycle_exit(
            environment="gamma",
            release_id="pilot-002",
            manifest_digest=manifest_digest,
            readiness=readiness,
            lifecycle_exit_ref=ref,
        )
    except ValueError as exc:
        assert "replayManifestDigest" in str(exc)
    else:
        raise AssertionError("same-digest replay drift must be rejected")
