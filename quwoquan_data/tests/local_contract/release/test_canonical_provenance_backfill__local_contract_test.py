"""Contract coverage for the fail-closed legacy canonical provenance repair."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.provenance_backfill import (  # noqa: E402
    CanonicalProvenanceBackfillError,
    backfill_canonical_source_digests,
)
from core.source_digest import current_source_digest  # noqa: E402


EXECUTION_ID = "20260719--travel-homepage-coverage--cn-zhejiang--canary-001"


def _git(repo_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repo_root), *arguments),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.decode("utf-8").strip()


def _init_repo(tmp_path: Path) -> tuple[Path, Path, str]:
    repo_root = tmp_path / "repo"
    for relative in (
        "quwoquan_data/scripts",
        "quwoquan_data/schema",
        "quwoquan_data/control_plane",
        "quwoquan_data/prompts",
        "quwoquan_data/templates",
        "quwoquan_data/verticals/travel",
    ):
        root = repo_root / relative
        root.mkdir(parents=True, exist_ok=True)
        (root / "input.txt").write_text(relative, encoding="utf-8")
    (repo_root / "quwoquan_data/requirements.txt").write_text(
        "jsonschema\n",
        encoding="utf-8",
    )
    manifest_path = (
        repo_root
        / "quwoquan_data/publish/entities/地点/景区/普陀山/manifest.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "quwoquan_data.entity_object",
                "executionId": EXECUTION_ID,
                "finalContentRef": "page.md",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _git(repo_root, "init")
    _git(repo_root, "add", ".")
    _git(
        repo_root,
        "-c",
        "user.name=contract-test",
        "-c",
        "user.email=contract-test@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    return repo_root, manifest_path, _git(repo_root, "rev-parse", "HEAD")


def test_backfill_canonical_source_digest__uses_exact_git_inputs_and_is_idempotent(
    tmp_path: Path,
) -> None:
    repo_root, manifest_path, revision = _init_repo(tmp_path)
    publish_root = repo_root / "quwoquan_data/publish"

    first = backfill_canonical_source_digests(
        publish_root=publish_root,
        source_revision=revision,
        execution_ids=[EXECUTION_ID],
        repo_root=repo_root,
    )

    expected = current_source_digest(repo_root=repo_root).to_document()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert first["updatedCount"] == 1
    assert first["idempotentCount"] == 0
    assert manifest["sourceDigest"] == expected

    second = backfill_canonical_source_digests(
        publish_root=publish_root,
        source_revision=revision,
        execution_ids=[EXECUTION_ID],
        repo_root=repo_root,
    )

    assert second["updatedCount"] == 0
    assert second["idempotentCount"] == 1


def test_backfill_canonical_source_digest__rejects_manifest_drift(
    tmp_path: Path,
) -> None:
    repo_root, manifest_path, revision = _init_repo(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["finalContentRef"] = "tampered.md"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(CanonicalProvenanceBackfillError, match="已偏离"):
        backfill_canonical_source_digests(
            publish_root=repo_root / "quwoquan_data/publish",
            source_revision=revision,
            execution_ids=[EXECUTION_ID],
            repo_root=repo_root,
        )
