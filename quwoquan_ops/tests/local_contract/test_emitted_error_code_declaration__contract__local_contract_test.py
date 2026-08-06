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
    ) -> tuple[Path, Path]:
        service = tmp / "quwoquan_service"
        runtime_errors = service / "runtime" / "errors" / "errors.go"
        runtime_errors.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_RUNTIME_ERRORS, runtime_errors)

        probe = service / "services" / "demo-service" / "internal" / "demo" / "handler.go"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text(PROBE_GO, encoding="utf-8")

        if extra_go is not None:
            relative, text = extra_go
            path = service / relative
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

    def _declared(self, document_text: str) -> set[str]:
        document = yaml.safe_load(document_text)
        return {
            entry["code"] for entry in self.module._iter_declaration_entries(document)
        }


if __name__ == "__main__":
    unittest.main(verbosity=2)
