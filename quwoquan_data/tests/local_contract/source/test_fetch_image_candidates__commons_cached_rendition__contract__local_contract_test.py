from __future__ import annotations

import sys
from pathlib import Path


DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.source.fetch_image_candidates import candidate_image_urls  # noqa: E402


def test_fetch_image_candidates_prefers_commons_cached_rendition():
    original = (
        "https://upload.wikimedia.org/wikipedia/commons/6/65/"
        "Mount_Emei_1.jpg"
    )

    candidates = candidate_image_urls(original)

    assert candidates[0] == (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/6/65/"
        "Mount_Emei_1.jpg/1280px-Mount_Emei_1.jpg"
    )
    assert candidates[1] == original
