"""Homepage roles preserve governed Codex Terra provenance."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution.planning.recipe import model as recipe
from content.execution.model_contract import (
    execution_model_pair,
    semantic_execution_binding,
)
from core.runtime_policy import load_runtime_policy


def test_homepage_terra_roles_use_runtime_selection() -> None:
    homepage = recipe.load_recipe("content/travel/homepage/homepage")
    models = execution_model_pair(homepage)
    runtime = load_runtime_policy(str(homepage["runtimeProfile"]))

    assert models.author.model_id == "gpt-5.6-terra"
    assert models.author.family.value == "gpt"
    assert models.author.provider.value == "codex_sdk"
    assert models.author.selection == runtime.semantic_author.selection
    assert models.author.selection.to_sdk_document() == {
        "id": "gpt-5.6-terra",
        "params": [],
    }
    assert models.reviewer.model_id == "gpt-5.6-terra"
    assert models.reviewer.family.value == "gpt"
    assert models.reviewer.provider.value == "codex_sdk"
    assert models.reviewer.selection == runtime.semantic_reviewer.selection


def test_homepage_cursor_auto_is_explicit_and_does_not_replace_sol_calibration() -> None:
    homepage = recipe.load_recipe("content/travel/homepage/homepage")
    binding = semantic_execution_binding(homepage, "cursor_auto")
    runtime = load_runtime_policy(str(homepage["runtimeProfile"]))

    assert binding.selection_id == "cursor_auto"
    assert binding.runtime.value == "local"
    assert binding.pair.author.provider.value == "cursor_sdk"
    assert binding.pair.author.model_id == "auto"
    assert binding.pair.reviewer.provider.value == "cursor_sdk"
    assert binding.pair.reviewer.model_id == "auto"
    assert runtime.semantic_calibration.binding.provider.value == "codex_sdk"
    assert runtime.semantic_calibration.binding.model == "gpt-5.6-sol"
