"""AppUatResultBundle diagnostic completeness projection contract.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-004
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from quwoquan_ops.cli.lib import app_uat_result_bundle as subject
from quwoquan_ops.cli.lib.target_uat_binding import build_target_uat_binding

ROOT = Path(__file__).resolve().parents[4]
SCHEMA_PATH = ROOT / "quwoquan_ops/environments/evidence/app_uat_result_bundle.schema.json"
READINESS_SCHEMA = ROOT / "quwoquan_service/contracts/metadata/_schemas/readiness_result_bundle.schema.json"
PLAN_REF = "data/releases/release-a/uat/sample_plan.json"
RELEASE_DIGEST = "sha256:" + "1" * 64
SPEC = "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-004"
ENTRIES = ("feed", "search", "recommendation", "direct_or_object_route")
CARRIERS = ("homepage", "article", "image", "video")


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _write(root: Path, ref: str, value: object, *, duplicate_key: str | None = None) -> dict[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    if duplicate_key is None:
        encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    else:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        encoded = encoded[:-1] + f',"{duplicate_key}":"duplicate"}}\n'.encode()
    path.write_bytes(encoded)
    return {"ref": ref, "digest": "sha256:" + hashlib.sha256(encoded).hexdigest()}


def _plan(root: Path, *, na: tuple[str, str] | None = ("recommendation", "video")) -> dict[str, str]:
    cells = []
    for entry in ENTRIES:
        for carrier in CARRIERS:
            if na == (entry, carrier):
                cells.append({"entry": entry, "carrier": carrier, "applicability": "not_applicable", "reasonCode": "APP.UAT.NOT_APPLICABLE"})
            else:
                cells.append({"entry": entry, "carrier": carrier, "applicability": "required", "specRef": SPEC, "runnerClass": f"qwq.content_consumer.{entry}.{carrier}"})
    distribution = {"homepage": 25, "article": 25, "image": 40, "video": 10}
    release_digest = RELEASE_DIGEST
    plan = {
        "schema": "quwoquan_data.release_uat_sample_plan",
        "releaseId": "release-a",
        "releaseDigest": release_digest,
        "milestone": "M100",
        "selectionEvidence": {"poolDigest": _digest("a"), "sourceIdentitySetDigest": _digest("e"), "canonicalMerkle": _digest("b"), "releaseContentsDigest": _digest("c"), "releaseEntityCohortDigest": _digest("d")},
        "eligiblePopulationCounts": {carrier: 100 for carrier in CARRIERS},
        "exactCohortCounts": {carrier: 100 for carrier in CARRIERS},
        "entryCarrierCells": cells,
        "sampleStrategy": {"name": "stratified_exact", "version": 1, "seedDigest": _digest("d"), "carrierOrder": list(CARRIERS), "sortKey": "identity", "direction": "ascending", "objectDigestAlgorithm": "sha256-path-blob-merkle", "sampleDistribution": distribution},
        "sampleCount": 100,
        "samples": [{"sampleId": f"m100-{carrier}-{index:03d}", "carrier": carrier, "objectId": (f"/entity/{carrier}-{index:03d}" if carrier == "homepage" else f"{carrier}-{index:03d}"), "objectRef": (f"objects/entities/{carrier}-{index:03d}" if carrier == "homepage" else f"objects/posts/{carrier}/{carrier}-{index:03d}"), "objectDigest": _digest("e")} for carrier, count in distribution.items() for index in range(1, count + 1)],
    }
    return _write(root, PLAN_REF, plan)


def _binding(root: Path, plan: dict[str, str], *, target: str, platform: str, device: str, profile: str = "rehearsal") -> dict[str, str]:
    runner = {
        "identity": "app-content-uat",
        "sourcePath": "quwoquan_app/test/user_acceptance/app_content_uat.dart",
        "digest": _digest("c"),
        "registered": profile != "rehearsal",
    }
    environment = target.removesuffix("-local")
    production = profile == "production"
    physical = profile != "rehearsal"
    value = build_target_uat_binding(
        runtime_binding={
            "environment": environment,
            "target": target,
            "releaseId": "release-a",
            "manifestDigest": RELEASE_DIGEST,
            "candidateDigest": _digest("2"),
            "packageDigest": _digest("4"),
            "runtimeConfigDigest": _digest("7"),
            "environmentRuntimeDigest": _digest("8"),
            "startupIdentity": {"configurationDigest": _digest("5")},
        },
        launch_binding={
            "environment": environment,
            "target": target,
            "platform": platform,
            "deviceId": device,
            "artifactDigest": _digest("b"),
            "applicationId": "com.leadwise.quwoquan.debug",
        },
        sample_plan_binding={
            "releaseId": "release-a",
            "releaseUatSamplePlanRef": plan["ref"],
            "releaseUatSamplePlanDigest": plan["digest"],
        },
        active_cas={"ref": f"env/{target}/active-cas.json", "digest": _digest("9")},
        readback={"ref": f"env/{target}/readback.json", "digest": _digest("a")},
        artifact_class="production" if production else "production_behavior",
        build_mode="release" if production else "debug",
        build_profile="prod" if production else "nonprod",
        provider={
            "identity": "first-party-https",
            "class": "first_party",
            "type": "https",
            "registered": physical,
            "conformanceEvidence": {
                "ref": "env/provider/conformance.json",
                "digest": _digest("f"),
            },
        },
        device={
            "identity": device,
            "class": "physical" if physical else ("emulator" if platform == "android" else "simulator"),
            "registered": physical,
        },
        runner=runner,
        profile=profile,
        non_promotable=not physical,
        created_at="2026-08-29T07:00:00Z",
    )
    return _write(root, f"env/{target}/bindings/{platform}-{device}.json", value)


def _raw(
    root: Path,
    binding: dict[str, str],
    *,
    target: str,
    platform: str,
    device: str,
    profile: str,
    entry: str,
    carrier: str,
    object_id: str | None = None,
    state: str = "passed",
    ref_suffix: str = "",
) -> dict[str, str]:
    runner = f"qwq.content_consumer.{entry}.{carrier}"
    selected_object_id = object_id or (
        f"/entity/{carrier}-001" if carrier == "homepage" else f"{carrier}-001"
    )
    artifact_ref = f"env/{target}/raw/artifact-{platform}-{device}-{entry}-{carrier}{ref_suffix}.bin"
    artifact_path = root / artifact_ref
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"receipt bytes")
    value = {
        "objectId": selected_object_id, "specRef": SPEC, "caseId": "app_content_uat", "producer": "app", "layer": "user_acceptance",
        "status": state, "target": {"kind": "page", "id": "content.feed"}, "commitSha": "c" * 40,
        "contractGraphSourceHash": "d" * 64, "deploymentTarget": target, "baselineId": "baseline-alpha",
        "packageDigest": _digest("4"), "configurationDigest": _digest("5"), "candidateManifestSha256": "6" * 64,
        "releaseDigest": RELEASE_DIGEST, "releaseId": "release-a", "targetUatBindingDigest": binding["digest"],
        "entrySurface": entry, "carrier": carrier, "deviceIdentity": device, "uatProfile": profile,
        "nonPromotable": profile == "rehearsal", "artifactClass": "production_behavior", "physicalDevice": profile != "rehearsal",
        "environment": target.removesuffix("-local"), "platform": platform, "deviceClass": "simulator" if profile == "rehearsal" else "physical",
        "provider": "first-party-https", "startedAt": "2026-08-29T07:00:00Z", "completedAt": "2026-08-29T07:01:00Z",
        "runnerIdentity": runner, "artifactSha256": hashlib.sha256(b"receipt bytes").hexdigest(), "artifactPath": artifact_ref,
    }
    if state != "passed":
        value["reasonCode"] = f"APP.UAT.{state}"
    return _write(root, f"env/{target}/raw/{platform}-{device}-{entry}-{carrier}{ref_suffix}.json", value)


def _setup(tmp_path: Path, *, bindings: int = 1) -> tuple[dict[str, str], list[dict[str, str]], list[dict[str, str]]]:
    plan = _plan(tmp_path)
    binding_sources = [_binding(tmp_path, plan, target="alpha-local", platform="android", device="emulator-5554")]
    if bindings == 2:
        binding_sources.append(_binding(tmp_path, plan, target="beta-local", platform="ios", device="ios-sim-01"))
    raws = []
    distribution = {"homepage": 25, "article": 25, "image": 40, "video": 10}
    for source, target, platform, device in [(binding_sources[0], "alpha-local", "android", "emulator-5554"), *([(binding_sources[1], "beta-local", "ios", "ios-sim-01")] if bindings == 2 else [])]:
        for entry in ENTRIES:
            for carrier in CARRIERS:
                if (entry, carrier) == ("recommendation", "video"):
                    continue
                for index in range(1, distribution[carrier] + 1):
                    object_id = (
                        f"/entity/{carrier}-{index:03d}"
                        if carrier == "homepage"
                        else f"{carrier}-{index:03d}"
                    )
                    raws.append(_raw(
                        tmp_path, source, target=target, platform=platform,
                        device=device, profile="rehearsal", entry=entry,
                        carrier=carrier, object_id=object_id,
                        ref_suffix=f"-{index:03d}",
                    ))
    return plan, binding_sources, raws


def _build(root: Path, plan: dict[str, str], bindings: list[dict[str, str]], raws: list[dict[str, str]]) -> dict[str, object]:
    return subject.build_app_uat_result_bundle(evidence_root=root, sample_plan=plan, target_bindings=bindings, raw_results=raws, generated_at="2026-08-29T08:00:00Z")


def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_complete_multi_binding_projection_is_deterministic_and_schema_valid(tmp_path: Path) -> None:
    plan, bindings, raws = _setup(tmp_path, bindings=2)
    first = _build(tmp_path, plan, list(reversed(bindings)), list(reversed(raws)))
    second = _build(tmp_path, plan, bindings, raws)
    assert first == second
    _validator().validate(first)
    assert first["schema"] == "quwoquan_ops.app_uat_result_bundle.v1"
    assert first["coverage"] == {"required": 780, "present": 780, "missing": 0, "duplicate": 0, "nonPassed": 0, "drifted": 0}
    assert len(first["targetBindings"]) == 2
    assert {row["provider"] for row in first["targetBindings"]} == {"first-party-https"}
    assert {row["provider"] for row in first["requiredSlots"]} == {"first-party-https"}
    assert len(first["notApplicableCells"]) == 2
    assert first["issues"] == []
    assert subject.validate(first) == first




def test_projection_preserves_exact_sample_object_identity(tmp_path: Path) -> None:
    plan, bindings, raws = _setup(tmp_path)
    document = _build(tmp_path, plan, bindings, raws)
    first = next(
        row for row in document["requiredSlots"]
        if row["entry"] == "feed" and row["carrier"] == "article"
        and row["objectId"] == "article-001"
    )
    assert first["sampleId"] == "m100-article-001"
    assert first["objectRef"] == "objects/posts/article/article-001"
    assert first["objectDigest"] == _digest("e")
    assert first["rawResults"]


def test_missing_duplicate_and_nonpassed_remain_diagnostic(tmp_path: Path) -> None:
    plan, bindings, raws = _setup(tmp_path)
    missing = raws.pop(0)
    duplicate = _raw(tmp_path, bindings[0], target="alpha-local", platform="android", device="emulator-5554", profile="rehearsal", entry="feed", carrier="article", ref_suffix="-duplicate")
    failed = _raw(tmp_path, bindings[0], target="alpha-local", platform="android", device="emulator-5554", profile="rehearsal", entry="feed", carrier="image", state="failed", ref_suffix="-failed")
    raws = [raw for raw in raws if not raw["ref"].endswith("feed-image-001.json")] + [duplicate, failed]
    document = _build(tmp_path, plan, bindings, raws)
    assert document["coverage"] == {"required": 390, "present": 389, "missing": 1, "duplicate": 1, "nonPassed": 1, "drifted": 0}
    assert {issue["code"] for issue in document["issues"]} == {"required_slot_missing", "required_slot_duplicate", "required_slot_non_passed"}
    duplicate_slot = next(row for row in document["requiredSlots"] if row["entry"] == "feed" and row["carrier"] == "article" and row["objectId"] == "article-001")
    assert len(duplicate_slot["rawResults"]) == 2
    failed_slot = next(row for row in document["requiredSlots"] if row["entry"] == "feed" and row["carrier"] == "image" and row["objectId"] == "image-001")
    assert failed_slot["rawResults"][0]["rawStatus"] == "failed"
    assert missing["ref"] not in json.dumps(document)


@pytest.mark.parametrize("state", ["failed", "blocked", "skipped"])
def test_all_nonpassed_states_are_preserved(tmp_path: Path, state: str) -> None:
    plan, bindings, raws = _setup(tmp_path)
    replacement = _raw(tmp_path, bindings[0], target="alpha-local", platform="android", device="emulator-5554", profile="rehearsal", entry="search", carrier="article", state=state, ref_suffix=f"-{state}")
    raws = [raw for raw in raws if not raw["ref"].endswith("search-article-001.json")] + [replacement]
    document = _build(tmp_path, plan, bindings, raws)
    assert document["coverage"]["nonPassed"] == 1
    assert any(raw["rawStatus"] == state for slot in document["requiredSlots"] for raw in slot["rawResults"])


def test_na_raw_and_cross_slot_do_not_hide_other_slots(tmp_path: Path) -> None:
    plan, bindings, raws = _setup(tmp_path)
    na_raw = _raw(tmp_path, bindings[0], target="alpha-local", platform="android", device="emulator-5554", profile="rehearsal", entry="recommendation", carrier="video")
    cross = _raw(tmp_path, bindings[0], target="alpha-local", platform="android", device="emulator-5554", profile="rehearsal", entry="feed", carrier="article", ref_suffix="-cross")
    cross_path = tmp_path / cross["ref"]
    value = json.loads(cross_path.read_text())
    value["specRef"] = SPEC + ".wrong"
    cross = _write(tmp_path, cross["ref"], value)
    document = _build(tmp_path, plan, bindings, raws + [na_raw, cross])
    assert document["coverage"]["drifted"] == 2
    assert {issue["code"] for issue in document["issues"] if issue["code"].startswith("not_") or "drifted" in issue["code"]} == {"not_applicable_has_raw", "raw_slot_identity_drifted"}
    assert document["coverage"]["present"] == 390


def test_cross_release_target_and_binding_digest_are_issues_not_fatal(tmp_path: Path) -> None:
    plan, bindings, raws = _setup(tmp_path)
    variants = []
    for suffix, mutation in (
        ("release", {"releaseId": "release-b"}),
        ("target", {"deploymentTarget": "beta-local"}),
        ("binding", {"targetUatBindingDigest": _digest("f")}),
    ):
        source = _raw(tmp_path, bindings[0], target="alpha-local", platform="android", device="emulator-5554", profile="rehearsal", entry="direct_or_object_route", carrier="article", ref_suffix=f"-{suffix}")
        path = tmp_path / source["ref"]
        value = json.loads(path.read_text())
        value.update(mutation)
        variants.append(_write(tmp_path, source["ref"], value))
    document = _build(tmp_path, plan, bindings, raws + variants)
    assert document["coverage"]["drifted"] == 3
    assert {issue["code"] for issue in document["issues"] if "drifted" in issue["code"]} == {"raw_release_drifted", "raw_target_binding_identity_drifted", "raw_binding_digest_drifted"}


def test_path_digest_duplicate_keys_and_unknown_raw_fields_are_fatal(tmp_path: Path) -> None:
    plan, bindings, raws = _setup(tmp_path)
    drifted = dict(raws[0], digest=_digest("f"))
    with pytest.raises(subject.AppUatResultBundleError, match="digest_drift"):
        _build(tmp_path, plan, bindings, [drifted])

    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}")
    link = tmp_path / "linked.json"
    link.symlink_to(outside)
    with pytest.raises(subject.AppUatResultBundleError, match="symlink"):
        _build(tmp_path, plan, bindings, [{"ref": "linked.json", "digest": _digest("a")}])

    raw_value = json.loads((tmp_path / raws[0]["ref"]).read_text())
    duplicate = _write(tmp_path, "duplicate.json", raw_value, duplicate_key="releaseId")
    with pytest.raises(subject.AppUatResultBundleError, match="duplicate JSON key"):
        _build(tmp_path, plan, bindings, [duplicate])

    raw_value["unknown"] = True
    unknown = _write(tmp_path, "unknown.json", raw_value)
    with pytest.raises(subject.AppUatResultBundleError, match="schema invalid"):
        _build(tmp_path, plan, bindings, [unknown])


def test_generated_at_is_required_and_projection_has_no_authority_fields(tmp_path: Path) -> None:
    plan, bindings, raws = _setup(tmp_path)
    with pytest.raises(TypeError):
        subject.build_app_uat_result_bundle(evidence_root=tmp_path, sample_plan=plan, target_bindings=bindings, raw_results=raws)
    document = _build(tmp_path, plan, bindings, raws)
    forbidden = {"status", "verdict", "passed", "promotable", "promotionAuthority", "authority"}

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(child) for child in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(child) for child in value), set())
        return set()

    assert not forbidden.intersection(keys(document))
    schema = json.loads(SCHEMA_PATH.read_text())
    assert not forbidden.intersection(keys(schema.get("properties", {})))
    assert not forbidden.intersection(keys(schema["$defs"]["coverage"]["properties"]))
    polluted = deepcopy(document)
    polluted["coverage"]["passed"] = 15
    with pytest.raises(subject.AppUatResultBundleError, match="forbidden"):
        subject.validate(polluted)


def test_write_projection_validates_and_atomically_rebuilds(tmp_path: Path) -> None:
    plan, bindings, raws = _setup(tmp_path)
    document = _build(tmp_path, plan, bindings, raws)
    path = subject.write_projection(evidence_root=tmp_path, relative_path="projections/app-uat.json", document=document)
    first = path.read_bytes()
    assert first == subject.canonical_projection_bytes(document)
    rewritten = deepcopy(document)
    rewritten["generatedAt"] = "2026-08-29T08:01:00Z"
    subject.write_projection(evidence_root=tmp_path, relative_path="projections/app-uat.json", document=rewritten)
    assert path.read_bytes() != first
    assert json.loads(path.read_text())["generatedAt"] == "2026-08-29T08:01:00Z"
