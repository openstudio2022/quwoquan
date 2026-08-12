from __future__ import annotations

from dataclasses import dataclass

from ..api import (
    BusinessObjectRef,
    CapabilityKey,
    CapabilityRef,
    OutputRef,
    ProviderCapabilityKey,
)
from .common import AcceptanceActorSet, ActorRole


@dataclass(frozen=True)
class CompletedCallParams:
    actors: OutputRef[AcceptanceActorSet]
    conversation: OutputRef[BusinessObjectRef]
    caller_role: ActorRole
    callee_role: ActorRole


@dataclass(frozen=True)
class CompletedCallResult:
    call: BusinessObjectRef
    final_state: str


COMPLETED_CALL = CapabilityRef(
    key=CapabilityKey("rtc.call.completed_call"),
    params_type=CompletedCallParams,
    result_type=CompletedCallResult,
    owner_service="rtc_service",
    required_provider_capabilities=(
        ProviderCapabilityKey("integration.push.delivery"),
        ProviderCapabilityKey("rtc.room.transport"),
    ),
)

__all__ = ("COMPLETED_CALL", "CompletedCallParams", "CompletedCallResult")
