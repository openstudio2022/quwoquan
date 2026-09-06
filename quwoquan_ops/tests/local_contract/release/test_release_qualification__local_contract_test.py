# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-wave-deployment/spec.md#gwt-001
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quwoquan_ops.ci.release_qualification import (
    ReleaseQualificationError,
    build_prod_runtime_config_deployment_bundle,
    create_candidate_material_from_factory_outputs,
    create_candidate_material_manifest,
    create_qualification_fact,
    create_qualification_request,
    digest,
)

SHA = "a" * 40
TREE = "b" * 40


def write(root: Path, ref: str, payload: dict) -> dict[str, str]:
    path = root / ref; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return {"ref": ref, "digest": digest(path)}


def setup(root: Path):
    rc = write(root, "rc.json", {"decision": "admitted", "tagName": "v1.2.3-rc.1", "peeledCommit": SHA, "sourceTree": TREE})
    seal = write(root, "seal.json", {"schema": "quwoquan_ops.main_source_seal.v1", "mainSha": SHA, "mainTree": TREE, "sourceHeadSha": "c" * 40})
    integration = write(root, "integration.json", {"schema": "quwoquan_ops.integration_qualification_fact.v1", "decision": "qualified", "devHead": "c" * 40, "devTree": TREE})
    authority = write(root, "authority.json", {"status": "approved", "sourceGitSha": SHA})
    request_path = create_qualification_request(root=root, rc_tag_admission_ref=rc, main_source_seal_ref=seal, integration_qualification_ref=integration, requested_by_ref=authority, requested_at="2026-09-05T10:00:00Z")
    request = {"ref": request_path.relative_to(root).as_posix(), "digest": digest(request_path)}
    version = write(root, "version.json", {"schema": "ProductVersionManifest", "targetVersion": "1.2.3"})
    sbom = write(root, "sbom.json", {"status": "passed"}); provenance = write(root, "provenance.json", {"status": "passed"}); signing = write(root, "signing.json", {"status": "passed"})
    request_id = json.loads(request_path.read_text())["requestId"]
    allocation_body = {
        "schema": "quwoquan_ops.artifact_build_number_allocation.v1",
        "requestId": request_id,
        "qualificationRequest": request,
        "artifactBuildNumber": 17,
        "predecessor": None,
        "hostedAuthority": {"provider": "github_actions_workflow_run_number", "runId": "9001", "runNumber": 17},
    }
    allocation_body["allocationId"] = digest(allocation_body)
    allocation = write(root, "allocation.json", allocation_body)
    artifacts = [{"platform": platform, "digest": "sha256:" + str(i) * 64, "ociRef": f"ghcr.io/q/{platform}@sha256:" + str(i) * 64} for i, platform in enumerate(("android", "ios", "service", "web"), 1)]
    material_path = create_candidate_material_manifest(root=root, request_ref=request, artifact_build_number=17, artifact_build_number_allocation_ref=allocation, product_version_manifest_ref=version, artifacts=artifacts, sbom_ref=sbom, provenance_ref=provenance, signing_ref=signing, created_at="2026-09-05T10:10:00Z")
    material = {"ref": material_path.relative_to(root).as_posix(), "digest": digest(material_path)}
    material_id = json.loads(material_path.read_text())["materialId"]
    return request, material, material_id


def test_explicit_request_material_once_and_final_physical_acceptance(tmp_path: Path) -> None:
    request, material, material_id = setup(tmp_path)
    def fact(name: str, extra=None): return write(tmp_path, f"{name}.json", {"status": "passed", "materialId": material_id, "sourceGitSha": SHA, **(extra or {})})
    package = fact("package", {"physicalDevicePlatforms": ["android", "ios"]})
    path = create_qualification_fact(root=tmp_path, request_ref=request, material_ref=material, package_acceptance_ref=package, provider_fact_ref=fact("provider"), uat_fact_ref=fact("uat"), supply_chain_fact_ref=fact("supply"), qualified_at="2026-09-05T10:20:00Z")
    result = json.loads(path.read_text())
    assert result["decision"] == "qualified"
    assert result["artifactBuildNumber"] == 17
    assert {item["platform"] for item in result["artifacts"]} == {"android", "ios", "service", "web"}


@pytest.mark.parametrize(
    "physical_platforms",
    (["android"], ["android", "simulated"], ["android", "android"]),
)
def test_final_package_acceptance_cannot_use_one_or_simulated_platform(
    tmp_path: Path, physical_platforms: list[str]
) -> None:
    request, material, material_id = setup(tmp_path)
    def fact(name: str, extra=None): return write(tmp_path, f"{name}.json", {"status": "passed", "materialId": material_id, "sourceGitSha": SHA, **(extra or {})})
    with pytest.raises(ReleaseQualificationError, match="both physical"):
        create_qualification_fact(root=tmp_path, request_ref=request, material_ref=material, package_acceptance_ref=fact("package", {"physicalDevicePlatforms": physical_platforms}), provider_fact_ref=fact("provider"), uat_fact_ref=fact("uat"), supply_chain_fact_ref=fact("supply"), qualified_at="2026-09-05T10:20:00Z")


def test_material_requires_exact_complete_oci_set(tmp_path: Path) -> None:
    request, _, _ = setup(tmp_path)
    version = write(tmp_path, "v2.json", {"targetVersion": "1.2.3"}); support = write(tmp_path, "support.json", {"status": "passed"})
    with pytest.raises(ReleaseQualificationError, match="platforms are incomplete"):
        create_candidate_material_manifest(root=tmp_path, request_ref=request, artifact_build_number=17, artifact_build_number_allocation_ref={"ref": "allocation.json", "digest": digest(tmp_path / "allocation.json")}, product_version_manifest_ref=version, artifacts=[{"platform": "android", "digest": "sha256:" + "1" * 64, "ociRef": "ghcr.io/q/a@sha256:" + "1" * 64}], sbom_ref=support, provenance_ref=support, signing_ref=support, created_at="2026-09-05T10:00:00Z")


def test_material_rejects_non_hosted_build_number_allocation(tmp_path: Path) -> None:
    request, material, _ = setup(tmp_path)
    manifest = json.loads((tmp_path / material["ref"]).read_text())
    allocation = json.loads(
        (tmp_path / manifest["artifactBuildNumberAllocation"]["ref"]).read_text()
    )
    allocation.pop("hostedAuthority")
    allocation.pop("allocationId")
    allocation["allocationId"] = digest(allocation)
    local_allocation = write(tmp_path, "local-allocation.json", allocation)
    with pytest.raises(ReleaseQualificationError, match="hosted artifact"):
        create_candidate_material_manifest(
            root=tmp_path,
            request_ref=request,
            artifact_build_number=17,
            artifact_build_number_allocation_ref=local_allocation,
            product_version_manifest_ref=manifest["productVersionManifest"],
            artifacts=manifest["artifacts"],
            sbom_ref=manifest["sbom"],
            provenance_ref=manifest["provenance"],
            signing_ref=manifest["signing"],
            created_at="2026-09-05T10:11:00Z",
        )


def _actual_factory_fixture(tmp_path: Path) -> dict[str, object]:
    from quwoquan_ops.ci.plan_service_release_images import (
        RUNTIME_IMAGE_OWNERS,
        TRUST_DOMAINS,
    )
    from quwoquan_ops.cli.prod.oci_supply_chain import OIDC_ISSUER, PREDICATES

    repository = tmp_path / "repository"
    prod_input = repository / "quwoquan_ops/environments/prod/runtime.yaml"
    prod_input.parent.mkdir(parents=True)
    prod_input.write_text("environment: prod\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(["git", "-C", str(repository), "add", prod_input.relative_to(repository)], check=True)

    rc_ref = "ghcr.io/example/quwoquan/rc-admission@sha256:" + "1" * 64
    request_oci_ref = "ghcr.io/example/quwoquan/request@sha256:" + "2" * 64
    request_body = {
        "schema": "quwoquan_ops.release_qualification_request.v1",
        "rcTagAdmission": {"ref": rc_ref, "digest": "sha256:" + "3" * 64},
        "mainSourceSeal": {"ref": "seal.json", "digest": "sha256:" + "4" * 64},
        "integrationQualification": {"ref": "integration.json", "digest": "sha256:" + "5" * 64},
        "requestAuthority": {"ref": "authority.json", "digest": "sha256:" + "6" * 64},
        "tagName": "v1.2.3-rc.1",
        "sourceGitSha": SHA,
        "sourceTree": TREE,
        "requestedAt": "2026-09-05T10:00:00Z",
    }
    request_body["requestId"] = digest(request_body)
    request = write(tmp_path, "request.json", request_body)
    allocation_oci_ref = "ghcr.io/example/quwoquan/allocation@sha256:" + "7" * 64
    allocation_body = {
        "schema": "quwoquan_ops.artifact_build_number_allocation.v1",
        "requestId": request_body["requestId"],
        "qualificationRequest": request,
        "artifactBuildNumber": 17,
        "predecessor": None,
        "hostedAuthority": {
            "provider": "github_actions_workflow_run_number",
            "runId": "9001",
            "runNumber": 17,
        },
    }
    allocation_body["allocationId"] = digest(allocation_body)
    allocation = write(tmp_path, "allocation-actual.json", allocation_body)
    version = write(tmp_path, "version-actual.json", {"targetVersion": "1.2.3"})

    signer_workflow = "example/quwoquan/.github/workflows/service_pipeline.yml"
    images = []
    subjects = []
    for index, (trust_domain, owner) in enumerate(
        (item for domain in TRUST_DOMAINS for item in ((domain, owner) for owner in RUNTIME_IMAGE_OWNERS)),
        10,
    ):
        image_digest = "sha256:" + f"{index:064x}"
        image_ref = f"ghcr.io/example/quwoquan/{owner}-{trust_domain}@{image_digest}"
        verification_digests = {
            name: "sha256:" + f"{index + offset:064x}"
            for offset, name in enumerate(PREDICATES, 1)
        }
        images.append(
            {
                "trustDomain": trust_domain,
                "runtimeImageOwner": owner,
                "ociRef": image_ref,
                "digest": image_digest,
                "signature": {
                    "issuer": OIDC_ISSUER,
                    "signerWorkflow": signer_workflow,
                    "verificationDigest": digest(
                        {
                            "subject": image_ref,
                            "issuer": OIDC_ISSUER,
                            "signerWorkflow": signer_workflow,
                            "attestations": verification_digests,
                        }
                    ),
                },
                "attestations": {
                    name: {
                        "predicateType": predicate,
                        "verificationDigest": verification_digests[name],
                    }
                    for name, predicate in PREDICATES.items()
                },
            }
        )
        subjects.append(
            {
                "trustDomain": trust_domain,
                "runtimeImageOwner": owner,
                "digest": image_digest,
            }
        )
    service_digest = digest({"images": subjects})
    service_ref = "ghcr.io/example/quwoquan/service-factory-material@sha256:" + "8" * 64
    service_body = {
        "schema": "quwoquan_ops.service_factory_material",
        "sourceGitSha": SHA,
        "sourceTree": TREE,
        "qualificationRequest": {
            "ref": request_oci_ref,
            "digest": request_oci_ref.rsplit("@", 1)[1],
            "factDigest": request["digest"],
            "requestId": request_body["requestId"],
        },
        "rcTagAdmission": {
            "ref": rc_ref,
            "digest": rc_ref.rsplit("@", 1)[1],
            "factDigest": request_body["rcTagAdmission"]["digest"],
            "admissionId": "sha256:" + "9" * 64,
            "tagName": request_body["tagName"],
        },
        "artifactBuildNumber": 17,
        "artifactBuildNumberAllocation": {
            "ref": allocation_oci_ref,
            "digest": allocation_oci_ref.rsplit("@", 1)[1],
            "factDigest": allocation["digest"],
            "allocationId": allocation_body["allocationId"],
        },
        "serviceDigest": service_digest,
        "images": images,
        "prodRuntimeConfigDeploymentBundle": build_prod_runtime_config_deployment_bundle(repository),
        "producer": {
            "repository": "example/quwoquan",
            "signerWorkflow": signer_workflow,
            "workflowRunId": "9001",
        },
        "buildPolicy": "build_sign_attest_once",
    }
    service_body["materialDigest"] = digest(service_body)
    service_material = write(tmp_path, "service-material.json", service_body)

    app_ref = "ghcr.io/example/quwoquan/app-candidate-artifact@sha256:" + "a" * 64
    app_artifact_specs = {
        "android": ("android-prod-apk", "sha256:" + "b" * 64),
        "ios": ("ios-prod-app", "sha256:" + "c" * 64),
        "web": ("web-shared", "sha256:" + "d" * 64),
    }
    app_artifacts = {}
    for platform, (product_id, artifact_digest) in app_artifact_specs.items():
        from quwoquan_ops.cli.lib.app_identity import (
            application_id_for_build_product,
            resolve_build_product,
        )

        product = resolve_build_product(product_id)
        manifest = {
            "schema": "app-artifact-manifest",
            "buildProductId": product_id,
            "buildProfile": product.build_profile,
            "platform": platform,
            "buildMode": product.build_mode,
            "distributionClass": product.distribution_class,
            "artifactFormat": product.artifact_format,
            "applicationId": application_id_for_build_product(product_id),
            "displayVersion": "1.2.3",
            "buildNumber": "17",
            "signingIdentityDigest": "sha256:" + "e" * 64,
            "sourceGitSha": SHA,
            "sourceTreeDigest": "sha1:" + TREE,
            "buildProvenanceDigest": "sha256:" + "f" * 64,
            "artifactDigest": artifact_digest,
            "qualificationRequestRef": request_oci_ref,
            "qualificationRequestDigest": request_oci_ref.rsplit("@", 1)[1],
            "rcTagAdmissionRef": rc_ref,
            "artifactBuildNumberAllocationRef": allocation_oci_ref,
            "artifactBuildNumberAllocationDigest": allocation_oci_ref.rsplit("@", 1)[1],
            "promotable": True,
        }
        if platform in {"android", "ios"}:
            manifest["runtimeConfigTrustEnvelopeDigest"] = "sha256:" + "0" * 64
        app_artifacts[platform] = manifest
    app_body = {
        "schema": "quwoquan_ops.app_factory_material",
        "sourceGitSha": SHA,
        "sourceTreeDigest": "sha1:" + TREE,
        "qualificationRequest": {
            "ref": request_oci_ref,
            "digest": request_oci_ref.rsplit("@", 1)[1],
        },
        "rcTagAdmissionRef": rc_ref,
        "artifactBuildNumber": 17,
        "artifactBuildNumberAllocation": {
            "ref": allocation_oci_ref,
            "digest": allocation_oci_ref.rsplit("@", 1)[1],
        },
        "artifacts": app_artifacts,
    }
    app_body["materialDigest"] = digest(app_body)
    app_material = write(tmp_path, "app-material.json", app_body)
    return {
        "repository": repository,
        "prodInput": prod_input,
        "request": request,
        "requestBody": request_body,
        "requestOciRef": request_oci_ref,
        "allocation": allocation,
        "allocationOciRef": allocation_oci_ref,
        "version": version,
        "serviceRef": service_ref,
        "serviceBody": service_body,
        "serviceMaterial": service_material,
        "appRef": app_ref,
        "appBody": app_body,
        "appMaterial": app_material,
    }


def _reduce_actual_factory_fixture(tmp_path: Path, fixture: dict[str, object], **overrides: object) -> Path:
    service = fixture["serviceBody"]
    app = fixture["appBody"]
    assert isinstance(service, dict) and isinstance(app, dict)
    values = {
        "root": tmp_path,
        "repository_root": fixture["repository"],
        "request_ref": fixture["request"],
        "request_oci_ref": fixture["requestOciRef"],
        "artifact_build_number_allocation_ref": fixture["allocation"],
        "allocation_oci_ref": fixture["allocationOciRef"],
        "product_version_manifest_ref": fixture["version"],
        "service_material_ref": fixture["serviceMaterial"],
        "service_evidence_ref": fixture["serviceRef"],
        "service_source_git_sha": service["sourceGitSha"],
        "service_source_tree": service["sourceTree"],
        "service_qualification_request_ref": service["qualificationRequest"]["ref"],
        "service_qualification_request_digest": service["qualificationRequest"]["digest"],
        "service_material_digest": service["materialDigest"],
        "service_artifact_digest": service["serviceDigest"],
        "app_material_ref": fixture["appMaterial"],
        "app_evidence_ref": fixture["appRef"],
        "app_source_git_sha": app["sourceGitSha"],
        "app_source_tree": app["sourceTreeDigest"],
        "app_qualification_request_ref": app["qualificationRequest"]["ref"],
        "app_qualification_request_digest": app["qualificationRequest"]["digest"],
        "app_artifact_build_number": app["artifactBuildNumber"],
        "app_allocation_ref": app["artifactBuildNumberAllocation"]["ref"],
        "app_allocation_digest": app["artifactBuildNumberAllocation"]["digest"],
        "app_material_digest": app["materialDigest"],
        "app_android_artifact_digest": app["artifacts"]["android"]["artifactDigest"],
        "app_ios_artifact_digest": app["artifacts"]["ios"]["artifactDigest"],
        "app_web_artifact_digest": app["artifacts"]["web"]["artifactDigest"],
        "created_at": "2026-09-05T10:20:00Z",
    }
    values.update(overrides)
    return create_candidate_material_from_factory_outputs(**values)


def test_factory_reducer_derives_cmm_only_from_actual_canonical_bytes(tmp_path: Path) -> None:
    fixture = _actual_factory_fixture(tmp_path)
    material = _reduce_actual_factory_fixture(tmp_path, fixture)
    body = json.loads(material.read_text())
    service = fixture["serviceBody"]
    app = fixture["appBody"]
    assert isinstance(service, dict) and isinstance(app, dict)
    assert body["artifactByteDigests"] == {
        **{
            platform: manifest["artifactDigest"]
            for platform, manifest in app["artifacts"].items()
        },
        "service": service["serviceDigest"],
    }
    assert body["factoryOutputs"]["service"]["payloadDigest"] == fixture["serviceMaterial"]["digest"]
    assert body["factoryOutputs"]["app"]["payloadDigest"] == fixture["appMaterial"]["digest"]
    assert body["factoryOutputs"]["app"]["artifactManifests"] == app["artifacts"]
    assert body["factoryOutputs"]["app"] == {
        "ociRef": fixture["appRef"],
        "ociDigest": str(fixture["appRef"]).rsplit("@", 1)[1],
        "payloadDigest": fixture["appMaterial"]["digest"],
        "materialDigest": app["materialDigest"],
        "artifactDigests": {
            platform: artifact_manifest["artifactDigest"]
            for platform, artifact_manifest in app["artifacts"].items()
        },
        "artifactManifests": app["artifacts"],
        "sourceTreeDigest": "sha1:" + TREE,
    }
    assert "appEvidenceDigest" not in body["factoryOutputs"]["app"]
    assert body["factoryOutputs"]["service"]["prodRuntimeConfigDeploymentBundle"] == service["prodRuntimeConfigDeploymentBundle"]
    assert {item["ociRef"] for item in body["artifacts"]} == {
        fixture["appRef"], fixture["serviceRef"],
    }


def test_factory_reducer_rejects_scalar_drift_from_actual_bytes(tmp_path: Path) -> None:
    fixture = _actual_factory_fixture(tmp_path)
    with pytest.raises(ReleaseQualificationError, match="scalar drifted"):
        _reduce_actual_factory_fixture(
            tmp_path,
            fixture,
            app_android_artifact_digest="sha256:" + "e" * 64,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        (
            "app_evidence_ref",
            "ghcr.io/example/quwoquan/other-app@sha256:" + "a" * 64,
        ),
        ("app_material_digest", "sha256:" + "e" * 64),
        ("app_source_git_sha", "e" * 40),
        ("app_source_tree", "sha1:" + "e" * 40),
        (
            "app_qualification_request_ref",
            "ghcr.io/example/quwoquan/request@sha256:" + "e" * 64,
        ),
        ("app_qualification_request_digest", "sha256:" + "e" * 64),
        ("app_artifact_build_number", 18),
        (
            "app_allocation_ref",
            "ghcr.io/example/quwoquan/allocation@sha256:" + "e" * 64,
        ),
        ("app_allocation_digest", "sha256:" + "e" * 64),
        ("app_ios_artifact_digest", "sha256:" + "e" * 64),
        ("app_web_artifact_digest", "sha256:" + "e" * 64),
    ),
)
def test_factory_reducer_rejects_app_scalar_or_locator_drift(
    tmp_path: Path, field: str, value: object
) -> None:
    fixture = _actual_factory_fixture(tmp_path)
    with pytest.raises(ReleaseQualificationError, match="scalar drifted|repository drifted"):
        _reduce_actual_factory_fixture(tmp_path, fixture, **{field: value})


def test_factory_reducer_rejects_actual_payload_tamper(tmp_path: Path) -> None:
    fixture = _actual_factory_fixture(tmp_path)
    app_path = tmp_path / fixture["appMaterial"]["ref"]
    app_path.write_bytes(app_path.read_bytes() + b" ")
    with pytest.raises(ReleaseQualificationError, match="exact bytes drifted"):
        _reduce_actual_factory_fixture(tmp_path, fixture)


def test_factory_reducer_rejects_noncanonical_app_payload_bytes(tmp_path: Path) -> None:
    fixture = _actual_factory_fixture(tmp_path)
    app_path = tmp_path / fixture["appMaterial"]["ref"]
    app = json.loads(app_path.read_text(encoding="utf-8"))
    app_path.write_text(json.dumps(app, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fixture["appMaterial"] = {
        "ref": app_path.relative_to(tmp_path).as_posix(),
        "digest": digest(app_path),
    }
    with pytest.raises(ReleaseQualificationError, match="bytes are not canonical JSON"):
        _reduce_actual_factory_fixture(tmp_path, fixture)


def test_factory_reducer_rejects_prod_config_closure_drift(tmp_path: Path) -> None:
    fixture = _actual_factory_fixture(tmp_path)
    fixture["prodInput"].write_text("environment: changed\n", encoding="utf-8")
    with pytest.raises(ReleaseQualificationError, match="bundle closure drifted"):
        _reduce_actual_factory_fixture(tmp_path, fixture)



def _rewrite_app_material(
    tmp_path: Path,
    fixture: dict[str, object],
    mutate,
    *,
    recompute_material_digest: bool = True,
) -> None:
    app = json.loads(json.dumps(fixture["appBody"]))
    mutate(app)
    if recompute_material_digest:
        app.pop("materialDigest", None)
        app["materialDigest"] = digest(app)
    path = tmp_path / fixture["appMaterial"]["ref"]
    fixture["appBody"] = app
    fixture["appMaterial"] = write(tmp_path, path.relative_to(tmp_path).as_posix(), app)


@pytest.mark.parametrize(
    ("label", "mutate"),
    (
        ("source", lambda app: app.__setitem__("sourceGitSha", "e" * 40)),
        ("tree", lambda app: app.__setitem__("sourceTreeDigest", "sha1:" + "e" * 40)),
        (
            "request",
            lambda app: app.__setitem__(
                "qualificationRequest",
                {
                    "ref": "ghcr.io/example/quwoquan/request@sha256:" + "e" * 64,
                    "digest": "sha256:" + "e" * 64,
                },
            ),
        ),
        (
            "rc",
            lambda app: app.__setitem__(
                "rcTagAdmissionRef",
                "ghcr.io/example/quwoquan/rc-admission@sha256:" + "e" * 64,
            ),
        ),
        ("build-number", lambda app: app.__setitem__("artifactBuildNumber", 18)),
        (
            "allocation",
            lambda app: app.__setitem__(
                "artifactBuildNumberAllocation",
                {
                    "ref": "ghcr.io/example/quwoquan/allocation@sha256:" + "e" * 64,
                    "digest": "sha256:" + "e" * 64,
                },
            ),
        ),
        (
            "artifact",
            lambda app: app["artifacts"]["android"].__setitem__(
                "artifactDigest", "sha256:" + "e" * 64
            ),
        ),
    ),
)
def test_factory_reducer_rejects_app_authority_or_artifact_drift(
    tmp_path: Path, label: str, mutate
) -> None:
    fixture = _actual_factory_fixture(tmp_path)
    app = fixture["appBody"]
    assert isinstance(app, dict)
    original_android_digest = app["artifacts"]["android"]["artifactDigest"]
    _rewrite_app_material(tmp_path, fixture, mutate)
    overrides = (
        {"app_android_artifact_digest": original_android_digest}
        if label == "artifact"
        else {}
    )
    with pytest.raises(ReleaseQualificationError, match="app factory material|scalar drifted"):
        _reduce_actual_factory_fixture(tmp_path, fixture, **overrides)


@pytest.mark.parametrize(
    ("label", "field", "value"),
    (
        ("build-product", "buildProductId", "android-nonprod-apk"),
        ("platform", "platform", "ios"),
        ("profile", "buildProfile", "nonprod"),
        ("mode", "buildMode", "debug"),
        ("distribution", "distributionClass", "dev_direct"),
        ("application", "applicationId", "com.example.drift"),
        ("manifest-source", "sourceGitSha", "e" * 40),
        ("manifest-tree", "sourceTreeDigest", "sha1:" + "e" * 40),
        (
            "manifest-request",
            "qualificationRequestRef",
            "ghcr.io/example/quwoquan/request@sha256:" + "e" * 64,
        ),
        (
            "manifest-request-digest",
            "qualificationRequestDigest",
            "sha256:" + "e" * 64,
        ),
        (
            "manifest-rc",
            "rcTagAdmissionRef",
            "ghcr.io/example/quwoquan/rc-admission@sha256:" + "e" * 64,
        ),
        (
            "manifest-allocation",
            "artifactBuildNumberAllocationRef",
            "ghcr.io/example/quwoquan/allocation@sha256:" + "e" * 64,
        ),
        (
            "manifest-allocation-digest",
            "artifactBuildNumberAllocationDigest",
            "sha256:" + "e" * 64,
        ),
        ("manifest-version", "displayVersion", "9.9.9"),
        ("manifest-build", "buildNumber", "18"),
        ("signing", "signingIdentityDigest", "sha256:" + "z" * 64),
        ("provenance", "buildProvenanceDigest", "sha256:" + "z" * 64),
        ("runtime-trust", "runtimeConfigTrustEnvelopeDigest", "sha256:" + "z" * 64),
        ("promotable", "promotable", False),
    ),
)
def test_factory_reducer_rejects_app_artifact_manifest_drift(
    tmp_path: Path, label: str, field: str, value: object
) -> None:
    fixture = _actual_factory_fixture(tmp_path)
    _rewrite_app_material(
        tmp_path,
        fixture,
        lambda app: app["artifacts"]["android"].__setitem__(field, value),
    )
    with pytest.raises(ReleaseQualificationError, match="AppArtifactManifest"):
        _reduce_actual_factory_fixture(tmp_path, fixture)


def test_factory_reducer_rejects_app_artifact_manifest_shape_drift(
    tmp_path: Path,
) -> None:
    fixture = _actual_factory_fixture(tmp_path)
    _rewrite_app_material(
        tmp_path,
        fixture,
        lambda app: app["artifacts"]["web"].__setitem__(
            "runtimeConfigTrustEnvelopeDigest", "sha256:" + "0" * 64
        ),
    )
    with pytest.raises(ReleaseQualificationError, match="shape drifted"):
        _reduce_actual_factory_fixture(tmp_path, fixture)


def test_factory_reducer_rejects_app_material_digest_drift(tmp_path: Path) -> None:
    fixture = _actual_factory_fixture(tmp_path)
    _rewrite_app_material(
        tmp_path,
        fixture,
        lambda app: app.__setitem__("materialDigest", "sha256:" + "e" * 64),
        recompute_material_digest=False,
    )
    with pytest.raises(ReleaseQualificationError, match="self material digest drifted"):
        _reduce_actual_factory_fixture(tmp_path, fixture)


def test_factory_reducer_rejects_self_referential_app_evidence_digest(
    tmp_path: Path,
) -> None:
    fixture = _actual_factory_fixture(tmp_path)
    _rewrite_app_material(
        tmp_path,
        fixture,
        lambda app: app.__setitem__("appEvidenceDigest", "sha256:" + "a" * 64),
    )
    with pytest.raises(ReleaseQualificationError, match="self-referential appEvidenceDigest"):
        _reduce_actual_factory_fixture(tmp_path, fixture)
