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
class AssistantRunParams:
    actors: OutputRef[AcceptanceActorSet]
    sender_role: ActorRole
    prompt: str

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("assistant prompt must be non-empty")


@dataclass(frozen=True)
class AssistantRunResult:
    session: BusinessObjectRef
    run: BusinessObjectRef


ASSISTANT_PROMPT_RUN = CapabilityRef(
    key=CapabilityKey("assistant.run.prompt_response"),
    params_type=AssistantRunParams,
    result_type=AssistantRunResult,
    owner_service="assistant_service",
    required_provider_capabilities=(
        ProviderCapabilityKey("assistant.model.generation"),
    ),
)

__all__ = (
    "ASSISTANT_PROMPT_RUN",
    "AssistantRunParams",
    "AssistantRunResult",
)
