from __future__ import annotations

import importlib.util
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    ROOT
    / "quwoquan_service"
    / "scripts"
    / "verify"
    / "structure"
    / "verify_append_only_fact_command_admission.py"
)


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "verify_append_only_fact_command_admission", SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载门禁：{SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_fact(
    service_root: Path,
    *,
    object_yaml: str,
    operations_yaml: str,
    context: str = "sample",
    name: str = "sample_fact",
) -> None:
    directory = (
        service_root / "services" / "sample-service" / "contracts" / context / name
    )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "object.yaml").write_text(textwrap.dedent(object_yaml), "utf-8")
    (directory / "operations.yaml").write_text(
        textwrap.dedent(operations_yaml), "utf-8"
    )


_REGISTERED_OBJECT = """
    kind: append_only_fact
    description: 采样事实对象，用于门禁负例覆盖。
    identity:
      fields: [sampleId]
      version_source: immutable
    access:
      commands: append_only_sink
      queries: named_reader
      cross_context: event_only
    relationships: []
    business_rules:
      - 语义键幂等追加。
    lifecycle:
      immutable: true
      append_command_admission:
        status: evaluated
        instance_invariant: none
        commands:
          - ReportSample
        rationale: 采样事实仅按语义键去重，写入侧不持有实例级可变状态。
        evaluated_at: '2026-08-07'
"""

_UNREGISTERED_OBJECT = """
    kind: append_only_fact
    description: 采样事实对象，用于门禁负例覆盖。
    identity:
      fields: [sampleId]
      version_source: immutable
    access:
      commands: append_only_sink
      queries: named_reader
      cross_context: event_only
    relationships: []
    business_rules:
      - 语义键幂等追加。
    lifecycle:
      immutable: true
"""

_ONE_COMMAND_OPERATIONS = """
    api_routes:
      - method: POST
        path: /sample/facts
        operation: ReportSample
        application:
          kind: command
"""

_TWO_COMMAND_OPERATIONS = """
    api_routes:
      - method: POST
        path: /sample/facts
        operation: ReportSample
        application:
          kind: command
      - method: POST
        path: /sample/facts:batch
        operation: ReportSampleBatch
        application:
          kind: command
"""


class AppendOnlyFactCommandAdmissionContractTest(unittest.TestCase):
    def test_repository_append_commands_are_all_registered(self) -> None:
        gate = _load_gate()
        scanned = gate._object_contract_files(gate.SERVICE_ROOT)
        self.assertTrue(scanned, "append command 判据门禁必须扫描到真实对象契约")
        self.assertEqual([], gate.collect_issues(), "\n".join(gate.collect_issues()))

    def test_missing_scan_root_fails_closed(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            gate.SERVICE_ROOT = Path(temp_dir) / "quwoquan_service"
            issues = gate.collect_issues()
        self.assertTrue(
            any("扫描根不存在" in issue for issue in issues),
            issues,
        )

    def test_zero_objects_fails_closed(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            gate.SERVICE_ROOT = Path(temp_dir)
            (gate.SERVICE_ROOT / "services").mkdir()
            issues = gate.collect_issues()
        self.assertTrue(
            any("扫描到 0 个对象契约" in issue for issue in issues),
            issues,
        )

    def test_unregistered_new_command_blocks(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            gate.SERVICE_ROOT = Path(temp_dir)
            _write_fact(
                gate.SERVICE_ROOT,
                object_yaml=_UNREGISTERED_OBJECT,
                operations_yaml=_ONE_COMMAND_OPERATIONS,
            )
            issues = gate.collect_issues()
        self.assertTrue(
            any("缺少 lifecycle.append_command_admission" in issue for issue in issues),
            issues,
        )

    def test_partially_registered_command_blocks(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            gate.SERVICE_ROOT = Path(temp_dir)
            _write_fact(
                gate.SERVICE_ROOT,
                object_yaml=_REGISTERED_OBJECT,
                operations_yaml=_TWO_COMMAND_OPERATIONS,
            )
            issues = gate.collect_issues()
        self.assertTrue(
            any("'ReportSampleBatch' 未在" in issue for issue in issues),
            issues,
        )

    def test_mutable_object_blocks(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            gate.SERVICE_ROOT = Path(temp_dir)
            _write_fact(
                gate.SERVICE_ROOT,
                object_yaml=_REGISTERED_OBJECT.replace(
                    "  immutable: true", "  immutable: false"
                ),
                operations_yaml=_ONE_COMMAND_OPERATIONS,
            )
            issues = gate.collect_issues()
        self.assertTrue(
            any("lifecycle.immutable: true" in issue for issue in issues),
            issues,
        )

    def test_declared_instance_invariant_blocks(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            gate.SERVICE_ROOT = Path(temp_dir)
            _write_fact(
                gate.SERVICE_ROOT,
                object_yaml=_REGISTERED_OBJECT.replace(
                    "instance_invariant: none",
                    "instance_invariant: grant_quota_window",
                ),
                operations_yaml=_ONE_COMMAND_OPERATIONS,
            )
            issues = gate.collect_issues()
        self.assertTrue(
            any("必须归属 aggregate_root" in issue for issue in issues),
            issues,
        )

    def test_stale_declaration_without_command_blocks(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            gate.SERVICE_ROOT = Path(temp_dir)
            _write_fact(
                gate.SERVICE_ROOT,
                object_yaml=_REGISTERED_OBJECT,
                operations_yaml="api_routes: []\n",
            )
            issues = gate.collect_issues()
        self.assertTrue(
            any("陈旧声明" in issue for issue in issues),
            issues,
        )


if __name__ == "__main__":
    unittest.main()
