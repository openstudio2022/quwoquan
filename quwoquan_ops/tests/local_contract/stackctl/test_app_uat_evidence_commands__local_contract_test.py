"""Ops UAT five-layer primitive command wiring contract.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-006
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from quwoquan_ops.cli.commands import app_uat_evidence as subject
from quwoquan_ops.cli.lib import environment_acceptance_fact as acceptance

RELEASE_DIGEST = "sha256:" + "1" * 64
MANIFEST_DIGEST = "sha256:" + "2" * 64
SPEC_REF = "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-006"
RUNNER = "qwq_app.content_uat.feed.article.v1"
PROFILE = {"platform": "android", "deviceProfile": "promotable"}


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _write(root: Path, ref: str, value: object) -> dict[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(encoded)
    return {"ref": ref, "digest": "sha256:" + hashlib.sha256(encoded).hexdigest()}


def _identity(
    environment: str = "alpha", target: str = "alpha-local"
) -> dict[str, str]:
    return {
        "environment": environment,
        "target": target,
        "deploymentTarget": target,
        "releaseId": "release-a",
        "releaseDigest": RELEASE_DIGEST,
        "importRunId": "import-run-a",
        "verifyRunId": "verify-run-a",
    }


def _plan(root: Path) -> dict[str, str]:
    entries = ("feed", "search", "recommendation", "direct_or_object_route")
    carriers = ("homepage", "article", "image", "video")
    cells = []
    for entry in entries:
        for carrier in carriers:
            if (entry, carrier) == ("feed", "article"):
                cells.append(
                    {
                        "entry": entry,
                        "carrier": carrier,
                        "applicability": "required",
                        "specRef": SPEC_REF,
                        "runnerClass": RUNNER,
                    }
                )
            else:
                cells.append(
                    {
                        "entry": entry,
                        "carrier": carrier,
                        "applicability": "not_applicable",
                        "reasonCode": "APP.UAT.NOT_APPLICABLE",
                    }
                )
    plan = {
        "schema": "quwoquan_data.release_uat_sample_plan",
        "releaseId": "release-a",
        "releaseDigest": RELEASE_DIGEST,
        "samples": [
            {
                "sampleId": "baseline-article-001",
                "carrier": "article",
                "objectId": "article-001",
                "objectRef": "objects/posts/article/article-001",
                "objectDigest": "sha256:" + "0" * 64,
            }
        ],
        "entryCarrierCells": cells,
    }
    return _write(root, "release/sample-plan.json", plan)


def _binding(root: Path, plan: dict[str, str]) -> dict[str, str]:
    from quwoquan_ops.cli.lib.target_uat_binding import build_target_uat_binding

    value = build_target_uat_binding(
        {
            "environment": "alpha",
            "target": "alpha-local",
            "releaseId": "release-a",
            "manifestDigest": RELEASE_DIGEST,
            "candidateDigest": _digest("2"),
            "packageDigest": _digest("3"),
            "runtimeConfigDigest": _digest("4"),
            "environmentRuntimeDigest": _digest("5"),
            "startupIdentity": {"configurationDigest": _digest("6")},
        },
        {
            "environment": "alpha",
            "target": "alpha-local",
            "platform": "android",
            "deviceId": "pixel-uat-01",
            "artifactDigest": _digest("7"),
            "applicationId": "com.leadwise.quwoquan.nonprod",
        },
        {
            "releaseId": "release-a",
            "releaseUatSamplePlanRef": plan["ref"],
            "releaseUatSamplePlanDigest": plan["digest"],
        },
        active_cas={"ref": "alpha/active-cas.json", "digest": _digest("8")},
        readback={"ref": "alpha/active-cas-readback.json", "digest": _digest("9")},
        artifact_class="production_behavior",
        build_mode="release",
        build_profile="nonprod",
        provider={
            "identity": "first-party-https",
            "class": "first_party",
            "type": "https",
            "registered": True,
            "conformanceEvidence": {
                "ref": "env/provider/conformance.json",
                "digest": _digest("f"),
            },
        },
        device={"identity": "pixel-uat-01", "class": "physical", "registered": True},
        runner={
            "identity": "app-content-uat",
            "sourcePath": "runner/app_uat.dart",
            "digest": _digest("a"),
            "registered": True,
        },
        profile="promotable",
        non_promotable=False,
        created_at="2026-08-29T07:00:00Z",
    )
    return _write(root, "alpha/binding.json", value)


def _raw(
    root: Path, binding: dict[str, str], *, status: str = "passed"
) -> dict[str, str]:
    raw = {
        "objectId": "article-001",
        "objectRef": "objects/posts/article/article-001",
        "objectDigest": "sha256:" + "0" * 64,
        "specRef": SPEC_REF,
        "caseId": "baseline-article-001",
        "producer": "app",
        "layer": "user_acceptance",
        "status": status,
        "target": {"kind": "page", "id": "content.feed.list"},
        "commitSha": "a" * 40,
        "contractGraphSourceHash": "b" * 64,
        "deploymentTarget": "alpha-local",
        "baselineId": "baseline-app-uat",
        "packageDigest": _digest("c"),
        "configurationDigest": _digest("d"),
        "candidateManifestSha256": "e" * 64,
        "releaseDigest": RELEASE_DIGEST,
        "releaseId": "release-a",
        "importRunId": "import-run-a",
        "verifyRunId": "verify-run-a",
        "targetUatBindingDigest": binding["digest"],
        "entrySurface": "feed",
        "carrier": "article",
        "environment": "alpha",
        "platform": "android",
        "deviceClass": "physical",
        "deviceRegistered": True,
        "provider": "first-party-https",
        "startedAt": "2026-08-29T07:00:00Z",
        "completedAt": "2026-08-29T07:01:00Z",
        "runnerIdentity": RUNNER,
        "artifactSha256": "f" * 64,
        "artifactPath": "alpha/raw-artifact.json",
        "deviceIdentity": "pixel-uat-01",
        "uatProfile": "promotable",
        "nonPromotable": False,
        "artifactClass": "production_behavior",
        "physicalDevice": True,
    }
    if status != "passed":
        raw["reasonCode"] = "APP.UAT.failed"
    source = _write(root, "alpha/raw.json", raw)
    return {
        **source,
        "slotId": acceptance.required_raw_slot_id(
            target_uat_binding_digest=binding["digest"],
            sample_id="baseline-article-001",
            entry_surface="feed",
            carrier="article",
            spec_ref=SPEC_REF,
            runner_identity=RUNNER,
        ),
        "status": status,
    }


def _ready(
    root: Path,
    name: str,
    status: str,
    *,
    environment: str = "alpha",
    target: str = "alpha-local",
) -> dict[str, str]:
    return _write(
        root,
        f"{environment}/{name}.json",
        {**_identity(environment, target), "status": status},
    )


def _acceptance_arguments(root: Path, store: Path) -> dict[str, object]:
    plan = _plan(root)
    binding = _binding(root, plan)
    raw = _raw(root, binding)
    active = _ready(root, "active-cas", "active")
    readback = _ready(root, "active-cas-readback", "passed")
    import_report = _ready(root, "import-report", "imported")
    data_readiness = _write(
        root,
        "alpha/data-readiness.json",
        {
            **_identity(),
            "passed": True,
            "manifestDigest": RELEASE_DIGEST,
            "activationEnvelope": {
                "importReportRef": import_report["ref"],
                "importReportDigest": import_report["digest"],
            },
        },
    )
    return {
        "evidence_root": root,
        "acceptance_root": store,
        "acceptance_profile": "environment_promotion",
        "environment": "alpha",
        "target": "alpha-local",
        "release_id": "release-a",
        "release_digest": RELEASE_DIGEST,
        "import_run_id": "import-run-a",
        "verify_run_id": "verify-run-a",
        "sample_plan_ref": plan["ref"],
        "sample_plan_digest": plan["digest"],
        "target_binding_refs": [{**binding, **PROFILE}],
        "required_raw_results": [raw],
        "required_target_profiles": [PROFILE],
        "data_readiness": data_readiness,
        "active_cas": {
            "ref": active["ref"],
            "digest": active["digest"],
            "readbackRef": readback["ref"],
            "readbackDigest": readback["digest"],
            "releaseId": "release-a",
            "releaseDigest": RELEASE_DIGEST,
        },
        "lifecycle_exit": _ready(root, "lifecycle-exit", "Exit"),
        "provider_readiness": _ready(root, "provider-readiness", "ready"),
        "observability_readiness": _ready(root, "observability-readiness", "ready"),
        "rollback_readiness": _ready(root, "rollback-readiness", "ready"),
        "predecessor_ref": None,
        "predecessor_digest": None,
        "predecessor_fact_id": None,
        "resource_finalization": {
            "leaseRevocationRefs": [_ready(root, "lease-revocation", "revoked")],
            "lockReleaseRefs": [_ready(root, "lock-release", "released")],
            "gcProtectionRefs": [_ready(root, "gc-protection", "protected")],
        },
        "prod_release_facts": None,
        "created_at": "2026-08-29T07:00:00Z",
        "source_fingerprint": _digest("f"),
    }


def _m1_acceptance_arguments(root: Path, store: Path) -> dict[str, object]:
    arguments = _acceptance_arguments(root, store)
    entries = ("feed", "search", "recommendation", "direct_or_object_route")
    carriers = ("homepage", "article", "image", "video")
    plan = {
        "schema": "quwoquan_data.release_uat_sample_plan",
        "releaseId": "release-a",
        "releaseDigest": RELEASE_DIGEST,
        "samples": [
            {
                "sampleId": f"baseline-{carrier}-001",
                "carrier": carrier,
                "objectId": f"{carrier}-001",
                "objectRef": (
                    f"objects/entities/{carrier}-001"
                    if carrier == "homepage"
                    else f"objects/posts/{carrier}/{carrier}-001"
                ),
                "objectDigest": _digest(str(index)),
            }
            for index, carrier in enumerate(carriers, 1)
        ],
        "entryCarrierCells": [
            {
                "entry": entry,
                "carrier": carrier,
                "applicability": "required",
                "specRef": SPEC_REF,
                "runnerClass": f"qwq_service.content_api.{entry}.{carrier}.v1",
            }
            for entry in entries
            for carrier in carriers
        ],
    }
    plan_ref = _write(root, "release/m1-sample-plan.json", plan)
    samples = {item["carrier"]: item for item in plan["samples"]}
    raw_results = []
    for cell in plan["entryCarrierCells"]:
        sample = samples[cell["carrier"]]
        raw = {
            "objectId": sample["objectId"],
            "objectRef": sample["objectRef"],
            "objectDigest": sample["objectDigest"],
            "specRef": cell["specRef"],
            "caseId": sample["sampleId"],
            "producer": "service",
            "layer": "api_integration",
            "status": "passed",
            "target": {"kind": "operation", "id": cell["entry"]},
            "commitSha": "a" * 40,
            "contractGraphSourceHash": "b" * 64,
            "deploymentTarget": "alpha-local",
            "baselineId": "baseline-m1-api-consumer",
            "packageDigest": "sha256:" + "c" * 64,
            "configurationDigest": "sha256:" + "d" * 64,
            "candidateManifestSha256": "e" * 64,
            "releaseId": "release-a",
            "releaseDigest": RELEASE_DIGEST,
            "importRunId": "import-run-a",
            "verifyRunId": "verify-run-a",
            "entrySurface": cell["entry"],
            "carrier": cell["carrier"],
            "environment": "alpha",
            "provider": "first-party-https",
            "startedAt": "2026-08-29T07:00:00Z",
            "completedAt": "2026-08-29T07:01:00Z",
            "runnerIdentity": cell["runnerClass"],
            "artifactSha256": "f" * 64,
            "artifactPath": f"alpha/m1-{cell['entry']}-{cell['carrier']}-artifact.json",
        }
        observation = {
            "schema": "qwq.content_api_consumer.observation.v1",
            "sampleId": sample["sampleId"],
            "entrySurface": cell["entry"],
            "carrier": cell["carrier"],
            "objectId": sample["objectId"],
            "runtimeObjectId": f"runtime-{cell['carrier']}-001",
            "releaseId": "release-a",
            "releaseDigest": RELEASE_DIGEST,
            "manifestDigest": MANIFEST_DIGEST,
            "importRunId": "import-run-a",
            "verifyRunId": "verify-run-a",
            "status": "passed",
            "startedAt": raw["startedAt"],
            "completedAt": raw["completedAt"],
            "http": {
                "method": "GET",
                "path": f"/{cell['entry']}",
                "status": 200,
                "requestId": "request-1",
                "traceId": "trace-1",
                "durationMs": 1,
                "responseSha256": _digest("9"),
            },
            "assertion": {"matchedRuntimeObjectId": f"runtime-{cell['carrier']}-001"},
        }
        observation_source = _write(
            root,
            f"alpha/m1-{cell['entry']}-{cell['carrier']}-artifact.json",
            observation,
        )
        raw["artifactSha256"] = observation_source["digest"].removeprefix("sha256:")
        source = _write(
            root,
            f"alpha/m1-raw-{cell['entry']}-{cell['carrier']}.json",
            raw,
        )
        raw_results.append(
            {
                **source,
                "slotId": acceptance.required_raw_slot_id(
                    sample_id=sample["sampleId"],
                    entry_surface=cell["entry"],
                    carrier=cell["carrier"],
                    spec_ref=cell["specRef"],
                    runner_identity=cell["runnerClass"],
                ),
                "status": "passed",
            }
        )
    data_path = root / str(arguments["data_readiness"]["ref"])
    data_payload = json.loads(data_path.read_text(encoding="utf-8"))
    data_payload["manifestDigest"] = MANIFEST_DIGEST
    data_path.write_bytes(
        (
            json.dumps(data_payload, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
    )
    arguments["data_readiness"]["digest"] = (
        "sha256:" + hashlib.sha256(data_path.read_bytes()).hexdigest()
    )
    source_health = _write(
        root,
        "alpha/source-content-consumer-health.json",
        {
            "command": "health",
            "target": "alpha-local",
            "scope": "content-consumer",
            **_identity(),
            "manifestDigest": MANIFEST_DIGEST,
            "findings": [],
            "generationIssues": [],
            "checks": [{"name": "content-api", "ok": True, "skipped": False}],
            "userAvailability": [
                {"name": name, "status": "ready", "issues": []}
                for name in acceptance._M1_REQUIRED_HEALTH_LAYERS
            ],
            "userAvailabilityReport": {
                "evidence": {
                    "content": {
                        "releaseId": "release-a",
                        "manifestDigest": MANIFEST_DIGEST,
                        "readinessReceiptRef": arguments["data_readiness"]["ref"],
                        "readinessReceiptDigest": arguments["data_readiness"]["digest"],
                        "releaseActive": True,
                        "exactQueriesReady": True,
                        "generationMatch": True,
                    }
                }
            },
        },
    )
    health_binding = _write(
        root,
        "alpha/consumer-health.json",
        {
            "schema": "qwq.content_api_consumer.health_binding.v1",
            "status": "passed",
            "environment": "alpha",
            "deploymentTarget": "alpha-local",
            "releaseId": "release-a",
            "releaseDigest": RELEASE_DIGEST,
            "manifestDigest": MANIFEST_DIGEST,
            "importRunId": "import-run-a",
            "verifyRunId": "verify-run-a",
            "sourceHealth": source_health,
            "requiredLayers": list(acceptance._M1_REQUIRED_HEALTH_LAYERS),
        },
    )
    arguments.update(
        {
            "acceptance_profile": "m1_api_consumer",
            "sample_plan_ref": plan_ref["ref"],
            "sample_plan_digest": plan_ref["digest"],
            "target_binding_refs": [],
            "required_raw_results": raw_results,
            "required_target_profiles": [],
            "manifest_digest": MANIFEST_DIGEST,
            "consumer_health": health_binding,
            "active_cas": None,
            "lifecycle_exit": None,
            "provider_readiness": None,
            "observability_readiness": None,
            "rollback_readiness": None,
            "resource_finalization": None,
            "prod_release_facts": None,
        }
    )
    arguments["source_fingerprint"] = acceptance.derive_m1_source_fingerprint(
        environment="alpha",
        target="alpha-local",
        release_id="release-a",
        release_digest=RELEASE_DIGEST,
        manifest_digest=MANIFEST_DIGEST,
        import_run_id="import-run-a",
        verify_run_id="verify-run-a",
        sample_plan=plan_ref,
        data_readiness=arguments["data_readiness"],
        consumer_health=health_binding,
        required_raw_results=raw_results,
    )
    return arguments


def _source_cli(name: str, source: object) -> list[str]:
    assert isinstance(source, dict)
    return [
        f"--{name}-ref",
        str(source["ref"]),
        f"--{name}-digest",
        str(source["digest"]),
    ]


def _m1_cli_arguments(arguments: dict[str, object]) -> list[str]:
    health = arguments["consumer_health"]
    assert isinstance(health, dict)
    command = [
        "--output-format",
        "json",
        "environment-acceptance-append",
        "--evidence-root",
        str(arguments["evidence_root"]),
        "--acceptance-root",
        str(arguments["acceptance_root"]),
        "--acceptance-profile",
        str(arguments["acceptance_profile"]),
        "--environment",
        str(arguments["environment"]),
        "--target",
        str(arguments["target"]),
        "--release-id",
        str(arguments["release_id"]),
        "--release-digest",
        str(arguments["release_digest"]),
        "--manifest-digest",
        str(arguments["manifest_digest"]),
        "--import-run-id",
        str(arguments["import_run_id"]),
        "--verify-run-id",
        str(arguments["verify_run_id"]),
        "--sample-plan-ref",
        str(arguments["sample_plan_ref"]),
        "--sample-plan-digest",
        str(arguments["sample_plan_digest"]),
        "--data-readiness-ref",
        str(arguments["data_readiness"]["ref"]),
        "--data-readiness-digest",
        str(arguments["data_readiness"]["digest"]),
        "--consumer-health-ref",
        str(health["ref"]),
        "--consumer-health-digest",
        str(health["digest"]),
        "--created-at",
        str(arguments["created_at"]),
    ]
    command.extend(["--source-fingerprint", str(arguments["source_fingerprint"])])
    for raw in arguments["required_raw_results"]:
        command.extend(
            [
                "--required-raw",
                f"{raw['slotId']}={raw['status']}={raw['ref']}={raw['digest']}",
            ]
        )
    return command


def test_stackctl_parser_registers_only_explicit_uat_evidence_surfaces() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subject.register_parser(subparsers)
    bind = parser.parse_args(
        [
            "app-uat-target-bind",
            "--evidence-root",
            "/tmp/evidence",
            "--binding-output-root",
            "/tmp/evidence",
            "--runtime-binding-ref",
            "runtime.json",
            "--runtime-binding-digest",
            _digest("1"),
            "--launch-binding-ref",
            "launch.json",
            "--launch-binding-digest",
            _digest("2"),
            "--sample-plan-ref",
            "plan.json",
            "--sample-plan-digest",
            _digest("3"),
            "--active-cas-ref",
            "active.json",
            "--active-cas-digest",
            _digest("4"),
            "--readback-ref",
            "readback.json",
            "--readback-digest",
            _digest("5"),
            "--artifact-class",
            "production_behavior",
            "--build-mode",
            "release",
            "--build-profile",
            "nonprod",
            "--provider-identity",
            "first-party-https",
            "--provider-class",
            "first_party",
            "--provider-type",
            "https",
            "--provider-registered",
            "--provider-conformance-ref",
            "env/provider/conformance.json",
            "--provider-conformance-digest",
            _digest("f"),
            "--device-identity",
            "pixel-uat-01",
            "--device-class",
            "physical",
            "--device-registered",
            "--runner-identity",
            "app-content-uat",
            "--runner-source-path",
            "runner/app_uat.dart",
            "--runner-digest",
            _digest("6"),
            "--runner-registered",
            "--profile",
            "promotable",
            "--no-non-promotable",
            "--created-at",
            "2026-08-29T07:00:00Z",
        ]
    )
    assert bind.command == "app-uat-target-bind"
    assert bind.device_registered is True and bind.non_promotable is False
    with pytest.raises(SystemExit):
        parser.parse_args(["app-uat-bundle", "--evidence-root", "/tmp/evidence"])
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["environment-acceptance-append", "--evidence-root", "/tmp/evidence"]
        )

    from quwoquan_ops.cli import stackctl

    stackctl_parser = stackctl.build_parser()
    assert (
        stackctl_parser.parse_args(
            [
                "app-uat-bundle",
                "--evidence-root",
                "/tmp/evidence",
                "--sample-plan-ref",
                "plan.json",
                "--sample-plan-digest",
                _digest("1"),
                "--target-binding",
                f"binding.json={_digest('2')}",
                "--raw-result",
                f"raw.json={_digest('3')}",
                "--output-ref",
                "projections/bundle.json",
                "--generated-at",
                "2026-08-29T07:00:00Z",
            ]
        ).command
        == "app-uat-bundle"
    )
    assert set(subject.COMMAND_HANDLERS) == {
        "app-uat-target-bind",
        "app-uat-bundle",
        "environment-acceptance-append",
    }


def test_command_handlers_translate_library_failures_to_typed_gate_block(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    args = argparse.Namespace(
        evidence_root=str(root),
        sample_plan_ref="plan.json",
        sample_plan_digest=_digest("1"),
        target_binding=[f"binding.json={_digest('2')}"],
        raw_result=[f"raw.json={_digest('3')}"],
        output_ref="projections/bundle.json",
        generated_at="2026-08-29T07:00:00Z",
    )
    result = subject.command_app_uat_bundle(args)
    assert result["exitCode"] == 2
    assert result["status"] == "GATE_BLOCK"
    assert str(result["blockerCode"]).startswith("OPS.")


def test_explicit_argument_shapes_reject_bundle_or_opaque_json_substitution() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subject.register_parser(subparsers)
    args = parser.parse_args(
        [
            "app-uat-bundle",
            "--evidence-root",
            "/tmp/evidence",
            "--sample-plan-ref",
            "plan.json",
            "--sample-plan-digest",
            _digest("1"),
            "--target-binding",
            '{"ref":"binding.json","digest":"' + _digest("2") + '"}',
            "--raw-result",
            f"raw.json={_digest('3')}",
            "--output-ref",
            "projection.json",
            "--generated-at",
            "2026-08-29T07:00:00Z",
        ]
    )
    result = subject.command_app_uat_bundle(args)
    assert result["status"] == "GATE_BLOCK"
    assert result["blockerCode"] == "OPS.APP_UAT_EVIDENCE.invalid_argument"


def test_output_roots_must_remain_inside_evidence_root(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    runtime = _write(
        root,
        "runtime.json",
        {
            "environment": "alpha",
            "target": "alpha-local",
            "releaseId": "release-a",
            "manifestDigest": RELEASE_DIGEST,
            "candidateDigest": _digest("2"),
            "packageDigest": _digest("3"),
            "runtimeConfigDigest": _digest("4"),
            "environmentRuntimeDigest": _digest("5"),
            "startupIdentity": {"configurationDigest": _digest("6")},
        },
    )
    launch = _write(
        root,
        "launch.json",
        {
            "environment": "alpha",
            "target": "alpha-local",
            "platform": "android",
            "deviceId": "pixel-uat-01",
            "artifactDigest": _digest("7"),
            "applicationId": "com.leadwise.quwoquan.nonprod",
        },
    )
    plan = _plan(root)
    active = _ready(root, "active", "active")
    readback = _ready(root, "readback", "passed")
    with pytest.raises(
        subject.AppUatEvidenceCommandError, match="contained by evidenceRoot"
    ):
        subject.build_target_uat_binding_command(
            evidence_root=root,
            output_root=outside,
            runtime_binding_ref=runtime["ref"],
            runtime_binding_digest=runtime["digest"],
            launch_binding_ref=launch["ref"],
            launch_binding_digest=launch["digest"],
            sample_plan_ref=plan["ref"],
            sample_plan_digest=plan["digest"],
            active_cas_ref=active["ref"],
            active_cas_digest=active["digest"],
            readback_ref=readback["ref"],
            readback_digest=readback["digest"],
            artifact_class="production_behavior",
            build_mode="release",
            build_profile="nonprod",
            provider_identity="first-party-https",
            provider_class="first_party",
            provider_type="https",
            provider_registered=True,
            provider_conformance_ref="env/provider/conformance.json",
            provider_conformance_digest=_digest("f"),
            device_identity="pixel-uat-01",
            device_class="physical",
            device_registered=True,
            runner_identity="app-content-uat",
            runner_source_path="runner/app_uat.dart",
            runner_digest=_digest("8"),
            runner_registered=True,
            profile="promotable",
            non_promotable=False,
            created_at="2026-08-29T07:00:00Z",
        )


def test_target_bind_requires_complete_activation_readback_and_is_create_once(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    runtime = _write(
        root,
        "runtime.json",
        {
            "environment": "alpha",
            "target": "alpha-local",
            "releaseId": "release-a",
            "manifestDigest": RELEASE_DIGEST,
            "candidateDigest": _digest("2"),
            "packageDigest": _digest("3"),
            "runtimeConfigDigest": _digest("4"),
            "environmentRuntimeDigest": _digest("5"),
            "startupIdentity": {"configurationDigest": _digest("6")},
        },
    )
    launch = _write(
        root,
        "launch.json",
        {
            "environment": "alpha",
            "target": "alpha-local",
            "platform": "android",
            "deviceId": "pixel-uat-01",
            "artifactDigest": _digest("7"),
            "applicationId": "com.leadwise.quwoquan.nonprod",
        },
    )
    plan = _plan(root)
    active = _ready(root, "active", "active")
    readback = _ready(root, "readback", "passed")
    arguments = {
        "evidence_root": root,
        "output_root": root,
        "runtime_binding_ref": runtime["ref"],
        "runtime_binding_digest": runtime["digest"],
        "launch_binding_ref": launch["ref"],
        "launch_binding_digest": launch["digest"],
        "sample_plan_ref": plan["ref"],
        "sample_plan_digest": plan["digest"],
        "active_cas_ref": active["ref"],
        "active_cas_digest": active["digest"],
        "readback_ref": readback["ref"],
        "readback_digest": readback["digest"],
        "artifact_class": "production_behavior",
        "build_mode": "release",
        "build_profile": "nonprod",
        "provider_identity": "first-party-https",
        "provider_class": "first_party",
        "provider_type": "https",
        "provider_registered": True,
        "provider_conformance_ref": "env/provider/conformance.json",
        "provider_conformance_digest": _digest("f"),
        "device_identity": "pixel-uat-01",
        "device_class": "physical",
        "device_registered": True,
        "runner_identity": "app-content-uat",
        "runner_source_path": "runner/app_uat.dart",
        "runner_digest": _digest("8"),
        "runner_registered": True,
        "profile": "promotable",
        "non_promotable": False,
        "created_at": "2026-08-29T07:00:00Z",
    }
    first = subject.build_target_uat_binding_command(**arguments)
    second = subject.build_target_uat_binding_command(**arguments)
    assert first["created"] is True and second["created"] is False
    assert first["bindingDigest"] == second["bindingDigest"]
    blocked = _ready(root, "readback-blocked", "pending")
    with pytest.raises(
        subject.AppUatEvidenceCommandError, match="activation_incomplete"
    ):
        subject.build_target_uat_binding_command(
            **{
                **arguments,
                "readback_ref": blocked["ref"],
                "readback_digest": blocked["digest"],
            }
        )


def test_failed_raw_does_not_append_and_bundle_cannot_substitute_raw(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    store = root / "acceptance-facts"
    root.mkdir()
    store.mkdir()
    arguments = _acceptance_arguments(root, store)
    failed_source = _raw(root, arguments["target_binding_refs"][0], status="failed")
    failed = {**arguments, "required_raw_results": [failed_source]}
    with pytest.raises(
        acceptance.EnvironmentAcceptanceFactError, match="exactly passed"
    ):
        subject.build_environment_acceptance_append_command(**failed)
    assert list(store.iterdir()) == []

    bundle = _write(
        root,
        "projections/app-uat.json",
        {
            "schema": "quwoquan_ops.app_uat_result_bundle.v1",
            "generatedAt": "2026-08-29T07:00:00Z",
        },
    )
    substituted = {
        **arguments,
        "required_raw_results": [
            {"bundleRef": bundle["ref"], "bundleDigest": bundle["digest"]}
        ],
    }
    with pytest.raises(
        acceptance.EnvironmentAcceptanceFactError, match="bundle substitution"
    ):
        subject.build_environment_acceptance_append_command(**substituted)
    assert list(store.iterdir()) == []


def test_m1_api_consumer_append_is_same_builder_and_create_once(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    store = root / "acceptance-facts"
    root.mkdir()
    store.mkdir()
    arguments = _m1_acceptance_arguments(root, store)
    first = subject.build_environment_acceptance_append_command(**arguments)
    second = subject.build_environment_acceptance_append_command(**arguments)
    assert first["factId"] == second["factId"]
    assert first["factDigest"] == second["factDigest"]
    fact = json.loads((root / first["factRef"]).read_text(encoding="utf-8"))
    assert fact["acceptanceProfile"] == "m1_api_consumer"
    assert fact["releaseDigest"] == RELEASE_DIGEST
    assert fact["manifestDigest"] == MANIFEST_DIGEST
    assert fact["releaseDigest"] != fact["manifestDigest"]
    assert "targetBindingRefs" not in fact
    assert set(fact["consumerHealth"]) == {"ref", "digest"}
    assert len(fact["requiredRawResults"]) == 16
    assert len(list((store / "alpha").glob("*.json"))) == 1


def test_m1_api_consumer_public_command_rejects_promotion_only_arguments(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    store = root / "acceptance-facts"
    root.mkdir()
    store.mkdir()
    arguments = _m1_acceptance_arguments(root, store)
    forbidden_cases = (
        ({"required_raw_results": []}, "requiredRawResults must be non-empty"),
        (
            {"required_raw_results": arguments["required_raw_results"][:-1]},
            "exactly 16",
        ),
        (
            {"target_binding_refs": [{"ref": "binding.json"}]},
            "must not provide targetBinding",
        ),
        ({"required_target_profiles": [PROFILE]}, "must not provide requiredProfile"),
        (
            {
                "predecessor_ref": "facts/alpha.json",
                "predecessor_digest": _digest("8"),
                "predecessor_fact_id": _digest("9"),
            },
            "must not provide predecessor",
        ),
        (
            {"prod_release_facts": {"unexpected": "fact"}},
            "must not provide prodReleaseFacts",
        ),
    )
    for changes, message in forbidden_cases:
        with pytest.raises(subject.AppUatEvidenceCommandError, match=message):
            subject.build_environment_acceptance_append_command(
                **{**arguments, **changes}
            )

    first_raw = arguments["required_raw_results"][0]
    first_path = root / first_raw["ref"]
    first_payload = json.loads(first_path.read_text(encoding="utf-8"))
    first_payload["deviceId"] = "forbidden-device"
    first_path.write_text(
        json.dumps(first_payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    first_raw["digest"] = acceptance.exact_byte_digest(first_path)
    arguments["source_fingerprint"] = acceptance.derive_m1_source_fingerprint(
        environment="alpha",
        target="alpha-local",
        release_id="release-a",
        release_digest=RELEASE_DIGEST,
        manifest_digest=MANIFEST_DIGEST,
        import_run_id="import-run-a",
        verify_run_id="verify-run-a",
        sample_plan={
            "ref": arguments["sample_plan_ref"],
            "digest": arguments["sample_plan_digest"],
        },
        data_readiness=arguments["data_readiness"],
        consumer_health=arguments["consumer_health"],
        required_raw_results=arguments["required_raw_results"],
    )
    with pytest.raises(
        acceptance.EnvironmentAcceptanceFactError, match="canonical ReadinessCaseResult"
    ):
        subject.build_environment_acceptance_append_command(**arguments)
    assert list(store.iterdir()) == []


def test_environment_promotion_public_command_keeps_existing_authority_requirements(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    store = root / "acceptance-facts"
    root.mkdir()
    store.mkdir()
    arguments = _acceptance_arguments(root, store)
    for changes, message in (
        ({"target_binding_refs": []}, "requires targetBinding"),
        ({"required_target_profiles": []}, "requires requiredProfile"),
    ):
        with pytest.raises(subject.AppUatEvidenceCommandError, match=message):
            subject.build_environment_acceptance_append_command(
                **{**arguments, **changes}
            )

    beta = {
        **arguments,
        "environment": "beta",
        "target": "beta-local",
        "predecessor_ref": None,
        "predecessor_digest": None,
        "predecessor_fact_id": None,
    }
    with pytest.raises(
        acceptance.EnvironmentAcceptanceFactError, match="requires exact alpha"
    ):
        subject.build_environment_acceptance_append_command(**beta)
    assert list(store.iterdir()) == []


def test_public_stackctl_m1_api_consumer_exact_create_once(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    store = root / "acceptance-facts"
    root.mkdir()
    store.mkdir()
    arguments = _m1_acceptance_arguments(root, store)
    command = [
        sys.executable,
        "-B",
        str(Path(subject.__file__).parents[1] / "stackctl.py"),
        *_m1_cli_arguments(arguments),
    ]
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": str(tmp_path / "python-cache"),
    }
    first = subprocess.run(
        command,
        cwd=Path(subject.__file__).parents[3],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        command,
        cwd=Path(subject.__file__).parents[3],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr or first.stdout
    assert second.returncode == 0, second.stderr or second.stdout
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    assert first_payload["factId"] == second_payload["factId"]
    assert first_payload["factDigest"] == second_payload["factDigest"]
    assert len(list((store / "alpha").glob("*.json"))) == 1


def test_predecessor_drift_blocks_before_fact_builder_and_create_once_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "evidence"
    store = root / "acceptance-facts"
    root.mkdir()
    store.mkdir()
    arguments = _acceptance_arguments(root, store)
    first = subject.build_environment_acceptance_append_command(**arguments)
    second = subject.build_environment_acceptance_append_command(**arguments)
    assert first["factId"] == second["factId"]
    assert len(list((store / "alpha").glob("*.json"))) == 1

    called = False

    def forbidden_builder(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("predecessor must fail before builder")

    monkeypatch.setattr(subject, "build_environment_acceptance_fact", forbidden_builder)
    beta = {
        **arguments,
        "environment": "beta",
        "target": "beta-local",
        "predecessor_ref": first["factRef"],
        "predecessor_digest": _digest("9"),
        "predecessor_fact_id": first["factId"],
    }
    with pytest.raises(
        acceptance.EnvironmentAcceptanceFactError, match="exact bytes drifted"
    ):
        subject.build_environment_acceptance_append_command(**beta)
    assert called is False


def test_m1_cli_rejects_caller_fingerprint_and_wrong_manifest_digest(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    store = root / "acceptance-facts"
    root.mkdir()
    store.mkdir()
    arguments = _m1_acceptance_arguments(root, store)
    with pytest.raises(subject.AppUatEvidenceCommandError, match="sourceFingerprint"):
        subject.build_environment_acceptance_append_command(
            **{**arguments, "source_fingerprint": _digest("a")}
        )
    with pytest.raises(subject.AppUatEvidenceCommandError, match="sourceFingerprint"):
        subject.build_environment_acceptance_append_command(
            **{**arguments, "manifest_digest": RELEASE_DIGEST}
        )
