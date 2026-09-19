from __future__ import annotations
import json
from pathlib import Path

def make_publish_repository(root: Path, repository_id: str = "test-content") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    (root / "repository.json").write_text(json.dumps({
        "schema": "quwoquan_data.publish_repository.v2",
        "repositoryId": repository_id,
        "layoutVersion": 2,
    }) + "\n", encoding="utf-8")
    return root
