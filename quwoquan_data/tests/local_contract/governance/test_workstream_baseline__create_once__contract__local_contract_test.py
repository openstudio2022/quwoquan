from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from core.source_digest import SourceDigest
from core.schema import assert_valid
from governance import workstream_baseline


SOURCE_DIGEST = "sha256:" + "1" * 64
CATALOG_DIGEST = "sha256:" + "2" * 64
SOURCE_REVISION = "sha256:" + "3" * 64


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _repository(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    source = repo / "quwoquan_data" / "input.txt"
    evidence = repo / ".qwq_output" / "data" / "tasks" / "old" / "receipt.json"
    source.parent.mkdir(parents=True)
    evidence.parent.mkdir(parents=True)
    source.write_text("before\n", encoding="utf-8")
    evidence.write_text('{"status":"interrupted"}\n', encoding="utf-8")
    _git(repo, "init", "-b", "dev1.0")
    _git(repo, "config", "user.email", "data@example.invalid")
    _git(repo, "config", "user.name", "Data Contract")
    _git(repo, "add", "quwoquan_data/input.txt")
    _git(repo, "commit", "-m", "baseline")
    source.write_text("after\n", encoding="utf-8")
    plan = tmp_path / "cursor.plan.md"
    plan.write_text(
        "todos:\n"
        "  - id: p0-one\n"
        "    status: pending\n"
        "  - id: p0-two\n"
        "    status: pending\n",
        encoding="utf-8",
    )
    return repo, evidence, plan


def _freeze_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workstream_baseline,
        "current_source_digest",
        lambda **_kwargs: SourceDigest(SOURCE_DIGEST),
    )
    monkeypatch.setattr(
        workstream_baseline,
        "entity_catalog_digest",
        lambda _ref: CATALOG_DIGEST,
    )
    monkeypatch.setattr(
        workstream_baseline,
        "content_source_revision",
        lambda **_kwargs: SOURCE_REVISION,
    )
    monkeypatch.setattr(workstream_baseline, "assert_valid", lambda *_args, **_kwargs: None)


def test_workstream_baseline_freezes_ownership_and_protected_evidence_create_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, evidence, plan = _repository(tmp_path)
    _freeze_identity(monkeypatch)

    payload, destination = workstream_baseline.create_data_workstream_baseline(
        entity_catalog_ref="quwoquan_data/catalog",
        cursor_plan_path=plan,
        protected_paths=[evidence],
        owner_rules=["quwoquan_data=integration-owner"],
        scopes=["quwoquan_data"],
        repo_root=repo,
        output_root=tmp_path / "receipts",
    )

    assert destination.is_file()
    assert payload["sourceDigest"] == SOURCE_DIGEST
    assert payload["entityCatalogDigest"] == CATALOG_DIGEST
    assert payload["sourceRevision"] == SOURCE_REVISION
    assert payload["cursorPlan"]["taskCount"] == 2
    assert payload["cursorPlan"]["pendingTaskCount"] == 2
    assert payload["runtimeFreeze"] == {
        "campaignAllowed": False,
        "releaseAllowed": False,
        "stackctlAllowed": False,
        "reason": "WAIT_CONTENT/GATE_BLOCK",
    }
    assert_valid(
        payload,
        "governance",
        "data_workstream_baseline",
        label="workstream baseline",
    )
    assert payload["worktreeEntries"] == [
        {
            "path": "quwoquan_data/input.txt",
            "status": " M",
            "fileSha256": payload["worktreeEntries"][0]["fileSha256"],
            "owner": "integration-owner",
        }
    ]

    recorded = json.loads(destination.read_text(encoding="utf-8"))
    _, replay_destination = workstream_baseline.create_data_workstream_baseline(
        entity_catalog_ref="quwoquan_data/catalog",
        cursor_plan_path=plan,
        protected_paths=[evidence],
        owner_rules=["quwoquan_data=integration-owner"],
        scopes=["quwoquan_data"],
        repo_root=repo,
        output_root=tmp_path / "receipts",
    )
    assert replay_destination == destination
    assert json.loads(destination.read_text(encoding="utf-8")) == recorded


def test_workstream_baseline_rejects_dirty_path_without_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, evidence, plan = _repository(tmp_path)
    _freeze_identity(monkeypatch)

    with pytest.raises(
        workstream_baseline.WorkstreamBaselineError,
        match="no owner rule",
    ):
        workstream_baseline.create_data_workstream_baseline(
            entity_catalog_ref="quwoquan_data/catalog",
            cursor_plan_path=plan,
            protected_paths=[evidence],
            owner_rules=["specs=integration-owner"],
            scopes=["quwoquan_data"],
            repo_root=repo,
            output_root=tmp_path / "receipts",
        )
