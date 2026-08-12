from __future__ import annotations

from typing import Any

from ..api import BusinessObjectRef, CapabilityRequest
from ..capabilities.common import AcceptanceActorSet
from ..capabilities.notification_service import (
    NOTIFICATION_DELIVERY,
    NotificationDeliveryParams,
    NotificationDeliveryResult,
)
from ..model import (
    CapabilityDefinition,
    CleanupResult,
    ProviderPlan,
    ProvisionedCapability,
    ReadbackResult,
    TestDataContext,
)
from ..operations import PublicOperationExecutor, TestDataRuntime
from .support import items, plan_for


_DELIVERY = CapabilityDefinition(
    capability=NOTIFICATION_DELIVERY,
    operations=("notification.notification.ListAppMessages",),
)


class NotificationAcceptanceDataProvider:
    def describe(self) -> tuple[CapabilityDefinition, ...]:
        return (_DELIVERY,)

    def plan(
        self,
        context: TestDataContext,
        request: CapabilityRequest[Any, Any],
        resolved_params: object,
    ) -> ProviderPlan:
        return plan_for(_DELIVERY, request, resolved_params)

    def provision(
        self,
        context: TestDataContext,
        plan: ProviderPlan,
    ) -> ProvisionedCapability:
        if not isinstance(plan.resolved_params, NotificationDeliveryParams):
            raise TypeError("Notification Provider received invalid resolved params")
        params = plan.resolved_params
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors dependency was not resolved")
        if not isinstance(params.source, BusinessObjectRef):
            raise TypeError("notification source dependency was not resolved")
        actor = params.actors.require(params.recipient_role)
        executor = _executor(context, NOTIFICATION_DELIVERY.key.value)
        response = executor.call(
            "notification.notification.ListAppMessages",
            actor=actor,
            step_id="list-app-messages",
            query={"limit": 100},
        )
        match = next(
            (
                item
                for item in items(response)
                if str(item.get("messageType") or item.get("kind") or "").strip()
                == params.message_type.value
                and str(item.get("sourceId") or "").strip()
                == params.source.object_id
            ),
            None,
        )
        if match is None:
            raise RuntimeError("required event-derived notification did not converge")
        notification_id = str(
            match.get("messageId")
            or match.get("notificationId")
            or match.get("id")
            or ""
        ).strip()
        if not notification_id:
            raise RuntimeError("notification readback misses canonical identity")
        return ProvisionedCapability(
            value=NotificationDeliveryResult(
                notification=BusinessObjectRef("Notification", notification_id),
                delivered=True,
            ),
            operation_count=executor.operation_count,
        )

    def readback(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> ReadbackResult:
        return ReadbackResult(
            passed=(
                isinstance(provisioned.value, NotificationDeliveryResult)
                and provisioned.value.delivered
            ),
            details={"deliverySourceBound": True},
        )

    def cleanup(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> CleanupResult:
        return CleanupResult(state="released")


def _executor(context: TestDataContext, capability_key: str) -> PublicOperationExecutor:
    if not isinstance(context.runtime, TestDataRuntime):
        raise TypeError("TestData runtime is unavailable")
    return PublicOperationExecutor(
        base_url=context.base_url,
        target=context.candidate.target,
        test_data_instance_id=context.test_data_instance_id,
        capability_key=capability_key,
        runtime=context.runtime,
    )


def build_provider() -> NotificationAcceptanceDataProvider:
    return NotificationAcceptanceDataProvider()
