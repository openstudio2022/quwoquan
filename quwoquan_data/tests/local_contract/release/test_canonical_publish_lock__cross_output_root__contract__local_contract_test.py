"""Every detached lane publishing to one canonical root shares one fence."""
from __future__ import annotations

import tempfile
from pathlib import Path

from core import paths


def test_publish_lock_identity_does_not_follow_execution_output_root(
    monkeypatch,
    tmp_path,
) -> None:
    publish_root = tmp_path / "canonical-publish"
    monkeypatch.setattr(paths, "PUBLISH_ROOT", publish_root)
    monkeypatch.setattr(paths, "OUTPUT_ROOT", tmp_path / "lane-homepage")
    homepage_lock = paths.publish_lock_path()
    monkeypatch.setattr(paths, "OUTPUT_ROOT", tmp_path / "lane-video")
    video_lock = paths.publish_lock_path()

    assert homepage_lock == video_lock
    assert homepage_lock.parent == Path(tempfile.gettempdir())
    assert not str(homepage_lock).startswith(str(publish_root))
