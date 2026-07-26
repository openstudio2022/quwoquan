from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "quwoquan_ops/cli/cloud_contract_handoff.py"
SPEC = importlib.util.spec_from_file_location("cloud_contract_handoff", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
handoff = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = handoff
SPEC.loader.exec_module(handoff)


class CloudContractHandoffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.graph = self.root / "contract_graph.json"
        self.lock = self.root / "contract_graph.lock.json"
        self.report = self.root / "contract_graph.breaking.json"
        self.policy = self.root / "ownership.json"
        self.policy.write_text(
            json.dumps(
                {
                    "leaseRoot": str(self.root / "leases"),
                    "resources": [
                        {
                            "id": "app-cloud-handoff",
                            "owner": "app-cloud-governance",
                            "writePaths": [str(self.lock), str(self.report)],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_graph(
        self,
        *,
        path_template: str = "/things",
        duplicate: bool = False,
    ) -> None:
        operations = [
            {
                "id": "sample.thing.ListThings",
                "localId": "ListThings",
                "domain": "sample",
                "objectId": "sample.thing",
                "method": "GET",
                "pathTemplate": path_template,
                "kind": "query",
                "kindExplicit": True,
                "facet": "ThingQueryFacade",
                "facadeMethod": "listThings",
                "aggregateOwner": "",
                "mutationTarget": "",
                "invariantTarget": "",
                "actorRequirement": "persona",
                "concurrency": {"versionPrecondition": "if_match"},
                "sourcePath": "sample/thing/operations.yaml",
            }
        ]
        if duplicate:
            operations.append(
                {
                    **operations[0],
                    "id": "other.thing.ListThings",
                    "domain": "other",
                    "objectId": "other.thing",
                    "sourcePath": "other/thing/operations.yaml",
                }
            )
        graph = {
            "objects": [],
            "operations": operations,
            "projections": [],
            "businessObjectMaps": [],
            "sources": [
                {
                    "path": "sample/thing/operations.yaml",
                    "sha256": "a" * 64,
                }
            ],
            "documents": [
                {
                    "path": "sample/thing/operations.yaml",
                    "sha256": "a" * 64,
                    "mediaType": "application/yaml",
                    "content": {
                        "api_routes": [
                            {
                                "operation": "ListThings",
                                "method": "GET",
                                "path": path_template,
                                "security": {"auth_mode": "required"},
                            }
                        ]
                    },
                },
                {
                    "path": "_shared/ui_surfaces.yaml",
                    "sha256": "b" * 64,
                    "mediaType": "application/yaml",
                    "content": {
                        "surfaces": [
                            {
                                "id": "thingList",
                                "owner": "sample" if not duplicate else "unknown",
                                "operation_ids": ["ListThings"],
                            }
                        ]
                    },
                },
            ],
        }
        self.graph.write_text(
            json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_rejects_retired_registry_and_graph_version_fields(self) -> None:
        self._write_graph()
        graph = json.loads(self.graph.read_text(encoding="utf-8"))
        for field, value in (
            ("version", 1),
            ("schema", 2),
            ("registryRevision", "retired"),
        ):
            with self.subTest(field=field):
                candidate = dict(graph)
                candidate[field] = value
                self.graph.write_text(
                    json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, "禁止退休字段"):
                    handoff.accept(self._args())

    def _args(self, *, approve_breaking: bool = False) -> argparse.Namespace:
        return argparse.Namespace(
            graph=self.graph,
            lock=self.lock,
            report=self.report,
            policy=self.policy,
            owner="app-cloud-governance",
            lease_ttl_minutes=10,
            approve_breaking=approve_breaking,
        )

    def test_accept_and_verify_are_content_addressed_and_release_lease(
        self,
    ) -> None:
        self._write_graph()

        self.assertEqual(handoff.accept(self._args()), 0)
        verify_args = self._args()
        self.assertEqual(handoff.verify(verify_args), 0)

        lock = json.loads(self.lock.read_text(encoding="utf-8"))
        self.assertEqual(
            lock["contractGraph"]["sha256"],
            handoff.sha256_bytes(self.graph.read_bytes()),
        )
        self.assertEqual(
            lock["appExposedOperations"][0]["canonicalOperationId"],
            "sample.thing.ListThings",
        )
        self.assertEqual(
            lock["appExposedOperations"][0]["concurrency"],
            {"versionPrecondition": "if_match"},
        )
        self.assertFalse((self.root / "leases/app-cloud-handoff.lock").exists())

    def test_ambiguous_surface_binding_fails_without_guessing(self) -> None:
        self._write_graph(duplicate=True)

        with self.assertRaisesRegex(ValueError, "禁止推断"):
            handoff.accept(self._args())

        self.assertFalse(self.lock.exists())
        self.assertFalse(self.report.exists())

    def test_breaking_transport_change_requires_explicit_approval(self) -> None:
        self._write_graph()
        handoff.accept(self._args())
        self._write_graph(path_template="/" + "v2" + "/things")

        with self.assertRaisesRegex(ValueError, "breaking change"):
            handoff.accept(self._args())

        self.assertEqual(handoff.accept(self._args(approve_breaking=True)), 0)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["decision"], "approved")
        self.assertEqual(report["breakingChanges"][0]["field"], "pathTemplate")


if __name__ == "__main__":
    unittest.main()
