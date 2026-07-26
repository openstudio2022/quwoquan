"""The source digest gate rejects execution drift and release receipt drift."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.source_digest import current_source_digest  # noqa: E402
from verify.verify_source_digest import source_digest_issues  # noqa: E402


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_source_digest_gate__execution_release__contract__local_contract(tmp_path: Path) -> None:
    digest = current_source_digest().to_document()
    _write(
        tmp_path / "tasks/example/execution_manifest.json",
        {"sourceDigest": digest},
    )
    _write(
        tmp_path / "releases/example/payload/release.json",
        {"sourceDigests": [digest]},
    )
    _write(
        tmp_path / "releases/example/attestations/release.json",
        {"sourceDigests": [digest]},
    )

    assert source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
    ) == []


def test_source_digest_gate__rejects_release_receipt_drift__contract__local_contract(
    tmp_path: Path,
) -> None:
    digest = current_source_digest().to_document()
    changed = dict(digest)
    changed["digest"] = "sha256:" + "0" * 64
    _write(
        tmp_path / "releases/example/payload/release.json",
        {"sourceDigests": [digest]},
    )
    aggregate = tmp_path / "releases/example/attestations/release.json"
    _write(aggregate, {"sourceDigests": [changed]})

    assert source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
    ) == [f"{aggregate}: sourceDigests drift from release header"]
