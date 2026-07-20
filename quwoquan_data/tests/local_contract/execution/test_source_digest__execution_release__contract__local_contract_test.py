"""Execution and release evidence must bind only repository-owned inputs."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.source_digest import SourceDigest, SourceDigestError, current_source_digest  # noqa: E402


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
