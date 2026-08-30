"""Load the single governed carrier-to-execution policy."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any

import yaml

from content.execution.campaign.lane import CAMPAIGN_CARRIERS
from core.paths import REPO_DATA_ROOT
from core.schema import assert_valid

POLICY_PATH = (
    REPO_DATA_ROOT / "control_plane" / "campaigns" / "carrier_execution_policy.yaml"
)


@lru_cache(maxsize=1)
def load_carrier_execution_policy() -> dict[str, Any]:
    if not POLICY_PATH.is_file():
        raise ValueError(f"GATE_BLOCK carrier execution policy missing: {POLICY_PATH}")
    loaded = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("GATE_BLOCK carrier execution policy must be an object")
    assert_valid(
        loaded,
        "execution",
        "carrier_execution_policy",
        label="carrier execution policy",
    )
    carriers = loaded["carriers"]
    for carrier in CAMPAIGN_CARRIERS:
        operation = str(carriers[carrier]["operation"])
        if operation != f"{carrier}.generate":
            raise ValueError(
                f"GATE_BLOCK carrier execution operation drift: {carrier}={operation}"
            )
    return loaded


def carrier_execution_policy(carrier: str) -> dict[str, Any]:
    if carrier not in CAMPAIGN_CARRIERS:
        raise ValueError(f"unsupported carrier: {carrier}")
    return dict(load_carrier_execution_policy()["carriers"][carrier])


def carrier_operation(carrier: str) -> str:
    return str(carrier_execution_policy(carrier)["operation"])


def carrier_policy_digest() -> str:
    encoded = json.dumps(
        load_carrier_execution_policy(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


__all__ = [
    "POLICY_PATH",
    "carrier_execution_policy",
    "carrier_operation",
    "carrier_policy_digest",
    "load_carrier_execution_policy",
]
