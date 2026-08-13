from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
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
        self.original_handoff_root = handoff.ROOT
        handoff.ROOT = self.root
        compiler_input = (
            self.root
            / "quwoquan_service/internal/metadata/ast/fixture.go"
        )
        compiler_input.parent.mkdir(parents=True, exist_ok=True)
        compiler_input.write_text("package ast\n", encoding="utf-8")
        self.graph = self.root / "contract_graph.json"
        self.lock = self.root / "contract_graph.lock.json"
        self.report = self.root / "contract_graph.breaking.json"
        self.previous_lock = self.root / "trusted.previous.lock.json"
        self.preview = (
            self.root
            / ".qwq_output/env/repo/runs/handoff/breaking.preview.json"
        )
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
        handoff.ROOT = self.original_handoff_root
        self.temp.cleanup()

    # ContractGraph 的实现/测试输入由编译期按 `--repo-root` 扫描派生，并以 path+sha256 绑进
    # readinessEvidence。fixture 必须带上这类绑定，否则测的是一个现实中不存在的 graph 形状。
    EVIDENCE_SOURCE = (
        "quwoquan_service/services/sample-service/internal/sample/thing"
        "/domain/model/thing.go"
    )

    def _write_evidence_source(self, body: str = "package model\n") -> str:
        resolved = self.root / self.EVIDENCE_SOURCE
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(body, encoding="utf-8")
        return handoff.sha256_bytes(resolved.read_bytes())

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
                "pagination": {"defaultItems": 20, "maximumItems": 20},
                "responseAdmission": {"maximumBodyBytes": 2097152},
                "successStatus": 202,
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
            "readinessEvidence": [
                {
                    "objectId": "sample.thing",
                    "operationIds": ["sample.thing.ListThings"],
                    "service": {
                        "domain": [
                            {
                                "path": self.EVIDENCE_SOURCE,
                                "sha256": self._write_evidence_source(),
                            }
                        ]
                    },
                }
            ],
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

    def _snapshot_trusted_baseline(self) -> None:
        graph = handoff.read_json(self.graph)
        exposures, unresolved = handoff.resolve_exposures(graph)
        self.assertEqual(unresolved, [])
        baseline = {
            "generator": handoff.GENERATOR,
            "contractGraph": {
                "sha256": handoff.sha256_bytes(self.graph.read_bytes()),
            },
            "appExposedOperations": handoff.operation_snapshots(
                graph,
                exposures,
            ),
        }
        handoff.atomic_write_json(self.previous_lock, baseline)
        handoff.atomic_write_json(self.lock, baseline)

    def _args(
        self,
        *,
        approve_breaking: bool = False,
        use_previous_lock: bool = True,
        previous_lock_sha256: str | None = "auto",
        preview_report: Path | None = None,
        approve_breaking_report: Path | None = None,
        approve_breaking_report_sha256: str | None = None,
        expected_current_lock_sha256: str | None = "auto",
    ) -> argparse.Namespace:
        if expected_current_lock_sha256 == "auto":
            expected_current_lock_sha256 = (
                handoff.sha256_bytes(self.lock.read_bytes())
                if self.lock.is_file()
                else None
            )
        if previous_lock_sha256 == "auto":
            previous_lock_sha256 = (
                handoff.sha256_bytes(self.previous_lock.read_bytes())
                if use_previous_lock and self.previous_lock.is_file()
                else None
            )
        return argparse.Namespace(
            graph=self.graph,
            lock=self.lock,
            report=self.report,
            policy=self.policy,
            owner="app-cloud-governance",
            lease_ttl_minutes=10,
            approve_breaking=approve_breaking,
            previous_lock=(self.previous_lock if use_previous_lock else None),
            previous_lock_sha256=previous_lock_sha256,
            preview_report=preview_report,
            approve_breaking_report=approve_breaking_report,
            approve_breaking_report_sha256=approve_breaking_report_sha256,
            expected_current_lock_sha256=expected_current_lock_sha256,
        )

    def test_accept_and_verify_are_content_addressed_and_release_lease(
        self,
    ) -> None:
        self._write_graph()
        self._snapshot_trusted_baseline()

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
        self.assertEqual(
            lock["appExposedOperations"][0]["pagination"],
            {"defaultItems": 20, "maximumItems": 20},
        )
        self.assertEqual(
            lock["appExposedOperations"][0]["responseAdmission"],
            {"maximumBodyBytes": 2097152},
        )
        self.assertEqual(
            lock["appExposedOperations"][0]["transport"],
            "json",
        )
        self.assertEqual(
            lock["appExposedOperations"][0]["successStatus"],
            202,
        )
        self.assertFalse((self.root / "leases/app-cloud-handoff.lock").exists())

    def test_make_accept_requires_all_compare_and_swap_inputs(self) -> None:
        cases = (
            ({}, "APP_CONTRACT_PREVIOUS_LOCK is required"),
            (
                {"APP_CONTRACT_PREVIOUS_LOCK": "/tmp/reviewed.previous.lock"},
                "APP_CONTRACT_PREVIOUS_LOCK_SHA256 is required",
            ),
            (
                {
                    "APP_CONTRACT_PREVIOUS_LOCK": "/tmp/reviewed.previous.lock",
                    "APP_CONTRACT_PREVIOUS_LOCK_SHA256": "1" * 64,
                },
                "APP_CONTRACT_EXPECTED_CURRENT_LOCK_SHA256 is required",
            ),
        )
        for variables, expected in cases:
            with self.subTest(expected=expected):
                command = [
                    "make",
                    "--no-print-directory",
                    "accept-app-contract-handoff",
                    *(f"{key}={value}" for key, value in variables.items()),
                ]
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn(expected, completed.stderr)

    def test_make_accept_dry_run_passes_all_compare_and_swap_inputs(self) -> None:
        previous_lock = "/tmp/reviewed.previous.lock"
        previous_sha = "1" * 64
        current_sha = "2" * 64
        completed = subprocess.run(
            [
                "make",
                "--no-print-directory",
                "--dry-run",
                "accept-app-contract-handoff",
                f"APP_CONTRACT_PREVIOUS_LOCK={previous_lock}",
                f"APP_CONTRACT_PREVIOUS_LOCK_SHA256={previous_sha}",
                f"APP_CONTRACT_EXPECTED_CURRENT_LOCK_SHA256={current_sha}",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn(f'--previous-lock "{previous_lock}"', completed.stdout)
        self.assertIn(
            f'--previous-lock-sha256 "{previous_sha}"', completed.stdout
        )
        self.assertIn(
            f'--expected-current-lock-sha256 "{current_sha}"',
            completed.stdout,
        )

    def test_preserves_sse_transport_as_generated_abi(self) -> None:
        self._write_graph()
        graph = json.loads(self.graph.read_text(encoding="utf-8"))
        graph["operations"][0]["transport"] = "sse"
        graph["operations"][0]["streaming"] = {
            "resumeRequestField": "resumeToken",
            "resumeResponseField": "eventId",
            "terminalField": "eventType",
            "terminalValues": ["completed"],
        }
        self.graph.write_text(
            json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self._snapshot_trusted_baseline()

        self.assertEqual(handoff.accept(self._args()), 0)
        lock = json.loads(self.lock.read_text(encoding="utf-8"))
        self.assertEqual(
            lock["appExposedOperations"][0]["transport"],
            "sse",
        )
        self.assertEqual(
            lock["appExposedOperations"][0]["streaming"]["resumeResponseField"],
            "eventId",
        )

    def test_ambiguous_surface_binding_fails_without_guessing(self) -> None:
        self._write_graph(duplicate=True)

        with self.assertRaisesRegex(ValueError, "禁止推断"):
            handoff.accept(self._args())

        self.assertFalse(self.lock.exists())
        self.assertFalse(self.report.exists())

    def test_app_shell_resolves_unique_recovery_operations_without_owner_guess(
        self,
    ) -> None:
        self._write_graph()
        graph = json.loads(self.graph.read_text(encoding="utf-8"))
        graph["operations"] = [
            {
                **graph["operations"][0],
                "id": "ops.app_release.GetAppRecoveryVersion",
                "localId": "GetAppRecoveryVersion",
                "domain": "ops",
                "objectId": "ops.app_release",
                "sourcePath": "product_ops/app_release/operations.yaml",
            },
            {
                **graph["operations"][0],
                "id": "ops.recovery_failure.ReportRecoveryFailure",
                "localId": "ReportRecoveryFailure",
                "domain": "ops",
                "objectId": "ops.recovery_failure",
                "method": "POST",
                "pathTemplate": "/ops/recovery-failures",
                "kind": "command",
                "sourcePath": "product_ops/recovery_failure/operations.yaml",
            },
        ]
        graph["documents"][-1]["content"] = {
            "surfaces": [
                {
                    "id": "appShell",
                    "owner": "app",
                    "operation_ids": [
                        "GetAppRecoveryVersion",
                        "ReportRecoveryFailure",
                    ],
                }
            ]
        }

        resolved, unresolved = handoff.resolve_exposures(graph)

        self.assertEqual(unresolved, [])
        self.assertEqual(
            [item["canonicalOperationId"] for item in resolved],
            [
                "ops.app_release.GetAppRecoveryVersion",
                "ops.recovery_failure.ReportRecoveryFailure",
            ],
        )
        self.assertTrue(
            all(item["surfaceIds"] == ["appShell"] for item in resolved)
        )

    def test_breaking_transport_change_requires_explicit_approval(self) -> None:
        self._write_graph()
        self._snapshot_trusted_baseline()
        lock_before = self.lock.read_bytes()
        self._write_graph(path_template="/" + "v2" + "/things")

        with self.assertRaisesRegex(ValueError, "preview.*canonical"):
            handoff.accept(self._args(preview_report=self.preview))

        self.assertEqual(self.lock.read_bytes(), lock_before)
        self.assertFalse(self.report.exists())
        preview_sha = handoff.sha256_bytes(self.preview.read_bytes())

        self.assertEqual(
            handoff.accept(
                self._args(
                    approve_breaking_report=self.preview,
                    approve_breaking_report_sha256=preview_sha,
                )
            ),
            0,
        )
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["decision"], "approved")
        self.assertEqual(report["breakingChanges"][0]["field"], "pathTemplate")
        self.assertEqual(
            report["reviewedBreakingReport"]["sha256"],
            preview_sha,
        )

    def test_breaking_success_status_change_requires_explicit_approval(
        self,
    ) -> None:
        self._write_graph()
        self._snapshot_trusted_baseline()
        graph = json.loads(self.graph.read_text(encoding="utf-8"))
        graph["operations"][0]["successStatus"] = 201
        self.graph.write_text(
            json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "preview.*canonical"):
            handoff.accept(self._args(preview_report=self.preview))

        preview_sha = handoff.sha256_bytes(self.preview.read_bytes())
        self.assertEqual(
            handoff.accept(
                self._args(
                    approve_breaking_report=self.preview,
                    approve_breaking_report_sha256=preview_sha,
                )
            ),
            0,
        )
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["decision"], "approved")
        self.assertEqual(report["breakingChanges"][0]["field"], "successStatus")

    def test_default_accept_never_uses_canonical_lock_as_baseline(self) -> None:
        self._write_graph()
        self._snapshot_trusted_baseline()
        lock_before = self.lock.read_bytes()
        self._write_graph(path_template="/v2/things")

        with self.assertRaisesRegex(ValueError, "显式传入独立 --previous-lock"):
            handoff.accept(self._args(use_previous_lock=False))

        self.assertEqual(self.lock.read_bytes(), lock_before)
        self.assertFalse(self.report.exists())

    def test_explicit_previous_lock_cannot_point_to_canonical_lock(self) -> None:
        self._write_graph()
        self._snapshot_trusted_baseline()
        args = self._args()
        args.previous_lock = self.lock

        with self.assertRaisesRegex(ValueError, "不能指向 canonical lock"):
            handoff.accept(args)

        self.assertFalse(self.report.exists())

    def test_previous_lock_is_bound_to_reviewed_sha256(self) -> None:
        self._write_graph()
        self._snapshot_trusted_baseline()
        args = self._args()
        previous = handoff.read_json(self.previous_lock)
        previous["appExposedOperations"][0]["pathTemplate"] = "/tampered"
        handoff.atomic_write_json(self.previous_lock, previous)

        with self.assertRaisesRegex(ValueError, "previous lock SHA256 漂移"):
            handoff.accept(args)

        self.assertFalse(self.report.exists())

    def test_breaking_review_path_cannot_escape_repository_output_root(
        self,
    ) -> None:
        outside = self.root.parent / ".qwq_output/env/repo/runs/review.json"
        with self.assertRaisesRegex(ValueError, "当前仓库"):
            handoff.require_review_path(outside)

    def test_approval_rejects_lock_compare_and_swap_drift(self) -> None:
        self._write_graph()
        self._snapshot_trusted_baseline()
        lock_before = self.lock.read_bytes()
        self._write_graph(path_template="/v2/things")
        with self.assertRaises(ValueError):
            handoff.accept(self._args(preview_report=self.preview))
        preview_sha = handoff.sha256_bytes(self.preview.read_bytes())

        with self.assertRaisesRegex(ValueError, "canonical lock.*漂移"):
            handoff.accept(
                self._args(
                    approve_breaking_report=self.preview,
                    approve_breaking_report_sha256=preview_sha,
                    expected_current_lock_sha256="0" * 64,
                )
            )

        self.assertEqual(self.lock.read_bytes(), lock_before)
        self.assertFalse(self.report.exists())

    def test_approval_is_bound_to_exact_reviewed_report(self) -> None:
        self._write_graph()
        self._snapshot_trusted_baseline()
        self._write_graph(path_template="/v2/things")
        with self.assertRaises(ValueError):
            handoff.accept(self._args(preview_report=self.preview))
        reviewed = handoff.read_json(self.preview)
        reviewed["changes"][0]["after"] = "/tampered"
        handoff.atomic_write_json(self.preview, reviewed)
        tampered_sha = handoff.sha256_bytes(self.preview.read_bytes())

        with self.assertRaisesRegex(ValueError, "派生结果不一致"):
            handoff.accept(
                self._args(
                    approve_breaking_report=self.preview,
                    approve_breaking_report_sha256=tampered_sha,
                )
            )

        self.assertFalse(self.report.exists())

    def test_deleting_canonical_lock_cannot_establish_new_baseline(self) -> None:
        self._write_graph()
        self._snapshot_trusted_baseline()
        self.lock.unlink()

        with self.assertRaisesRegex(ValueError, "canonical lock 不存在"):
            handoff.accept(
                self._args(
                    expected_current_lock_sha256="0" * 64,
                )
            )

        self.assertFalse(self.report.exists())

    def test_legacy_boolean_breaking_approval_is_rejected(self) -> None:
        self._write_graph()
        self._snapshot_trusted_baseline()
        self._write_graph(path_template="/v2/things")

        with self.assertRaisesRegex(ValueError, "--approve-breaking 已退役"):
            handoff.accept(self._args(approve_breaking=True))

        self.assertFalse(self.report.exists())

    # ── ContractGraph 输入 provenance 完整性 ─────────────────────────────
    #
    # ContractGraph 有两类互不相交的输入：契约视图里的声明（`graph["sources"]`，被
    # `sourceDigestSetSha256` 覆盖）与编译期按 `--repo-root` 扫描派生的实现/测试文件（绑进
    # readinessEvidence）。声明侧摘要与 compilerHash 都看不到实现侧漂移，所以「同一份
    # sourceDigestSetSha256 + compilerHash 下 graph sha256 变化」是可以合法发生的，而一份
    # 相对自身输入已经过期的 graph 曾能被锁定并通过全部下游门禁。

    def test_declaration_digests_cannot_observe_implementation_input_drift(
        self,
    ) -> None:
        """钉死诊断本身：实现侧漂移对两个声明侧摘要完全不可见。

        这条断言说明为什么必须新增磁盘校验——不是因为摘要没被一起重算（accept 一直在同一次
        build_lock 里重算三者），而是因为它们的覆盖面里根本没有实现/测试输入。
        """
        self._write_graph()
        graph = handoff.read_json(self.graph)
        before_sources = handoff.source_digest_set_sha(graph)
        before_compiler = handoff.compiler_digest()

        self._write_evidence_source("package model\n\n// 并行会话的改动\n")

        self.assertEqual(handoff.source_digest_set_sha(graph), before_sources)
        self.assertEqual(handoff.compiler_digest(), before_compiler)
        # 但 graph 记录的绑定已经不再描述磁盘现状。
        with self.assertRaisesRegex(ValueError, "与磁盘不一致"):
            handoff.verify_graph_input_bindings(graph)

    def test_accept_blocks_when_recorded_implementation_input_drifted(
        self,
    ) -> None:
        self._write_graph()
        self._snapshot_trusted_baseline()
        # generate 之后、accept 之前，并行会话改了一个被扫描的实现文件。
        self._write_evidence_source("package model\n\n// 并行会话的改动\n")

        with self.assertRaisesRegex(ValueError, "1 个已改动"):
            handoff.accept(self._args())

        self.assertFalse(self.report.exists())

    def test_accept_blocks_when_recorded_implementation_input_disappeared(
        self,
    ) -> None:
        self._write_graph()
        self._snapshot_trusted_baseline()
        (self.root / self.EVIDENCE_SOURCE).unlink()

        with self.assertRaisesRegex(ValueError, "1 个已消失"):
            handoff.accept(self._args())

        self.assertFalse(self.report.exists())

    def test_input_verification_fails_closed_without_evidence_bindings(
        self,
    ) -> None:
        """缺 readinessEvidence 时必须阻断，不能退化成空扫描恒绿。"""
        self._write_graph()
        self._snapshot_trusted_baseline()
        graph = handoff.read_json(self.graph)
        graph.pop("readinessEvidence")
        self.graph.write_text(
            json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "空扫描恒绿"):
            handoff.accept(self._args())

        self.assertFalse(self.report.exists())

    def test_evidence_bindings_reject_malformed_and_conflicting_digests(
        self,
    ) -> None:
        self._write_graph()
        graph = handoff.read_json(self.graph)
        packet = graph["readinessEvidence"][0]

        malformed = json.loads(json.dumps(graph))
        malformed["readinessEvidence"][0]["service"]["domain"][0]["sha256"] = "abc"
        with self.assertRaisesRegex(ValueError, "digest 非 SHA256"):
            handoff.evidence_digest_bindings(malformed)

        conflicting = json.loads(json.dumps(graph))
        conflicting["readinessEvidence"][0]["service"]["application"] = [
            {"path": self.EVIDENCE_SOURCE, "sha256": "c" * 64}
        ]
        with self.assertRaisesRegex(ValueError, "冲突 digest"):
            handoff.evidence_digest_bindings(conflicting)

        # 未被污染的 packet 仍然只产出一条绑定。
        self.assertEqual(
            handoff.evidence_digest_bindings({"readinessEvidence": [packet]}),
            [(self.EVIDENCE_SOURCE, self._write_evidence_source())],
        )

    def test_verify_inputs_passes_when_recorded_inputs_match_disk(self) -> None:
        self._write_graph()

        self.assertEqual(handoff.verify_inputs(self._args()), 0)


if __name__ == "__main__":
    unittest.main()
