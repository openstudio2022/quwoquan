"""Homepage author model must exactly match the active Grok Fast policy."""
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

from content.execution import recipe  # noqa: E402
from content.execution.model_contract import execution_model_pair  # noqa: E402
from core.runtime_policy import load_runtime_policy  # noqa: E402


def test_homepage_author_uses_the_runtime_grok_fast_selection() -> None:
    homepage = recipe.load_recipe("content/travel/homepage/homepage")
    models = execution_model_pair(homepage)
    runtime = load_runtime_policy(str(homepage["runtimeProfile"]))

    assert models.author.model_id == "grok-4.5"
    assert models.author.family.value == "grok"
    assert models.author.selection == runtime.cursor_model_selection
    assert models.author.selection.to_sdk_document() == {
        "id": "grok-4.5",
        "params": [
            {"id": "effort", "value": "high"},
            {"id": "fast", "value": "true"},
        ],
    }
    assert models.reviewer.model_id == "composer-2.5"
    assert models.reviewer.family != models.author.family
