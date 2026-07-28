"""Execution and release evidence must bind only repository-owned inputs."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.source_digest import (  # noqa: E402
    SourceDigest,
    SourceDigestError,
    _iter_files,
    current_source_digest,
)
from content.execution import workspace  # noqa: E402
from support.execution_manifest_fixture import ExecutionFixtureBuilder  # noqa: E402


def test_source_digest__execution_release__contract__local_contract() -> None:
    document = current_source_digest().to_document()

    assert SourceDigest.from_document(document).to_document() == document
    assert ".qwq_output" not in document["inputs"]
    assert "quwoquan_data/control_plane" in document["inputs"]
    assert "quwoquan_data/verticals/travel" in document["inputs"]
    assert not any(input_path.startswith("quwoquan_ops/") for input_path in document["inputs"])


def test_source_digest__rejects_runtime_output_as_input__contract__local_contract() -> None:
    document = current_source_digest().to_document()
    document["inputs"] = [".qwq_output"]

    try:
        SourceDigest.from_document(document)
    except SourceDigestError as exc:
        assert "fixed repository inputs" in str(exc)
    else:
        raise AssertionError("runtime output must never become a source digest input")


def test_source_digest__ignores_empty_directory_markers__contract__local_contract(
    tmp_path: Path,
) -> None:
    (tmp_path / ".gitkeep").touch()
    source = tmp_path / "policy.yaml"
    source.write_text("enabled: true\n", encoding="utf-8")

    assert _iter_files(tmp_path) == (source,)


def test_source_digest__execution_manifest_drift_has_a_stable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_id = "20260727--travel-homepage-coverage--test-region-a--pilot-001"
    ExecutionFixtureBuilder(execution_id).build()
    monkeypatch.setattr(
        workspace,
        "current_source_digest",
        lambda: SourceDigest("sha256:" + "0" * 64),
    )

    with pytest.raises(workspace.ExecutionSourceDigestDriftError, match="sourceDigest drift"):
        workspace.load_execution_manifest(execution_id)

    frozen = workspace.load_frozen_execution_manifest(execution_id)
    assert frozen["executionId"] == execution_id
