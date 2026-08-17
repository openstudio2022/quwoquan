from __future__ import annotations

from quwoquan_app.test.local_contract.runtime.ios_hot_restart_launcher__local_contract_test import (
    IosHotRestartLauncherContractTest as _IosHotRestartLauncherContractTest,
    _runtime_identity_issues,
)


class TestIosHotRestartLauncherCompanion(_IosHotRestartLauncherContractTest):
    def test_missing_runtime_identity_readback_is_blocking(self) -> None:
        self.assertEqual(
            _runtime_identity_issues([], expected_environment="alpha"),
            ["no installed iOS runtime identity snapshots were captured"],
        )
