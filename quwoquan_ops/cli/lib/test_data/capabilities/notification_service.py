from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..api import BusinessObjectRef, CapabilityKey, CapabilityRef, OutputRef
from .common import AcceptanceActorSet, ActorRole


class NotificationMessageType(StrEnum):
    CHAT = "chat"


@dataclass(frozen=True)
class NotificationDeliveryParams:
    actors: OutputRef[AcceptanceActorSet]
    source: OutputRef[BusinessObjectRef]
    recipient_role: ActorRole
    message_type: NotificationMessageType


@dataclass(frozen=True)
class NotificationDeliveryResult:
    notification: BusinessObjectRef
    delivered: bool


NOTIFICATION_DELIVERY = CapabilityRef(
    key=CapabilityKey("notification.delivery.app_message"),
    params_type=NotificationDeliveryParams,
    result_type=NotificationDeliveryResult,
    owner_service="notification_service",
    mutates_environment=False,
)

__all__ = (
    "NOTIFICATION_DELIVERY",
    "NotificationDeliveryParams",
    "NotificationDeliveryResult",
    "NotificationMessageType",
)
