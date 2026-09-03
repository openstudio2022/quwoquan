"""EnvironmentAcceptanceFact M1 API consumer contracts.

Mechanically split from test_environment_acceptance_fact__local_contract_test.py.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib import environment_acceptance_fact as subject

RELEASE_DIGEST = "sha256:" + "1" * 64
MANIFEST_DIGEST = "sha256:" + "2" * 64
SPEC_REF = "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-006"

from importlib import import_module

_shared = import_module("test_environment_acceptance_fact__local_contract_test")
_evidence = _shared._evidence
_identity = _shared._identity
_schema_validator = _shared._schema_validator
_write_json = _shared._write_json


def _m1_api_evidence(root: Path) -> tuple[dict[str, object], list[dict[str, str]]]:
    arguments, _profiles = _evidence(root)
    arguments["acceptance_profile"] = "m1_api_consumer"
    arguments["target_binding_refs"] = []
    arguments["required_target_profiles"] = []
    plan = json.loads(
        (root / str(arguments["sample_plan_ref"])).read_text(encoding="utf-8")
    )
    plan["samples"] = [
        {
            "sampleId": f"baseline-{carrier}-001",
            "carrier": carrier,
            "objectId": f"{carrier}-001",
            "objectRef": (
                f"objects/entities/{carrier}-001"
                if carrier == "homepage"
                else f"objects/posts/{carrier}/{carrier}-001"
            ),
            "objectDigest": "sha256:" + str(index) * 64,
        }
        for index, carrier in enumerate(subject._CARRIERS, 1)
    ]
    plan["entryCarrierCells"] = [
        {
            "entry": entry,
            "carrier": carrier,
            "applicability": "required",
            "specRef": SPEC_REF,
            "runnerClass": f"qwq_service.content_api.{entry}.{carrier}.v1",
        }
        for entry in subject._ENTRIES
        for carrier in subject._CARRIERS
    ]
    plan_ref = _write_json(root, "release/m1-sample-plan.json", plan)
    arguments["sample_plan_ref"] = plan_ref["ref"]
    arguments["sample_plan_digest"] = plan_ref["digest"]
    samples = {item["carrier"]: item for item in plan["samples"]}
    results = []
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
            "schema": subject._M1_OBSERVATION_SCHEMA,
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
                "responseSha256": "sha256:" + "9" * 64,
            },
            "assertion": {"matchedRuntimeObjectId": f"runtime-{cell['carrier']}-001"},
        }
        observation_ref = _write_json(
            root,
            f"alpha/m1-{cell['entry']}-{cell['carrier']}-artifact.json",
            observation,
        )
        raw["artifactSha256"] = observation_ref["digest"].removeprefix("sha256:")
        raw_ref = _write_json(
            root,
            f"alpha/m1-raw-{cell['entry']}-{cell['carrier']}.json",
            raw,
        )
        results.append(
            {
                **raw_ref,
                "slotId": subject.required_raw_slot_id(
                    sample_id=sample["sampleId"],
                    entry_surface=cell["entry"],
                    carrier=cell["carrier"],
                    spec_ref=cell["specRef"],
                    runner_identity=cell["runnerClass"],
                ),
                "status": "passed",
            }
        )
    arguments["required_raw_results"] = results
    arguments["manifest_digest"] = MANIFEST_DIGEST
    data_path = root / str(arguments["data_readiness"]["ref"])
    data_payload = json.loads(data_path.read_text(encoding="utf-8"))
    data_payload["manifestDigest"] = MANIFEST_DIGEST
    data_path.write_text(
        json.dumps(data_payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    arguments["data_readiness"]["digest"] = subject.exact_byte_digest(data_path)
    source_health = _write_json(
        root,
        "alpha/source-content-consumer-health.json",
        {
            "command": "health",
            "target": "alpha-local",
            "scope": "content-consumer",
            **_identity("alpha", "alpha-local"),
            "manifestDigest": MANIFEST_DIGEST,
            "findings": [],
            "generationIssues": [],
            "checks": [{"name": "content-api", "ok": True, "skipped": False}],
            "userAvailability": [
                {"name": name, "status": "ready", "issues": []}
                for name in subject._M1_REQUIRED_HEALTH_LAYERS
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
    arguments["consumer_health"] = _write_json(
        root,
        "alpha/consumer-health.json",
        {
            "schema": subject._M1_HEALTH_SCHEMA,
            "status": "passed",
            "environment": "alpha",
            "deploymentTarget": "alpha-local",
            "releaseId": "release-a",
            "releaseDigest": RELEASE_DIGEST,
            "manifestDigest": MANIFEST_DIGEST,
            "importRunId": "import-run-a",
            "verifyRunId": "verify-run-a",
            "sourceHealth": source_health,
            "requiredLayers": list(subject._M1_REQUIRED_HEALTH_LAYERS),
        },
    )
    arguments["source_fingerprint"] = subject.derive_m1_source_fingerprint(
        environment="alpha",
        target="alpha-local",
        release_id="release-a",
        release_digest=RELEASE_DIGEST,
        manifest_digest=MANIFEST_DIGEST,
        import_run_id="import-run-a",
        verify_run_id="verify-run-a",
        sample_plan={"ref": plan_ref["ref"], "digest": plan_ref["digest"]},
        data_readiness=arguments["data_readiness"],
        consumer_health=arguments["consumer_health"],
        required_raw_results=results,
    )
    for field in (
        "active_cas",
        "lifecycle_exit",
        "provider_readiness",
        "observability_readiness",
        "rollback_readiness",
        "resource_finalization",
        "prod_release_facts",
    ):
        arguments.pop(field, None)
    return arguments, []


def test_m1_api_consumer_is_alpha_service_only_without_promotion_authority(
    tmp_path: Path,
) -> None:
    arguments, profiles = _m1_api_evidence(tmp_path)
    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    _schema_validator().validate(fact)
    assert fact["acceptanceProfile"] == "m1_api_consumer"
    assert fact["environment"] == "alpha" and fact["target"] == "alpha-local"
    assert "targetBindingRefs" not in fact
    assert set(fact["consumerHealth"]) == {"ref", "digest"}
    assert len(fact["requiredRawResults"]) == 16
    subject.validate_environment_acceptance_fact(
        fact,
        evidence_root=tmp_path,
        required_target_profiles=profiles,
    )

    wrong_target = deepcopy(fact)
    wrong_target["target"] = "alpha-proof"
    wrong_target["factId"] = subject.derive_fact_id(wrong_target)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="alpha-local"):
        subject.validate_environment_acceptance_fact(
            wrong_target,
            evidence_root=tmp_path,
            required_target_profiles=[],
        )

    promoted = deepcopy(fact)
    promoted["acceptanceProfile"] = "environment_promotion"
    promoted["factId"] = subject.derive_fact_id(promoted)
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="fields are invalid"
    ):
        subject.validate_environment_acceptance_fact(
            promoted,
            evidence_root=tmp_path,
            required_target_profiles=[],
        )


def test_m1_api_consumer_rejects_app_raw_and_binding_derived_slot(
    tmp_path: Path,
) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    first = fact["requiredRawResults"][0]
    path = tmp_path / first["ref"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.update({"producer": "app", "layer": "user_acceptance"})
    path.write_text(
        json.dumps(raw, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    first["digest"] = subject.exact_byte_digest(path)
    fact["factId"] = subject.derive_fact_id(fact)
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="canonical ReadinessCaseResult"
    ):
        subject.validate_environment_acceptance_fact(
            fact,
            evidence_root=tmp_path,
            required_target_profiles=[],
        )


def test_m1_api_consumer_rejects_noncanonical_raw_and_missing_run_identity(
    tmp_path: Path,
) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    first = fact["requiredRawResults"][0]
    for field in ("importRunId", "verifyRunId"):
        raw_path = tmp_path / first["ref"]
        original = json.loads(raw_path.read_text(encoding="utf-8"))
        broken = dict(original)
        broken.pop(field)
        raw_path.write_text(
            json.dumps(broken, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )
        first["digest"] = subject.exact_byte_digest(raw_path)
        fact["factId"] = subject.derive_fact_id(fact)
        with pytest.raises(
            subject.EnvironmentAcceptanceFactError,
            match="canonical ReadinessCaseResult",
        ):
            subject.validate_environment_acceptance_fact(
                fact, evidence_root=tmp_path, required_target_profiles=[]
            )
        raw_path.write_text(
            json.dumps(original, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )


def test_m1_api_consumer_rejects_promotion_fields_and_requires_consumer_health(
    tmp_path: Path,
) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    for field, value in (
        ("activeCas", {}),
        ("lifecycleExit", {}),
        ("providerReadiness", {}),
        ("observabilityReadiness", {}),
        ("rollbackReadiness", {}),
        ("resourceFinalization", {}),
        ("targetBindingRefs", []),
    ):
        mixed = deepcopy(fact)
        mixed[field] = value
        with pytest.raises(
            subject.EnvironmentAcceptanceFactError, match="fields are invalid"
        ):
            subject.validate_environment_acceptance_fact(
                mixed, evidence_root=tmp_path, required_target_profiles=[]
            )
    missing_health = deepcopy(fact)
    missing_health.pop("consumerHealth")
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="fields are invalid"
    ):
        subject.validate_environment_acceptance_fact(
            missing_health, evidence_root=tmp_path, required_target_profiles=[]
        )


def test_m1_dual_digests_are_distinct_and_wrong_manifest_fails(tmp_path: Path) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    assert fact["releaseDigest"] == RELEASE_DIGEST
    assert fact["manifestDigest"] == MANIFEST_DIGEST
    assert fact["releaseDigest"] != fact["manifestDigest"]
    wrong = deepcopy(fact)
    wrong["manifestDigest"] = wrong["releaseDigest"]
    wrong["factId"] = subject.derive_fact_id(wrong)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="manifestDigest"):
        subject.validate_environment_acceptance_fact(
            wrong, evidence_root=tmp_path, required_target_profiles=[]
        )


def test_m1_source_fingerprint_is_recomputed_not_caller_authority(
    tmp_path: Path,
) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    forged = deepcopy(fact)
    forged["sourceFingerprint"] = "sha256:" + "a" * 64
    forged["factId"] = subject.derive_fact_id(forged)
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="sourceFingerprint"
    ):
        subject.validate_environment_acceptance_fact(
            forged, evidence_root=tmp_path, required_target_profiles=[]
        )


def test_m1_health_binding_recurses_to_source_and_ignores_nonrequired_layers(
    tmp_path: Path,
) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    health_path = tmp_path / arguments["consumer_health"]["ref"]
    binding = json.loads(health_path.read_text(encoding="utf-8"))
    source_path = tmp_path / binding["sourceHealth"]["ref"]
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["userAvailability"].extend(
        [
            {"name": "provider_ready", "status": "blocked", "issues": ["irrelevant"]},
            {"name": "device_bound", "status": "blocked", "issues": ["irrelevant"]},
            {
                "name": "content_live_passed",
                "status": "blocked",
                "issues": ["irrelevant"],
            },
        ]
    )
    source_path.write_text(
        json.dumps(source, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    binding["sourceHealth"]["digest"] = subject.exact_byte_digest(source_path)
    health_path.write_text(
        json.dumps(binding, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    arguments["consumer_health"]["digest"] = subject.exact_byte_digest(health_path)
    arguments["source_fingerprint"] = subject.derive_m1_source_fingerprint(
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
    subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]

    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    source["userAvailability"][0]["status"] = "blocked"
    source_path.write_text(
        json.dumps(source, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="exact-byte digest drifted"
    ):
        subject.validate_environment_acceptance_fact(
            fact, evidence_root=tmp_path, required_target_profiles=[]
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update({"http": None}), "requires HTTP facts"),
        (
            lambda value: value["http"].update({"status": 503}),
            "HTTP status is not 2xx",
        ),
        (
            lambda value: value.update({"runtimeObjectId": "runtime-drift"}),
            "runtimeObjectId did not match",
        ),
        (
            lambda value: value.update({"releaseDigest": "sha256:" + "8" * 64}),
            "identity drifted at releaseDigest",
        ),
    ],
)
def test_m1_observation_http_and_identity_are_strict(
    tmp_path: Path, mutation, message: str
) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    first = arguments["required_raw_results"][0]
    raw_path = tmp_path / first["ref"]
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    observation_path = tmp_path / raw["artifactPath"]
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    mutation(observation)
    observation_path.write_text(
        json.dumps(observation, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    raw["artifactSha256"] = subject.exact_byte_digest(observation_path).removeprefix(
        "sha256:"
    )
    raw_path.write_text(
        json.dumps(raw, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    first["digest"] = subject.exact_byte_digest(raw_path)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match=message):
        subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]


def test_m1_observation_missing_drift_and_symlink_are_blocked(tmp_path: Path) -> None:
    for mode, message in (
        ("missing", "missing"),
        ("bytes", "observation exact bytes drifted"),
        ("symlink", "linked"),
    ):
        root = tmp_path / mode
        root.mkdir()
        arguments, _ = _m1_api_evidence(root)
        first = arguments["required_raw_results"][0]
        raw = json.loads((root / first["ref"]).read_text(encoding="utf-8"))
        observation_path = root / raw["artifactPath"]
        if mode == "missing":
            observation_path.unlink()
        elif mode == "bytes":
            observation_path.write_bytes(observation_path.read_bytes() + b" ")
        else:
            outside = root / "outside-observation.json"
            outside.write_bytes(observation_path.read_bytes())
            observation_path.unlink()
            observation_path.symlink_to(outside)
        with pytest.raises(subject.EnvironmentAcceptanceFactError, match=message):
            subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
