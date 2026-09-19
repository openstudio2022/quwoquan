"""Candidate v4 no-owner contract tests."""
import json, subprocess
from pathlib import Path
import pytest
from quwoquan_ops.cli.lib.candidate_evidence import build_candidate_evidence, validate_candidate_path_set

ROOT = Path(__file__).resolve().parents[4]

def test_path_set_is_lossless_sorted_and_has_no_owner_fields() -> None:
    document = {"schema_version": 2, "changed_paths": ["a.txt", "z.txt"]}
    validate_candidate_path_set(document)
    encoded = json.dumps(document)
    for retired in ("owner_identity_ref", "resolved_owner", "owner_chain", "impacted_owner_groups"):
        assert retired not in encoded

def test_path_set_rejects_duplicate_or_unsorted_paths() -> None:
    with pytest.raises(ValueError): validate_candidate_path_set({"schema_version": 2, "changed_paths": ["z", "a"]})
    with pytest.raises(ValueError): validate_candidate_path_set({"schema_version": 2, "changed_paths": ["a", "a"]})

def test_candidate_builder_api_requires_only_actual_changed_paths() -> None:
    import inspect
    assert list(inspect.signature(build_candidate_evidence).parameters)[:1] == ["changed_paths"]
