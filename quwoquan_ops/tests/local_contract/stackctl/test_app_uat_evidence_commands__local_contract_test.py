"""Ops UAT five-layer primitive command wiring contract.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-006
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

from quwoquan_ops.cli.commands import app_uat_evidence as subject
from quwoquan_ops.cli.lib import environment_acceptance_fact as acceptance

RELEASE_DIGEST = "sha256:" + "1" * 64
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


def _identity(environment: str = "alpha", target: str = "alpha-local") -> dict[str, str]:
    return {
        "environment": environment,
        "target": target,
        "deploymentTarget": target,
        "releaseId": "release-a",
        "releaseDigest": RELEASE_DIGEST,
    }


def _plan(root: Path) -> dict[str, str]:
    entries = ("feed", "search", "recommendation", "direct_or_object_route")
    carriers = ("homepage", "article", "image", "video")
    cells = []
    for entry in entries:
        for carrier in carriers:
            if (entry, carrier) == ("feed", "article"):
                cells.append({
                    "entry": entry,
                    "carrier": carrier,
                    "applicability": "required",
                    "specRef": SPEC_REF,
                    "runnerClass": RUNNER,
                })
            else:
                cells.append({
                    "entry": entry,
                    "carrier": carrier,
                    "applicability": "not_applicable",
                    "reasonCode": "APP.UAT.NOT_APPLICABLE",
                })
    plan = {
        "schema": "quwoquan_data.release_uat_sample_plan",
        "releaseId": "release-a",
        "releaseDigest": RELEASE_DIGEST,
        "samples": [
            {
                "sampleId": "m100-article-001",
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
        **_identity(),
        "producer": "app",
        "layer": "user_acceptance",
        "status": status,
        "caseId": "m100-article-001",
        "targetUatBindingDigest": binding["digest"],
        "objectId": "article-001",
        "entrySurface": "feed",
        "carrier": "article",
        "specRef": SPEC_REF,
        "runnerIdentity": RUNNER,
        "platform": "android",
        "provider": "first-party-https",
        "uatProfile": "promotable",
    }
    source = _write(root, "alpha/raw.json", raw)
    return {
        **source,
        "slotId": acceptance.required_raw_slot_id(
            target_uat_binding_digest=binding["digest"],
            sample_id="m100-article-001",
            entry_surface="feed",
            carrier="article",
            spec_ref=SPEC_REF,
            runner_identity=RUNNER,
        ),
        "status": status,
    }


def _ready(
    root: Path, name: str, status: str, *, environment: str = "alpha", target: str = "alpha-local"
) -> dict[str, str]:
    return _write(root, f"{environment}/{name}.json", {**_identity(environment, target), "status": status})


def _acceptance_arguments(root: Path, store: Path) -> dict[str, object]:
    plan = _plan(root)
    binding = _binding(root, plan)
    raw = _raw(root, binding)
    active = _ready(root, "active-cas", "active")
    readback = _ready(root, "active-cas-readback", "passed")
    return {
        "evidence_root": root,
        "acceptance_root": store,
        "environment": "alpha",
        "target": "alpha-local",
        "release_id": "release-a",
        "release_digest": RELEASE_DIGEST,
        "sample_plan_ref": plan["ref"],
        "sample_plan_digest": plan["digest"],
        "target_binding_refs": [{**binding, **PROFILE}],
        "required_raw_results": [raw],
        "required_target_profiles": [PROFILE],
        "data_readiness": _ready(root, "data-readiness", "passed"),
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


def test_stackctl_parser_registers_only_explicit_uat_evidence_surfaces() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subject.register_parser(subparsers)
    bind = parser.parse_args([
        "app-uat-target-bind",
        "--evidence-root", "/tmp/evidence",
        "--binding-output-root", "/tmp/evidence",
        "--runtime-binding-ref", "runtime.json",
        "--runtime-binding-digest", _digest("1"),
        "--launch-binding-ref", "launch.json",
        "--launch-binding-digest", _digest("2"),
        "--sample-plan-ref", "plan.json",
        "--sample-plan-digest", _digest("3"),
        "--active-cas-ref", "active.json",
        "--active-cas-digest", _digest("4"),
        "--readback-ref", "readback.json",
        "--readback-digest", _digest("5"),
        "--artifact-class", "production_behavior",
        "--build-mode", "release",
        "--build-profile", "nonprod",
        "--provider-identity", "first-party-https",
        "--provider-class", "first_party",
        "--provider-type", "https",
        "--provider-registered",
        "--provider-conformance-ref", "env/provider/conformance.json",
        "--provider-conformance-digest", _digest("f"),
        "--device-identity", "pixel-uat-01",
        "--device-class", "physical",
        "--device-registered",
        "--runner-identity", "app-content-uat",
        "--runner-source-path", "runner/app_uat.dart",
        "--runner-digest", _digest("6"),
        "--runner-registered",
        "--profile", "promotable",
        "--no-non-promotable",
        "--created-at", "2026-08-29T07:00:00Z",
    ])
    assert bind.command == "app-uat-target-bind"
    assert bind.device_registered is True and bind.non_promotable is False
    with pytest.raises(SystemExit):
        parser.parse_args(["app-uat-bundle", "--evidence-root", "/tmp/evidence"])
    with pytest.raises(SystemExit):
        parser.parse_args(["environment-acceptance-append", "--evidence-root", "/tmp/evidence"])


    from quwoquan_ops.cli import stackctl

    stackctl_parser = stackctl.build_parser()
    assert stackctl_parser.parse_args([
        "app-uat-bundle",
        "--evidence-root", "/tmp/evidence",
        "--sample-plan-ref", "plan.json",
        "--sample-plan-digest", _digest("1"),
        "--target-binding", f"binding.json={_digest('2')}",
        "--raw-result", f"raw.json={_digest('3')}",
        "--output-ref", "projections/bundle.json",
        "--generated-at", "2026-08-29T07:00:00Z",
    ]).command == "app-uat-bundle"
    assert set(subject.COMMAND_HANDLERS) == {
        "app-uat-target-bind",
        "app-uat-bundle",
        "environment-acceptance-append",
    }


def test_command_handlers_translate_library_failures_to_typed_gate_block(tmp_path: Path) -> None:
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
    args = parser.parse_args([
        "app-uat-bundle",
        "--evidence-root", "/tmp/evidence",
        "--sample-plan-ref", "plan.json",
        "--sample-plan-digest", _digest("1"),
        "--target-binding", '{"ref":"binding.json","digest":"' + _digest("2") + '"}',
        "--raw-result", f"raw.json={_digest('3')}",
        "--output-ref", "projection.json",
        "--generated-at", "2026-08-29T07:00:00Z",
    ])
    result = subject.command_app_uat_bundle(args)
    assert result["status"] == "GATE_BLOCK"
    assert result["blockerCode"] == "OPS.APP_UAT_EVIDENCE.invalid_argument"


def test_output_roots_must_remain_inside_evidence_root(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    runtime = _write(root, "runtime.json", {
        "environment": "alpha", "target": "alpha-local", "releaseId": "release-a",
        "manifestDigest": RELEASE_DIGEST, "candidateDigest": _digest("2"),
        "packageDigest": _digest("3"), "runtimeConfigDigest": _digest("4"),
        "environmentRuntimeDigest": _digest("5"),
        "startupIdentity": {"configurationDigest": _digest("6")},
    })
    launch = _write(root, "launch.json", {
        "environment": "alpha", "target": "alpha-local", "platform": "android",
        "deviceId": "pixel-uat-01", "artifactDigest": _digest("7"),
        "applicationId": "com.leadwise.quwoquan.nonprod",
    })
    plan = _plan(root)
    active = _ready(root, "active", "active")
    readback = _ready(root, "readback", "passed")
    with pytest.raises(subject.AppUatEvidenceCommandError, match="contained by evidenceRoot"):
        subject.build_target_uat_binding_command(
            evidence_root=root, output_root=outside,
            runtime_binding_ref=runtime["ref"], runtime_binding_digest=runtime["digest"],
            launch_binding_ref=launch["ref"], launch_binding_digest=launch["digest"],
            sample_plan_ref=plan["ref"], sample_plan_digest=plan["digest"],
            active_cas_ref=active["ref"], active_cas_digest=active["digest"],
            readback_ref=readback["ref"], readback_digest=readback["digest"],
            artifact_class="production_behavior", build_mode="release",
            build_profile="nonprod", provider_identity="first-party-https",
            provider_class="first_party", provider_type="https",
            provider_registered=True,
            provider_conformance_ref="env/provider/conformance.json",
            provider_conformance_digest=_digest("f"),
            device_identity="pixel-uat-01",
            device_class="physical", device_registered=True,
            runner_identity="app-content-uat", runner_source_path="runner/app_uat.dart",
            runner_digest=_digest("8"), runner_registered=True,
            profile="promotable",
            non_promotable=False, created_at="2026-08-29T07:00:00Z",
        )


def test_target_bind_requires_complete_activation_readback_and_is_create_once(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    runtime = _write(root, "runtime.json", {
        "environment": "alpha", "target": "alpha-local", "releaseId": "release-a",
        "manifestDigest": RELEASE_DIGEST, "candidateDigest": _digest("2"),
        "packageDigest": _digest("3"), "runtimeConfigDigest": _digest("4"),
        "environmentRuntimeDigest": _digest("5"),
        "startupIdentity": {"configurationDigest": _digest("6")},
    })
    launch = _write(root, "launch.json", {
        "environment": "alpha", "target": "alpha-local", "platform": "android",
        "deviceId": "pixel-uat-01", "artifactDigest": _digest("7"),
        "applicationId": "com.leadwise.quwoquan.nonprod",
    })
    plan = _plan(root)
    active = _ready(root, "active", "active")
    readback = _ready(root, "readback", "passed")
    arguments = {
        "evidence_root": root, "output_root": root,
        "runtime_binding_ref": runtime["ref"], "runtime_binding_digest": runtime["digest"],
        "launch_binding_ref": launch["ref"], "launch_binding_digest": launch["digest"],
        "sample_plan_ref": plan["ref"], "sample_plan_digest": plan["digest"],
        "active_cas_ref": active["ref"], "active_cas_digest": active["digest"],
        "readback_ref": readback["ref"], "readback_digest": readback["digest"],
        "artifact_class": "production_behavior", "build_mode": "release",
        "build_profile": "nonprod", "provider_identity": "first-party-https",
        "provider_class": "first_party", "provider_type": "https",
        "provider_registered": True,
        "provider_conformance_ref": "env/provider/conformance.json",
        "provider_conformance_digest": _digest("f"),
        "device_identity": "pixel-uat-01",
        "device_class": "physical", "device_registered": True,
        "runner_identity": "app-content-uat", "runner_source_path": "runner/app_uat.dart",
        "runner_digest": _digest("8"), "runner_registered": True,
        "profile": "promotable",
        "non_promotable": False, "created_at": "2026-08-29T07:00:00Z",
    }
    first = subject.build_target_uat_binding_command(**arguments)
    second = subject.build_target_uat_binding_command(**arguments)
    assert first["created"] is True and second["created"] is False
    assert first["bindingDigest"] == second["bindingDigest"]
    blocked = _ready(root, "readback-blocked", "pending")
    with pytest.raises(subject.AppUatEvidenceCommandError, match="activation_incomplete"):
        subject.build_target_uat_binding_command(
            **{**arguments, "readback_ref": blocked["ref"], "readback_digest": blocked["digest"]}
        )


def test_failed_raw_does_not_append_and_bundle_cannot_substitute_raw(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    store = root / "acceptance-facts"
    root.mkdir()
    store.mkdir()
    arguments = _acceptance_arguments(root, store)
    failed_source = _raw(root, arguments["target_binding_refs"][0], status="failed")
    failed = {**arguments, "required_raw_results": [failed_source]}
    with pytest.raises(acceptance.EnvironmentAcceptanceFactError, match="exactly passed"):
        subject.build_environment_acceptance_append_command(**failed)
    assert list(store.iterdir()) == []

    bundle = _write(root, "projections/app-uat.json", {
        "schema": "quwoquan_ops.app_uat_result_bundle.v1",
        "generatedAt": "2026-08-29T07:00:00Z",
    })
    substituted = {
        **arguments,
        "required_raw_results": [{"bundleRef": bundle["ref"], "bundleDigest": bundle["digest"]}],
    }
    with pytest.raises(acceptance.EnvironmentAcceptanceFactError, match="bundle substitution"):
        subject.build_environment_acceptance_append_command(**substituted)
    assert list(store.iterdir()) == []


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
    with pytest.raises(acceptance.EnvironmentAcceptanceFactError, match="exact bytes drifted"):
        subject.build_environment_acceptance_append_command(**beta)
    assert called is False
