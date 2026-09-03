from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = ROOT / "quwoquan_ops/gate/verify_stackctl_provider_readiness_contract.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_stackctl_provider_readiness_contract", VERIFIER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StackctlProviderReadinessGateContractTest(unittest.TestCase):
    def test_provider_conformance_script_is_checked_at_canonical_owner(self) -> None:
        verifier = _load_verifier()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stackctl = root / "stackctl.py"
            stackctl.write_text(
                (
                    verifier.STACKCTL.read_text(encoding="utf-8")
                    + '\nPROVIDER_CONFORMANCE_SCRIPT = "quwoquan_ops/cli/lib/provider_conformance.py"\n'
                ),
                encoding="utf-8",
            )
            contract = root / "stackctl_contract.py"
            contract.write_text(
                verifier.STACKCTL_CONTRACT.read_text(encoding="utf-8").replace(
                    'PROVIDER_CONFORMANCE_SCRIPT = "quwoquan_ops/cli/lib/provider_conformance.py"',
                    'PROVIDER_CONFORMANCE_SCRIPT = "wrong-provider-entrypoint.py"',
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(verifier, "STACKCTL", stackctl),
                mock.patch.object(verifier, "STACKCTL_CONTRACT", contract),
            ):
                self.assertEqual(verifier.main(), 1)

    def test_current_provider_readiness_wiring_satisfies_gate(self) -> None:
        verifier = _load_verifier()

        self.assertEqual(verifier.main(), 0)


if __name__ == "__main__":
    unittest.main()
