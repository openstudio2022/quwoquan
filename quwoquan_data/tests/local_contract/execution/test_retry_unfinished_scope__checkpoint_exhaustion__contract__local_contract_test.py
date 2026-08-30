from __future__ import annotations

import json
from pathlib import Path

from content.execution.planning.retry_unfinished_scope import _exhausted_author_refs


def _write(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def test_exhausted_author_ref_can_bind_checkpoint_by_invocation_attempt(
    tmp_path: Path,
) -> None:
    execution_id = "20260812--travel-image-m100--china--scale-001"
    task_root = tmp_path / execution_id
    journal = task_root / "_shared/semantic_tasks/work-unit"
    _write(
        journal / "request.json",
        {
            "executionId": execution_id,
            "stage": "author",
            "maxAttempts": 2,
        },
    )
    state = {"agentRunHistory": []}
    for attempt in (1, 2):
        digest = f"sha256:{attempt:064d}"
        run_id = f"run-{attempt}"
        _write(
            journal / f"attempts/{attempt:04d}.json",
            {
                "runId": run_id,
                "attemptDigest": digest,
                "status": "finished",
            },
        )
        state["agentRunHistory"].append(
            {
                "outcomes": [
                    {
                        "ref": "乌镇_image",
                        "runId": None,
                        "invocationAttemptDigest": digest,
                        "failureKind": "checkpoint_gate",
                    }
                ]
            }
        )

    assert _exhausted_author_refs(
        task_root,
        execution_id=execution_id,
        state=state,
    ) == {"乌镇_image"}
