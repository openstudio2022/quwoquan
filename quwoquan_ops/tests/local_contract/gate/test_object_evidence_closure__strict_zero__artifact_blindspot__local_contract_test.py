"""verify_object_evidence_closure 的 artifact 摘要闭合与 scanner blindspot 合约。

由 test_object_evidence_closure__strict_zero__contract_graph__local_contract_test.py
（Python 1000 行硬顶治理）按场景拆出：sha 漂移即结构缺口、路径逃逸拒绝、
blindspot 登记册必须以 sha 绑定生产实现证据。测试逐字搬移；共享 harness 见
tests/support。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock


_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.tests.support.object_evidence_closure_test_support import (
    ObjectEvidenceClosureStrictZeroSupport,
    canonical_evidence_packet,
    closure,
    synthetic_graph,
)


class ObjectEvidenceClosureStrictZeroTest(ObjectEvidenceClosureStrictZeroSupport):
    def test_unregistered_blind_spot_is_blocked(self) -> None:
        graph = self.write_graph(
            synthetic_graph(missing="blindspot.python_store_invisible")
        )

        result = self.run_gate("--graph", str(graph))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("GATE_BLOCK 维度盲点集合与登记册不一致", result.stdout)
        self.assertIn("content.demo", result.stdout)

    # --- artifact 与 report identity ------------------------------------

    def test_artifact_sha_mutation_is_a_structural_gap(self) -> None:
        artifact, original_digest = self.write_artifact("store.go", b"before")
        artifact.write_bytes(b"after")

        with mock.patch.object(closure, "ROOT", self.workspace):
            gaps = closure.artifact_gaps(
                "content.demo",
                "aggregate_root",
                "implemented",
                {
                    "service": {
                        "store": [
                            {
                                "path": artifact.relative_to(self.workspace).as_posix(),
                                "sha256": original_digest,
                            }
                        ]
                    }
                },
            )

        self.assertEqual([gap.dimension for gap in gaps], ["derivation.artifact_digest"])
        self.assertIn("expected=", gaps[0].detail)
        self.assertIn("actual=", gaps[0].detail)

    def test_publication_delivery_artifact_is_in_digest_closure(self) -> None:
        artifact, digest = self.write_artifact("relay.go", b"relay-v1")
        packet = {
            "publicationDelivery": [
                {
                    "storage": "content_demo_outbox",
                    "artifact": {
                        "path": artifact.relative_to(self.workspace).as_posix(),
                        "sha256": digest,
                    },
                }
            ]
        }

        with mock.patch.object(closure, "ROOT", self.workspace):
            self.assertEqual(
                closure.artifact_gaps(
                    "content.demo", "aggregate_root", "implemented", packet
                ),
                [],
            )
            artifact.write_bytes(b"relay-v2")
            gaps = closure.artifact_gaps(
                "content.demo", "aggregate_root", "implemented", packet
            )
        self.assertEqual([gap.dimension for gap in gaps], ["derivation.artifact_digest"])
        self.assertIn("publicationDelivery", gaps[0].detail)

    def test_service_outbox_artifact_is_in_digest_closure(self) -> None:
        artifact, digest = self.write_artifact("outbox.go", b"outbox-v1")
        packet = canonical_evidence_packet()
        packet["service"]["outbox"] = [
            {
                "storage": "content_demo_outbox",
                "artifact": {
                    "path": artifact.relative_to(self.workspace).as_posix(),
                    "sha256": digest,
                },
            }
        ]

        with mock.patch.object(closure, "ROOT", self.workspace):
            self.assertEqual(
                closure.artifact_gaps(
                    "content.demo", "aggregate_root", "implemented", packet
                ),
                [],
            )
            artifact.write_bytes(b"outbox-v2")
            gaps = closure.artifact_gaps(
                "content.demo", "aggregate_root", "implemented", packet
            )

        self.assertEqual([gap.dimension for gap in gaps], ["derivation.artifact_digest"])
        self.assertIn("service.outbox", gaps[0].detail)

    def test_outbox_gap_diagnostic_reads_producer_separated_service_evidence(self) -> None:
        detail = closure.publication_gap_detail(
            "implementation.outbox",
            {
                "publicationStores": ["already_bound", "missing_outbox"],
                "service": {
                    "outbox": [
                        {
                            "storage": "already_bound",
                            "artifact": {"path": "unused.go", "sha256": "0" * 64},
                        }
                    ]
                },
            },
        )

        self.assertIn("missing_outbox", detail)
        self.assertNotIn("already_bound", detail)

    def test_artifact_paths_reject_absolute_traversal_and_symlink_escape(self) -> None:
        artifact, digest = self.write_artifact("inside.go", b"inside")
        with tempfile.TemporaryDirectory() as outside_dir:
            outside = Path(outside_dir) / "outside.go"
            outside.write_bytes(b"outside")
            symlink = self.workspace / "escaped.go"
            symlink.symlink_to(outside)
            cases = (
                str(artifact),
                "../outside.go",
                symlink.relative_to(self.workspace).as_posix(),
            )
            with mock.patch.object(closure, "ROOT", self.workspace):
                for path_text in cases:
                    with self.subTest(path=path_text):
                        gaps = closure.artifact_integrity_gaps(
                            "content.demo",
                            "aggregate_root",
                            "implemented",
                            "service.store",
                            {"path": path_text, "sha256": digest},
                        )
                        self.assertEqual(
                            [gap.dimension for gap in gaps],
                            ["derivation.artifact_missing"],
                        )

    # --- scanner blindspot ------------------------------------------------

    def test_attested_scope_alone_cannot_release_a_blind_spot(self) -> None:
        registry = self.write_blind_spot_registry(
            [
                {
                    "object_id": "content.demo",
                    "dimension": "blindspot.publication_delivery_tracking",
                    "attested_scope": "demo scope",
                }
            ]
        )

        with self.assertRaises(SystemExit) as failure:
            closure.load_blind_spot_registry(registry)

        self.assertIn("classification", str(failure.exception))
        self.assertIn("attested_scope 不能证明实现存在", str(failure.exception))

    def test_implemented_blind_spot_requires_sha_bound_write_and_delivery(self) -> None:
        write, write_digest = self.write_artifact(
            "quwoquan_service/services/demo-service/internal/demo/store.go",
            b"write",
        )
        delivery, delivery_digest = self.write_artifact(
            "quwoquan_service/services/demo-service/internal/demo/relay.go",
            b"delivery",
        )
        key = ("content.demo", "blindspot.publication_delivery_tracking")
        registry_path = self.write_blind_spot_registry(
            [
                {
                    "object_id": key[0],
                    "dimension": key[1],
                    "attested_scope": "demo scope",
                    "classification": closure.BLIND_SPOT_IMPLEMENTED,
                    "implementation_evidence": {
                        "publication_write": [
                            {
                                "path": write.relative_to(self.workspace).as_posix(),
                                "sha256": write_digest,
                            }
                        ],
                        "publication_delivery": [
                            {
                                "path": delivery.relative_to(self.workspace).as_posix(),
                                "sha256": delivery_digest,
                            }
                        ],
                    },
                }
            ]
        )
        with mock.patch.object(closure, "ROOT", self.workspace):
            registry = closure.load_blind_spot_registry(registry_path)
        gap = closure.Gap(
            key[0], "aggregate_root", "implemented", key[1], "scanner blindspot"
        )

        self.assertEqual(closure.blind_spot_gaps([gap], registry), [])

    def test_implemented_blind_spot_rejects_test_source_as_evidence(self) -> None:
        test_source, digest = self.write_artifact(
            "quwoquan_service/services/demo-service/internal/demo/store_test.go",
            b"test only",
        )
        registry_path = self.write_blind_spot_registry(
            [
                {
                    "object_id": "content.demo",
                    "dimension": "blindspot.publication_write_tracking",
                    "attested_scope": "demo scope",
                    "classification": closure.BLIND_SPOT_IMPLEMENTED,
                    "implementation_evidence": {
                        "publication_write": [
                            {
                                "path": test_source.relative_to(
                                    self.workspace
                                ).as_posix(),
                                "sha256": digest,
                            }
                        ],
                        "publication_delivery": [
                            {
                                "path": test_source.relative_to(
                                    self.workspace
                                ).as_posix(),
                                "sha256": digest,
                            }
                        ],
                    },
                }
            ]
        )

        with (
            mock.patch.object(closure, "ROOT", self.workspace),
            self.assertRaises(SystemExit) as failure,
        ):
            closure.load_blind_spot_registry(registry_path)

        self.assertIn("生产 Go/Python 源码", str(failure.exception))

    def test_implementation_missing_blind_spot_stays_blocking(self) -> None:
        key = ("content.demo", "blindspot.publication_delivery_tracking")
        gap = closure.Gap(
            key[0], "aggregate_root", "implemented", key[1], "scanner blindspot"
        )
        problems = closure.blind_spot_gaps(
            [gap],
            {
                key: {
                    "attested_scope": "demo scope",
                    "classification": closure.BLIND_SPOT_MISSING,
                }
            },
        )

        self.assertEqual(len(problems), 1)
        self.assertIn("implementation_missing", problems[0])
        self.assertIn("必须补生产实现", problems[0])


if __name__ == "__main__":
    unittest.main()
