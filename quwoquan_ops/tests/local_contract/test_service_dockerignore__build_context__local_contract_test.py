"""Keep rebuildable service artifacts out of service image contexts."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SERVICE_DOCKERIGNORE = ROOT / "quwoquan_service" / ".dockerignore"


def test_service_dockerignore_excludes_rebuildable_root_artifacts() -> None:
    ignored = SERVICE_DOCKERIGNORE.read_text(encoding="utf-8").splitlines()

    for path in (
        ".qwq_output/",
        "/api",
        "/import",
        "/generated/contract_graph.json",
        "contracts/metadata/_shared/test_fixtures/media/",
        "contracts/metadata/_shared/test_fixtures/original_media/",
    ):
        assert path in ignored
