"""managed runtime 只消费 target 对应的 canonical occupancy authority。

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
"""
from __future__ import annotations

import contextlib
import unittest
from unittest import mock

from quwoquan_ops.cli import stackctl


class ManagedRuntimeAuthorityRoutingTest(unittest.TestCase):
    """真实 topology + receipt loader 的共享资源 authority 组合契约。"""

    def _empty_release_receipts(self, patches: contextlib.ExitStack) -> None:
        patches.enter_context(
            mock.patch.object(stackctl, "load_startup_attempt", return_value=None)
        )
        patches.enter_context(
            mock.patch.object(
                stackctl, "load_workload_startup_attempt", return_value=None
            )
        )
        patches.enter_context(
            mock.patch.object(
                stackctl, "load_test_live_startup_attempt", return_value=None
            )
        )

    def test_real_topology_absent_or_stopped_prod_sim_does_not_block(self) -> None:
        topology = stackctl.load_environment_topology()
        for occupancy_state in ("absent", "stopped"):
            with self.subTest(occupancy_state=occupancy_state), contextlib.ExitStack() as patches:
                self._empty_release_receipts(patches)
                conflicts = patches.enter_context(
                    mock.patch.object(
                        stackctl,
                        "active_conflicting_local_targets",
                        return_value=(),
                    )
                )
                requested, active = stackctl._dev_session_active_receipts(
                    topology, "alpha-local"
                )

            self.assertIsNone(requested)
            self.assertEqual(active, [])
            conflicts.assert_called_once_with(topology, "alpha-local")

    def test_real_topology_active_prod_sim_is_typed_conflict(self) -> None:
        topology = stackctl.load_environment_topology()
        with contextlib.ExitStack() as patches:
            self._empty_release_receipts(patches)
            patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "active_conflicting_local_targets",
                    return_value=("prod-sim",),
                )
            )
            _requested, conflict = stackctl._dev_session_runtime_preflight(
                topology=topology,
                target="alpha-local",
            )

        self.assertIsNotNone(conflict)
        assert conflict is not None
        self.assertEqual(conflict["target"], "prod-sim")
        self.assertEqual(conflict["receiptScope"], "canonical-occupancy")
        self.assertEqual(conflict["workload"], "canonical-occupancy")
        self.assertEqual(conflict["status"], "running")

    def test_unknown_target_fails_closed_without_prod_sim_reclaim(self) -> None:
        topology = stackctl.load_environment_topology()
        with (
            mock.patch.object(
                stackctl,
                "bounded_replace_stale_test_live_startup_attempt",
                side_effect=AssertionError("unknown target must never reclaim"),
            ) as reclaim,
            self.assertRaisesRegex(ValueError, "unsupported|not admissible"),
        ):
            stackctl._dev_session_active_receipts(topology, "prod-sim")
        reclaim.assert_not_called()


class ManagedRuntimeAuthorityFailureTest(unittest.TestCase):
    def test_malformed_alpha_preflight_preserves_first_detail_without_replacement(
        self,
    ) -> None:
        import tempfile
        from pathlib import Path

        first_detail = "startup attempt receipt fields mismatch"
        with (
            contextlib.ExitStack() as patches,
            tempfile.TemporaryDirectory() as temporary,
        ):
            patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    lambda _target: contextlib.nullcontext(),
                )
            )
            patches.enter_context(
                mock.patch.object(stackctl, "load_environment_topology", return_value={})
            )
            patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_dev_session_runtime_preflight",
                    side_effect=ValueError(first_detail),
                )
            )
            replace = patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_bounded_replace_stale_managed_receipt",
                    side_effect=AssertionError("malformed receipt must not replace"),
                )
            )
            start = patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_start_mutable_test_live_runtime",
                    side_effect=AssertionError("malformed receipt must not start"),
                )
            )
            with self.assertRaises(stackctl.ManagedPreparationBlocked) as raised:
                stackctl._managed_runtime_ready(
                    environment="alpha",
                    target="alpha-local",
                    report_dir=Path(temporary),
                )

        self.assertEqual(raised.exception.details, [first_detail])
        replace.assert_not_called()
        start.assert_not_called()



if __name__ == "__main__":
    unittest.main()
