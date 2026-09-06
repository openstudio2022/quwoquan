# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/gray-release-to-prod/spec.md#gwt-001
from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

from quwoquan_ops.ci.qualified_prod import canonical_bytes, digest
from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import deploy_domain, deploy_release_inputs
from quwoquan_ops.cli.commands.deploy_release_state import _validate_release_transition
from quwoquan_ops.cli.prod import hosted_release_ledger


def sha(marker: str) -> str:
    return "sha256:" + marker * 64


SOURCE = "a" * 40
CONTROL = "b" * 40
TREE = "c" * 40
CANDIDATE = sha("1")
PREVIOUS_CANDIDATE = sha("2")
ARTIFACT_DIGEST = sha("3")
CURRENT_OCI = sha("4")
PREVIOUS_OCI = sha("5")


def write(root: Path, ref: str, payload: dict[str, object]) -> dict[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(payload) + b"\n")
    return {"ref": ref, "digest": digest(path)}

def write_oci(root: Path, repository: str, payload: dict[str, object]) -> dict[str, str]:
    exact_digest = digest(canonical_bytes(payload) + b"\n")
    return write(root, f"ghcr.io/quwoquan/{repository}@{exact_digest}", payload)


def materialized_input(root: Path) -> tuple[Path, dict[str, object]]:
    service_oci = sha("4")
    app_oci = sha("5")
    service_material_digest = sha("6")
    app_material_digest = sha("7")
    artifacts = [
        {"platform": "service", "ociRef": f"ghcr.io/quwoquan/service-factory-material@{service_oci}", "digest": service_oci},
        {"platform": "web", "ociRef": f"ghcr.io/quwoquan/app-candidate-artifact@{app_oci}", "digest": app_oci},
    ]
    factory_outputs = {
        "service": {
            "ociRef": artifacts[0]["ociRef"],
            "ociDigest": service_oci,
            "payloadDigest": sha("8"),
            "materialDigest": service_material_digest,
            "serviceDigest": sha("9"),
            "prodRuntimeConfigDeploymentBundle": {"schema": "quwoquan_ops.prod_runtime_config_deployment_bundle.v1", "digest": sha("a")},
        },
        "app": {
            "ociRef": artifacts[1]["ociRef"],
            "ociDigest": app_oci,
            "payloadDigest": sha("b"),
            "materialDigest": app_material_digest,
            "artifactDigests": {"android": sha("c"), "ios": sha("d"), "web": sha("e")},
            "artifactManifests": {"android": {}, "ios": {}, "web": {}},
            "sourceTreeDigest": "sha1:" + TREE,
        },
        "qualificationRequestOciRef": f"ghcr.io/quwoquan/qualification-request@{sha('1')}",
        "artifactBuildNumberAllocationOciRef": f"ghcr.io/quwoquan/artifact-build-number@{sha('2')}",
    }
    material_body: dict[str, object] = {
        "schema": "quwoquan_ops.candidate_material_manifest.v1",
        "sourceGitSha": SOURCE,
        "sourceTree": TREE,
        "artifactBuildNumber": 17,
        "artifacts": artifacts,
        "factoryOutputs": factory_outputs,
    }
    material_body["materialId"] = digest(material_body)
    material = write_oci(root, "candidate-material", material_body)
    qualification_body: dict[str, object] = {
        "schema": "quwoquan_ops.qualification_fact.v1",
        "decision": "qualified",
        "sourceGitSha": SOURCE,
        "sourceTree": TREE,
        "artifactBuildNumber": 17,
        "candidateMaterialManifest": material,
        "artifacts": artifacts,
    }
    qualification_body["qualificationId"] = digest(qualification_body)
    qualification = write_oci(root, "qualification", qualification_body)
    tag_body: dict[str, object] = {
        "schema": "quwoquan_ops.release_tag_admission_fact.v1",
        "decision": "admitted",
        "tagKind": "stable",
        "tagName": "v1.2.3",
        "tagObjectOid": "d" * 40,
        "peeledCommit": SOURCE,
        "sourceTree": TREE,
        "qualificationFact": qualification,
        "qualificationId": qualification_body["qualificationId"],
        "candidateMaterialManifest": material,
        "candidateMaterialId": material_body["materialId"],
        "candidateIdentity": CANDIDATE,
        "artifacts": artifacts,
    }
    tag_body["admissionId"] = digest(tag_body)
    tag = write_oci(root, "release-tag-admission", tag_body)
    previous_body: dict[str, object] = {
        "schema": "quwoquan_ops.prod_released_fact.v1",
        "terminal": "released",
        "active": True,
        "revoked": False,
        "digestsExist": True,
        "compatible": True,
        "candidateId": PREVIOUS_CANDIDATE,
        "ociDigests": [PREVIOUS_OCI],
    }
    previous_body["releaseId"] = digest(previous_body)
    previous = write_oci(root, "released-prod", previous_body)
    rollback = write_oci(root, "rollback-readiness", {
        "schema": "quwoquan_ops.rollback_readiness_fact.v1",
        "status": "ready",
        "previousActiveReleasedLedger": previous,
        "ociDigests": [PREVIOUS_OCI],
        "digestsExist": True,
        "compatible": True,
    })
    factory_refs = {
        kind: {key: value[key] for key in ("ociRef", "ociDigest", "payloadDigest", "materialDigest")}
        for kind, value in (("service", factory_outputs["service"]), ("app", factory_outputs["app"]))
    }
    admission_oci_digests = sorted({service_oci, app_oci, service_material_digest, app_material_digest})
    admission_body: dict[str, object] = {
        "schema": "quwoquan_ops.prod_activation_admission_fact.v1",
        "decision": "admitted",
        "stableTag": "v1.2.3",
        "tagObjectOid": tag_body["tagObjectOid"],
        "sourceGitSha": SOURCE,
        "sourceTree": TREE,
        "controlPlaneGitSha": CONTROL,
        "releaseTagAdmission": tag,
        "qualification": qualification,
        "candidateMaterialManifest": material,
        "factoryMaterials": factory_refs,
        "previousActiveReleasedLedger": previous,
        "rollbackReadiness": rollback,
        "artifacts": artifacts,
        "ociDigests": admission_oci_digests,
        "previousOciDigests": [PREVIOUS_OCI],
        "createdBeforeStage": "canary",
        "admittedAt": "2026-09-05T10:00:00Z",
    }
    admission_body["admissionId"] = digest(admission_body)
    admission = write_oci(root, "prod-activation-admission", admission_body)
    service_material = write(root, "factory/service/manifest.json", {"schema": "quwoquan_ops.service_factory_material", "images": [], "prodRuntimeConfigDeploymentBundle": factory_outputs["service"]["prodRuntimeConfigDeploymentBundle"], "materialDigest": service_material_digest})
    app_material = write(root, "factory/app/manifest.json", {"schema": "quwoquan_ops.app_factory_material", "materialDigest": app_material_digest})
    envelope = {
        "schema": "quwoquan_ops.prod_activation_input.v1",
        "prodActivationAdmission": admission,
        "releaseTagAdmission": tag,
        "qualification": qualification,
        "candidateMaterialManifest": material,
        "serviceFactoryMaterial": {**factory_refs["service"], "materializedManifest": service_material},
        "appFactoryMaterial": {**factory_refs["app"], "materializedManifest": app_material},
        "previousReleased": previous,
        "rollbackReadiness": rollback,
        "stableTag": "v1.2.3",
        "sourceGitSha": SOURCE,
        "sourceTree": TREE,
        "controlPlaneGitSha": CONTROL,
        "candidateMaterialId": material_body["materialId"],
        "previousReleasedId": previous_body["releaseId"],
        "candidateDigest": CANDIDATE,
        "previousCandidateDigest": PREVIOUS_CANDIDATE,
        "serviceMaterialDigest": service_material_digest,
        "appMaterialDigest": app_material_digest,
        "ociDigests": admission_oci_digests,
        "previousOciDigests": [PREVIOUS_OCI],
    }
    path = root / "prod-activation-input.json"
    path.write_bytes(canonical_bytes(envelope) + b"\n")
    return path, {
        "admission": admission,
        "tag": tag,
        "material": material,
        "serviceMaterial": service_material,
        "appMaterial": app_material,
        "servicePayload": {"schema": "quwoquan_ops.service_factory_material", "images": [], "prodRuntimeConfigDeploymentBundle": factory_outputs["service"]["prodRuntimeConfigDeploymentBundle"], "materialDigest": service_material_digest},
        "appPayload": {"schema": "quwoquan_ops.app_factory_material", "materialDigest": app_material_digest},
    }


def load(root: Path, input_path: Path, graph: dict[str, object]) -> dict[str, str]:
    with mock.patch(
        "quwoquan_ops.ci.qualified_prod._validated_factory_actual_materials",
        return_value=(
            graph["servicePayload"],
            graph["appPayload"],
            graph["serviceMaterial"],
            graph["appMaterial"],
        ),
    ):
        identity, _, candidate_material_id, deploy_material = deploy_release_inputs._load_prod_activation_admission(str(input_path))
    assert candidate_material_id == identity["candidateMaterialId"]
    assert deploy_material["candidateMaterialId"] == candidate_material_id
    return identity


def test_parser_exposes_only_one_prod_activation_admission_input() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    stub = types.SimpleNamespace(TARGETS=("prod-hosted",), ENVIRONMENTS=("prod",))
    with mock.patch.dict(sys.modules, {"quwoquan_ops.cli.stackctl": stub}):
        deploy_domain.register_parser(subparsers)
    args = parser.parse_args(
        ["deploy", "--target", "prod-hosted", "--prod-activation-admission", "/tmp/input.json"]
    )
    assert args.prod_activation_admission == "/tmp/input.json"
    for retired in (
        "environment_acceptance_ref",
        "environment_acceptance_sha256",
        "environment_acceptance_root",
        "release_evidence_ref",
        "release_manifest",
    ):
        assert not hasattr(args, retired)
    for old_option in ("--release-evidence-ref", "--release-manifest"):
        with pytest.raises(SystemExit):
            parser.parse_args(["deploy", "--target", "prod-hosted", old_option, "legacy.json"])


def test_old_prod_environment_acceptance_shape_is_rejected(tmp_path: Path) -> None:
    old = tmp_path / "old-eaf.json"
    old.write_text(
        json.dumps({"schema": "quwoquan_ops.environment_acceptance_fact.v2", "environment": "prod"}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="envelope"):
        deploy_release_inputs._load_prod_activation_admission(str(old))


def test_activation_graph_and_manifest_tuple_are_strictly_bound(tmp_path: Path) -> None:
    input_path, graph = materialized_input(tmp_path)
    identity = load(tmp_path, input_path, graph)
    admission = graph["admission"]
    assert isinstance(admission, dict)
    assert identity["prodActivationAdmissionPayloadDigest"] == admission["digest"]
    assert identity["prodActivationAdmissionId"] != admission["digest"]
    assert identity["candidateMaterialManifestRef"] == graph["material"]["ref"]
    assert identity["previousReleasedPayloadDigest"]


@pytest.mark.parametrize("drift", ("digest", "self-id", "source", "candidate"))
def test_activation_digest_self_id_source_and_candidate_drift_block(
    tmp_path: Path, drift: str
) -> None:
    input_path, graph = materialized_input(tmp_path)
    envelope = json.loads(input_path.read_text(encoding="utf-8"))
    if drift == "digest":
        envelope["prodActivationAdmission"]["digest"] = sha("f")
    elif drift == "candidate":
        envelope["candidateDigest"] = sha("f")
    else:
        admission_path = tmp_path / envelope["prodActivationAdmission"]["ref"]
        admission = json.loads(admission_path.read_text(encoding="utf-8"))
        if drift == "self-id":
            admission["admissionId"] = sha("f")
        else:
            admission["sourceGitSha"] = "f" * 40
        admission_path.write_bytes(canonical_bytes(admission) + b"\n")
        envelope["prodActivationAdmission"]["digest"] = digest(admission_path)
    input_path.write_bytes(canonical_bytes(envelope) + b"\n")
    with pytest.raises(RuntimeError):
        load(tmp_path, input_path, graph)


def test_stage_jump_and_admission_drift_are_blocked() -> None:
    state = {
        "schema": "prod-release-ledger",
        "generation": "1",
        "stage": "canary",
        "decision": "continue",
        "from_candidate_digest": PREVIOUS_CANDIDATE,
        "to_candidate_digest": CANDIDATE,
        "prod_activation_admission_payload_digest": sha("6"),
    }
    stub = types.SimpleNamespace(_release_stage_from_state=lambda value: value["stage"])
    kwargs = {
        "from_candidate_digest": PREVIOUS_CANDIDATE,
        "to_candidate_digest": CANDIDATE,
        "prod_activation_admission_payload_digest": sha("6"),
    }
    with mock.patch.dict(sys.modules, {"quwoquan_ops.cli.stackctl": stub}):
        with pytest.raises(RuntimeError, match="cannot advance"):
            _validate_release_transition(state, stage="20", **kwargs)
        with pytest.raises(RuntimeError, match="prod_activation_admission_payload_digest"):
            _validate_release_transition(
                state,
                stage="5",
                **{**kwargs, "prod_activation_admission_payload_digest": sha("f")},
            )


def test_legal_canary_persists_current_admission_identity(tmp_path: Path) -> None:
    request = {
        "schema": hosted_release_ledger.REQUEST_SCHEMA,
        "service": "mainline",
        "fromCandidateDigest": PREVIOUS_CANDIDATE,
        "toCandidateDigest": CANDIDATE,
        "step": "0",
        "stage": "canary",
        "triggerStage": "canary",
        "fromServiceFactoryOciDigest": PREVIOUS_CANDIDATE,
        "toServiceFactoryOciDigest": CANDIDATE,
        "fromAppFactoryOciDigest": "sha256:" + "1" * 64,
        "toAppFactoryOciDigest": "sha256:" + "1" * 64,
        "decision": "continue",
        "rollbackOutcome": "not_triggered",
        "rollbackEvidence": {"triggered": False},
        "candidateMaterialId": ARTIFACT_DIGEST,
        "prodActivationAdmissionRef": f"ghcr.io/owner/prod-activation-admission@{sha('6')}",
        "prodActivationAdmissionOciDigest": sha("6"),
        "prodActivationAdmissionPayloadDigest": sha("6"),
        "prodActivationAdmissionId": sha("6"),
        "candidateMaterialManifestRef": f"ghcr.io/owner/candidate-material@{sha('7')}",
        "candidateMaterialManifestOciDigest": sha("7"),
        "candidateMaterialManifestPayloadDigest": sha("7"),
        "previousReleasedRef": f"ghcr.io/owner/released-prod@{sha('b')}",
        "previousReleasedOciDigest": sha("b"),
        "previousReleasedPayloadDigest": sha("b"),
        "previousReleasedId": sha("c"),
        "imageDigest": ARTIFACT_DIGEST,
        "configDigest": ARTIFACT_DIGEST,
        "contractGraphDigest": ARTIFACT_DIGEST,
        "adapterDigest": ARTIFACT_DIGEST,
        "expectedGeneration": 0,
        "sloReadback": {},
        "postChecks": [],
        "lastGoodCandidateDigest": PREVIOUS_CANDIDATE,
        "verifiedAt": "2026-09-05T10:00:00Z",
    }
    readback = hosted_release_ledger.commit(tmp_path, request)
    assert readback["receipt"]["prodActivationAdmissionPayloadDigest"] == sha("6")
    assert readback["receipt"]["candidateMaterialManifestPayloadDigest"] == sha("7")
    assert readback["receipt"]["previousReleasedPayloadDigest"] == sha("b")
    old = dict(request)
    old.pop("prodActivationAdmissionRef")
    old["environmentAcceptanceRef"] = "prod/fact.json"
    with pytest.raises(ValueError, match="invalid shape"):
        hosted_release_ledger._validate_request(old)
