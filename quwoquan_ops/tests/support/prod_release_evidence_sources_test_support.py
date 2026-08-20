"""Prod 发布交易用例的证据源 fixture 构造。

这些构造器把 application package payload、Provider conformance 逐格证据与
raw 目录布局拼成 finalizer/collector 期望的输入形状，供 local_contract 用例复用。
"""

from __future__ import annotations

from pathlib import Path

from quwoquan_ops.ci.render_provider_conformance_source import (
    expected_required_cell_count_from_readiness,
)
from quwoquan_ops.cli.lib import provider_conformance
from quwoquan_ops.cli.prod import collect_release_artifact_descriptors as evidence_collector
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact as finalizer
from quwoquan_ops.cli.prod import generate_mainline_release_artifact as generator
from quwoquan_ops.tests.support.app_artifact_manifest_test_support import (
    app_artifact_manifest,
)

PROVIDER_EVIDENCE_DIGEST = "sha256:" + ("e" * 64)
PROVIDER_EVIDENCE_REF = (
    "oci://ghcr.io/example/quwoquan/provider-evidence@" + PROVIDER_EVIDENCE_DIGEST
)


def _application_package_payloads(root: Path) -> Path:
    payloads = root / "application-payloads"
    for environment in finalizer.ENVIRONMENTS:
        for surface in finalizer.APPLICATION_PACKAGES[environment]:
            package = payloads / environment / surface
            package.mkdir(parents=True, exist_ok=True)
            if environment == "prod" and surface == "android":
                (package / "quwoquan.apk").write_bytes(b"signed-apk")
            elif environment == "prod" and surface == "opsPortal":
                generator.write_json(package / "manifest.json", {"name": "ops"})
                (package / "dist").mkdir(exist_ok=True)
                (package / "dist/index.html").write_text(
                    "ops portal", encoding="utf-8"
                )
            else:
                (package / "payload.bin").write_bytes(
                    f"{environment}/{surface}".encode("utf-8")
                )
    return payloads

def _provider_raw_dir(root: Path) -> Path:
    return root / "provider-raw"

def _evidence_sources(
    root: Path, manifest: dict[str, object]
) -> dict[str, Path]:
    sources = root / "sources"
    payload_root = _application_package_payloads(root)
    source = manifest["source"]
    assert isinstance(source, dict)
    contract_graph_path = sources / "contractGraph.json"
    generator.write_json(
        contract_graph_path,
        {
            "schema": "qwq.contract-graph",
            "sources": [],
            "documents": [],
            "objects": [],
            "operations": [],
            "projections": [],
        },
    )
    provider_readiness = {
        environment: {
            capability_id: {
                "required": True,
                "capability_ready": True,
            }
            for capability_id in ("search", "fixture-message-transport")
        }
        for environment in provider_conformance.READINESS_ENVIRONMENTS
    }
    provider_cells = sorted(
        provider_conformance.expected_required_cell_keys(
            {
                "providerConformanceCapabilityIds": sorted(
                    provider_readiness["prod"]
                )
            }
        )
    )
    provider_evidence_count = expected_required_cell_count_from_readiness(
        provider_readiness
    )
    if len(provider_cells) != provider_evidence_count:
        raise AssertionError("Provider fixture cell count does not match readiness")
    provider_files: dict[str, str] = {}
    for index, (capability_id, environment, layer) in enumerate(provider_cells):
        relative = (
            f"env/{environment}/runs/provider-check-{index:03d}/"
            "provider-conformance.evidence.json"
        )
        provider_raw = _provider_raw_dir(root) / relative
        generator.write_json(
            provider_raw,
            {
                "provider": capability_id,
                "environment": environment,
                "testLayer": layer,
                "status": "passed",
            },
        )
        provider_files[f"evidence/raw/provider/{relative}"] = (
            finalizer.sha256_file(provider_raw)
        )
    payloads: dict[str, dict[str, object]] = {
        "publicWeb": {
            "schema": "client-app.web.official-release",
            "sourceGitSha": source["gitSha"],
            "sourceTreeDigest": source["treeDigest"],
            "contentSHA256": finalizer.sha256_tree(
                payload_root / "prod/web"
            ).removeprefix("sha256:"),
            "artifactManifest": app_artifact_manifest(
                environment="prod",
                surface="web",
                source_git_sha=str(source["gitSha"]),
                source_tree_digest=str(source["treeDigest"]),
                artifact_digest=finalizer.sha256_tree(payload_root / "prod/web"),
            ),
        },
        "androidOfficialRelease": {
            "schema": "client-app.android.official-release",
            "sourceGitSha": source["gitSha"],
            "sourceTreeDigest": source["treeDigest"],
            "packagedAPK": "quwoquan.apk",
            "apkSHA256": finalizer.sha256_file(
                payload_root / "prod/android/quwoquan.apk"
            ).removeprefix("sha256:"),
            "artifactManifest": app_artifact_manifest(
                environment="prod",
                surface="android",
                source_git_sha=str(source["gitSha"]),
                source_tree_digest=str(source["treeDigest"]),
                artifact_digest=finalizer.sha256_file(
                    payload_root / "prod/android/quwoquan.apk"
                ),
            ),
        },
        "opsPortal": {
            "schema": "qwq.ops_portal_package",
            "sourceGitSha": source["gitSha"],
            "sourceTreeDigest": source["treeDigest"],
            "packageDigest": finalizer.sha256_ops_portal_tree(
                payload_root / "prod/opsPortal/dist"
            ),
            "digests": {
                "manifest": finalizer.sha256_file(
                    payload_root / "prod/opsPortal/manifest.json"
                ),
                "distTree": finalizer.sha256_ops_portal_tree(
                    payload_root / "prod/opsPortal/dist"
                ),
            },
        },
        "contractGraph": {
            "schema": "qwq.contract-graph",
            "sources": [],
            "documents": [],
            "objects": [],
            "operations": [],
            "projections": [],
        },
        "providerEvidence": {
            "schema": "provider-conformance-readiness",
            "status": "passed",
            "generatedAt": "2026-07-28T00:00:00Z",
            "source": {
                key: source[key]
                for key in ("gitSha", "treeDigest", "repository", "workflowRunId")
            },
            "candidateMaterial": {
                "environmentArtifacts": {
                    environment: {
                        "environmentArtifactDigest": artifact[
                            "environmentArtifactDigest"
                        ],
                        "images": {
                            owner: descriptor["digest"]
                            for owner, descriptor in artifact["images"].items()
                        },
                    }
                    for environment, artifact in manifest[
                        "environmentArtifacts"
                    ].items()
                },
                "contractGraphDigest": finalizer.sha256_file(contract_graph_path),
            },
            "sourceEvidence": {
                "ref": PROVIDER_EVIDENCE_REF,
                "digest": PROVIDER_EVIDENCE_DIGEST,
                "files": provider_files,
            },
            "evidenceCount": provider_evidence_count,
            "sourceCoverageIssues": [],
            "readiness": provider_readiness,
            "issues": [],
        },
    }
    application_material: dict[str, dict[str, str]] = {
        environment: {} for environment in finalizer.ENVIRONMENTS
    }
    for environment, surface in sorted(evidence_collector.ALL_APPLICATION_KEYS):
        special_source = next(
            (
                artifact_id
                for artifact_id, target in evidence_collector.APPLICATION_SOURCE_TARGETS.items()
                if target == (environment, surface)
            ),
            None,
        )
        application_payload = (
            payloads[special_source]
            if special_source is not None
            else {
                "packageDigest": finalizer.sha256_tree(
                    payload_root / environment / surface
                )
            }
        )
        application_material[environment][surface] = (
            evidence_collector.application_package_digest(
                application_payload,
                environment=environment,
                surface=surface,
            )
        )
    release_closure_files: dict[str, dict[str, str]] = {}
    for index, (label, relative) in enumerate(
        sorted(evidence_collector.RELEASE_CLOSURE_PATHS.items())
    ):
        closure_path = sources / relative
        generator.write_json(
            closure_path,
            {"label": label, "sequence": index},
        )
        release_closure_files[label] = {
            "path": relative,
            "digest": finalizer.sha256_file(closure_path),
        }
    payloads["testEvidence"] = {
        "schema": "qwq.three-layer-case-results",
        "status": "passed",
        "layers": {
            layer: {
                "status": "passed",
                "artifactDigest": "sha256:" + ("f" * 64),
                **(
                    {
                        "candidateMaterial": {
                            "environmentArtifacts": {
                                environment: {
                                    "environmentArtifactDigest": artifact[
                                        "environmentArtifactDigest"
                                    ],
                                    "images": {
                                        owner: descriptor["digest"]
                                        for owner, descriptor in artifact[
                                            "images"
                                        ].items()
                                    },
                                    "configurationPackages": {
                                        service: descriptor["digest"]
                                        for service, descriptor in artifact[
                                            "configurationPackages"
                                        ].items()
                                    },
                                }
                                for environment, artifact in manifest[
                                    "environmentArtifacts"
                                ].items()
                            },
                            "applicationPackages": application_material,
                            "contractGraphDigest": finalizer.sha256_file(
                                contract_graph_path
                            ),
                        }
                    }
                    if layer == "user_acceptance"
                    else {}
                ),
            }
            for layer in finalizer.TEST_LAYERS
        },
        "evidence": {"files": release_closure_files},
    }
    result: dict[str, Path] = {}
    for key, payload in payloads.items():
        path = contract_graph_path if key == "contractGraph" else sources / f"{key}.json"
        generator.write_json(path, payload)
        result[key] = path
    return result

def _application_package_sources(
    root: Path,
    manifest: dict[str, object],
) -> dict[tuple[str, str], Path]:
    source = manifest["source"]
    assert isinstance(source, dict)
    payloads = _application_package_payloads(root)
    result: dict[tuple[str, str], Path] = {}
    for environment, surface in sorted(evidence_collector.GENERIC_APPLICATION_KEYS):
        path = root / "application-sources" / f"{environment}--{surface}.json"
        generator.write_json(
            path,
            {
                "schema": evidence_collector.GENERIC_APPLICATION_SCHEMA,
                "environment": environment,
                "surface": surface,
                "sourceGitSha": source["gitSha"],
                "sourceTreeDigest": source["treeDigest"],
                "packageDigest": (package_digest := finalizer.sha256_tree(
                    payloads / environment / surface
                )),
                "artifactManifest": app_artifact_manifest(
                    environment=environment,
                    surface=surface,
                    source_git_sha=str(source["gitSha"]),
                    source_tree_digest=str(source["treeDigest"]),
                    artifact_digest=package_digest,
                ),
            },
        )
        result[(environment, surface)] = path
    return result
