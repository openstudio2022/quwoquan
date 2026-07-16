"""Three-stage protocol enforcement with retry."""
from __future__ import annotations

from pathlib import Path
from typing import Callable


def check_stage_outputs(inputs_dir: Path, results_dir: Path, assistant_task: Path) -> list[str]:
    """Verify the three-stage protocol produced non-empty outputs."""
    errors = []
    if not assistant_task.exists():
        errors.append(f"assistant_task missing: {assistant_task}")
    if not inputs_dir.exists() or not any(inputs_dir.glob("*.json")):
        errors.append(f"inputs empty: {inputs_dir}")
    if not results_dir.exists() or not any(results_dir.glob("*.json")):
        errors.append(f"results empty: {results_dir}")
    return errors


def execute_with_retry(
    step_name: str,
    prepare_fn: Callable[[], None],
    validate_fn: Callable[[], list[str]],
    max_retries: int = 3,
) -> bool:
    """Execute prepare→validate loop with retries.

    Between prepare and validate, the Agent is expected to:
    1. Read assistant_tasks/{step}.json
    2. Process each input in inputs/{step}/
    3. Write results to results/{step}/

    Returns True if validation passes, False if blocked.
    """
    for attempt in range(1, max_retries + 1):
        prepare_fn()
        errors = validate_fn()
        if not errors:
            print(f"[{step_name}] PASS (attempt {attempt})")
            return True
        print(f"[{step_name}] attempt {attempt}/{max_retries} FAIL:")
        for e in errors:
            print(f"  - {e}")
    print(f"[{step_name}] BLOCKED after {max_retries} attempts. Awaiting human decision.")
    return False
