"""S0 知识资产迁移门禁负例。"""

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-004.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-004.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-004.t3

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[4]
GATE_PATH = REPO_ROOT / "quwoquan_ops/gate/verify_knowledge_asset_s0_migration.py"
FIXTURE_PATH = (
    REPO_ROOT
    / "quwoquan_ops/policies/migrations/knowledge_assets_s0_v1.json"
)


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_knowledge_asset_s0", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KnowledgeAssetS0MigrationGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_gate()
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def _verify(self, mutate) -> list[str]:
        document = copy.deepcopy(self.fixture)
        mutate(document)
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.json"
            fixture.write_text(
                json.dumps(document, ensure_ascii=False), encoding="utf-8"
            )
            return self.module.verify_fixture(fixture, root=REPO_ROOT)

    def test_real_fixture_passes(self) -> None:
        self.assertEqual([], self.module.verify_fixture(FIXTURE_PATH, root=REPO_ROOT))

    def test_rejects_count_drift(self) -> None:
        issues = self._verify(lambda doc: doc["rows"].pop())
        self.assertTrue(any("row count drift" in issue for issue in issues), issues)

    def test_rejects_digest_drift(self) -> None:
        def mutate(doc) -> None:
            doc["rows"][0]["clause_digest"] = "0" * 64

        issues = self._verify(mutate)
        self.assertTrue(any("digest drift" in issue for issue in issues), issues)

    def test_rejects_missing_target(self) -> None:
        def mutate(doc) -> None:
            row = next(r for r in doc["rows"] if r["disposition"] != "discard")
            row["target_path"] = "specs/feature-tree/does-not-exist/spec.md"

        issues = self._verify(mutate)
        self.assertTrue(any("target missing" in issue for issue in issues), issues)

    def test_rejects_missing_anchor(self) -> None:
        def mutate(doc) -> None:
            row = next(
                r
                for r in doc["rows"]
                if r["binding_type"] == "markdown-anchor"
            )
            row["target_anchor"] = "missing-s0-anchor"

        issues = self._verify(mutate)
        self.assertTrue(any("anchor missing" in issue for issue in issues), issues)

    def test_rejects_unresolved_blocker(self) -> None:
        def mutate(doc) -> None:
            doc["rows"][0]["terminal_status"] = "GATE_BLOCK(owner_or_anchor_missing)"

        issues = self._verify(mutate)
        self.assertTrue(any("unresolved blocker" in issue for issue in issues), issues)

    def test_rejects_dangling_refs(self) -> None:
        def mutate(doc) -> None:
            doc["rows"][0]["dangling_refs"] = ["retired/carrier.md"]

        issues = self._verify(mutate)
        self.assertTrue(any("dangling refs" in issue for issue in issues), issues)


    def test_rejects_source_identity_drift(self) -> None:
        def mutate(doc) -> None:
            row = doc["rows"][0]
            row["normalized_clause_identity"] += "\nforged"
            row["clause_digest"] = self.module._digest(row)

        issues = self._verify(mutate)
        self.assertTrue(
            any("normalized clause identity drift" in issue for issue in issues),
            issues,
        )

    def test_rejects_source_bytes_drift(self) -> None:
        source_path = self.fixture["source_files"][0]["source_path"]
        original = self.module._git_bytes

        def changed(root: Path, head: str, path: str) -> bytes:
            content = original(root, head, path)
            return content + b"\nsource-drift"

        with mock.patch.object(self.module, "_git_bytes", side_effect=changed):
            issues = self.module.verify_fixture(FIXTURE_PATH, root=REPO_ROOT)
        self.assertTrue(
            any("source bytes drift" in issue and source_path in issue for issue in issues),
            issues,
        )

    def test_frozen_source_object_is_available(self) -> None:
        source_path = self.fixture["source_files"][0]["source_path"]
        completed = subprocess.run(
            [
                "git",
                "cat-file",
                "-e",
                f"{self.module.EXPECTED_HEAD}:{source_path}",
            ],
            cwd=REPO_ROOT,
            check=False,
        )
        self.assertEqual(0, completed.returncode)


if __name__ == "__main__":
    unittest.main()
