"""stage receipt 链 + lane claim 的交接契约测试（DEC-005）。

绑定验收：handoff-protocol.md 的 receipt 协议（create-once、sequence 单调、
verdict/next 语义、execution_state 同步）与 orchestration.md 的
single-writer claim（获取/刷新/冲突/TTL 接手/释放）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import content.execution.stage_receipt as stage_receipt  # noqa: E402
from content.execution.receipt_state_reducer import reduce_receipt_projection  # noqa: E402
from core.schema import assert_valid  # noqa: E402

EXEC_ID = "20260823--family-article-case--region--pilot-001"


def _write_fixture_receipt(execution_id: str, payload: dict) -> Path:
    return stage_receipt._write_current_receipt_create_once(
        execution_id, payload, writer_token=stage_receipt._stage_authority_writer_token()
    )


def _digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _binding(ref: str) -> dict[str, str]:
    return {"scope": "execution", "ref": ref, "digest": _digest(ref)}


def _receipt(
    *, sequence: int, stage: str, verdict: str = "pass", next_stage: str,
    model_family: str = "deterministic", issue_code: str = "DATA.TEST.BLOCKED",
) -> dict:
    issues = [] if verdict == "pass" else [{
        "code": issue_code, "message": "fixture blocked", "recoveryStage": next_stage,
    }]
    return {
        "schema": "quwoquan_data.stage_receipt", "executionId": EXEC_ID,
        "stage": stage, "sequence": sequence, "verdict": verdict,
        "actor": {"host": "test", "modelFamily": model_family, "sessionId": "fixture", "invocation": None},
        "typedIssues": issues, "next": next_stage,
        "authority": {
            "openRequest": _binding(f"authority/{sequence}/open.json"),
            "machineGate": _binding(f"authority/{sequence}/gate.json"),
            "workflowContract": {"scope": "repo", "ref": "policy.json", "digest": _digest("workflow")},
            "semanticResult": None,
            "artifacts": [], "releaseBinding": None, "acceptanceBinding": None,
        },
        "recordedAt": f"2026-09-01T00:00:{sequence:02d}Z",
    }


@pytest.fixture(autouse=True)
def _isolated_execution_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def fake_execution_root(execution_id: str) -> Path:
        return tmp_path / "tasks" / execution_id

    monkeypatch.setattr(stage_receipt, "execution_root", fake_execution_root)
    return tmp_path


def test_receipt_sequence_is_monotonic_and_create_once() -> None:
    payload_1 = _receipt(sequence=1, stage="0.plan", next_stage="sources")
    assert_valid(payload_1, "execution", "stage_receipt", label="fixture receipt")
    path_1 = _write_fixture_receipt(EXEC_ID, payload_1)
    assert path_1.name == "001-0.plan.json"

    payload_2 = _receipt(sequence=2, stage="sources", next_stage="1.download")
    path_2 = _write_fixture_receipt(EXEC_ID, payload_2)
    assert path_2.name == "002-sources.json"
    assert _write_fixture_receipt(EXEC_ID, payload_2) == path_2

    conflict = {**payload_2, "verdict": "blocked", "next": "sources",
                "typedIssues": [{"code": "DATA.TEST.BLOCKED", "message": "blocked", "recoveryStage": "sources"}]}
    with pytest.raises(FileExistsError):
        _write_fixture_receipt(EXEC_ID, conflict)
    assert stage_receipt.latest_receipt(EXEC_ID)["stage"] == "sources"


def test_current_schema_rejects_self_reported_success_shape() -> None:
    legacy = {
        "schema": "quwoquan_data.stage_receipt", "executionId": EXEC_ID,
        "stage": "0.plan", "sequence": 1, "verdict": "pass", "next": "sources",
        "commands": [{"command": "verify x", "exitCode": 0}],
        "recordedAt": "2026-09-01T00:00:00Z",
    }
    with pytest.raises(ValueError, match="schema violation"):
        assert_valid(legacy, "execution", "stage_receipt", label="self-reported receipt")


def test_receipt_target_execution_identity_must_match() -> None:
    payload = _receipt(sequence=1, stage="0.plan", next_stage="sources")
    with pytest.raises(ValueError, match="executionId must match"):
        _write_fixture_receipt(f"{EXEC_ID}-other", payload)


def test_receipt_state_status_mapping() -> None:
    assert stage_receipt.receipt_state_status(_receipt(sequence=1, stage="0.plan", next_stage="sources")).value == "running"
    assert stage_receipt.receipt_state_status(_receipt(sequence=1, stage="0.plan", verdict="blocked", next_stage="0.plan")).value == "manual_required"
    shipped = _receipt(sequence=10, stage="ship", next_stage="END")
    shipped["authority"]["releaseBinding"] = {"releaseId": "release-1", "releaseDigest": _digest("release")}
    shipped["authority"]["acceptanceBinding"] = {"scope": "output", "ref": "acceptance.json", "digest": _digest("acceptance"), "environment": "gamma"}
    assert stage_receipt.receipt_state_status(shipped).value == "succeeded"


def test_receipt_reducer_writes_minimal_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = stage_receipt.execution_root(EXEC_ID) / "_shared/execution_state.json"
    import content.execution.receipt_state_reducer as reducer
    from content.execution import stage_authority

    def load_projection_receipt(execution_id: str, receipt: Path) -> dict:
        assert execution_id == EXEC_ID
        return json.loads(Path(receipt).read_text(encoding="utf-8"))

    monkeypatch.setattr(reducer, "execution_state_path", lambda _execution_id: state_path)
    monkeypatch.setattr(
        stage_authority, "validate_stage_receipt_authority", load_projection_receipt
    )
    _write_fixture_receipt(EXEC_ID, _receipt(sequence=1, stage="0.plan", next_stage="sources"))
    reduce_receipt_projection(EXEC_ID)
    projection = json.loads(state_path.read_text(encoding="utf-8"))
    assert projection["completed"] == ["0.plan"]
    assert projection["status"] == "running"
    assert projection["next"] == "sources"
    assert projection["latestReceiptRef"] == "_shared/receipts/001-0.plan.json"



def test_legacy_business_state_writer_is_permanently_rejected() -> None:
    from content.execution import context

    with pytest.raises(ValueError, match="STATE_WRITER_RETIRED"):
        context.save_execution_state(object())


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
    _write_fixture_receipt(
        EXEC_ID, _receipt(sequence=1, stage="0.plan", next_stage="sources")
    )
    _write_fixture_receipt(
        EXEC_ID, _receipt(sequence=2, stage="sources", verdict="blocked",
                          next_stage="sources", model_family="gpt",
                          issue_code="DATA.TEST.SOURCE_PENDING")
    )
    status = stage_receipt.fleet_status([EXEC_ID])
    assert status["total"] == 1
    assert status["succeeded"] == 0
    assert status["stageDistribution"] == {"blocked@sources": 1}
    assert status["modelFamilies"] == {"gpt": 1}
    assert status["blockedReasons"] == {"DATA.TEST.SOURCE_PENDING": 1}


# spec_ref: multi-carrier-release GWT-020.t4（round timeout 与 claim TTL 的关系约束）
def test_round_timeout_must_stay_inside_the_claim_survival_window() -> None:
    ttl = stage_receipt.DEFAULT_CLAIM_TTL_MINUTES
    margin = stage_receipt.CLAIM_TTL_SAFETY_MARGIN_MINUTES
    budget = (ttl - margin) * 60

    admitted = stage_receipt.round_timeout_admission(
        EXEC_ID, round_timeout_seconds=budget
    )
    assert admitted["admitted"] is True
    assert admitted["ttlMinutes"] == ttl
    assert admitted["reason"] == ""

    refused = stage_receipt.round_timeout_admission(
        EXEC_ID, round_timeout_seconds=budget + 1
    )
    assert refused["admitted"] is False
    assert str(budget) in refused["reason"], "判否必须给出可执行的上限秒数"

    # 单轮超时长于 TTL 是最危险的一档：在飞会话还活着，claim 已可被别的 lane 接手。
    beyond_ttl = stage_receipt.round_timeout_admission(
        EXEC_ID, round_timeout_seconds=ttl * 60 + 1
    )
    assert beyond_ttl["admitted"] is False


def test_round_timeout_is_judged_against_the_claim_on_disk_not_the_default() -> None:
    stage_receipt.acquire_lane_claim(
        EXEC_ID, actor_host="cursor", actor_session="sess-A", ttl_minutes=10
    )
    margin = stage_receipt.CLAIM_TTL_SAFETY_MARGIN_MINUTES

    verdict = stage_receipt.round_timeout_admission(
        EXEC_ID, round_timeout_seconds=(10 - margin) * 60 + 1
    )
    assert verdict["admitted"] is False
    assert verdict["ttlMinutes"] == 10, "判据要读执行者实际声明的 TTL"
    assert stage_receipt.round_timeout_admission(
        EXEC_ID, round_timeout_seconds=(10 - margin) * 60
    )["admitted"] is True


def test_non_positive_round_timeout_is_refused_rather_than_treated_as_no_timeout() -> None:
    for seconds in (0, -1):
        verdict = stage_receipt.round_timeout_admission(
            EXEC_ID, round_timeout_seconds=seconds
        )
        assert verdict["admitted"] is False
        assert verdict["ttlMinutes"] == 0


# spec_ref: multi-carrier-release GWT-020.t4（stage 枚举收敛到单一真相源）
def test_stage_enumerations_all_derive_from_one_closed_set() -> None:
    from core import paths
    from core.control_types import OBJECT_STAGE_SEQUENCE, RECEIPT_STAGE_SEQUENCE
    from core.stage_artifact_contract import STAGES
    from verify import handler as verify_handler

    assert stage_receipt.RECEIPT_STAGES == tuple(
        stage.value for stage in RECEIPT_STAGE_SEQUENCE
    )
    assert paths.OBJECT_STAGES == tuple(
        stage.value for stage in OBJECT_STAGE_SEQUENCE
    )
    assert STAGES == paths.OBJECT_STAGES
    assert set(paths.OBJECT_STAGES) <= set(stage_receipt.RECEIPT_STAGES), (
        "对象过程阶段必须是 receipt 协议阶段的子集"
    )
    assert stage_receipt.RECEIPT_NEXT_VALUES == (
        *stage_receipt.RECEIPT_STAGES,
        "END",
    )

    # CLI 的 --through 闭集与库常量同源：改阶段名不会只改到其中一处。
    parser = argparse.ArgumentParser()
    verify_handler.register_parser(parser.add_subparsers(dest="command"))
    for stage in paths.OBJECT_STAGES:
        parsed = parser.parse_args(
            [
                "verify",
                "stage-artifacts",
                "--execution-id",
                EXEC_ID,
                "--through",
                stage,
            ]
        )
        assert parsed.through == stage
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "verify",
                "stage-artifacts",
                "--execution-id",
                EXEC_ID,
                "--through",
                "6.nonexistent",
            ]
        )



def test_same_receipt_replay_heals_missing_projection(
    _isolated_execution_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.execution import receipt_state_reducer, stage_authority

    def load_projection_receipt(execution_id: str, receipt: Path) -> dict:
        assert execution_id == EXEC_ID
        return json.loads(Path(receipt).read_text(encoding="utf-8"))

    state_path = (_isolated_execution_root / "tasks" / EXEC_ID
                  / "_shared/execution_state.json")
    monkeypatch.setattr(receipt_state_reducer, "execution_state_path", lambda _execution_id: state_path)
    monkeypatch.setattr(
        stage_authority, "validate_stage_receipt_authority", load_projection_receipt
    )
    payload = _receipt(sequence=1, stage="0.plan", next_stage="sources")
    receipt_path = _write_fixture_receipt(EXEC_ID, payload)
    assert _write_fixture_receipt(EXEC_ID, payload) == receipt_path
    reduce_receipt_projection(EXEC_ID)
    assert len(stage_receipt.list_receipt_files(EXEC_ID)) == 1
    assert json.loads(state_path.read_text(encoding="utf-8"))["latestStage"] == "0.plan"
