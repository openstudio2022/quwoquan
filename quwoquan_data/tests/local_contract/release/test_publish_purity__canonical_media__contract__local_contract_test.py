from __future__ import annotations

import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from verify.verify_publish_purity import publish_purity_issues  # noqa: E402


def test_publish_media_only_accepts_content_addressed_objects(tmp_path: Path):
    (tmp_path / "media" / "objects" / "sha256").mkdir(parents=True)
    assert publish_purity_issues(tmp_path) == []

    retired = tmp_path / "media" / "profile_presets"
    retired.mkdir()
    issues = publish_purity_issues(tmp_path)
    assert any("content-addressed objects" in issue for issue in issues)
