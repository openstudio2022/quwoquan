from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from content.execution.controller import publish as subject
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from core.io import write_json


def test_controller_checks_video_identity_before_reliable_publish_job_plan() -> None:
    source = inspect.getsource(subject._run_publish)

    assert source.index("_assert_video_canonical_plan") < source.index(
        "prepare_reliable_publish_jobs"
    )


def test_video_publish_plan_rejects_canonical_exact_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_id = "20260810--travel-video-exact-plan--test--scale-001"
    execution = tmp_path / execution_id
    publish_ref = "posts/video/体验/待发布视频/1"
    manifest = {
        "contentType": "video",
        "executionId": execution_id,
        "assets": [],
    }
    write_json(execution / publish_ref / "manifest.json", manifest)
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "content.execution.workspace.execution_root",
        lambda _execution_id: execution,
    )
    monkeypatch.setattr("core.paths.PUBLISH_ROOT", tmp_path / "publish")

    def reject(**kwargs: object) -> None:
        calls.append(dict(kwargs))
        raise ObjectTransactionError(
            "canonical video identity duplicated by content sha256"
        )

    monkeypatch.setattr(
        "content.release.canonical.canonical_inventory.assert_canonical_video_unique",
        reject,
    )

    with pytest.raises(ObjectTransactionError, match="content sha256"):
        subject._assert_video_canonical_plan(execution_id, {publish_ref})

    assert calls == [
        {
            "publish_root": tmp_path / "publish",
            "manifest": manifest,
            "excluded_manifest_path": f"{publish_ref}/manifest.json",
        }
    ]
