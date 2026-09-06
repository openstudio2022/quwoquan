"""The retired M1 profile must not remain an EnvironmentAcceptanceFact API."""

from __future__ import annotations

import inspect

import pytest

from quwoquan_ops.cli.lib import environment_acceptance_fact as subject
from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import ACCEPTANCE_PROFILES


def test_m1_profile_and_v1_builder_are_absent_after_v2_cutover() -> None:
    assert "m1_api_consumer" not in ACCEPTANCE_PROFILES
    assert "environment_promotion" not in ACCEPTANCE_PROFILES
    assert not hasattr(subject, "build_environment_acceptance_fact")
    with pytest.raises(TypeError, match="required_target_profiles"):
        subject.validate_environment_acceptance_fact(
            {}, verify_references=False, required_target_profiles=[]
        )


def test_content_identity_helpers_are_absent_from_entire_eaf_module() -> None:
    assert "required_raw_slot_id" not in vars(subject)
    assert "derive_m1_source_fingerprint" not in vars(subject)
    assert "content_consumer_raw_slot_id" not in vars(subject)
    assert "derive_content_consumer_source_fingerprint" not in vars(subject)
    assert "acceptance_profile" not in inspect.signature(
        subject.validate_environment_acceptance_fact
    ).parameters
