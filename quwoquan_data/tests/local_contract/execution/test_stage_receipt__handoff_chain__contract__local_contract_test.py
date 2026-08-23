"""stage receipt 链 + lane claim 的交接契约测试（DEC-005）。

绑定验收：handoff-protocol.md 的 receipt 协议（create-once、sequence 单调、
verdict/next 语义、execution_state 同步）与 orchestration.md 的
single-writer claim（获取/刷新/冲突/TTL 接手/释放）。
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import content.execution.stage_receipt as stage_receipt  # noqa: E402

EXEC_ID = "20260823--family-article-case--region--pilot-001"


def _base_kwargs(**overrides: object) -> dict:
    kwargs: dict = {
        "execution_id": EXEC_ID,
        "stage": "0.plan",
        "verdict": "pass",
        "actor_host": "cursor",
        "actor_model_family": "claude",
        "actor_session": "sess-1",
        "artifacts": ["0.plan/request.json"],
        "open_items": [],
        "next_stage": "sources",
        "evidence_commands": [{"command": "verify x", "exitCode": 0}],
        "issue_count": 0,
        "repair_rounds": 0,
    }
    kwargs.update(overrides)
    return kwargs


@pytest.fixture(autouse=True)
def _isolated_execution_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def fake_execution_root(execution_id: str) -> Path:
        return tmp_path / "tasks" / execution_id

    monkeypatch.setattr(stage_receipt, "execution_root", fake_execution_root)
    return tmp_path


def test_receipt_sequence_is_monotonic_and_create_once() -> None:
    payload_1 = stage_receipt.build_receipt(**_base_kwargs())
    path_1 = stage_receipt.write_receipt_create_once(EXEC_ID, payload_1)
    assert path_1.name == "001-0.plan.json"

    payload_2 = stage_receipt.build_receipt(
        **_base_kwargs(stage="sources", next_stage="1.download")
    )
    assert payload_2["sequence"] == 2
    path_2 = stage_receipt.write_receipt_create_once(EXEC_ID, payload_2)
    assert path_2.name == "002-sources.json"

    with pytest.raises(FileExistsError):
        stage_receipt.write_receipt_create_once(EXEC_ID, payload_2)

    latest = stage_receipt.latest_receipt(EXEC_ID)
    assert latest is not None
    assert latest["stage"] == "sources"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"actor_model_family": "auto"}, "not literal 'auto'"),
        (
            {"verdict": "blocked", "next_stage": "0.plan"},
            "at least one --open-item",
        ),
        ({"next_stage": "END"}, "only legal for the ship stage"),
        (
            {"stage": "ship", "next_stage": "release"},
            "ship pass receipt must set next=END",
        ),
        (
            {
                "verdict": "blocked",
                "next_stage": "sources",
                "open_items": [
                    {"item": "缺口", "disposition": "return_to_stage"}
                ],
            },
            "requires returnStage",
        ),
    ],
)
def test_receipt_protocol_rejections(overrides: dict, message: str) -> None:
    kwargs = _base_kwargs(**overrides)
    with pytest.raises(ValueError, match=message):
        stage_receipt.build_receipt(**kwargs)


def test_receipt_state_status_mapping() -> None:
    running = stage_receipt.build_receipt(**_base_kwargs())
    assert stage_receipt.receipt_state_status(running).value == "running"
    blocked = stage_receipt.build_receipt(
        **_base_kwargs(
            verdict="blocked",
            next_stage="sources",
            open_items=[{"item": "缺口", "disposition": "gate_block"}],
        )
    )
    assert stage_receipt.receipt_state_status(blocked).value == "manual_required"
    shipped = stage_receipt.build_receipt(
        **_base_kwargs(stage="ship", next_stage="END")
    )
    assert stage_receipt.receipt_state_status(shipped).value == "succeeded"


def test_lane_claim_acquire_refresh_conflict_release() -> None:
    first = stage_receipt.acquire_lane_claim(
        EXEC_ID, actor_host="cursor", actor_session="sess-A"
    )
    assert first["acquired"] is True

    refresh = stage_receipt.acquire_lane_claim(
        EXEC_ID, actor_host="cursor", actor_session="sess-A"
    )
    assert refresh["acquired"] is True
    assert refresh["claim"]["claimedAt"] == first["claim"]["claimedAt"]

    conflict = stage_receipt.acquire_lane_claim(
        EXEC_ID, actor_host="codex", actor_session="sess-B"
    )
    assert conflict["acquired"] is False

    foreign_release = stage_receipt.release_lane_claim(
        EXEC_ID, actor_session="sess-B"
    )
    assert foreign_release["released"] is False

    owner_release = stage_receipt.release_lane_claim(
        EXEC_ID, actor_session="sess-A"
    )
    assert owner_release["released"] is True
    assert not stage_receipt.claim_path(EXEC_ID).is_file()


def test_lane_claim_expired_ttl_can_be_taken_over() -> None:
    stage_receipt.acquire_lane_claim(
        EXEC_ID, actor_host="cursor", actor_session="sess-A", ttl_minutes=45
    )
    path = stage_receipt.claim_path(EXEC_ID)
    stale = json.loads(path.read_text(encoding="utf-8"))
    stale["heartbeatAt"] = (
        (datetime.now(UTC) - timedelta(minutes=46))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    path.write_text(json.dumps(stale), encoding="utf-8")

    takeover = stage_receipt.acquire_lane_claim(
        EXEC_ID, actor_host="codex", actor_session="sess-B"
    )
    assert takeover["acquired"] is True
    assert takeover["claim"]["owner"]["sessionId"] == "sess-B"


def test_lane_claim_check_is_read_only_and_reports_activity() -> None:
    empty = stage_receipt.check_lane_claim(EXEC_ID)
    assert empty == {"active": False, "claim": None}
    assert not stage_receipt.claim_path(EXEC_ID).is_file()

    stage_receipt.acquire_lane_claim(
        EXEC_ID, actor_host="codex", actor_session="sess-A"
    )
    before = stage_receipt.claim_path(EXEC_ID).read_text(encoding="utf-8")
    active = stage_receipt.check_lane_claim(EXEC_ID)
    assert active["active"] is True
    assert active["claim"]["owner"]["sessionId"] == "sess-A"
    assert (
        stage_receipt.claim_path(EXEC_ID).read_text(encoding="utf-8") == before
    ), "check 不得刷新心跳或改写 claim"

    path = stage_receipt.claim_path(EXEC_ID)
    stale = json.loads(path.read_text(encoding="utf-8"))
    stale["heartbeatAt"] = (
        (datetime.now(UTC) - timedelta(minutes=46))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    path.write_text(json.dumps(stale), encoding="utf-8")
    expired = stage_receipt.check_lane_claim(EXEC_ID)
    assert expired["active"] is False
    assert expired["claim"]["owner"]["sessionId"] == "sess-A"


def test_fleet_status_aggregates_latest_receipts() -> None:
    stage_receipt.write_receipt_create_once(
        EXEC_ID, stage_receipt.build_receipt(**_base_kwargs())
    )
    stage_receipt.write_receipt_create_once(
        EXEC_ID,
        stage_receipt.build_receipt(
            **_base_kwargs(
                stage="sources",
                verdict="blocked",
                next_stage="sources",
                actor_model_family="gpt",
                open_items=[{"item": "两个目标缺源", "disposition": "gate_block"}],
            )
        ),
    )
    status = stage_receipt.fleet_status([EXEC_ID])
    assert status["total"] == 1
    assert status["succeeded"] == 0
    assert status["stageDistribution"] == {"blocked@sources": 1}
    assert status["modelFamilies"] == {"gpt": 1}
    assert status["blockedReasons"] == {"两个目标缺源": 1}
