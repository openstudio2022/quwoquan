"""Stage receipt 链与 single-writer lane claim（DEC-005）。

receipt 是跨会话/跨宿主交接与恢复的唯一状态源：
`_shared/receipts/<seq 3 位>-<stage>.json`，create-once 原子写，最新 sequence 为权威。
claim 是可清理过程层（`_shared/claims/lane.json`），心跳过 TTL 即死 lane 可接手。
本模块只做检查与确定性 IO，不驱动、不等待 agent、不推进状态机。
"""
from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.control_types import ExecutionStateStatus
from core.paths import DATA_EXECUTIONS_ROOT, execution_root, is_execution_id
from core.schema import assert_valid

RECEIPT_SCHEMA = "quwoquan_data.stage_receipt"
RECEIPT_STAGES: tuple[str, ...] = (
    "0.plan", "sources", "1.download", "2.quality", "3.compose",
    "4.draft", "5.review", "publish", "release", "ship",
)
RECEIPT_NEXT_VALUES: tuple[str, ...] = (*RECEIPT_STAGES, "END")
OPEN_ITEM_DISPOSITIONS: tuple[str, ...] = (
    "return_to_stage", "gate_block", "out_of_scope",
)
DEFAULT_CLAIM_TTL_MINUTES = 45
_RECEIPT_NAME_RE = re.compile(r"^(\d{3})-(.+)\.json$")


def receipts_dir(execution_id: str) -> Path:
    return execution_root(execution_id) / "_shared" / "receipts"


def claim_path(execution_id: str) -> Path:
    return execution_root(execution_id) / "_shared" / "claims" / "lane.json"


def _now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _claim_expired(existing: dict) -> bool:
    heartbeat = datetime.fromisoformat(
        str(existing["heartbeatAt"]).replace("Z", "+00:00")
    )
    return _now() >= heartbeat + timedelta(minutes=int(existing["ttlMinutes"]))


def list_receipt_files(execution_id: str) -> list[tuple[int, str, Path]]:
    """按 sequence 升序返回 (sequence, stage, path)。非法命名直接失败。"""
    root = receipts_dir(execution_id)
    if not root.is_dir():
        return []
    entries: list[tuple[int, str, Path]] = []
    for path in sorted(root.iterdir()):
        if path.name.startswith("."):
            continue
        match = _RECEIPT_NAME_RE.fullmatch(path.name)
        if match is None:
            raise ValueError(f"illegal receipt filename: {path}")
        entries.append((int(match.group(1)), match.group(2), path))
    entries.sort(key=lambda item: item[0])
    return entries


def load_receipt(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"receipt must be an object: {path}")
    return payload


def latest_receipt(execution_id: str) -> dict | None:
    entries = list_receipt_files(execution_id)
    if not entries:
        return None
    return load_receipt(entries[-1][2])


def _next_sequence(execution_id: str) -> int:
    entries = list_receipt_files(execution_id)
    return entries[-1][0] + 1 if entries else 1


def build_receipt(
    *,
    execution_id: str,
    stage: str,
    verdict: str,
    actor_host: str,
    actor_model_family: str,
    actor_session: str,
    artifacts: list[str],
    open_items: list[dict],
    next_stage: str,
    evidence_commands: list[dict],
    issue_count: int,
    repair_rounds: int,
) -> dict:
    """构建并做协议级校验；schema 校验由 assert_valid 兜底。"""
    if actor_model_family.strip().lower() == "auto":
        raise ValueError(
            "actor.modelFamily must record the actual routed family, not literal 'auto'"
        )
    if verdict == "blocked" and not open_items:
        raise ValueError("blocked receipt requires at least one --open-item")
    if verdict == "pass":
        if stage == "ship" and next_stage != "END":
            raise ValueError("ship pass receipt must set next=END")
        if stage != "ship" and next_stage == "END":
            raise ValueError("next=END is only legal for the ship stage")
    for item in open_items:
        if item["disposition"] == "return_to_stage" and "returnStage" not in item:
            raise ValueError(
                f"open item requires returnStage for return_to_stage: {item['item']}"
            )
    payload = {
        "schema": RECEIPT_SCHEMA,
        "executionId": execution_id,
        "stage": stage,
        "sequence": _next_sequence(execution_id),
        "verdict": verdict,
        "actor": {
            "host": actor_host,
            "modelFamily": actor_model_family,
            "sessionId": actor_session,
        },
        "artifacts": list(artifacts),
        "openItems": list(open_items),
        "next": next_stage,
        "evidence": {
            "commands": list(evidence_commands),
            "issueCount": issue_count,
            "repairRounds": repair_rounds,
        },
        "recordedAt": _now_iso(),
    }
    assert_valid(payload, "execution", "stage_receipt", label="stage-record")
    return payload


def write_receipt_create_once(execution_id: str, payload: dict) -> Path:
    """tmp + os.link 原子 create-once：目标已存在即失败，绝不覆盖历史。"""
    root = receipts_dir(execution_id)
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{payload['sequence']:03d}-{payload['stage']}.json"
    tmp = root / f".tmp-{os.getpid()}-{target.name}"
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        os.link(tmp, target)
    except FileExistsError as exc:
        raise FileExistsError(
            f"receipt already exists (create-once): {target}"
        ) from exc
    finally:
        tmp.unlink(missing_ok=True)
    return target


def receipt_state_status(payload: dict) -> ExecutionStateStatus:
    """receipt → execution_state.status 的唯一映射（handoff-protocol.md）。"""
    if payload["verdict"] == "blocked":
        return ExecutionStateStatus.MANUAL_REQUIRED
    if payload["stage"] == "ship":
        return ExecutionStateStatus.SUCCEEDED
    return ExecutionStateStatus.RUNNING


def record_stage_receipt(**kwargs: object) -> Path:
    """写 receipt 并在同一命令内更新 execution_state（写入权单轨）。"""
    payload = build_receipt(**kwargs)  # type: ignore[arg-type]
    target = write_receipt_create_once(str(kwargs["execution_id"]), payload)
    from content.execution.context import load_execution_state, save_execution_state

    state = load_execution_state(str(kwargs["execution_id"]))
    state.status = receipt_state_status(payload)
    save_execution_state(state)
    return target


def acquire_lane_claim(
    execution_id: str,
    *,
    actor_host: str,
    actor_session: str,
    ttl_minutes: int = DEFAULT_CLAIM_TTL_MINUTES,
) -> dict:
    """single-writer claim：同 session 刷新心跳；异 session 未过 TTL 拒绝。"""
    path = claim_path(execution_id)
    existing: dict | None = None
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            existing = json.load(handle)
    if (
        existing is not None
        and existing["owner"]["sessionId"] != actor_session
        and not _claim_expired(existing)
    ):
        return {
            "acquired": False,
            "reason": "active claim held by another session",
            "claim": existing,
        }
    claim = {
        "executionId": execution_id,
        "owner": {"host": actor_host, "sessionId": actor_session},
        "claimedAt": (
            existing["claimedAt"]
            if existing is not None
            and existing["owner"]["sessionId"] == actor_session
            else _now_iso()
        ),
        "heartbeatAt": _now_iso(),
        "ttlMinutes": ttl_minutes,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".tmp-{os.getpid()}-lane.json"
    tmp.write_text(
        json.dumps(claim, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp, path)
    return {"acquired": True, "reason": "", "claim": claim}


def check_lane_claim(execution_id: str) -> dict:
    """只读探测活跃 claim：不写盘、不刷心跳。

    驱动层（loop_driver）预检专用：claim 的获取与释放只属于执行者
    （每轮宿主会话），驱动自己写 claim 会锁死宿主会话的合法 claim。
    """
    path = claim_path(execution_id)
    if not path.is_file():
        return {"active": False, "claim": None}
    with path.open(encoding="utf-8") as handle:
        existing = json.load(handle)
    return {"active": not _claim_expired(existing), "claim": existing}


def release_lane_claim(execution_id: str, *, actor_session: str) -> dict:
    """仅释放本 session 持有的 claim；异主 no-op（防误删活跃 lane）。"""
    path = claim_path(execution_id)
    if not path.is_file():
        return {"released": False, "reason": "no claim on disk"}
    with path.open(encoding="utf-8") as handle:
        existing = json.load(handle)
    if existing["owner"]["sessionId"] != actor_session:
        return {"released": False, "reason": "claim held by another session"}
    path.unlink()
    return {"released": True, "reason": ""}


def _execution_status_entry(execution_id: str) -> dict:
    receipt = latest_receipt(execution_id)
    if receipt is None:
        return {
            "executionId": execution_id,
            "stage": None,
            "verdict": None,
            "next": "0.plan",
            "modelFamily": None,
            "blockedItems": [],
        }
    return {
        "executionId": execution_id,
        "stage": receipt["stage"],
        "verdict": receipt["verdict"],
        "next": receipt["next"],
        "modelFamily": receipt["actor"]["modelFamily"],
        "blockedItems": [
            item["item"]
            for item in receipt["openItems"]
            if receipt["verdict"] == "blocked"
        ],
    }


def fleet_status(execution_ids: list[str] | None = None) -> dict:
    """只读聚合 receipt 链：产出率、阶段分布、blocked 原因、模型族切片。"""
    if execution_ids:
        ids = list(execution_ids)
    elif DATA_EXECUTIONS_ROOT.is_dir():
        ids = sorted(
            entry.name
            for entry in DATA_EXECUTIONS_ROOT.iterdir()
            if entry.is_dir() and is_execution_id(entry.name)
        )
    else:
        ids = []
    executions = [_execution_status_entry(execution_id) for execution_id in ids]
    stage_distribution: dict[str, int] = {}
    model_families: dict[str, int] = {}
    blocked_reasons: dict[str, int] = {}
    succeeded = 0
    for entry in executions:
        key = entry["next"] if entry["verdict"] != "blocked" else f"blocked@{entry['stage']}"
        stage_distribution[key] = stage_distribution.get(key, 0) + 1
        if entry["next"] == "END" and entry["verdict"] == "pass":
            succeeded += 1
        if entry["modelFamily"]:
            model_families[entry["modelFamily"]] = (
                model_families.get(entry["modelFamily"], 0) + 1
            )
        for item in entry["blockedItems"]:
            blocked_reasons[item] = blocked_reasons.get(item, 0) + 1
    return {
        "total": len(executions),
        "succeeded": succeeded,
        "stageDistribution": dict(sorted(stage_distribution.items())),
        "modelFamilies": dict(sorted(model_families.items())),
        "blockedReasons": dict(
            sorted(blocked_reasons.items(), key=lambda kv: -kv[1])
        ),
        "executions": executions,
    }
