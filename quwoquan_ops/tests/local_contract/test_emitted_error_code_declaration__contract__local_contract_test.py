"""反向错误码维度的负例合约：发射了没有声明位的码必须被抓到，补声明后必须转绿。

用合成 root 驱动真实 resolver：把仓内 runtime/errors/errors.go 原样复制进临时树，
保证 module/kind/reason 常量表与 helper 映射走的是同一个真相源，而不是测试内
另建一张表。两种 YAML 声明形态（块形态与 flow 形态）各测一遍，两个声明源各测一遍。
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = ROOT / "quwoquan_ops/gate/verify_emitted_error_code_declaration.py"
REAL_RUNTIME_ERRORS = ROOT / "quwoquan_service/runtime/errors/errors.go"

PROBE_CODE = "CONTENT.USER.synthetic_probe_reason"
# 复制进合成树的 runtime/errors/errors.go 自身会发射兜底码，与被测事实无关，
# 因此固定进合成基线，避免它污染断言。
RUNTIME_FALLBACK_CODE = "UNKNOWN.SYSTEM.internal_error"

PROBE_GO = textwrap.dedent(
    """
    package demo

    import (
    \tnet_http "net/http"

    \trterr "quwoquan_service/runtime/errors"
    )

    func writeProbeError(w net_http.ResponseWriter) *rterr.AppError {
    \treturn rterr.NewAppError(
    \t\trterr.NewCode(rterr.ModuleContent, rterr.KindUser, "synthetic_probe_reason"),
    \t\t"探针错误",
    \t\t"synthetic probe",
    \t)
    }
    """
)

BLOCK_FORM_DECLARATION = textwrap.dedent(
    f"""
    domain: CONTENT
    errors:
    - code: {PROBE_CODE}
      kind: USER
      http_status: 400
      emitted_by:
      - surface: http
        operations: [ProbeOperation]
      recovery_action: surface
      go_const: ErrSyntheticProbeReason
      dart_const: syntheticProbeReason
    """
)

FLOW_FORM_DECLARATION = (
    "domain: CONTENT\n"
    "errors:\n"
    f"- {{code: {PROBE_CODE}, kind: USER, http_status: 400, "
    "emitted_by: [{surface: http, operations: [ProbeOperation]}], "
    "recovery_action: surface, go_const: ErrSyntheticProbeReason, "
    "dart_const: syntheticProbeReason}\n"
)


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_emitted_error_code_declaration", VERIFIER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verifier: {VERIFIER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class EmittedErrorCodeDeclarationContractTest(unittest.TestCase):
    """维度必须在「实现发射但无声明位」这个方向上可红可绿。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_verifier()
        if not REAL_RUNTIME_ERRORS.is_file():
            raise unittest.SkipTest(f"missing runtime errors source: {REAL_RUNTIME_ERRORS}")

    def _build_root(
        self,
        tmp: Path,
        *,
        declaration: tuple[str, str] | None = None,
        baseline_codes: list[dict] | None = None,
        unresolved_sites: list[dict] | None = None,
        extra_go: tuple[str, str] | None = None,
        extra_gos: tuple[tuple[str, str], ...] = (),
        probe_go: str = PROBE_GO,
        extra_dart: tuple[str, str] | None = None,
        extra_darts: tuple[tuple[str, str], ...] = (),
        extra_python: tuple[str, str] | None = None,
        extra_swift: tuple[str, str] | None = None,
    ) -> tuple[Path, Path]:
        service = tmp / "quwoquan_service"
        runtime_errors = service / "runtime" / "errors" / "errors.go"
        runtime_errors.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_RUNTIME_ERRORS, runtime_errors)

        probe = service / "services" / "demo-service" / "internal" / "demo" / "handler.go"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text(probe_go, encoding="utf-8")

        if extra_go is not None:
            relative, text = extra_go
            path = service / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        for relative, text in extra_gos:
            path = service / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        if extra_dart is not None:
            relative, text = extra_dart
            path = tmp / "quwoquan_app" / "lib" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        for relative, text in extra_darts:
            path = tmp / "quwoquan_app" / "lib" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        if extra_python is not None:
            relative, text = extra_python
            path = service / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        if extra_swift is not None:
            relative, text = extra_swift
            path = tmp / "quwoquan_app" / "ios" / "Runner" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        if declaration is not None:
            relative, text = declaration
            path = service / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        baseline_path = tmp / "baseline.yaml"
        baseline_path.write_text(
            yaml.safe_dump(
                {
                    "schema": self.module.BASELINE_SCHEMA,
                    "codes": baseline_codes
                    if baseline_codes is not None
                    else [{"code": RUNTIME_FALLBACK_CODE, "detected_by": "scan"}],
                    "unresolved_sites": unresolved_sites or [],
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return tmp, baseline_path

    def _evaluate(self, **kwargs) -> tuple[list[str], dict]:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            root, baseline_path = self._build_root(tmp, **kwargs)
            return self.module.evaluate(root, baseline_path)

    def test_undeclared_emission_without_baseline_is_blocked(self) -> None:
        failures, summary = self._evaluate()
        self.assertIn(PROBE_CODE, summary["new_codes"])
        self.assertTrue(
            any(PROBE_CODE in failure for failure in failures),
            f"未声明发射位必须 BLOCK，实际 failures={failures}",
        )

    def test_block_form_declaration_turns_green(self) -> None:
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            )
        )
        self.assertIn(PROBE_CODE, self._declared(BLOCK_FORM_DECLARATION))
        self.assertEqual([], summary["new_codes"])
        self.assertEqual([], failures)

    def test_flow_form_declaration_turns_green(self) -> None:
        """flow 形态是本仓 668 个已声明码里 154 个的唯一出现形态，必须被认。"""
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                FLOW_FORM_DECLARATION,
            )
        )
        self.assertEqual([], summary["new_codes"])
        self.assertEqual([], failures)

    def test_runtime_failure_codes_source_turns_green(self) -> None:
        """第二个声明源 runtime_failure_codes.yaml 同样必须被认。"""
        failures, summary = self._evaluate(
            declaration=(
                "contracts/runtime_errors/errors/runtime_failure_codes.yaml",
                "schema: runtime-failure-codes\ncodes:\n"
                f"  - code: {PROBE_CODE}\n    origin: user\n    kind: validation\n",
            )
        )
        self.assertEqual([], summary["new_codes"])
        self.assertEqual([], failures)

    def test_baselined_code_is_reported_but_not_blocked(self) -> None:
        failures, summary = self._evaluate(
            baseline_codes=[
                {"code": PROBE_CODE, "detected_by": "scan"},
                {"code": RUNTIME_FALLBACK_CODE, "detected_by": "scan"},
            ]
        )
        self.assertIn(PROBE_CODE, summary["baselined_codes"])
        self.assertEqual([], summary["new_codes"])
        self.assertEqual([], failures)

    def test_baseline_entry_that_gained_declaration_must_be_removed(self) -> None:
        """基线只减不增：码补上声明位后基线条目必须删除，否则死豁免长期挂账。"""
        failures, _ = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            ),
            baseline_codes=[
                {"code": PROBE_CODE, "detected_by": "scan"},
                {"code": RUNTIME_FALLBACK_CODE, "detected_by": "scan"},
            ],
        )
        self.assertTrue(
            any("必须从基线删除" in failure for failure in failures),
            f"陈旧基线条目必须 BLOCK，实际 failures={failures}",
        )

    def test_generated_factory_and_go_const_calls_are_production_evidence(self) -> None:
        source = textwrap.dedent(
            """
            package demo

            import demogenerated "quwoquan_service/services/demo-service/generated/demo/probe"

            func mapProbe(err error) error {
            \tif err != nil {
            \t\treturn demogenerated.AppErrorFromSyntheticProbeReason(err.Error())
            \t}
            \treturn demogenerated.ErrSyntheticProbeReason
            }
            """
        )
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            ),
            extra_go=("services/demo-service/internal/demo/generated_factory.go", source),
        )
        self.assertEqual([], failures)
        self.assertGreaterEqual(
            summary["emission_forms"]["generated_app_error_factory"], 1
        )
        self.assertGreaterEqual(summary["emission_forms"]["go_const_identifier"], 1)

    def test_domain_sentinel_to_generated_factory_is_distinct_evidence(self) -> None:
        source = textwrap.dedent(
            """
            package demo

            import (
            \t"errors"
            \tdemogenerated "quwoquan_service/services/demo-service/generated/demo/probe"
            )

            var errProbe = errors.New("probe")

            func mapProbe(err error) error {
            \tif errors.Is(err, errProbe) {
            \t\treturn demogenerated.AppErrorFromSyntheticProbeReason(err.Error())
            \t}
            \treturn err
            }
            """
        )
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            ),
            extra_go=("services/demo-service/internal/demo/sentinel.go", source),
        )
        self.assertEqual([], failures)
        self.assertGreaterEqual(summary["emission_forms"]["domain_sentinel_handler"], 1)

    def test_local_constructor_resolves_reason_and_status_without_allowlist(self) -> None:
        source = textwrap.dedent(
            """
            package demo

            import (
            \t"net/http"
            \trterr "quwoquan_service/runtime/errors"
            )

            func probeError(reason string, status int) error {
            \tkind := rterr.KindUser
            \tif status >= 500 {
            \t\tkind = rterr.KindSystem
            \t}
            \treturn rterr.NewAppError(
            \t\trterr.NewCode(rterr.ModuleContent, kind, reason), "probe", "probe")
            }

            func mapProbe() error {
            \treturn probeError("synthetic_probe_reason", http.StatusBadRequest)
            }
            """
        )
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            ),
            extra_go=("services/demo-service/internal/demo/local_ctor.go", source),
        )
        self.assertEqual([], failures)
        self.assertEqual(0, summary["unresolved_sites"])
        self.assertGreaterEqual(summary["emission_forms"]["local_error_ctor"], 1)

    def test_local_constructor_resolves_exact_status_switch_call_sites(self) -> None:
        """Only reachable status branches emit; a dead conflict arm is not evidence."""
        source = textwrap.dedent(
            """
            package demo

            import (
            \t"net/http"
            \trterr "quwoquan_service/runtime/errors"
            )

            func routeError(status int) error {
            \treason := "internal_error"
            \tkind := rterr.KindSystem
            \tmodule := rterr.ModuleOps
            \tswitch status {
            \tcase http.StatusBadRequest, http.StatusMethodNotAllowed:
            \t\treason, kind = "invalid_argument", rterr.KindUser
            \tcase http.StatusNotFound:
            \t\treason, kind, module = "route_not_found", rterr.KindUser, rterr.ModuleGateway
            \tcase http.StatusConflict:
            \t\treason, kind = "conflict", rterr.KindUser
            \t}
            \treturn rterr.NewAppError(
            \t\trterr.NewCode(module, kind, reason), "probe", "probe")
            }

            """
        )
        callers = textwrap.dedent(
            """
            package demo

            import "net/http"

            func emitReachableStatuses() {
            \t_ = routeError(http.StatusBadRequest)
            \t_ = routeError(http.StatusNotFound)
            \t_ = routeError(http.StatusInternalServerError)
            \t// _ = routeError(http.StatusConflict) is documentation, not emission.
            }
            """
        )
        declarations = textwrap.dedent(
            """
            schema: runtime-failure-codes
            codes:
              - code: OPS.USER.invalid_argument
              - code: GATEWAY.USER.route_not_found
              - code: OPS.SYSTEM.internal_error
            """
        )
        failures, summary = self._evaluate(
            declaration=(
                "contracts/runtime_errors/errors/runtime_failure_codes.yaml",
                declarations,
            ),
            probe_go="package demo\n",
            extra_go=("services/demo-service/internal/demo/status_switch.go", source),
            extra_gos=(("services/demo-service/internal/demo/callers.go", callers),),
        )
        self.assertEqual([], failures)
        self.assertEqual(0, summary["unresolved_sites"])
        self.assertEqual(3, summary["emission_forms"]["local_error_ctor"])
        self.assertNotIn("OPS.USER.conflict", summary["new_codes"])

    def test_local_constructor_status_switch_exposes_undeclared_reachable_code(self) -> None:
        source = textwrap.dedent(
            """
            package demo

            import (
            \t"net/http"
            \trterr "quwoquan_service/runtime/errors"
            )

            func routeError(status int) error {
            \treason := "internal_error"
            \tkind := rterr.KindSystem
            \tswitch status {
            \tcase http.StatusBadRequest:
            \t\treason, kind = "synthetic_probe_reason", rterr.KindUser
            \t}
            \treturn rterr.NewAppError(
            \t\trterr.NewCode(rterr.ModuleContent, kind, reason), "probe", "probe")
            }

            func emitBadRequest() { _ = routeError(http.StatusBadRequest) }
            """
        )
        failures, summary = self._evaluate(
            probe_go="package demo\n",
            extra_go=("services/demo-service/internal/demo/status_switch.go", source),
        )
        self.assertIn(PROBE_CODE, summary["new_codes"])
        self.assertTrue(any(PROBE_CODE in failure for failure in failures))

    def test_local_constructor_dynamic_status_is_unresolved(self) -> None:
        source = textwrap.dedent(
            """
            package demo

            import (
            \t"net/http"
            \trterr "quwoquan_service/runtime/errors"
            )

            func routeError(status int) error {
            \treason := "internal_error"
            \tkind := rterr.KindSystem
            \tswitch status {
            \tcase http.StatusBadRequest:
            \t\treason, kind = "synthetic_probe_reason", rterr.KindUser
            \t}
            \treturn rterr.NewAppError(
            \t\trterr.NewCode(rterr.ModuleContent, kind, reason), "probe", "probe")
            }

            func emitDynamic(status int) { _ = routeError(status) }
            """
        )
        failures, summary = self._evaluate(
            probe_go="package demo\n",
            extra_go=("services/demo-service/internal/demo/status_switch.go", source),
        )
        self.assertEqual(1, summary["new_unresolved_sites"])
        self.assertTrue(any("新增未解析发射位" in failure for failure in failures))

    def test_app_failure_code_literal_is_scanned_but_comment_is_not(self) -> None:
        source = textwrap.dedent(
            f"""
            // failureCode: '{PROBE_CODE}' must not count by itself.
            final class ProbeReceipt {{
              const ProbeReceipt(this.failureCode);
              final String failureCode;
            }}

            ProbeReceipt emitProbe() => const ProbeReceipt(
              failureCode: '{PROBE_CODE}',
            );
            """
        )
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            ),
            extra_dart=("service/demo_service/demo/probe/application/probe.dart", source),
        )
        self.assertEqual([], failures)
        self.assertEqual(1, summary["emission_forms"]["app_stable_code_emission"])

    def test_ios_failure_code_assignment_is_scanned_but_allowlist_and_comment_are_not(self) -> None:
        source = textwrap.dedent(
            f'''
            // let failureCode = "OPS.SYSTEM.comment_only"
            let allowedCodes = ["OPS.SYSTEM.allowlist_only"]

            func emitNativeFailure(firstFrameMissing: Bool) {{
              let failureCode = firstFrameMissing
                ? "{PROBE_CODE}"
                : ""
              journal.record(failureCode: failureCode)
            }}
            '''
        )
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            ),
            probe_go="package demo\n",
            extra_swift=("Probe.swift", source),
        )
        self.assertEqual([], failures)
        self.assertEqual(
            1, summary["emission_forms"]["app_native_stable_code_emission"]
        )
        self.assertNotIn("OPS.SYSTEM.comment_only", summary["new_codes"])
        self.assertNotIn("OPS.SYSTEM.allowlist_only", summary["new_codes"])

    def test_declared_http_error_without_production_emission_is_blocked(self) -> None:
        declaration_only = BLOCK_FORM_DECLARATION.replace(
            PROBE_CODE, "CONTENT.USER.declared_only_probe"
        ).replace("ErrSyntheticProbeReason", "ErrDeclaredOnlyProbe").replace(
            "syntheticProbeReason", "declaredOnlyProbe"
        )
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/declared_only/errors.yaml",
                declaration_only,
            )
        )
        self.assertIn(
            "CONTENT.USER.declared_only_probe", summary["declared_without_emission"]
        )
        self.assertTrue(
            any("没有发射证据" in failure for failure in failures),
            f"declared-only HTTP code must BLOCK, failures={failures}",
        )

    def test_generated_definition_is_not_production_emission(self) -> None:
        declaration_only = BLOCK_FORM_DECLARATION.replace(
            PROBE_CODE, "CONTENT.USER.generated_only_probe"
        ).replace("ErrSyntheticProbeReason", "ErrGeneratedOnlyProbe").replace(
            "syntheticProbeReason", "generatedOnlyProbe"
        )
        generated_source = textwrap.dedent(
            """
            package probe

            import rterr "quwoquan_service/runtime/errors"

            func AppErrorFromGeneratedOnlyProbe(debug string) *rterr.AppError {
            \treturn rterr.NewAppError(
            \t\trterr.NewCode(rterr.ModuleContent, rterr.KindUser, "generated_only_probe"),
            \t\t"generated", debug)
            }
            """
        )
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/generated_only/errors.yaml",
                declaration_only,
            ),
            extra_go=(
                "services/demo-service/generated/demo/generated_only/errors.go",
                generated_source,
            ),
        )
        self.assertIn(
            "CONTENT.USER.generated_only_probe", summary["declared_without_emission"]
        )
        self.assertTrue(any("没有发射证据" in failure for failure in failures))

    def test_declared_http_error_with_stable_literal_is_emission_evidence(self) -> None:
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            ),
            probe_go=f'''package demo

func writeFailure() map[string]string {{
    return map[string]string{{"code": "{PROBE_CODE}"}}
}}
''',
        )
        self.assertNotIn(PROBE_CODE, summary["declared_without_emission"])
        self.assertFalse(any(PROBE_CODE in failure for failure in failures))

    def test_app_generated_error_member_requires_production_failure_use(self) -> None:
        generated_enum = f'''// generated
enum ProbeErrorCode {{
  syntheticProbeReason('{PROBE_CODE}', 'probe', 400),
  unknown('', 'unknown', 500);

  final String code;
  final String message;
  final int status;
  const ProbeErrorCode(this.code, this.message, this.status);
}}
'''
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            ),
            extra_darts=(
                (
                    "runtime/errors/generated/demo/probe_errors.g.dart",
                    generated_enum,
                ),
                (
                    "service/demo/probe/application/failure.dart",
                    '''import 'package:quwoquan_app/runtime/errors/generated/demo/probe_errors.g.dart';

final failure = RuntimeFailure(
  code: ProbeErrorCode.syntheticProbeReason.code,
);
''',
                ),
            ),
            probe_go="package demo\n",
        )
        self.assertNotIn(PROBE_CODE, summary["declared_without_emission"])
        self.assertEqual(1, summary["emission_forms"]["app_generated_error_symbol"])
        self.assertFalse(any(PROBE_CODE in failure for failure in failures))

    def test_typed_app_failure_field_resolves_generated_enum_through_part_library(self) -> None:
        generated_enum = f'''// generated
enum ProbeErrorCode {{
  syntheticProbeReason('{PROBE_CODE}', 'probe', 400),
  unknown('', 'unknown', 500);

  final String code;
  final String message;
  final int status;
  const ProbeErrorCode(this.code, this.message, this.status);
}}
'''
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            ),
            probe_go="package demo\n",
            extra_darts=(
                (
                    "runtime/errors/generated/demo/probe_errors.g.dart",
                    generated_enum,
                ),
                (
                    "service/demo/probe/application/controller.dart",
                    """import 'package:quwoquan_app/runtime/errors/generated/demo/probe_errors.g.dart';

part 'controller_actions.dart';
""",
                ),
                (
                    "service/demo/probe/application/controller_actions.dart",
                    """part of 'controller.dart';

final receipt = DeviceActionReceipt(
  failureCode: ProbeErrorCode.syntheticProbeReason.code,
);
""",
                ),
            ),
        )
        self.assertEqual([], failures)
        self.assertNotIn(PROBE_CODE, summary["declared_without_emission"])
        self.assertEqual(1, summary["emission_forms"]["app_generated_error_symbol"])

    def test_same_named_local_error_object_without_generated_import_is_not_evidence(self) -> None:
        generated_enum = f'''// generated
enum ProbeErrorCode {{
  syntheticProbeReason('{PROBE_CODE}', 'probe', 400),
  unknown('', 'unknown', 500);

  final String code;
  final String message;
  final int status;
  const ProbeErrorCode(this.code, this.message, this.status);
}}
'''
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            ),
            probe_go="package demo\n",
            extra_darts=(
                (
                    "runtime/errors/generated/demo/probe_errors.g.dart",
                    generated_enum,
                ),
                (
                    "service/demo/probe/application/fake.dart",
                    """final class ProbeErrorCode {
  static const syntheticProbeReason = _FakeCode('not-canonical');
}

final receipt = DeviceActionReceipt(
  failureCode: ProbeErrorCode.syntheticProbeReason.code,
);
""",
                ),
            ),
        )
        self.assertIn(PROBE_CODE, summary["declared_without_emission"])
        self.assertTrue(any(PROBE_CODE in failure for failure in failures))
        self.assertEqual(0, summary["emission_forms"]["app_generated_error_symbol"])

    def test_generated_code_local_flow_into_typed_failure_field_is_evidence(self) -> None:
        generated_enum = f'''// generated
enum ProbeErrorCode {{
  syntheticProbeReason('{PROBE_CODE}', 'probe', 400),
  unknown('', 'unknown', 500);

  final String code;
  final String message;
  final int status;
  const ProbeErrorCode(this.code, this.message, this.status);
}}
'''
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            ),
            probe_go="package demo\n",
            extra_darts=(
                (
                    "runtime/errors/generated/demo/probe_errors.g.dart",
                    generated_enum,
                ),
                (
                    "service/demo/probe/application/typed_flow.dart",
                    """import 'package:quwoquan_app/runtime/errors/generated/demo/probe_errors.g.dart';

final canonicalFailureCode = switch (outcome) {
  'failed' => ProbeErrorCode.syntheticProbeReason.code,
  _ => null,
};
final receipt = DeviceActionReceipt(failureCode: canonicalFailureCode);
""",
                ),
            ),
        )
        self.assertEqual([], failures)
        self.assertNotIn(PROBE_CODE, summary["declared_without_emission"])
        self.assertEqual(1, summary["emission_forms"]["app_generated_error_symbol"])

    def test_typed_generated_symbol_in_comment_or_string_is_not_evidence(self) -> None:
        generated_enum = f'''// generated
enum ProbeErrorCode {{
  syntheticProbeReason('{PROBE_CODE}', 'probe', 400),
  unknown('', 'unknown', 500);

  final String code;
  final String message;
  final int status;
  const ProbeErrorCode(this.code, this.message, this.status);
}}
'''
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            ),
            probe_go="package demo\n",
            extra_darts=(
                (
                    "runtime/errors/generated/demo/probe_errors.g.dart",
                    generated_enum,
                ),
                (
                    "service/demo/probe/application/not_emitted.dart",
                    """import 'package:quwoquan_app/runtime/errors/generated/demo/probe_errors.g.dart';

// failureCode: ProbeErrorCode.syntheticProbeReason.code,
const sourceSnippet = '''failureCode: ProbeErrorCode.syntheticProbeReason.code,''';
""",
                ),
            ),
        )
        self.assertIn(PROBE_CODE, summary["declared_without_emission"])
        self.assertTrue(any(PROBE_CODE in failure for failure in failures))
        self.assertEqual(0, summary["emission_forms"]["app_generated_error_symbol"])

    def test_generated_app_error_definition_alone_is_not_emission(self) -> None:
        generated_enum = f'''// generated
enum ProbeErrorCode {{
  syntheticProbeReason('{PROBE_CODE}', 'probe', 400),
  unknown('', 'unknown', 500);

  final String code;
  final String message;
  final int status;
  const ProbeErrorCode(this.code, this.message, this.status);
}}
'''
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            ),
            extra_dart=(
                "runtime/errors/generated/demo/probe_errors.g.dart",
                generated_enum,
            ),
            probe_go="package demo\n",
        )
        self.assertIn(PROBE_CODE, summary["declared_without_emission"])
        self.assertTrue(any("没有发射证据" in failure for failure in failures))

    def test_python_error_code_constant_is_emission_but_comment_is_not(self) -> None:
        failures, summary = self._evaluate(
            declaration=(
                "services/demo-service/contracts/demo/probe/errors.yaml",
                BLOCK_FORM_DECLARATION,
            ),
            probe_go="package demo\n",
            extra_python=(
                "services/demo-service/internal/demo/probe/adapters/inbound/http/router.py",
                f'''# COMMENT_CODE = "CONTENT.SYSTEM.comment_only"
PROBE_ERROR_CODE = "{PROBE_CODE}"

def response(code: str) -> dict[str, str]:
    return {{"code": code}}
''',
            ),
        )
        self.assertNotIn(PROBE_CODE, summary["declared_without_emission"])
        self.assertEqual(1, summary["emission_forms"]["python_stable_code_literal"])
        self.assertFalse(any("CONTENT.SYSTEM.comment_only" in item for item in failures))

    def test_wildcard_baseline_entry_is_rejected(self) -> None:
        """禁止通配符批量豁免整个 module。"""
        with self.assertRaises(SystemExit) as caught:
            self._evaluate(baseline_codes=[{"code": "CONTENT.USER.*"}])
        self.assertIn("精确", str(caught.exception))

    def test_new_unresolved_site_is_blocked(self) -> None:
        """module/kind 不唯一的新盲点必须 BLOCK，否则维度会悄悄失去覆盖。"""
        failures, summary = self._evaluate(
            baseline_codes=[
                {"code": PROBE_CODE, "detected_by": "scan"},
                {"code": RUNTIME_FALLBACK_CODE, "detected_by": "scan"},
            ],
            extra_go=(
                "services/demo-service/internal/demo/dynamic.go",
                textwrap.dedent(
                    """
                    package demo

                    import rterr "quwoquan_service/runtime/errors"

                    func writeDynamic(status int) *rterr.AppError {
                    \tmodule := rterr.ModuleContent
                    \tkind := rterr.KindSystem
                    \tif status == 400 {
                    \t\tmodule = rterr.ModuleGateway
                    \t\tkind = rterr.KindUser
                    \t}
                    \treturn rterr.NewAppError(
                    \t\trterr.NewCode(module, kind, "dynamic_reason"),
                    \t\t"动态错误",
                    \t\t"dynamic",
                    \t)
                    }
                    """
                ),
            ),
        )
        self.assertEqual(1, summary["new_unresolved_sites"])
        self.assertTrue(
            any("未解析发射位" in failure for failure in failures),
            f"新增盲点必须 BLOCK，实际 failures={failures}",
        )

    def test_unresolved_site_requires_attested_scope(self) -> None:
        """盲点条目必须写明手工枚举所依据的搜索范围（弱判据纪律）。"""
        with self.assertRaises(SystemExit) as caught:
            self._evaluate(
                unresolved_sites=[
                    {"path": "x.go", "expression": "NewCode(module, kind, reason)"}
                ]
            )
        self.assertIn("attested_scope", str(caught.exception))

    def test_absent_baseline_is_zero_debt_not_a_disabled_scanner(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            missing = Path(raw) / "retired-zero-debt-baseline.yaml"
            baseline = self.module.load_baseline(missing)

        self.assertEqual({}, baseline.codes)
        self.assertEqual({}, baseline.unresolved)

    def _declared(self, document_text: str) -> set[str]:
        document = yaml.safe_load(document_text)
        return {
            entry["code"] for entry in self.module._iter_declaration_entries(document)
        }


if __name__ == "__main__":
    unittest.main(verbosity=2)
