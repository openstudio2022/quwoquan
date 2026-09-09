# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-040
import json
from pathlib import Path

import pytest

from core.publish_repository import (
    PublishRepositoryError, canonical_files, repository_sidecar_root,
    require_publish_repository,
)


def repository(root: Path):
    root.mkdir()
    (root / ".git").mkdir()
    document = {"schema": "quwoquan_data.publish_repository.v2", "repositoryId": "test-content", "layoutVersion": 2, "producerContractDigest": "sha256:" + "a" * 64}
    (root / "repository.json").write_text(json.dumps(document))
    return document


def test_root_is_explicit_and_identity_checked(tmp_path):
    root = tmp_path / "publish"
    expected = repository(root)
    assert require_publish_repository(root, expected_repository_id="test-content") == expected
    with pytest.raises(PublishRepositoryError, match="IDENTITY"):
        require_publish_repository(root, expected_repository_id="another")
    with pytest.raises(PublishRepositoryError, match="MISSING"):
        require_publish_repository(tmp_path / "absent")
    assert not (tmp_path / "absent").exists()


def test_repository_control_files_are_not_canonical_objects(tmp_path):
    root = tmp_path / "publish"
    repository(root)
    (root / ".git" / "config").write_text("git metadata")
    (root / ".gitignore").write_text("**/media/**")
    (root / "releases").mkdir()
    (root / "releases" / "cohort.json").write_text("{}")
    object_dir = root / "posts/article/导览/p0001/标题/1"
    object_dir.mkdir(parents=True)
    (object_dir / "manifest.json").write_text("{}")
    assert canonical_files(root) == (object_dir / "manifest.json",)


def test_unexpected_roots_and_symlinks_are_not_ignored(tmp_path):
    root = tmp_path / "publish"
    repository(root)
    (root / "scratch").mkdir()
    with pytest.raises(PublishRepositoryError, match="ROOT_ENTRY"):
        canonical_files(root)
    (root / "scratch").rmdir()
    (root / "entities").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(PublishRepositoryError, match="SYMLINK"):
        canonical_files(root)


def test_different_output_roots_contend_on_the_same_real_lock(tmp_path):
    import os
    import subprocess
    import sys
    from core.paths import REPO_DATA_ROOT
    from content.release.canonical.object_transaction_lock import canonical_publish_lock

    root = tmp_path / "publish"
    repository(root)
    code = """
import fcntl, sys
from pathlib import Path
from core.paths import publish_lock_path
lock = publish_lock_path(Path(sys.argv[1]))
with lock.open('a+') as stream:
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('blocked')
    else:
        print('acquired')
"""
    env = {**os.environ, "QWQ_OUTPUT_ROOT": str(tmp_path / "another-worktree/output"), "PYTHONPATH": str(REPO_DATA_ROOT / "scripts"), "PYTHONDONTWRITEBYTECODE": "1"}
    with canonical_publish_lock(root):
        result = subprocess.run([sys.executable, "-B", "-c", code, str(root)], env=env, text=True, capture_output=True, timeout=10, check=True)
        assert result.stdout.strip() == "blocked"
    result = subprocess.run([sys.executable, "-B", "-c", code, str(root)], env=env, text=True, capture_output=True, timeout=10, check=True)
    assert result.stdout.strip() == "acquired"


def test_all_worktrees_use_one_publish_fence(tmp_path, monkeypatch):
    from core import paths
    root = tmp_path / "publish"
    repository(root)
    expected = repository_sidecar_root(root)
    assert expected == root / ".git/qwq-publish"
    monkeypatch.setattr(paths, "CANONICAL_PUBLISH_SIDECAR_ROOT", tmp_path / "lane-one/cache")
    first = paths.canonical_publish_sidecar_root(root)
    monkeypatch.setattr(paths, "CANONICAL_PUBLISH_SIDECAR_ROOT", tmp_path / "lane-two/cache")
    assert first == paths.canonical_publish_sidecar_root(root) == expected
    assert not expected.exists()
    expected.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(PublishRepositoryError, match="SYMLINK"):
        repository_sidecar_root(root)
