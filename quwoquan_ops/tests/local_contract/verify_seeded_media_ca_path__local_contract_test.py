from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_alpha_media_fixture_surface import _resolve_local_root_ca


class SeededMediaCAPathContractTest(unittest.TestCase):
    def test_local_ca_is_resolved_from_external_deploy_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(Path(tmp_dir) / "deploy")},
                clear=False,
            ):
                self.assertEqual(
                    _resolve_local_root_ca("alpha-local", ""),
                    Path(tmp_dir)
                    / "deploy"
                    / "alpha-local"
                    / "certificates"
                    / "tls"
                    / "ca"
                    / "root.crt",
                )
                self.assertEqual(
                    _resolve_local_root_ca("gamma-local", ""),
                    Path(tmp_dir)
                    / "deploy"
                    / "gamma-local"
                    / "certificates"
                    / "root.crt",
                )


if __name__ == "__main__":
    unittest.main()
