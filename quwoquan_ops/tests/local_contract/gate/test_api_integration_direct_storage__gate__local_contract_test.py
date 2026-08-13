# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-001
"""api_integration 直插存储专项区分门禁的配套合约。

覆盖 `verify_api_integration_direct_storage.py`：一般用例直插被拒、
`__data_consistency__` facet 与 provider-state harness 放行、棘轮只减不增。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = REPO_ROOT / "quwoquan_ops/gate/verify_api_integration_direct_storage.py"

DIRECT_WRITE_SOURCE = (
    "package api_integration\n\n"
    "func seed() {\n"
    "\t_, _ = pgPool.Exec(ctx, \"INSERT INTO accounts VALUES ($1)\", id)\n"
    "}\n"
)

COMMAND_DRIVEN_SOURCE = (
    "package api_integration\n\n"
    "func seed() {\n"
    "\t_ = application.SubmitCommand(ctx, command)\n"
    "}\n"
)

HARNESS_CLEANUP_SOURCE = (
    "package api_integration\n\n"
    "func cleanCollections() {\n"
    "\t_, _ = mongoDB.Collection(name).DeleteMany(ctx, bson.D{})\n"
    "}\n"
)

#: 口径收紧后必须捕获的写形态：Mongo Update 非 ctx 首参、ReplaceOne、
#: BulkWrite，以及反引号跨行 SQL 写句。
WIDE_MONGO_WRITE_SOURCE = (
    "package api_integration\n\n"
    "func seed() {\n"
    "\t_, _ = mongoDB.Collection(name).UpdateOne(\n"
    "\t\tcontext.Background(),\n"
    "\t\tbson.M{\"_id\": id},\n"
    "\t\tbson.M{\"$set\": bson.M{\"createdAt\": old}},\n"
    "\t)\n"
    "}\n"
)

MULTILINE_SQL_WRITE_SOURCE = (
    "package api_integration\n\n"
    "func seed() {\n"
    "\t_, _ = assignmentPGPool.Exec(ctx, `\n"
    "INSERT INTO experiments(id) VALUES ($1)`, id)\n"
    "}\n"
)


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_api_integration_direct_storage_for_contract_test",
        VERIFIER_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApiIntegrationDirectStorageContractTest(unittest.TestCase):
    def _residue(self, files: dict[str, str], ceiling: int | None = None) -> tuple[int, list[str]]:
        verifier = _load_verifier()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            services_root = root / "quwoquan_service/services"
            for relative, source in files.items():
                target = services_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source, encoding="utf-8")
            previous = (verifier.ROOT, verifier.SERVICES_ROOT, verifier.DIRECT_STORAGE_FILE_CEILING)
            verifier.ROOT = root
            verifier.SERVICES_ROOT = services_root
            if ceiling is not None:
                verifier.DIRECT_STORAGE_FILE_CEILING = ceiling
            try:
                import contextlib
                import io

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = verifier.main()
                return code, stdout.getvalue().splitlines()
            finally:
                (
                    verifier.ROOT,
                    verifier.SERVICES_ROOT,
                    verifier.DIRECT_STORAGE_FILE_CEILING,
                ) = previous

    def test_plain_direct_write_counts_into_the_ratchet(self) -> None:
        code, output = self._residue(
            {
                "example-service/tests/api_integration/ctx/obj/"
                "close_account_contract__api_integration_test.go": DIRECT_WRITE_SOURCE
            },
            ceiling=0,
        )
        self.assertEqual(code, 1, output)
        self.assertTrue(any("grew to 1" in line for line in output), output)

    def test_data_consistency_facet_is_a_declared_speciality(self) -> None:
        code, output = self._residue(
            {
                "example-service/tests/api_integration/ctx/obj/"
                "outbox_replay__data_consistency__api_integration_test.go": DIRECT_WRITE_SOURCE
            },
            ceiling=0,
        )
        self.assertEqual(code, 0, output)

    def test_provider_state_harness_is_the_canonical_channel(self) -> None:
        code, output = self._residue(
            {
                "example-service/tests/api_integration/ctx/obj/"
                "contract_provider_state_persistence__api_integration_test.go": DIRECT_WRITE_SOURCE
            },
            ceiling=0,
        )
        self.assertEqual(code, 0, output)

    def test_package_support_harness_is_a_declared_speciality(self) -> None:
        """包级 seed/setup harness（`__support` / `_test_support` 结尾）是同包
        contract 用例共享的前置状态收口点，直插豁免。"""
        code, output = self._residue(
            {
                "example-service/tests/api_integration/ctx/obj/"
                "helpers__support__api_integration_test.go": DIRECT_WRITE_SOURCE,
                "example-service/tests/api_integration/ctx/obj/"
                "runtime_test_support__api_integration_test.go": DIRECT_WRITE_SOURCE,
            },
            ceiling=0,
        )
        self.assertEqual(code, 0, output)

    def test_support_suffix_must_terminate_the_subject(self) -> None:
        """`__support` 只在 subject 结尾生效；中段出现不构成 harness 声明。"""
        code, output = self._residue(
            {
                "example-service/tests/api_integration/ctx/obj/"
                "helpers__support_extra__api_integration_test.go": DIRECT_WRITE_SOURCE
            },
            ceiling=0,
        )
        self.assertEqual(code, 1, output)

    def test_mongo_update_without_ctx_first_arg_is_counted(self) -> None:
        code, output = self._residue(
            {
                "example-service/tests/api_integration/ctx/obj/"
                "call_timeout_contract__api_integration_test.go": WIDE_MONGO_WRITE_SOURCE
            },
            ceiling=0,
        )
        self.assertEqual(code, 1, output)

    def test_multiline_backtick_sql_write_is_counted(self) -> None:
        code, output = self._residue(
            {
                "example-service/tests/api_integration/ctx/obj/"
                "postgres_fact__api_integration_test.go": MULTILINE_SQL_WRITE_SOURCE
            },
            ceiling=0,
        )
        self.assertEqual(code, 1, output)

    def test_harness_cleanup_delete_is_not_counted(self) -> None:
        code, output = self._residue(
            {
                "example-service/tests/api_integration/ctx/obj/"
                "testmain__reliability__api_integration_test.go": HARNESS_CLEANUP_SOURCE
            },
            ceiling=0,
        )
        self.assertEqual(code, 0, output)

    def test_command_driven_precondition_is_not_counted(self) -> None:
        code, output = self._residue(
            {
                "example-service/tests/api_integration/ctx/obj/"
                "close_account_contract__api_integration_test.go": COMMAND_DRIVEN_SOURCE
            },
            ceiling=0,
        )
        self.assertEqual(code, 0, output)

    def test_residue_within_ceiling_reports_and_passes(self) -> None:
        code, output = self._residue(
            {
                "example-service/tests/api_integration/ctx/obj/"
                "close_account_contract__api_integration_test.go": DIRECT_WRITE_SOURCE
            },
            ceiling=1,
        )
        self.assertEqual(code, 0, output)
        self.assertTrue(any("files=1 (ceiling=1)" in line for line in output), output)

    def test_real_tree_residue_matches_the_declared_ceiling(self) -> None:
        verifier = _load_verifier()
        residue = 0
        for path in sorted(verifier.SERVICES_ROOT.rglob("*__api_integration_test.go")):
            relative = path.relative_to(verifier.ROOT).as_posix()
            if "/tests/api_integration/" not in relative:
                continue
            if verifier.is_declared_specialised(path.name):
                continue
            if verifier.DIRECT_WRITE_RE.search(
                path.read_text(encoding="utf-8", errors="ignore")
            ):
                residue += 1
        self.assertLessEqual(residue, verifier.DIRECT_STORAGE_FILE_CEILING)


if __name__ == "__main__":
    unittest.main()
