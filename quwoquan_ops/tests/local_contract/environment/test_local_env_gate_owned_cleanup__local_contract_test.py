# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#gwt-003
from __future__ import annotations

from unittest import mock
from quwoquan_ops.cli.lib.local_env_gate_matrix import evidence


def test_reused_and_unknown_runtime_never_down() -> None:
    down = mock.Mock()
    for ownership in (None, {"runtimeReused": True, "instanceGeneration": "old"}, {"runtimeCreated": False}):
        payload, code = evidence._run_down_phase("beta-local", down_fn=down, phases=[], phase_name="cleanup", ownership=ownership)
        assert code == 0
        assert payload["cleanupDisposition"] == "preserved_not_owned"
    down.assert_not_called()


def test_created_cleanup_requires_exact_generation() -> None:
    down = mock.Mock(return_value={"exitCode": 0, "reportDir": "/report"})
    _, code = evidence._run_down_phase("beta-local", down_fn=down, phases=[], phase_name="cleanup", ownership={"runtimeCreated": True})
    assert code == 2
    down.assert_not_called()
    with mock.patch.object(evidence, "_invoke_env", side_effect=lambda fn, args, **kwargs: fn(args)):
        _, code = evidence._run_down_phase("beta-local", down_fn=down, phases=[], phase_name="cleanup", ownership={"runtimeCreated": True, "instanceGeneration": "runtime-1"})
    assert code == 0
    assert down.call_args.args[0].expected_generation == "runtime-1"
    assert down.call_args.args[0].target == "beta-local"


def test_journal_preserves_other_target_and_binds_generation() -> None:
    journal = {"gamma-local": {"runtimeCreated": True, "instanceGeneration": "g1"}}
    down = mock.Mock(return_value={"exitCode": 0, "reportDir": "/report"})
    with mock.patch.object(evidence, "_invoke_env", side_effect=lambda fn, args, **kwargs: fn(args)):
        assert evidence._drain_resource_journal(journal, down_fn=down, phases=[], environments={}) == 0
    assert down.call_count == 1
    assert down.call_args.args[0].target == "gamma-local"
    assert down.call_args.args[0].expected_generation == "g1"
    assert not journal
    assert not hasattr(evidence, "_pre_down_shared_targets")
