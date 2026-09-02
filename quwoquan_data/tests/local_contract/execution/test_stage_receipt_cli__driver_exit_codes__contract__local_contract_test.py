"""OPEN-012 薄驱动锚点：authority CLI 退出码与文档漂移。

`task stage-open/semantic-prepare/semantic-record/stage-gate/stage-close` 与 `task lane-claim` 是宿主公开写入口；
authority 命令冻结 0/2/3 退出码，且旧 `stage-record` 必须不可达。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
CLI_PATH = DATA_ROOT / "scripts" / "cli.py"
SKILL_REFERENCES_ROOT = (
    DATA_ROOT.parent / ".agents/skills/content-production/references"
)
HANDOFF_PROTOCOL_PATH = SKILL_REFERENCES_ROOT / "handoff-protocol.md"
ORCHESTRATION_PATH = SKILL_REFERENCES_ROOT / "orchestration.md"

EXECUTION_ID = "20260901--travel-homepage-driver-anchor--sichuan--pilot-001"


def _run_task(tmp_path: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["QWQ_OUTPUT_ROOT"] = str(tmp_path / "output")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", str(CLI_PATH), "task", *argv],
        capture_output=True,
        text=True,
        env=environment,
        cwd=DATA_ROOT.parent,
    )


def _write_context(tmp_path: Path, name: str, value: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def _state_path(tmp_path: Path) -> Path:
    return (
        tmp_path
        / "output/data/tasks"
        / EXECUTION_ID
        / "_shared/execution_state.json"
    )


def test_stage_authority_protocol_and_conflict_exit_codes(
    tmp_path: Path,
) -> None:
    missing_init = _run_task(
        tmp_path, "stage-open", "--execution-id", EXECUTION_ID, "--stage", "0.plan"
    )
    assert missing_init.returncode == 2
    assert "stage-open rejected" in missing_init.stderr

    free_gate = _write_context(tmp_path, "free-gate.json", {"command": "false", "exitCode": 0})
    rejected_gate = _run_task(
        tmp_path, "stage-gate", "--execution-id", EXECUTION_ID, "--stage", "0.plan",
        "--context", str(free_gate),
    )
    assert rejected_gate.returncode == 2
    assert "stage-gate rejected" in rejected_gate.stderr

    free_close = _write_context(tmp_path, "free-close.json", {"next": "ship"})
    rejected_close = _run_task(
        tmp_path, "stage-close", "--execution-id", EXECUTION_ID, "--stage", "0.plan",
        "--context", str(free_close),
    )
    assert rejected_close.returncode == 2
    assert "stage-close rejected" in rejected_close.stderr

    import content.execution.stage_receipt_cli as stage_receipt_cli
    import content.execution.stage_authority as stage_authority
    import pytest

    class Args:
        execution_id = EXECUTION_ID
        stage = "0.plan"

    original = stage_authority.open_stage
    stage_authority.open_stage = lambda *_args: (_ for _ in ()).throw(
        stage_authority.StageAuthorityConflict("fixture conflict")
    )
    try:
        with pytest.raises(SystemExit) as exit_info:
            stage_receipt_cli._handle_stage_open(Args())
    finally:
        stage_authority.open_stage = original
    assert exit_info.value.code == 3


def test_stage_record_is_not_a_public_command(tmp_path: Path) -> None:
    result = _run_task(tmp_path, "stage-record", "--execution-id", EXECUTION_ID)
    assert result.returncode == 2
    assert "invalid choice: 'stage-record'" in result.stderr


def test_semantic_cli_input_contract_and_exit_codes(tmp_path: Path) -> None:
    prepare_help = _run_task(tmp_path, "semantic-prepare", "--help")
    assert prepare_help.returncode == 0
    assert "--input" not in prepare_help.stdout
    record_help = _run_task(tmp_path, "semantic-record", "--help")
    assert record_help.returncode == 0
    assert "--input INPUT" in record_help.stdout

    invalid = _write_context(tmp_path, "semantic-invalid.json", {"verdict": "pass"})
    rejected = _run_task(
        tmp_path, "semantic-record", "--execution-id", EXECUTION_ID,
        "--stage", "sources", "--input", str(invalid),
    )
    assert rejected.returncode == 2
    assert "semantic-record rejected" in rejected.stderr

    import content.execution.stage_receipt_cli as stage_receipt_cli
    import content.execution.stage_semantic_recorder as recorder
    import pytest

    class Args:
        execution_id = EXECUTION_ID
        stage = "sources"
        input = str(invalid)

    original = recorder.record_stage_semantic_result
    recorder.record_stage_semantic_result = lambda *_args: (_ for _ in ()).throw(
        recorder.StageSemanticConflict("fixture conflict")
    )
    try:
        with pytest.raises(SystemExit) as exit_info:
            stage_receipt_cli._handle_semantic_record(Args())
    finally:
        recorder.record_stage_semantic_result = original
    assert exit_info.value.code == 3


def test_lane_claim_exit_codes_zero_two_three(tmp_path: Path) -> None:
    acquired = _run_task(
        tmp_path,
        "lane-claim",
        "--execution-id",
        EXECUTION_ID,
        "--actor-host",
        "cursor",
        "--actor-session",
        "owner-session",
    )
    assert acquired.returncode == 0, acquired.stderr
    assert json.loads(acquired.stdout)["acquired"] is True

    conflict = _run_task(
        tmp_path,
        "lane-claim",
        "--execution-id",
        EXECUTION_ID,
        "--actor-host",
        "codex",
        "--actor-session",
        "intruder-session",
    )
    assert conflict.returncode == 3
    assert json.loads(conflict.stdout)["acquired"] is False

    check = _run_task(
        tmp_path,
        "lane-claim",
        "--execution-id",
        EXECUTION_ID,
        "--check",
    )
    assert check.returncode == 3
    assert json.loads(check.stdout)["active"] is True

    missing_session = _run_task(
        tmp_path,
        "lane-claim",
        "--execution-id",
        EXECUTION_ID,
        "--actor-host",
        "cursor",
    )
    assert missing_session.returncode == 2
    assert "actor-session" in missing_session.stderr


def test_writing_pack_schema_failure_path_is_typed(tmp_path: Path) -> None:
    import core.paths as core_paths
    from verify.stage_artifacts import verify_stage_artifacts

    root = tmp_path / "output/data/tasks" / EXECUTION_ID
    object_root = root / "posts/article/planning_consultation/驱动锚点/1"
    pack_path = object_root / "3.compose/writing_pack.json"
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(
        json.dumps({"schema": "quwoquan.content.writing_pack"}, ensure_ascii=False),
        encoding="utf-8",
    )

    original_execution_root = core_paths.execution_root
    core_paths_dict = core_paths.__dict__
    core_paths_dict["execution_root"] = lambda _execution_id: root
    try:
        import verify.stage_artifacts as stage_artifacts_module

        stage_artifacts_dict = stage_artifacts_module.__dict__
        original_module_root = stage_artifacts_dict["execution_root"]
        stage_artifacts_dict["execution_root"] = lambda _execution_id: root
        try:
            report = verify_stage_artifacts(
                execution_id=EXECUTION_ID,
                publish_root=tmp_path / "publish",
                release_root=tmp_path / "release",
            )
        finally:
            stage_artifacts_dict["execution_root"] = original_module_root
    finally:
        core_paths_dict["execution_root"] = original_execution_root

    assert report["passed"] is False
    schema_issues = [
        issue for issue in report["issues"] if "writing_pack.json: schema invalid" in issue
    ]
    assert schema_issues, report["issues"]


def test_handoff_protocol_document_binds_the_implemented_semantics() -> None:
    from content.execution.stage_receipt import RECEIPT_STAGES, receipt_state_status
    from core.control_types import ExecutionStateStatus

    text = HANDOFF_PROTOCOL_PATH.read_text(encoding="utf-8")

    documented_stages = re.findall(
        r"[0-9A-Za-z.]+(?:\.[a-z]+)?",
        text.split("```text")[1].split("```")[0],
    )
    documented_sequence = [
        token for token in documented_stages if token in set(RECEIPT_STAGES)
    ]
    assert documented_sequence == list(RECEIPT_STAGES)

    assert "`stage=ship` 且 `verdict=pass` → `status=succeeded`" in text
    assert receipt_state_status(
        {"stage": "ship", "verdict": "pass"}
    ) is ExecutionStateStatus.SUCCEEDED
    assert "`verdict=blocked` → `status=manual_required`" in text
    assert receipt_state_status(
        {"stage": "4.draft", "verdict": "blocked"}
    ) is ExecutionStateStatus.MANUAL_REQUIRED
    assert "其余 pass receipt → `status=running`" in text
    assert receipt_state_status(
        {"stage": "4.draft", "verdict": "pass"}
    ) is ExecutionStateStatus.RUNNING

    # orchestration 记载的 claim 协议面必须在 CLI 上真实存在：
    # 驱动只读预检 --check、执行者释放 --release，冲突退出码 3 由 CLI help 冻结。
    orchestration = ORCHESTRATION_PATH.read_text(encoding="utf-8")
    assert "task lane-claim --check" in orchestration
    assert "task lane-claim --release" in orchestration
    subcommand_help = subprocess.run(
        [sys.executable, "-B", str(CLI_PATH), "task", "lane-claim", "--help"],
        capture_output=True,
        text=True,
        cwd=DATA_ROOT.parent,
    )
    assert subcommand_help.returncode == 0
    assert "--check" in subcommand_help.stdout
    assert "--release" in subcommand_help.stdout
    task_help = subprocess.run(
        [sys.executable, "-B", str(CLI_PATH), "task", "--help"],
        capture_output=True,
        text=True,
        cwd=DATA_ROOT.parent,
    )
    assert task_help.returncode == 0
    normalized_help = " ".join(task_help.stdout.split())
    assert "冲突退出码 3" in normalized_help
    assert "stage-open" in normalized_help
    assert "stage-gate" in normalized_help
    assert "stage-close" in normalized_help
    assert "semantic-prepare" in normalized_help
    assert "semantic-record" in normalized_help
    assert "stage-record" not in normalized_help
