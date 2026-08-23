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
from quwoquan_ops.cli.lib.app_identity import resolve_build_product
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
    for build_product_id in finalizer.APPLICATION_PACKAGES:
        package = payloads / build_product_id
        package.mkdir(parents=True, exist_ok=True)
        (package / "payload.bin").write_bytes(build_product_id.encode("utf-8"))
    portal = payloads / "opsPortal"
    generator.write_json(portal / "manifest.json", {"name": "ops"})
    (portal / "dist").mkdir(exist_ok=True)
    (portal / "dist/index.html").write_text("ops portal", encoding="utf-8")
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
        },
        "androidOfficialRelease": {
            "schema": "client-app.android.official-release",
            "sourceGitSha": source["gitSha"],
            "sourceTreeDigest": source["treeDigest"],
        },
        "opsPortal": {
            "schema": "qwq.ops_portal_package",
            "sourceGitSha": source["gitSha"],
            "sourceTreeDigest": source["treeDigest"],
            "packageDigest": finalizer.sha256_ops_portal_tree(
                payload_root / "opsPortal/dist"
            ),
            "digests": {
                "manifest": finalizer.sha256_file(
                    payload_root / "opsPortal/manifest.json"
                ),
                "distTree": finalizer.sha256_ops_portal_tree(
                    payload_root / "opsPortal/dist"
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
    application_material = {
        build_product_id: finalizer.sha256_tree(payload_root / build_product_id)
        for build_product_id in finalizer.APPLICATION_PACKAGES
    }
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
                            "opsPortal": finalizer.sha256_ops_portal_tree(
                                payload_root / "opsPortal/dist"
                            ),
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
) -> dict[str, Path]:
    source = manifest["source"]
    assert isinstance(source, dict)
    payloads = _application_package_payloads(root)
    result: dict[str, Path] = {}
    for build_product_id in sorted(evidence_collector.GENERIC_APPLICATION_KEYS):
        product = resolve_build_product(build_product_id)
        path = root / "application-sources" / f"{build_product_id}.json"
        package_digest = finalizer.sha256_tree(payloads / build_product_id)
        generator.write_json(
            path,
            {
                "schema": evidence_collector.GENERIC_APPLICATION_SCHEMA,
                "buildProductId": build_product_id,
                "buildProfile": product.build_profile,
                "platform": product.platform,
                "sourceGitSha": source["gitSha"],
                "sourceTreeDigest": source["treeDigest"],
                "packageDigest": package_digest,
                "artifactManifest": app_artifact_manifest(
                    build_product_id=build_product_id,
                    source_git_sha=str(source["gitSha"]),
                    source_tree_digest=str(source["treeDigest"]),
                    artifact_digest=package_digest,
                ),
            },
        )
        result[build_product_id] = path
    return result
