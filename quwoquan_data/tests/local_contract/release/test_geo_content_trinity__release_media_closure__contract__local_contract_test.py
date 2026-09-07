# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md#gwt-001
"""Legacy checked-in publish data must not bypass the current media gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
PUBLISH = ROOT / "quwoquan_data" / "publish"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import content.release.canonical.aggregate_release as aggregate_release
from content.release.canonical.rehydrate_media_holdings import (
    main as admit_carried_media_holdings,
)
from core import content_library

ENTITY_CATALOG_DIGEST = "sha256:" + "e" * 64


@pytest.fixture(autouse=True)
def _carried_media_holdings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rebuild the durable carried holdings in this test's private library.

    Pytest deliberately redirects the writable carried-media root away from the
    real one, while this real-tree test needs the real carried bytes as input.
    Point reads at the machine's out-of-repo carried root and admissions at a
    temporary CAS so the result cannot mutate a developer's content library.
    Skip when the carried root has not been provisioned on this machine.
    """

    from core import paths as _paths

    carried_root = _paths.default_carried_media_root()
    if not carried_root.is_dir() or not any(carried_root.iterdir()):
        pytest.skip(f"carried media root not provisioned: {carried_root}")
    monkeypatch.setenv("QWQ_CARRIED_MEDIA_ROOT", str(carried_root))
    monkeypatch.setitem(
        content_library.LIBRARY_CAS_ROOT_BY_KIND,
        content_library.MEDIA_KIND,
        tmp_path / "content-library" / "_media_cas",
    )
    assert admit_carried_media_holdings(publish_root=PUBLISH) == 0


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def _manifest_paths(kind: str) -> list[Path]:
    return sorted((PUBLISH / kind).rglob("manifest.json"))


def test_legacy_execution_selected_builder_is_physically_absent() -> None:
    assert not hasattr(aggregate_release, "build_aggregate_release")
    source = Path(aggregate_release.__file__).read_text(encoding="utf-8")
    assert "target_environment" not in source
