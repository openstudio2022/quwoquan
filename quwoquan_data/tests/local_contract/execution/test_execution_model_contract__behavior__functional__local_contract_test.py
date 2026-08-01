"""Author/reviewer model contract must be explicit and independently runnable."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.execution import runner
from content.execution.model_contract import execution_model_pair
from core.io import read_json


AUTHOR_PARAMETERS = [
    {"id": "effort", "value": "high"},
    {"id": "fast", "value": "false"},
]


def _recipe(*, reviewer_family: str = "composer") -> dict:
    return {
        "execution": {
            "runtime": "local",
            "model": "grok-4.5",
            "modelFamily": "grok",
            "modelParameters": AUTHOR_PARAMETERS,
            "reviewModel": "composer-2.5",
            "reviewModelFamily": reviewer_family,
            "reviewModelParameters": [],
        }
    }


def test_execution_model_contract__requires_explicit_model_families__local_contract() -> None:
    recipe = _recipe()
    recipe["execution"].pop("reviewModelFamily")

    with pytest.raises(ValueError, match="reviewModelFamily"):
        execution_model_pair(recipe)


def test_execution_model_contract__allows_provider_routed_same_family__local_contract() -> None:
    recipe = {
        "execution": {
            "model": "auto",
            "modelFamily": "auto",
            "modelParameters": [],
            "reviewModel": "auto",
            "reviewModelFamily": "auto",
            "reviewModelParameters": [],
        }
    }

    pair = execution_model_pair(recipe)

    assert pair.author.model_id == pair.reviewer.model_id == "auto"
    assert pair.author.family.value == pair.reviewer.family.value == "auto"


def test_execution_model_contract__keeps_model_and_family_separate__local_contract() -> None:
    pair = execution_model_pair(_recipe())

    assert pair.author.model_id == "grok-4.5"
    assert pair.author.family.value == "grok"
    assert pair.author.selection.parameters_document() == AUTHOR_PARAMETERS
    assert pair.reviewer.model_id == "composer-2.5"
    assert pair.reviewer.family.value == "composer"
    assert pair.reviewer.selection.parameters_document() == []


def test_execution_model_contract__writes_schema_checked_runtime_evidence__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    execution_id = "20260713--travel-homepage-coverage--test-region-a--pilot-902"
    monkeypatch.setattr(runner, "execution_root", lambda _execution_id: tmp_path)
    report = {
        "ready": True,
        "runtime": "local",
        "author": {
            "model": "grok-4.5",
            "modelFamily": "grok",
            "modelParameters": AUTHOR_PARAMETERS,
            "startup": {
                "ready": True,
                "status": "finished",
                "errorClass": "",
                "errorCode": "",
                "httpStatus": None,
                "runtime": "local",
                "model": "grok-4.5",
                "modelParameters": AUTHOR_PARAMETERS,
                "cacheHit": False,
            },
        },
        "reviewer": {
            "model": "composer-2.5",
            "modelFamily": "composer",
            "modelParameters": [],
            "startup": {
                "ready": True,
                "status": "finished",
                "errorClass": "",
                "errorCode": "",
                "httpStatus": None,
                "runtime": "local",
                "model": "composer-2.5",
                "modelParameters": [],
                "cacheHit": True,
            },
        },
    }

    runner.write_execution_model_readiness(execution_id, report)

    payload = read_json(tmp_path / "evidence/model_readiness.json")
    assert payload["author"]["modelParameters"] == AUTHOR_PARAMETERS
    assert payload["reviewer"]["modelFamily"] == "composer"


def test_execution_model_contract__controller_requires_matching_durable_proof__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    execution_id = "20260713--travel-homepage-coverage--test-region-a--pilot-903"
    monkeypatch.setattr(runner, "execution_root", lambda _execution_id: tmp_path)
    report = {
        "ready": True,
        "runtime": "local",
        "author": {
            "model": "grok-4.5",
            "modelFamily": "grok",
            "modelParameters": AUTHOR_PARAMETERS,
            "startup": {
                "ready": True,
                "status": "finished",
                "errorClass": "",
                "errorCode": "",
                "httpStatus": None,
                "runtime": "local",
                "model": "grok-4.5",
                "modelParameters": AUTHOR_PARAMETERS,
                "cacheHit": False,
            },
        },
        "reviewer": {
            "model": "composer-2.5",
            "modelFamily": "composer",
            "modelParameters": [],
            "startup": {
                "ready": True,
                "status": "finished",
                "errorClass": "",
                "errorCode": "",
                "httpStatus": None,
                "runtime": "local",
                "model": "composer-2.5",
                "modelParameters": [],
                "cacheHit": False,
            },
        },
    }
    runner.write_execution_model_readiness(execution_id, report)

    runner.require_execution_model_readiness(execution_id, _recipe())

    report["author"]["model"] = "other-model"
    runner.write_execution_model_readiness(execution_id, report)
    with pytest.raises(RuntimeError, match="does not match"):
        runner.require_execution_model_readiness(execution_id, _recipe())
