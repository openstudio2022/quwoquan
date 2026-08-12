"""Output/root-layout reconciliation safety contracts.

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import output_layout_reconciliation as reconciliation
from quwoquan_ops.cli.lib import output_layout_reconciliation_identity as identity


SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "environments/output_layout_reconciliation_plan.schema.json"
)
SHA = "sha256:" + "a" * 64


def _truth() -> dict[str, dict[str, str]]:
    return {
        "outputLayoutManifest": {"path": "manifest.json", "sha256": SHA},
        "outputLayoutVerifier": {"path": "output.py", "sha256": SHA},
        "reconciliationPlanSchema": {"path": "schema.json", "sha256": SHA},
        "rootLayoutVerifier": {"path": "root.py", "sha256": SHA},
    }


def _no_open_files(
    roots: list[Path] | tuple[Path, ...],
) -> tuple[dict[str, list[dict[str, object]]], list[str]]:
    del roots
    return {}, []


def _cache_issue(repository_root: Path, path: Path) -> str:
    return (
        f"{path.relative_to(repository_root).as_posix()}: output local state only "
        "permits process/ and cache/; configuration, TLS and volumes belong to "
        "deployment infrastructure"
    )


def _plan_for_paths(
    repository_root: Path,
    output_root: Path,
    paths: list[Path],
) -> dict[str, object]:
    return reconciliation.build_plan(
        repository_root=repository_root,
        output_root=output_root,
        canonical_issues=[_cache_issue(repository_root, path) for path in paths],
        truth=_truth(),
        open_file_probe=_no_open_files,
        created_at="2026-08-11T00:00:00Z",
    )


class OutputLayoutReconciliationContractTest(unittest.TestCase):
    def test_parser_and_draft_2020_schema_freeze_repo_plan_apply_boundary(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["schema"]["const"],
            reconciliation.PLAN_SCHEMA,
        )
        args = stackctl.build_parser().parse_args(
            [
                "repair",
                "--target",
                "repo",
                "--fix",
                "reconcile-output-layout",
            ]
        )
        self.assertEqual(args.output_layout_action, "plan")
        self.assertFalse(args.confirm_output_layout_reconciliation)

        with tempfile.TemporaryDirectory() as temporary_dir:
            repository_root = Path(temporary_dir) / "repo"
            output_root = repository_root / ".qwq_output"
            output_root.mkdir(parents=True)
            plan = _plan_for_paths(repository_root, output_root, [])
        reconciliation.validate_plan(plan)
        self.assertEqual(plan["status"], "ready")
        self.assertTrue(plan["noOp"])

    def test_plan_binds_path_bytes_mode_mtime_digest_producer_and_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            repository_root = Path(temporary_dir) / "repo"
            output_root = repository_root / ".qwq_output"
            source = output_root / "env/repo/local/go-cache/pkg/mod/cache.bin"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"cache-bytes")
            source.chmod(0o640)

            plan = _plan_for_paths(repository_root, output_root, [source])

        self.assertEqual(plan["status"], "ready")
        record = plan["records"][0]
        snapshot = record["snapshot"]
        self.assertEqual(record["producer"], "output_env_repo:local:go-cache")
        self.assertEqual(record["target"], "go-cache")
        self.assertEqual(record["operation"], "move")
        self.assertTrue(record["canonicalDestination"].endswith("go-cache/cache/pkg/mod/cache.bin"))
        self.assertEqual(snapshot["byteCount"], len(b"cache-bytes"))
        self.assertEqual(snapshot["mode"], 0o640)
        self.assertGreater(snapshot["mtimeNs"], 0)
        self.assertEqual(snapshot["pathByteLength"], len(str(source).encode("utf-8")))
        self.assertRegex(snapshot["sha256"], r"^sha256:[0-9a-f]{64}$")

    def test_missing_confirmation_blocks_before_plan_read_or_global_lock(self) -> None:
        args = argparse.Namespace(
            command="repair",
            target="repo",
            fix="reconcile-output-layout",
            report_dir="",
            output_layout_action="apply",
            output_layout_plan_ref="missing.json",
            confirm_output_layout_reconciliation=False,
        )
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary_dir),
            ),
            mock.patch.object(stackctl, "_write_summary_bundle"),
            mock.patch.object(
                stackctl,
                "_global_output_layout_reconciliation_lock",
            ) as operation_lock,
            mock.patch.object(reconciliation, "load_plan") as load_plan,
        ):
            result = stackctl.command_repair(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertIn("--confirm-output-layout-reconciliation", " ".join(result["details"]))
        operation_lock.assert_not_called()
        load_plan.assert_not_called()

    def test_global_exclusive_lock_conflicts_with_runtime_shared_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            lock_path = Path(temporary_dir) / "local-runtime.lock"
            with mock.patch.object(
                stackctl,
                "local_runtime_operation_lock_path",
                return_value=lock_path,
            ):
                lease = stackctl.acquire_local_runtime_use_lock(
                    target="alpha-local",
                    purpose="runtime-package-build",
                    lock_path=lock_path,
                )
                try:
                    with self.assertRaisesRegex(RuntimeError, "already running"):
                        with stackctl._global_output_layout_reconciliation_lock():
                            self.fail("exclusive output reconciliation lock must not enter")
                finally:
                    lease.close()

    def test_tampered_plan_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            repository_root = Path(temporary_dir) / "repo"
            output_root = repository_root / ".qwq_output"
            output_root.mkdir(parents=True)
            plan = _plan_for_paths(repository_root, output_root, [])
        tampered = copy.deepcopy(plan)
        tampered["createdAt"] = "2026-08-12T00:00:00Z"
        with self.assertRaisesRegex(
            reconciliation.OutputLayoutReconciliationError,
            "digest mismatch",
        ):
            reconciliation.validate_plan(tampered)

    def test_mode_or_mtime_drift_blocks_before_move(self) -> None:
        for drift in ("mode", "mtime"):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as temporary_dir:
                repository_root = Path(temporary_dir) / "repo"
                output_root = repository_root / ".qwq_output"
                source = output_root / "env/repo/local/go-cache/pkg/cache.bin"
                source.parent.mkdir(parents=True)
                source.write_bytes(b"cache")
                plan = _plan_for_paths(repository_root, output_root, [source])
                if drift == "mode":
                    source.chmod(0o600)
                else:
                    metadata = source.stat()
                    os.utime(
                        source,
                        ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000_000),
                    )
                with self.assertRaisesRegex(
                    reconciliation.OutputLayoutReconciliationError,
                    "identity drifted",
                ):
                    reconciliation.apply_plan(
                        plan,
                        repository_root=repository_root,
                        output_root=output_root,
                        truth=_truth(),
                        open_file_probe=_no_open_files,
                    )
                self.assertTrue(source.exists())

    def test_active_process_and_open_fd_are_explicit_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            repository_root = Path(temporary_dir) / "repo"
            output_root = repository_root / ".qwq_output"
            source = output_root / "env/repo/local/go-cache/pkg/cache.bin"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"cache")

            def active_probe(
                roots: list[Path] | tuple[Path, ...],
            ) -> tuple[dict[str, list[dict[str, object]]], list[str]]:
                del roots
                return {
                    str(source): [
                        {"pid": 101, "descriptor": "cwd"},
                        {"pid": 202, "descriptor": "9u"},
                    ]
                }, []

            plan = reconciliation.build_plan(
                repository_root=repository_root,
                output_root=output_root,
                canonical_issues=[_cache_issue(repository_root, source)],
                truth=_truth(),
                open_file_probe=active_probe,
            )

        record = plan["records"][0]
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(record["activeProcessPids"], [101])
        self.assertEqual(record["openFileDescriptorPids"], [202])
        self.assertTrue(record["flags"]["activeProcess"])
        self.assertTrue(record["flags"]["openFileDescriptor"])

    def test_lsof_parser_preserves_process_and_descriptor_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            open_path = root / "cache.bin"
            open_path.write_bytes(b"cache")
            output = (
                f"p101\nfcwd\nn{root}\n"
                f"p202\nf9u\nn{open_path}\n"
            )
            with mock.patch.object(
                identity.subprocess,
                "run",
                return_value=CompletedProcess(["lsof"], 0, output, ""),
            ):
                records, issues = identity.lsof_records([root])
            self.assertEqual(issues, [])
            self.assertEqual(records[str(root)], [{"pid": 101, "descriptor": "cwd"}])
            self.assertEqual(
                records[str(open_path)],
                [{"pid": 202, "descriptor": "9u"}],
            )

            with mock.patch.object(
                identity.subprocess,
                "run",
                side_effect=FileNotFoundError,
            ):
                records, issues = identity.lsof_records([root])
            self.assertEqual(records, {})
            self.assertIn("lsof is not installed", " ".join(issues))

    def test_nested_symlink_and_destination_conflict_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            repository_root = Path(temporary_dir) / "repo"
            output_root = repository_root / ".qwq_output"
            source = output_root / "env/repo/local/go-cache/pkg"
            source.mkdir(parents=True)
            external = Path(temporary_dir) / "outside"
            external.write_text("outside", encoding="utf-8")
            (source / "alias").symlink_to(external)
            symlink_plan = _plan_for_paths(repository_root, output_root, [source])
            self.assertEqual(symlink_plan["status"], "blocked")
            self.assertIn("symlink", " ".join(symlink_plan["records"][0]["blockers"]))

        with tempfile.TemporaryDirectory() as temporary_dir:
            repository_root = Path(temporary_dir) / "repo"
            output_root = repository_root / ".qwq_output"
            source = output_root / "env/repo/local/go-cache/pkg/cache.bin"
            destination = output_root / "env/repo/local/go-cache/cache/pkg/cache.bin"
            source.parent.mkdir(parents=True)
            destination.parent.mkdir(parents=True)
            source.write_bytes(b"source")
            destination.write_bytes(b"conflict")
            conflict_plan = _plan_for_paths(repository_root, output_root, [source])
            self.assertEqual(conflict_plan["status"], "blocked")
            self.assertIn("destination already exists", " ".join(conflict_plan["blockers"]))

    def test_partial_failure_rolls_back_every_completed_move(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            repository_root = Path(temporary_dir) / "repo"
            output_root = repository_root / ".qwq_output"
            first = output_root / "env/repo/local/go-cache/pkg/a.bin"
            second = output_root / "env/repo/local/python-cache/lib/b.bin"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_bytes(b"a")
            second.write_bytes(b"b")
            plan = _plan_for_paths(repository_root, output_root, [first, second])
            second_destination = Path(plan["records"][1]["canonicalDestination"])

            def fail_second_forward(source: str, destination: str) -> object:
                if Path(source) == second and Path(destination) == second_destination:
                    raise OSError("injected second move failure")
                return shutil.move(source, destination)

            with self.assertRaisesRegex(
                reconciliation.OutputLayoutReconciliationError,
                "injected second move failure",
            ):
                reconciliation.apply_plan(
                    plan,
                    repository_root=repository_root,
                    output_root=output_root,
                    truth=_truth(),
                    open_file_probe=_no_open_files,
                    move=fail_second_forward,
                )
            self.assertEqual(first.read_bytes(), b"a")
            self.assertEqual(second.read_bytes(), b"b")
            for record in plan["records"]:
                self.assertFalse(Path(record["canonicalDestination"]).exists())

    def test_success_readback_is_idempotent_for_the_exact_same_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            repository_root = Path(temporary_dir) / "repo"
            output_root = repository_root / ".qwq_output"
            source = output_root / "env/repo/local/go-cache/pkg/cache.bin"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"cache")
            plan = _plan_for_paths(repository_root, output_root, [source])
            destination = Path(plan["records"][0]["canonicalDestination"])

            first = reconciliation.apply_plan(
                plan,
                repository_root=repository_root,
                output_root=output_root,
                truth=_truth(),
                open_file_probe=_no_open_files,
            )
            second = reconciliation.apply_plan(
                plan,
                repository_root=repository_root,
                output_root=output_root,
                truth=_truth(),
                open_file_probe=_no_open_files,
            )

            self.assertFalse(source.exists())
            self.assertEqual(destination.read_bytes(), b"cache")
            self.assertEqual(len(first["moved"]), 1)
            self.assertEqual(second["moved"], [])
            self.assertTrue(second["replayed"])
            self.assertEqual(second["readBack"], [str(destination)])

    def test_noop_apply_and_create_once_plan_are_side_effect_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            repository_root = Path(temporary_dir) / "repo"
            output_root = repository_root / ".qwq_output"
            output_root.mkdir(parents=True)
            plan = _plan_for_paths(repository_root, output_root, [])
            result = reconciliation.apply_plan(
                plan,
                repository_root=repository_root,
                output_root=output_root,
                truth=_truth(),
                open_file_probe=_no_open_files,
            )
            self.assertTrue(result["noOp"])
            self.assertEqual(result["moved"], [])
            plan_path = Path(temporary_dir) / "runs/plan.json"
            reconciliation.write_create_once(plan_path, plan)
            with self.assertRaises(FileExistsError):
                reconciliation.write_create_once(plan_path, plan)

    def test_source_data_receipt_secret_and_probe_failure_never_become_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            repository_root = Path(temporary_dir) / "repo"
            output_root = repository_root / ".qwq_output"
            source_cache = repository_root / "quwoquan_app/scripts/__pycache__"
            data = output_root / "data/local/workspace/quarantine/q1"
            receipt = output_root / "env/alpha/runs/up/receipt.json"
            secret = output_root / "env/repo/local/session/config.env"
            for item in (source_cache, data):
                item.mkdir(parents=True)
            receipt.parent.mkdir(parents=True)
            secret.parent.mkdir(parents=True)
            receipt.write_text("{}", encoding="utf-8")
            secret.write_text("token=redacted", encoding="utf-8")
            issues = [
                f"{source_cache.relative_to(repository_root)}: source cache is forbidden",
                f"{data.relative_to(repository_root)}: data only permits tasks/releases/local",
                f"{receipt.relative_to(repository_root)}: deployment configuration is forbidden",
                f"{secret.relative_to(repository_root)}: unredacted secret assignment is forbidden",
            ]
            plan = reconciliation.build_plan(
                repository_root=repository_root,
                output_root=output_root,
                canonical_issues=issues,
                truth=_truth(),
                open_file_probe=lambda roots: ({}, ["lsof unavailable"]),
            )

        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["actionCount"], 0)
        self.assertIn("lsof unavailable", plan["probeIssues"])
        flags = {record["target"]: record["flags"] for record in plan["records"]}
        self.assertTrue(flags["source"]["sourcePath"])
        self.assertTrue(flags["data"]["protectedQuarantine"])
        self.assertTrue(flags["alpha"]["protectedReceipt"])
        self.assertTrue(flags["session"]["secretMaterial"])


if __name__ == "__main__":
    unittest.main()
