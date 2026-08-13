from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = (
    ROOT
    / "quwoquan_service/scripts/verify/contract_graph/verify_contract_graph_single_track.py"
)


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_contract_graph_single_track_source_freshness",
        VERIFIER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verifier: {VERIFIER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ContractGraphSourceFreshnessContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.verifier = _load_verifier()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.repository = Path(self.temporary_directory.name)
        self.metadata = self.repository / "compiler-view"
        self.metadata.mkdir()

    def _graph_for(self, relative_path: str, content: bytes) -> dict[str, object]:
        source = self.metadata / relative_path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(content)
        return {
            "sources": [
                {
                    "path": relative_path,
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            ]
        }

    def _failures(self, graph: dict[str, object]) -> list[str]:
        return self.verifier.contract_graph_source_failures(
            graph,
            self.metadata,
            self.repository,
        )

    def test_current_compiler_view_digest_passes(self) -> None:
        graph = self._graph_for("user/account/fields.yaml", b"fields: []\n")

        self.assertEqual(self._failures(graph), [])

    def test_stale_embedded_digest_fails_closed(self) -> None:
        graph = self._graph_for("user/account/fields.yaml", b"fields: []\n")
        graph["sources"][0]["sha256"] = "0" * 64

        failures = self._failures(graph)

        self.assertEqual(len(failures), 1)
        self.assertIn("source digest drift", failures[0])

    def test_parent_escape_is_rejected_before_file_access(self) -> None:
        graph = {
            "sources": [
                {
                    "path": "../outside.yaml",
                    "sha256": "0" * 64,
                }
            ]
        }

        failures = self._failures(graph)

        self.assertEqual(len(failures), 1)
        self.assertIn("escapes the metadata view", failures[0])


if __name__ == "__main__":
    unittest.main()
