from __future__ import annotations

from typing import Any

from ..api import BusinessObjectRef, CapabilityRequest
from ..capabilities.circle_service import (
    CIRCLE_WITH_MEMBERS,
    CircleWithMembersParams,
    CircleWithMembersResult,
)
from ..capabilities.common import AcceptanceActorSet
from ..model import (
    CapabilityDefinition,
    CleanupResult,
    PartialProvisioningError,
    ProviderPlan,
    ProvisionedCapability,
    ReadbackResult,
    TestDataContext,
)
from ..operations import PublicOperationExecutor, TestDataRuntime
from .support import plan_for, required_id


_CIRCLE = CapabilityDefinition(
    capability=CIRCLE_WITH_MEMBERS,
    operations=(
        "circle.circle.CreateCircle",
        "circle.circle_membership.JoinCircle",
        "circle.circle.GetCircle",
        "circle.circle.ArchiveCircle",
    ),
)


class CircleAcceptanceDataProvider:
    def describe(self) -> tuple[CapabilityDefinition, ...]:
        return (_CIRCLE,)

    def plan(
        self,
        context: TestDataContext,
        request: CapabilityRequest[Any, Any],
        resolved_params: object,
    ) -> ProviderPlan:
        return plan_for(_CIRCLE, request, resolved_params)

    def provision(
        self,
        context: TestDataContext,
        plan: ProviderPlan,
    ) -> ProvisionedCapability:
        if not isinstance(plan.resolved_params, CircleWithMembersParams):
            raise TypeError("Circle Provider received invalid resolved params")
        params = plan.resolved_params
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors dependency was not resolved")
        owner = params.actors.require(params.owner_role)
        executor = _executor(context, CIRCLE_WITH_MEMBERS.key.value)
        created = executor.call(
            "circle.circle.CreateCircle",
            actor=owner,
            step_id="create-circle",
            body={
                "name": "验收圈子",
                "description": "按用例隔离的验收圈子",
                "category": "travel",
                "tags": ["acceptance"],
                "visibility": "public",
                "joinPolicy": "open",
                "autoSyncChat": True,
            },
        )
        circle = BusinessObjectRef("Circle", required_id(created, "circleId", "id"))
        memberships: list[BusinessObjectRef] = []
        try:
            for index, role in enumerate(params.member_roles):
                member = params.actors.require(role)
                joined = executor.call(
                    "circle.circle_membership.JoinCircle",
                    actor=member,
                    step_id=f"join-circle-{index:02d}",
                    bindings={"circleId": circle.object_id},
                )
                membership_id = str(
                    joined.get("membershipId")
                    or joined.get("id")
                    or member.persona.object_id
                ).strip()
                memberships.append(
                    BusinessObjectRef("CircleMembership", membership_id)
                )
        except BaseException as error:
            raise PartialProvisioningError(
                "Circle Provider stopped after creating a circle",
                provisioned=ProvisionedCapability(
                    value=CircleWithMembersResult(
                        circle=circle,
                        memberships=tuple(memberships),
                    ),
                    cleanup_handle=(circle,),
                    cleanup_context=owner,
                    operation_count=executor.operation_count,
                ),
            ) from error
        return ProvisionedCapability(
            value=CircleWithMembersResult(
                circle=circle,
                memberships=tuple(memberships),
            ),
            cleanup_handle=(circle,),
            cleanup_context=owner,
            operation_count=executor.operation_count,
        )

    def readback(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> ReadbackResult:
        if not isinstance(provisioned.value, CircleWithMembersResult):
            return ReadbackResult(passed=False)
        executor = _executor(context, CIRCLE_WITH_MEMBERS.key.value + ".readback")
        response = executor.call(
            "circle.circle.GetCircle",
            actor=provisioned.cleanup_context,
            step_id="get-circle",
            bindings={"circleId": provisioned.value.circle.object_id},
        )
        observed = str(response.get("circleId") or response.get("id") or "").strip()
        return ReadbackResult(
            passed=observed == provisioned.value.circle.object_id,
            operation_count=executor.operation_count,
            details={"membershipCount": len(provisioned.value.memberships)},
        )

    def cleanup(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> CleanupResult:
        if not isinstance(provisioned.value, CircleWithMembersResult):
            return CleanupResult(state="quarantined")
        executor = _executor(context, CIRCLE_WITH_MEMBERS.key.value + ".cleanup")
        executor.call(
            "circle.circle.ArchiveCircle",
            actor=provisioned.cleanup_context,
            step_id="archive-circle",
            bindings={"circleId": provisioned.value.circle.object_id},
        )
        return CleanupResult(state="released", operation_count=executor.operation_count)


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


def build_provider() -> CircleAcceptanceDataProvider:
    return CircleAcceptanceDataProvider()
