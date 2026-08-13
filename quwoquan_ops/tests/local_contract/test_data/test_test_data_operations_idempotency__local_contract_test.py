"""Public test-data operation idempotency and retry contracts.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md#gwt-002
"""

from __future__ import annotations

import unittest
from unittest import mock

from quwoquan_ops.cli.lib.local_environment_auth import (
    LocalAcceptanceActor,
    LocalAcceptanceSession,
    LocalEnvironmentHTTPError,
)
from quwoquan_ops.cli.lib.test_data.api import BusinessObjectRef
from quwoquan_ops.cli.lib.test_data.capabilities.common import ActorHandle, ActorRole
from quwoquan_ops.cli.lib.test_data import operations as operation_module
from quwoquan_ops.cli.lib.test_data.operations import (
    ContractOperation,
    PublicOperationExecutor,
    TestDataRuntime as DataRuntime,
)


_OPERATION_ID = "example.widget.CreateWidget"


class _Catalog:
    def require(self, operation_id: str) -> ContractOperation:
        if operation_id != _OPERATION_ID:
            raise ValueError(f"unexpected operation: {operation_id}")
        return ContractOperation(
            operation_id=operation_id,
            method="POST",
            path_template="/widgets",
        )


def _register_actor(
    runtime: DataRuntime,
    *,
    test_data_instance_id: str,
) -> tuple[ActorHandle, list[dict[str, object]]]:
    suffix = test_data_instance_id.replace("-", "")
    handle = ActorHandle(
        role=ActorRole.PRIMARY,
        account=BusinessObjectRef("UserAccount", f"account-{suffix}"),
        persona=BusinessObjectRef("Persona", f"persona-{suffix}"),
        session_handle=f"session-{suffix}",
    )
    runtime.register_actor(
        handle,
        LocalAcceptanceActor(
            role=ActorRole.PRIMARY.value,
            session=LocalAcceptanceSession(
                owner_id=handle.account.object_id,
                persona_id=handle.persona.object_id,
                access_token=f"opaque-{suffix}",
            ),
            challenge_id=f"challenge-{suffix}",
            account_state="active",
            identity_origin="phone",
        ),
        test_data_instance_id=test_data_instance_id,
    )
    receipts: list[dict[str, object]] = []
    runtime.register_operation_receipt_sink(
        test_data_instance_id,
        lambda receipt: receipts.append(dict(receipt)),
    )
    return handle, receipts


def _executor(
    runtime: DataRuntime,
    *,
    test_data_instance_id: str,
) -> PublicOperationExecutor:
    return PublicOperationExecutor(
        base_url="https://gamma.local.quwoquan.invalid",
        target="gamma-local",
        test_data_instance_id=test_data_instance_id,
        capability_key="example.widget",
        runtime=runtime,
        catalog=_Catalog(),  # type: ignore[arg-type]
    )


class TestDataOperationIdempotencyContractTest(unittest.TestCase):
    def test_failed_same_instance_retry_reuses_key_and_records_only_success(
        self,
    ) -> None:
        runtime = DataRuntime()
        actor, durable_receipts = _register_actor(
            runtime,
            test_data_instance_id="instance-retry",
        )
        first_attempt = _executor(
            runtime,
            test_data_instance_id="instance-retry",
        )
        retry_attempt = _executor(
            runtime,
            test_data_instance_id="instance-retry",
        )
        responses: list[str] = []

        def request(*_args: object, **kwargs: object) -> dict[str, object]:
            responses.append(kwargs["headers"]["Idempotency-Key"])  # type: ignore[index]
            if len(responses) == 1:
                raise LocalEnvironmentHTTPError(
                    method="POST",
                    path="/widgets",
                    status=503,
                )
            return {"widgetId": "widget-1"}

        with mock.patch.object(
            operation_module,
            "request_local_environment_json",
            side_effect=request,
        ):
            with self.assertRaises(LocalEnvironmentHTTPError):
                first_attempt.call(
                    _OPERATION_ID,
                    actor=actor,
                    step_id="create-widget",
                    body={"name": "one"},
                )
            self.assertEqual(first_attempt.operation_count, 0)
            self.assertEqual(runtime.operation_receipts, [])
            self.assertEqual(durable_receipts, [])

            result = retry_attempt.call(
                _OPERATION_ID,
                actor=actor,
                step_id="create-widget",
                body={"name": "one"},
            )

        self.assertEqual(result, {"widgetId": "widget-1"})
        self.assertEqual(responses[0], responses[1])
        self.assertEqual(
            responses[1],
            "gamma-local/instance-retry/example.widget/primary/"
            f"{_OPERATION_ID}/create-widget",
        )
        self.assertEqual(retry_attempt.operation_count, 1)
        self.assertEqual(len(runtime.operation_receipts), 1)
        self.assertEqual(len(durable_receipts), 1)

    def test_operation_identity_is_isolated_by_test_data_instance(self) -> None:
        runtime = DataRuntime()
        first_actor, first_receipts = _register_actor(
            runtime,
            test_data_instance_id="instance-a",
        )
        second_actor, second_receipts = _register_actor(
            runtime,
            test_data_instance_id="instance-b",
        )
        captured_keys: list[str] = []

        def request(*_args: object, **kwargs: object) -> dict[str, object]:
            captured_keys.append(kwargs["headers"]["Idempotency-Key"])  # type: ignore[index]
            return {"widgetId": "widget-1"}

        with mock.patch.object(
            operation_module,
            "request_local_environment_json",
            side_effect=request,
        ):
            _executor(runtime, test_data_instance_id="instance-a").call(
                _OPERATION_ID,
                actor=first_actor,
                step_id="create-widget",
                body={"name": "one"},
            )
            _executor(runtime, test_data_instance_id="instance-b").call(
                _OPERATION_ID,
                actor=second_actor,
                step_id="create-widget",
                body={"name": "one"},
            )

        self.assertEqual(len(set(captured_keys)), 2)
        self.assertIn("/instance-a/", captured_keys[0])
        self.assertIn("/instance-b/", captured_keys[1])
        self.assertEqual(len(first_receipts), 1)
        self.assertEqual(len(second_receipts), 1)
        self.assertEqual(len(runtime.operation_receipts), 2)
        self.assertNotEqual(
            runtime.operation_receipts[0]["requestDigest"],
            runtime.operation_receipts[1]["requestDigest"],
        )


if __name__ == "__main__":
    unittest.main()
