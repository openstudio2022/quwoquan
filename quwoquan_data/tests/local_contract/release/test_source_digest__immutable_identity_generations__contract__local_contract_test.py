from __future__ import annotations

import shutil
import subprocess
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

    for forbidden in (
        "quwoquan_data/schema",
        "quwoquan_data/schema/_common",
        "quwoquan_data/schema/content",
        "quwoquan_data/schema/execution",
        "quwoquan_data/schema/source",
        "quwoquan_data/control_plane",
        "quwoquan_data/scripts/core",
        "quwoquan_data/scripts/verify",
    ):
        assert forbidden not in inputs
    assert all((DATA_SCRIPTS.parents[1] / item).is_file() for item in inputs)
    assert not any("recommendation-service" in item for item in inputs)
    assert not any(item.endswith("/ui_config.yaml") for item in inputs)
    assert not any("release_uat" in item or "/release/environment" in item for item in inputs)
    assert not any("import_report" in item or "readback" in item for item in inputs)
    assert (
        "quwoquan_service/services/content-service/contracts/media/media_asset/"
        "image_variant_policy.yaml"
    ) in inputs


def _materialize_source_definition_inputs(repo: Path) -> None:
    source_root = DATA_SCRIPTS.parents[1]
    for relative in SourceDefinitionSnapshot(CURRENT_DIGEST).to_document()["inputs"]:
        source = source_root / relative
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)


def test_source_definition_digest_ignores_consumer_paths_and_tracks_exact_inputs(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _materialize_source_definition_inputs(repo)
    baseline = SourceDefinitionSnapshot.build(repo_root=repo)

    consumer = repo / "quwoquan_data/scripts/content/release/environment/consumer.py"
    consumer.parent.mkdir(parents=True, exist_ok=True)
    consumer.write_text("CONSUMER = 'changed'\n", encoding="utf-8")
    assert SourceDefinitionSnapshot.build(repo_root=repo) == baseline

    exact = repo / SourceDefinitionSnapshot(CURRENT_DIGEST).to_document()["inputs"][0]
    exact.write_text(exact.read_text(encoding="utf-8") + "\nproducer-change\n", encoding="utf-8")
    assert SourceDefinitionSnapshot.build(repo_root=repo) != baseline
