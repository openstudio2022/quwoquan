from __future__ import annotations

import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core import paths  # noqa: E402
from core.object_storage import FilesystemObjectStorage, storage_from_env  # noqa: E402


def test_filesystem_object_storage_defaults_to_data_objects(tmp_path, monkeypatch):
    monkeypatch.delenv("QWQ_OBJECT_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("QWQ_OBJECT_STORAGE_ROOT", raising=False)
    monkeypatch.setattr(paths, "OUTPUT_ROOT", tmp_path / ".qwq_output")

    storage = storage_from_env()

    assert isinstance(storage, FilesystemObjectStorage)
    assert storage.root == (tmp_path / ".qwq_output/data/objects").resolve()
    assert not (tmp_path / ".qwq_output/object_store").exists()
