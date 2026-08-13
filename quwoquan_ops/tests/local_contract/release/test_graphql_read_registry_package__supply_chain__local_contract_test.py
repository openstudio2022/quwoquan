"""GraphQL persisted-query registry package supply-chain contracts.

spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.graphql_read_registry_package import (
    SigningMaterial,
    materialize_graphql_read_runtime_config,
    materialize_graphql_read_registry_package,
    resolve_signing_material,
    validate_packaged_graphql_read_registry,
)


CANDIDATE = "sha256:" + "1" * 64


def _digest(value: str) -> str:
    return "sha256:" + value * 64


class GraphQLReadRegistryPackageContractTest(unittest.TestCase):
    def _candidate(self, root: Path, *, enabled: bool = True) -> Path:
        candidate = root / "candidate"
        service = candidate / "packages/services/api-edge"
        config_dir = service / "config"
        manifest_dir = service / "manifests"
        config_dir.mkdir(parents=True)
        manifest_dir.mkdir(parents=True)
        config = {
            "graphql_read": {
                "enabled": enabled,
                "registry_file": "graphql-read-registry.json" if enabled else "",
                "candidate_digest": "package-required" if enabled else "",
                "schema_file": "graphql-read-schema.graphqls" if enabled else "",
                "schema_digest": "package-required" if enabled else "",
                "trusted_public_keys_json": "package-required" if enabled else "",
                "owner_timeout_ms": 1500 if enabled else 0,
            },
            "config": {"version": _digest("2")},
        }
        (config_dir / "config.yaml").write_text(
            yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
        )
        documents = [
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "api-edge"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "api-edge",
                                    "volumeMounts": [
                                        {
                                            "name": "runtime-config",
                                            "mountPath": "/etc/qwq/config",
                                            "readOnly": True,
                                        }
                                    ],
                                }
                            ],
                            "volumes": [
                                {
                                    "name": "runtime-config",
                                    "configMap": {"name": "api-edge-runtime-config"},
                                }
                            ],
                        }
                    }
                },
            },
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {"name": "api-edge-runtime-config"},
                "data": {"api-edge.yaml": "placeholder\n"},
            },
        ]
        (manifest_dir / "all.yaml").write_text(
            yaml.safe_dump_all(documents, sort_keys=False), encoding="utf-8"
        )
        (service / "provenance.json").write_text(
            json.dumps(
                {
                    "schema": "qwq.service_package",
                    "service": "api-edge",
                    "environment": "alpha",
                    "configVersion": _digest("2"),
                    "digests": {
                        "config": _digest("3"),
                        "manifests": _digest("4"),
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return candidate

    def _signing(self, root: Path) -> SigningMaterial:
        private_key = root / "signing.pem"
        public_der = root / "public.der"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)],
            check=True,
            capture_output=True,
        )
        os.chmod(private_key, 0o600)
        subprocess.run(
            [
                "openssl",
                "pkey",
                "-in",
                str(private_key),
                "-pubout",
                "-outform",
                "DER",
                "-out",
                str(public_der),
            ],
            check=True,
            capture_output=True,
        )
        raw_public_key = public_der.read_bytes()[-32:]
        keyring = root / "trusted-public-keys.json"
        keyring.write_text(
            json.dumps(
                {"release-2026": base64.b64encode(raw_public_key).decode("ascii")},
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.chmod(keyring, 0o600)
        return SigningMaterial(
            key_id="release-2026",
            private_key_path=private_key,
            trusted_public_keys_path=keyring,
        )

    def test_materialize_signs_generator_exact_payload_and_binds_candidate_costs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-graphql-package-") as temporary:
            root = Path(temporary)
            candidate = self._candidate(root)
            signing = self._signing(root)
            descriptor = materialize_graphql_read_registry_package(
                repo_root=ROOT,
                candidate_root=candidate,
                environment="alpha",
                target="alpha-local",
                candidate_digest=CANDIDATE,
                signing=signing,
            )
            self.assertEqual(descriptor["candidateDigest"], CANDIDATE)
            self.assertEqual(descriptor["costModelVersion"], "graphql-cost-v1")
            self.assertRegex(descriptor["costPlanAggregateDigest"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(descriptor["signingKeyId"], "release-2026")
            secret_path = str(signing.private_key_path).encode("utf-8")
            secret_bytes = signing.private_key_path.read_bytes()
            for artifact in candidate.rglob("*"):
                if artifact.is_file():
                    encoded = artifact.read_bytes()
                    self.assertNotIn(secret_path, encoded)
                    self.assertNotIn(secret_bytes, encoded)

            validated = validate_packaged_graphql_read_registry(
                repo_root=ROOT,
                candidate_root=candidate,
                expected_environment="alpha",
                expected_target="alpha-local",
                expected_candidate_digest=CANDIDATE,
                expected_descriptor=descriptor,
            )
            self.assertEqual(validated, descriptor)

            config = yaml.safe_load(
                (candidate / "packages/services/api-edge/config/config.yaml").read_text()
            )
            self.assertTrue(config["graphql_read"]["enabled"])
            self.assertEqual(config["graphql_read"]["candidate_digest"], CANDIDATE)
            self.assertEqual(
                config["graphql_read"]["schema_digest"], descriptor["schemaDigest"]
            )
            self.assertEqual(
                set(json.loads(config["graphql_read"]["trusted_public_keys_json"])),
                {"release-2026"},
            )

            manifests = list(
                yaml.safe_load_all(
                    (candidate / "packages/services/api-edge/manifests/all.yaml").read_text()
                )
            )
            config_map = next(item for item in manifests if item.get("kind") == "ConfigMap")
            self.assertEqual(
                set(config_map["data"]),
                {
                    "api-edge.yaml",
                    "graphql-read-registry.json",
                    "graphql-read-schema.graphqls",
                    "graphql-read-trusted-public-keys.json",
                    "graphql-read-package.json",
                },
            )

    def test_mutable_runtime_materializes_signed_candidate_bound_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-graphql-runtime-") as temporary:
            root = Path(temporary)
            config_path = root / "api-edge.yaml"
            config_path.write_text(
                yaml.safe_dump(
                    {
                        "graphql_read": {
                            "enabled": True,
                            "registry_file": "graphql-read-registry.json",
                            "candidate_digest": "package-required",
                            "schema_file": "graphql-read-schema.graphqls",
                            "schema_digest": "package-required",
                            "trusted_public_keys_json": "package-required",
                            "owner_timeout_ms": 1500,
                        },
                        "config": {"version": _digest("2")},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            signing = self._signing(root)
            descriptor = materialize_graphql_read_runtime_config(
                repo_root=ROOT,
                runtime_config_path=config_path,
                environment="alpha",
                target="alpha-local",
                candidate_digest=CANDIDATE,
                signing=signing,
            )
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.assertEqual(config["graphql_read"]["candidate_digest"], CANDIDATE)
            self.assertEqual(
                config["graphql_read"]["schema_digest"],
                descriptor["schemaDigest"],
            )
            self.assertEqual(config["config"]["version"], descriptor["configVersion"])
            self.assertEqual(
                {path.name for path in root.iterdir()},
                {
                    "api-edge.yaml",
                    "graphql-read-registry.payload.json",
                    "graphql-read-registry.json",
                    "graphql-read-schema.graphqls",
                    "graphql-read-trusted-public-keys.json",
                    "public.der",
                    "signing.pem",
                    "trusted-public-keys.json",
                },
            )
            secret_bytes = signing.private_key_path.read_bytes()
            for artifact in root.iterdir():
                if artifact.is_file() and artifact != signing.private_key_path:
                    self.assertNotIn(secret_bytes, artifact.read_bytes())

    def test_validation_recomputes_ast_payload_and_rejects_tamper_or_foreign_candidate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-graphql-package-") as temporary:
            root = Path(temporary)
            candidate = self._candidate(root)
            descriptor = materialize_graphql_read_registry_package(
                repo_root=ROOT,
                candidate_root=candidate,
                environment="alpha",
                target="alpha-local",
                candidate_digest=CANDIDATE,
                signing=self._signing(root),
            )
            with self.assertRaisesRegex(ValueError, "candidate"):
                validate_packaged_graphql_read_registry(
                    repo_root=ROOT,
                    candidate_root=candidate,
                    expected_environment="alpha",
                    expected_target="alpha-local",
                    expected_candidate_digest="sha256:" + "9" * 64,
                    expected_descriptor=descriptor,
                )

    def test_self_verify_never_invokes_current_source_generators(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-graphql-package-") as temporary:
            root = Path(temporary)
            candidate = self._candidate(root)
            descriptor = materialize_graphql_read_registry_package(
                repo_root=ROOT,
                candidate_root=candidate,
                environment="alpha",
                target="alpha-local",
                candidate_digest=CANDIDATE,
                signing=self._signing(root),
            )

            with mock.patch(
                "quwoquan_ops.cli.lib.graphql_read_registry_package._generate_payload",
                side_effect=AssertionError("self_verify must not run codegen"),
            ):
                validated = validate_packaged_graphql_read_registry(
                    repo_root=ROOT,
                    candidate_root=candidate,
                    expected_environment="alpha",
                    expected_target="alpha-local",
                    expected_candidate_digest=CANDIDATE,
                    expected_descriptor=descriptor,
                    purpose="self_verify",
                )

            self.assertEqual(validated, descriptor)

            payload_path = candidate / descriptor["payloadRef"]
            payload = json.loads(payload_path.read_text())
            payload["entries"][0]["cost"]["complexity"] += 1
            payload_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "payload|digest|AST"):
                validate_packaged_graphql_read_registry(
                    repo_root=ROOT,
                    candidate_root=candidate,
                    expected_environment="alpha",
                    expected_target="alpha-local",
                    expected_candidate_digest=CANDIDATE,
                    expected_descriptor=descriptor,
                )

    def test_signing_material_is_explicit_external_restricted_and_matches_keyring(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-graphql-package-") as temporary:
            root = Path(temporary)
            signing = self._signing(root)
            environment = {
                "QWQ_GRAPHQL_READ_REGISTRY_SIGNING_KEY_ID": signing.key_id,
                "QWQ_GRAPHQL_READ_REGISTRY_SIGNING_PRIVATE_KEY_FILE": str(
                    signing.private_key_path
                ),
                "QWQ_GRAPHQL_READ_REGISTRY_TRUSTED_PUBLIC_KEYS_FILE": str(
                    signing.trusted_public_keys_path
                ),
            }
            self.assertEqual(resolve_signing_material(ROOT, environment.get), signing)
            with self.assertRaisesRegex(ValueError, "required"):
                resolve_signing_material(ROOT, {}.get)
            os.chmod(signing.private_key_path, 0o644)
            with self.assertRaisesRegex(ValueError, "permissions"):
                resolve_signing_material(ROOT, environment.get)

            external = root / "external.pem"
            external.write_bytes(signing.private_key_path.read_bytes())
            signing.private_key_path.unlink()
            signing.private_key_path.symlink_to(external)
            with self.assertRaisesRegex(ValueError, "non-symlink"):
                resolve_signing_material(ROOT, environment.get)

    def test_disabled_graphql_cannot_enter_a_runtime_candidate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-graphql-package-") as temporary:
            root = Path(temporary)
            candidate = self._candidate(root, enabled=False)
            with self.assertRaisesRegex(ValueError, "disabled"):
                materialize_graphql_read_registry_package(
                    repo_root=ROOT,
                    candidate_root=candidate,
                    environment="alpha",
                    target="alpha-local",
                    candidate_digest=CANDIDATE,
                    signing=self._signing(root),
                )

    def test_four_environments_declare_package_owned_graphql_inputs(self) -> None:
        service = ROOT / "quwoquan_service/services/api-edge"
        for environment in ("alpha", "beta", "gamma", "prod"):
            payload = yaml.safe_load(
                (service / f"environments/{environment}/config.yaml").read_text()
            )
            overrides = payload["overrides"]
            self.assertIs(overrides["sys.api-edge.graphql_read.enabled"], True)
            self.assertEqual(
                overrides["sys.api-edge.graphql_read.registry_file"],
                "graphql-read-registry.json",
            )
            self.assertEqual(
                overrides["sys.api-edge.graphql_read.candidate_digest"],
                "package-required",
            )
            self.assertEqual(
                overrides["sys.api-edge.graphql_read.schema_file"],
                "graphql-read-schema.graphqls",
            )

        deployment = (service / "deploy/base/deployment.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("mountPath: /etc/qwq/config\n", deployment)
        self.assertNotIn("subPath: api-edge.yaml", deployment)

    def test_local_runtime_copies_only_candidate_bound_graphql_public_inputs(self) -> None:
        launcher = (
            ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('if [[ "$service" == "api-edge" ]]; then', launcher)
        self.assertIn('"${QWQ_RELEASE_CANDIDATE_DIGEST:?candidate digest is required}"', launcher)
        for name in (
            "graphql-read-schema.graphqls",
            "graphql-read-registry.json",
            "graphql-read-trusted-public-keys.json",
        ):
            self.assertIn(name, launcher)
        self.assertIn("GraphQL registry runtime copy drifted", launcher)
        self.assertIn(
            'copy_service_package_config "$service" || return $?', launcher
        )
        self.assertNotIn("QWQ_GRAPHQL_READ_REGISTRY_SIGNING_PRIVATE_KEY_FILE", launcher)

    def test_stackctl_fails_signing_before_staging_and_seals_before_images(self) -> None:
        source = (ROOT / "quwoquan_ops/cli/stackctl.py").read_text(encoding="utf-8")
        command = source[source.index("def command_package(") :]
        new_candidate = command[: command.index("def _command_package_unlocked(")]
        self.assertLess(
            new_candidate.index("resolve_graphql_read_signing_material(ROOT)"),
            new_candidate.index("staging_dir = Path("),
        )
        unlocked = command[command.index("def _command_package_unlocked(") :]
        self.assertLess(
            unlocked.index("materialize_graphql_read_registry_package("),
            unlocked.index("_build_package_bound_local_images("),
        )
        self.assertIn('"graphqlReadRegistry": graphql_read_registry_package', unlocked)
        self.assertIn(
            "candidate_root=api_edge_package.parents[2]",
            unlocked,
        )
        self.assertNotIn(
            "candidate_root=api_edge_package.parent.parent",
            unlocked,
        )


if __name__ == "__main__":
    unittest.main()
