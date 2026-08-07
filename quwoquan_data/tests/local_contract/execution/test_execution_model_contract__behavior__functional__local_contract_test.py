"""Author/reviewer model contract must be explicit and independently runnable."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.execution.controller.execute import runner
from content.execution.model_contract import (
    execution_model_pair,
    semantic_execution_binding,
)
from core.io import read_json

AUTHOR_PARAMETERS: list[dict[str, str]] = []
AUTHOR_MODEL = "gpt-5.6-terra"
REVIEWER_MODEL = "gpt-5.6-terra"


def _recipe(*, reviewer_family: str = "gpt") -> dict:
    return {
        "runtimeProfile": "semantic_agent_local_calibrated",
        "execution": {
            "runtime": "local",
            "model": AUTHOR_MODEL,
            "modelFamily": "gpt",
            "modelParameters": AUTHOR_PARAMETERS,
            "reviewModel": REVIEWER_MODEL,
            "reviewModelFamily": reviewer_family,
            "reviewModelParameters": [],
        }
    }


def test_execution_model_contract__requires_explicit_model_families__local_contract() -> None:
    recipe = _recipe()
    recipe["execution"].pop("reviewModelFamily")

    with pytest.raises(ValueError, match="reviewModelFamily"):
        execution_model_pair(recipe)


def test_execution_model_contract__allows_independent_terra_same_family__local_contract() -> None:
    recipe = {
        "runtimeProfile": "semantic_agent_local_calibrated",
        "execution": {
            "model": "gpt-5.6-terra",
            "modelFamily": "gpt",
            "modelParameters": [],
            "reviewModel": "gpt-5.6-terra",
            "reviewModelFamily": "gpt",
            "reviewModelParameters": [],
        }
    }

    pair = execution_model_pair(recipe)

    assert pair.author.model_id == pair.reviewer.model_id == "gpt-5.6-terra"
    assert pair.author.family.value == pair.reviewer.family.value == "gpt"


def test_execution_model_contract__keeps_codex_terra_identity_explicit__local_contract() -> None:
    pair = execution_model_pair(_recipe())

    assert pair.author.model_id == AUTHOR_MODEL
    assert pair.author.family.value == "gpt"
    assert pair.author.selection.parameters_document() == AUTHOR_PARAMETERS
    assert pair.reviewer.model_id == REVIEWER_MODEL
    assert pair.reviewer.family.value == "gpt"
    assert pair.reviewer.selection.parameters_document() == []


def test_execution_model_contract__writes_schema_checked_runtime_evidence__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    execution_id = "20260713--travel-homepage-coverage--test-region-a--pilot-902"
    monkeypatch.setattr(runner, "execution_root", lambda _execution_id: tmp_path)
    report = {
        "ready": True,
        "semanticSelectionId": "default",
        "provider": "codex_sdk",
        "runtime": "local",
        "author": {
            "model": AUTHOR_MODEL,
            "modelFamily": "gpt",
            "modelParameters": AUTHOR_PARAMETERS,
            "startup": {
                "ready": True,
                "status": "finished",
                "errorClass": "",
                "errorCode": "",
                "httpStatus": None,
                "runtime": "local",
                "model": AUTHOR_MODEL,
                "modelParameters": AUTHOR_PARAMETERS,
                "cacheHit": False,
            },
        },
        "reviewer": {
            "model": REVIEWER_MODEL,
            "modelFamily": "gpt",
            "modelParameters": [],
            "startup": {
                "ready": True,
                "status": "finished",
                "errorClass": "",
                "errorCode": "",
                "httpStatus": None,
                "runtime": "local",
                "model": REVIEWER_MODEL,
                "modelParameters": [],
                "cacheHit": True,
            },
        },
    }

    runner.write_execution_model_readiness(execution_id, report)

    payload = read_json(tmp_path / "evidence/model_readiness.json")
    assert payload["author"]["modelParameters"] == AUTHOR_PARAMETERS
    assert payload["provider"] == "codex_sdk"
    assert payload["reviewer"]["modelFamily"] == "gpt"


def test_execution_model_contract__controller_requires_matching_durable_proof__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    execution_id = "20260713--travel-homepage-coverage--test-region-a--pilot-903"
    monkeypatch.setattr(runner, "execution_root", lambda _execution_id: tmp_path)
    report = {
        "ready": True,
        "semanticSelectionId": "default",
        "provider": "codex_sdk",
        "runtime": "local",
        "author": {
            "model": AUTHOR_MODEL,
            "modelFamily": "gpt",
            "modelParameters": AUTHOR_PARAMETERS,
            "startup": {
                "ready": True,
                "status": "finished",
                "errorClass": "",
                "errorCode": "",
                "httpStatus": None,
                "runtime": "local",
                "model": AUTHOR_MODEL,
                "modelParameters": AUTHOR_PARAMETERS,
                "cacheHit": False,
            },
        },
        "reviewer": {
            "model": REVIEWER_MODEL,
            "modelFamily": "gpt",
            "modelParameters": [],
            "startup": {
                "ready": True,
                "status": "finished",
                "errorClass": "",
                "errorCode": "",
                "httpStatus": None,
                "runtime": "local",
                "model": REVIEWER_MODEL,
                "modelParameters": [],
                "cacheHit": False,
            },
        },
    }
    monkeypatch.setattr(
        runner,
        "semantic_execution_binding_for_execution",
        lambda _execution_id: semantic_execution_binding(_recipe(), "default"),
    )
    runner.write_execution_model_readiness(execution_id, report)

    runner.require_execution_model_readiness(execution_id, _recipe())

    report["author"]["model"] = "other-model"
    runner.write_execution_model_readiness(execution_id, report)
    with pytest.raises(RuntimeError, match="does not match"):
        runner.require_execution_model_readiness(execution_id, _recipe())
