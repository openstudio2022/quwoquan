"""GWT9 Prompt 审计链合同测试。

Given 商用批产物必须可回放归因（provider/model/runId/promptSha256），
When Agent 提交 result envelope，
Then 缺任一审计字段 fail-closed；promptSha256 与 prompt 全文稳定对应。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.execution import production_contracts as pc  # noqa: E402

_JOB = {
    "jobId": "job_audit",
    "executionId": "20260711--travel-article-agent-audit--test-region-a--pilot-001",
    "ref": "posts/article/审计链样章",
    "stage": "post_author",
}


def _valid_envelope(**overrides):
    envelope = pc.build_agent_result_envelope(
        job=_JOB,
        files=[{"path": "posts/article/demo.md", "sha256": "sha256:" + "0" * 64, "role": "draft"}],
        gates=[
            pc.build_gate_verdict(
                gate_id="review",
                decision="passed",
                input_hash="sha256:" + "0" * 64,
                output_hash="sha256:" + "0" * 64,
            )
        ],
        provider="cursor_sdk",
        model="composer",
        run_id="run_20260710_audit",
        prompt_sha256=pc.sha256_text("完整执行 prompt 正文"),
        agent_id="agent_audit",
    )
    envelope.update(overrides)
    return envelope


def test_envelope_carries_full_audit_chain_and_validates():
    envelope = _valid_envelope()
    agent = envelope["agent"]
    assert agent["provider"] == "cursor_sdk"
    assert agent["model"] == "composer"
    assert agent["runId"] == "run_20260710_audit"
    assert agent["promptSha256"].startswith("sha256:")
    # 字段级校验（不带 workspace_root 的文件存在性检查）。
    issues = pc.validate_agent_result_envelope(envelope)
    assert issues == []


def test_envelope_missing_audit_fields_fail_closed():
    # 整个 agent 块缺失。
    stripped = _valid_envelope()
    stripped.pop("agent")
    issues = pc.validate_agent_result_envelope(stripped)
    assert any("envelope.agent is required" in i for i in issues)
    # 逐字段缺失。
    for field in ("provider", "model", "runId"):
        broken = _valid_envelope()
        broken["agent"] = {**broken["agent"], field: ""}
        issues = pc.validate_agent_result_envelope(broken)
        assert any(f"envelope.agent.{field} is required" in i for i in issues), (field, issues)
    # promptSha256 必须是 sha256:<hex>。
    bad_hash = _valid_envelope()
    bad_hash["agent"] = {**bad_hash["agent"], "promptSha256": "md5:abc"}
    issues = pc.validate_agent_result_envelope(bad_hash)
    assert any("promptSha256" in i for i in issues)


def test_prompt_sha_is_stable_and_replayable():
    """同一 prompt 全文必须映射到同一 promptSha256（重放归因的前提）。"""
    prompt = "你是单篇内容创作 Subagent。……（同一份 prompt 全文）"
    assert pc.sha256_text(prompt) == pc.sha256_text(prompt)
    assert pc.sha256_text(prompt) != pc.sha256_text(prompt + " ")


def test_schema_files_freeze_audit_fields():
    """schema JSON（契约真相源）必须冻结审计字段为 required。"""
    envelope_schema = json.loads(
        (DATA_ROOT / "schema" / "content" / "agent_result_envelope.schema.json").read_text(encoding="utf-8")
    )
    assert "agent" in envelope_schema["required"]
    agent_block = envelope_schema["properties"]["agent"]
    assert set(agent_block["required"]) == {"provider", "model", "runId", "promptSha256"}
    assert agent_block["properties"]["promptSha256"]["pattern"].startswith("^sha256:")
