#!/usr/bin/env python3
"""App metadata/codegen gates must scan canonical service contracts."""

from __future__ import annotations

import importlib.util
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_ROOT = REPO_ROOT / "quwoquan_app" / "scripts" / "runtime"


def load_verifier(name: str):
    path = SCRIPT_ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifyMetadataAppContractGatesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.routes = load_verifier("verify_metadata_routes_vs_codegen_app")
        cls.responses = load_verifier(
            "verify_metadata_response_body_vs_codegen_app"
        )

    def test_routes_scan_every_generated_contract_domain(self) -> None:
        routes = self.routes.collect_yaml_routes_by_domain()
        generated_domains = {
            path.parent.name
            for path in self.routes.GEN_DIR.glob("*/*_api_metadata.g.dart")
            if self.routes.parse_dart_operation_map(path)
        }
        self.assertEqual(set(routes), generated_domains)
        self.assertTrue(all(routes[domain] for domain in generated_domains))

    def test_response_gate_scans_current_canonical_declarations(self) -> None:
        declarations = self.responses.collect_response_decls()
        checked = sum(len(operations) for operations in declarations.values())
        self.assertGreater(checked, 0)
        self.assertIn("content", declarations)
        self.assertIn("chat", declarations)

    def test_route_gate_rejects_empty_green_result(self) -> None:
        with mock.patch.object(
            self.routes, "collect_yaml_routes_by_domain", return_value={}
        ):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(self.routes.main(), 1)

    def test_response_gate_rejects_empty_green_result(self) -> None:
        with (
            mock.patch.object(
                self.responses, "collect_projection_index", return_value={}
            ),
            mock.patch.object(
                self.responses, "collect_response_decls", return_value={}
            ),
        ):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(self.responses.main(), 1)


if __name__ == "__main__":
    unittest.main()
