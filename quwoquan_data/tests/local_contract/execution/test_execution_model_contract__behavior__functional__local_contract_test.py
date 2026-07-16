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


def _recipe(*, reviewer_family: str = "gpt") -> dict:
    return {
        "execution": {
            "runtime": "local",
            "model": "composer",
            "modelFamily": "composer",
            "reviewModel": "gpt-5.5",
            "reviewModelFamily": reviewer_family,
        }
    }


def test_execution_model_contract__requires_explicit_model_families__local_contract() -> None:
    recipe = _recipe()
    recipe["execution"].pop("reviewModelFamily")

    with pytest.raises(ValueError, match="reviewModelFamily"):
        execution_model_pair(recipe)


def test_execution_model_contract__rejects_same_family_reviewer__local_contract() -> None:
    with pytest.raises(ValueError, match="must differ"):
        execution_model_pair(_recipe(reviewer_family="composer"))


def test_execution_model_contract__keeps_model_and_family_separate__local_contract() -> None:
    pair = execution_model_pair(_recipe())

    assert pair.author.model_id == "composer"
    assert pair.author.family.value == "composer"
    assert pair.reviewer.model_id == "gpt-5.5"
    assert pair.reviewer.family.value == "gpt"


def test_execution_model_contract__writes_schema_checked_runtime_evidence__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    execution_id = "20260713--travel-homepage-coverage--cn-zhejiang--canary-902"
    monkeypatch.setattr(runner, "execution_root", lambda _execution_id: tmp_path)
    report = {
        "contractVersion": "execution-model-readiness-v1",
        "ready": True,
        "runtime": "local",
        "author": {
            "model": "composer",
            "modelFamily": "composer",
            "startup": {
                "ready": True,
                "status": "finished",
                "errorClass": "",
                "errorCode": "",
                "httpStatus": None,
                "runtime": "local",
                "model": "composer",
                "cacheHit": False,
            },
        },
        "reviewer": {
            "model": "gpt-5.5",
            "modelFamily": "gpt",
            "startup": {
                "ready": True,
                "status": "finished",
                "errorClass": "",
                "errorCode": "",
                "httpStatus": None,
                "runtime": "local",
                "model": "gpt-5.5",
                "cacheHit": True,
            },
        },
    }

    runner.write_execution_model_readiness(execution_id, report)

    payload = read_json(tmp_path / "evidence/model_readiness.json")
    assert payload["reviewer"]["modelFamily"] == "gpt"
