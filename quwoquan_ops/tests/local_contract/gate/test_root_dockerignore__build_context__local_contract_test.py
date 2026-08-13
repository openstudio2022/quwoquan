"""Keep local runtime outputs and fixture media out of production build contexts."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_root_dockerignore_excludes_rebuildable_outputs_and_fixture_media() -> None:
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert ".qwq_output/" in ignored
    assert (
        "quwoquan_service/contracts/metadata/_shared/test_fixtures/media/" in ignored
    )
    assert (
        "quwoquan_service/contracts/metadata/_shared/test_fixtures/original_media/"
        in ignored
    )
