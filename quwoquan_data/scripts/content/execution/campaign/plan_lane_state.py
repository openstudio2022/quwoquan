"""Canonical initial lane state for campaign reports."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign.external_inputs import (
    external_inputs_digest,
    payload_digest,
)
from content.execution.campaign.lane import (
    normalize_active_carriers,
    normalize_workloads,
)
from content.execution.campaign.plan_lane_status import (
    aggregate_status,
    apply_receipt_fields,
    load_publish_for_lane,
    load_review_for_lane,
)
from content.execution.campaign.plan_identity import (
    campaign_path,
    plan_path,
    report_path,
    sha256_payload,
    utc_now,
)
from content.execution.campaign.plan_source_pool import aggregate_plan_source_pool
from content.execution.campaign.submission import load_submissions
from content.execution.campaign.workspace import (
    CampaignRuntimePaths,
    assert_frozen_main_tree,
)
from content.execution.closure.adoption_campaign_contract import (
    CAMPAIGN_ADOPTION_FIELD,
    validate_adoption_target_identity,
    validate_campaign_adoption_binding,
)
from content.execution.planning.capacity_calibration import (
    assert_capacity_source_binding,
)
from content.execution.planning.semantic_preflight_admission import (
    bind_semantic_preflight_receipt,
    validate_semantic_preflight_binding_at,
)

if TYPE_CHECKING:
    from content.execution.campaign.runtime import CampaignRunSession


CAMPAIGN_SUBMISSION_POLL_SECONDS = 2


def empty_lane(execution_id: str = "pending") -> dict[str, Any]:
    return {
        "executionId": execution_id,
        "status": "pending",
        "phase": "submission",
        "reviewReturnCode": None,
        "publishReturnCode": None,
        "sourceCapsuleRef": None,
        "sourceCapsuleDigest": None,
        "sourceCapsuleCommitSha": None,
        "sourceCapsuleSourceDigest": None,
        "sourceCapsuleReadOnly": None,
        "executionRootRef": None,
        "cleanupStatus": "not_created",
        "approvedQuota": None,
        "qualifiedCount": None,
        "finalizedCount": None,
        "selectedCount": None,
        "discardedCount": None,
        "shortfallCount": None,
        "deliveryPendingCount": 0,
        "deliveryIntentRefs": [],
        "error": None,
    }
