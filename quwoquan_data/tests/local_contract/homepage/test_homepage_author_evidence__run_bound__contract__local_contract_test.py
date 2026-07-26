"""Homepage author controller evidence is bound to the real output file."""
from __future__ import annotations

from types import SimpleNamespace
import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.execution.controller.homepage_author_evidence import _write_homepage_author_evidence  # noqa: E402
from content.execution.agent.outcome import AgentRunOutcome  # noqa: E402
from content.execution.queue.core import stable_job_id  # noqa: E402
from content.execution.production_contracts import sha256_file, sha256_text, validate_agent_result_envelope  # noqa: E402
from core.io import read_json, write_json  # noqa: E402
from core.schema import assert_valid  # noqa: E402
from governance.coverage.entity_extract import entity_ref  # noqa: E402


def test_homepage_author_evidence_binds_real_cursor_run_and_page(tmp_path: Path) -> None:
    execution_id = "20260715--travel-homepage-stage-evidence--test-region-a--pilot-001"
    object_ref = entity_ref("地点", "景区", "测试景区")
    draft_dir = tmp_path / "4.draft"
    draft_dir.mkdir(parents=True)
    page = draft_dir / "page.md"
    prompt = draft_dir / "prompt.md"
    page.write_text("# 测试景区\n\n这是由真实作者流程写回的正文。", encoding="utf-8")
    prompt.write_text("仅依据底稿创作。", encoding="utf-8")
    write_json(
        draft_dir / "author_job_packet.json",
        {"executionId": execution_id, "objectRef": object_ref},
    )
    draft_meta = {
        "provider": "cursor_sdk",
        "model": "composer",
        "promptSha256": sha256_text(prompt.read_text(encoding="utf-8")),
        "draftSha256": sha256_file(page),
    }
    ctx = SimpleNamespace(
        execution_id=execution_id,
        agent_provider="cursor_sdk",
        model="composer",
    )

    _write_homepage_author_evidence(
        ctx,
        draft_dir=draft_dir,
        domain="地点",
        etype="景区",
        entity="测试景区",
        outcome=AgentRunOutcome.finished(run_id="cursor-run-1", agent_id="agent-1"),
        draft_meta=draft_meta,
    )

    self_check = read_json(draft_dir / "author_self_check.json")
    envelope = read_json(draft_dir / "agent_result_envelope.json")
    assert_valid(self_check, "content", "author_self_check")
    assert_valid(envelope, "content", "agent_result_envelope")
    assert self_check["passed"] is True
    assert envelope["agent"]["runId"] == "cursor-run-1"
    assert envelope["jobId"] == stable_job_id(execution_id, object_ref, "author")
    assert envelope["ref"] == object_ref
    assert envelope["stage"] == "author"
    assert validate_agent_result_envelope(envelope, workspace_root=draft_dir) == []
