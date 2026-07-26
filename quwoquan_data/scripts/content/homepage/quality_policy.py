"""Resolve homepage quality limits from the owning reusable vertical policy."""
from __future__ import annotations

from content.execution.identity import parse_execution_id
from governance.content_supply_policy import load_content_supply_policy


def homepage_source_fidelity_limit(execution_id: str) -> float:
    identity = parse_execution_id(execution_id)
    return load_content_supply_policy(identity.vertical).homepage_max_source_fidelity


__all__ = ["homepage_source_fidelity_limit"]
