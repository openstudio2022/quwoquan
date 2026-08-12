from __future__ import annotations

from typing import Any, Mapping

from ..api import CapabilityRequest
from ..model import CapabilityDefinition, ProviderPlan


def plan_for(
    definition: CapabilityDefinition,
    request: CapabilityRequest[Any, Any],
    resolved_params: object,
) -> ProviderPlan:
    if request.capability != definition.capability:
        raise TypeError("Provider received a capability owned by another definition")
    return ProviderPlan(
        request_id=request.request_id.value,
        capability_definition_digest=definition.digest,
        operations=definition.operations,
        resolved_params=resolved_params,
    )


def required_id(payload: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = str(payload.get(name) or "").strip()
        if value:
            return value
    raise RuntimeError("public operation response misses required identity")


def items(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = payload.get("items")
    if raw is None:
        raw = payload.get("data")
    if not isinstance(raw, list):
        return ()
    return tuple(item for item in raw if isinstance(item, Mapping))
