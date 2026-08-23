# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-001.t4
from __future__ import annotations

from pathlib import Path

from content.execution.campaign.carrier_execution_policy import (
    carrier_execution_policy,
    carrier_policy_digest,
    load_carrier_execution_policy,
)
from core.schema import load_schema
from jsonschema.validators import Draft202012Validator


def test_carrier_execution_policy_is_closed_and_all_new_schemas_resolve() -> None:
    policy = load_carrier_execution_policy()

    assert tuple(policy["carriers"]) == ("homepage", "article", "image", "video")
    assert carrier_execution_policy("homepage")["operation"] == "homepage.generate"
    assert carrier_execution_policy("video")["defaultSelector"] == "source-ready-priority"
    assert carrier_policy_digest().startswith("sha256:")
    for schema_name in (
        "carrier_execution_policy",
        "work_request",
        "work_request_compile_receipt",
        "work_request_compile_result",
    ):
        schema = load_schema("execution", schema_name)
        Draft202012Validator.check_schema(schema)


def test_request_and_submission_consumers_have_no_retired_mapping_or_batch_writer() -> None:
    root = Path(__file__).resolve().parents[4]
    consumers = (
        root / "quwoquan_data/scripts/content/execution/campaign/request_envelope.py",
        root / "quwoquan_data/scripts/content/execution/campaign/request_envelope_build.py",
        root / "quwoquan_data/scripts/content/execution/campaign/request_envelope_writer.py",
        root / "quwoquan_data/scripts/content/execution/campaign/submission.py",
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in consumers)

    assert "_OPERATIONS =" not in text
    assert "_SELECTORS =" not in text
    assert "_OPERATOR_PROMPTS =" not in text
    assert "def write_campaign_envelopes" not in text
    assert "carrier_execution_policy" in text
