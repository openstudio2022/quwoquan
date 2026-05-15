"""Tests for produce prepare and validate."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import os
os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

from _common.paths import ensure_batch_layout, batch_command_root
from _common.io import write_json
from produce.gate import gate_produce


def test_gate_produce_fails_without_posts():
    task_id = "test_produce_001"
    batch_id = "batch_001"
    ensure_batch_layout(task_id, batch_id)

    issues = gate_produce(task_id, batch_id, "article")
    assert len(issues) >= 1


def test_gate_produce_passes_with_valid_post():
    task_id = "test_produce_002"
    batch_id = "batch_001"
    ensure_batch_layout(task_id, batch_id)

    posts_dir = batch_command_root(task_id, batch_id, "produce") / "posts" / "article" / "topic_001"
    posts_dir.mkdir(parents=True)
    (posts_dir / "article.md").write_text("# Test Article\n\nContent here...", encoding="utf-8")
    write_json(posts_dir / "manifest.json", {
        "topicId": "topic_001",
        "contentType": "article",
        "entityRefs": ["ent_001"],
        "tagRefs": ["tag_001", "tag_002"],
        "reviewDecision": "approved",
    })

    issues = gate_produce(task_id, batch_id, "article")
    assert issues == []
