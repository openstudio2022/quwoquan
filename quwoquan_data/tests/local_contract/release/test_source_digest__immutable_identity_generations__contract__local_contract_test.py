from __future__ import annotations

import sys
from pathlib import Path

import pytest

DATA_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(DATA_SCRIPTS))

from core.source_digest import (  # noqa: E402
    SourceDefinitionSnapshot,
    SourceDigest,
    SourceDigestError,
    parse_immutable_source_digest_document,
)

CURRENT_DIGEST = "sha256:" + "a" * 64
LEGACY_DIGEST = "sha256:" + "b" * 64


def test_current_source_definition_identity_is_parsed_from_frozen_evidence() -> None:
    """Release evidence frozen by the current contract must stay readable.

    Objects bind the source-definition and execution-bundle identities
    separately, so a release built from them names only the source-definition
    inputs.  Reading that evidence through the retired combined contract would
    reject every release the current producer can build.
    """

    document = SourceDefinitionSnapshot(CURRENT_DIGEST).to_document()

    parsed = parse_immutable_source_digest_document(document)

    assert isinstance(parsed, SourceDefinitionSnapshot)
    assert parsed.digest == CURRENT_DIGEST


def test_retired_combined_identity_remains_readable_as_terminal_evidence() -> None:
    document = SourceDigest(LEGACY_DIGEST).to_document()

    parsed = parse_immutable_source_digest_document(document)

    assert isinstance(parsed, SourceDigest)
    assert parsed.digest == LEGACY_DIGEST


def test_runtime_output_is_never_an_accepted_input_closure() -> None:
    document = SourceDefinitionSnapshot(CURRENT_DIGEST).to_document()
    document["inputs"] = [".qwq_output"]

    with pytest.raises(SourceDigestError):
        parse_immutable_source_digest_document(document)


def test_source_definition_inputs_are_producer_owned_and_exact() -> None:
    inputs = SourceDefinitionSnapshot(CURRENT_DIGEST).to_document()["inputs"]

    assert "quwoquan_data/schema" not in inputs
    assert not any("recommendation-service" in item for item in inputs)
    assert not any(item.endswith("/ui_config.yaml") for item in inputs)
    assert (
        "quwoquan_service/services/content-service/contracts/media/media_asset/"
        "image_variant_policy.yaml"
    ) in inputs
    assert all("/release/environment" not in item for item in inputs)
