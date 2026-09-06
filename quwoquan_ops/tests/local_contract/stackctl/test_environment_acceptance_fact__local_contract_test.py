# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-wave-deployment/spec.md#gwt-001
"""Canonical EnvironmentAcceptanceFact v2 single-track contract tests."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from quwoquan_ops.cli.lib import environment_acceptance_fact as subject
from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import SCHEMA, SCHEMA_PATH
from quwoquan_ops.cli.lib.environment_acceptance_fact_validator import (
    validate_environment_acceptance_fact as validate_v2,
)


def _schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_canonical_schema_is_v2_and_rejects_v1_shape() -> None:
    validator = _schema_validator()
    errors = list(
        validator.iter_errors(
            {
                "schema": "quwoquan_ops.environment_acceptance_fact.v1",
                "acceptanceProfile": "environment_promotion",
            }
        )
    )

    assert SCHEMA == "quwoquan_ops.environment_acceptance_fact.v2"
    assert errors


def test_validator_rejects_v1_and_unknown_dependency_kwargs() -> None:
    with pytest.raises(ValueError, match="EnvironmentAcceptanceFact v2"):
        validate_v2(
            {
                "schema": "quwoquan_ops.environment_acceptance_fact.v1",
                "acceptanceProfile": "environment_promotion",
            },
            verify_references=False,
        )
    with pytest.raises(TypeError, match="required_target_profiles"):
        validate_v2({}, verify_references=False, required_target_profiles=[])
    with pytest.raises(TypeError, match="evidence_root"):
        validate_v2({}, verify_references=False, evidence_root=Path("."))


def test_public_module_has_no_v1_builder_writer_or_predecessor_api() -> None:
    retired = {
        "build_environment_acceptance_fact",
        "create_environment_acceptance_fact",
        "derive_fact_id",
        "environment_acceptance_fact_relative_path",
        "validate_predecessor_acceptance",
        "write_environment_acceptance_fact",
    }
    assert retired.isdisjoint(vars(subject))
    assert set(subject.__all__) == {
        "ACCEPTANCE_PROFILES",
        "ENVIRONMENTS",
        "PREDECESSOR",
        "SCHEMA",
        "SCHEMA_PATH",
        "EnvironmentAcceptanceFactError",
        "canonical_fact_bytes",
        "exact_byte_digest",
        "load_environment_acceptance_fact",
        "validate_environment_acceptance_fact",
    }
    assert "evidence_root" not in inspect.signature(
        subject.load_environment_acceptance_fact
    ).parameters
