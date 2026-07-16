"""The literal gate rejects control values and accepts typed owners."""
from __future__ import annotations

from verify.verify_control_literals import source_control_literal_issues


def test_control_literals_reject_raw_stage_status_and_environment_choices() -> None:
    source = '''
from somewhere import StageResult
result = StageResult("download_plan", AUTO, "failed")
parser.add_argument("--env", choices=["alpha", "gamma"])
'''
    issues = source_control_literal_issues(source, label="sample.py")
    assert any("ExecutionStage" in issue for issue in issues)
    assert any("StageStatus" in issue for issue in issues)
    assert any("controlled choices" in issue for issue in issues)


def test_control_literals_accept_closed_types() -> None:
    source = '''
from core.control_types import ExecutionStage, StageKind, StageStatus
from somewhere import StageResult
result = StageResult(ExecutionStage.DOWNLOAD_PLAN, StageKind.AUTO, StageStatus.FAILED)
'''
    assert source_control_literal_issues(source, label="sample.py") == []


def test_control_literals_reject_environment_milestone_scale_and_timeout() -> None:
    source = '''
env = "gamma"
rollout_milestone = "canary"
limit = 100
request_timeout = 20
'''
    issues = source_control_literal_issues(
        source,
        label="quwoquan_data/scripts/content/sample.py",
    )
    assert any("DeploymentEnvironment" in issue for issue in issues)
    assert any("RolloutMilestone" in issue for issue in issues)
    assert any("batch size" in issue for issue in issues)
    assert any("runtime control number" in issue for issue in issues)


def test_control_literals_reject_string_issue_state_machine_and_legacy_result_issues() -> None:
    source = '''
from core.control_types import ExecutionStage, StageKind, StageStatus
from somewhere import StageResult
if "retained sources" in issue_message.lower():
    retry()
result = StageResult(
    ExecutionStage.DOWNLOAD_FETCH,
    StageKind.AUTO,
    StageStatus.FAILED,
    issues=[issue_message],
)
'''
    issues = source_control_literal_issues(
        source,
        label="quwoquan_data/scripts/content/execution/sample.py",
    )
    assert any("message substrings" in issue for issue in issues)
    assert any("typed issue_records" in issue for issue in issues)


def test_control_literals_reject_silent_broad_exception() -> None:
    source = '''
try:
    execute_stage()
except Exception:
    pass
'''
    issues = source_control_literal_issues(
        source,
        label="quwoquan_data/scripts/content/execution/sample.py",
    )
    assert any("not pass silently" in issue for issue in issues)


def test_control_literals_reject_provider_defaults_and_inline_query_timeout() -> None:
    source = '''
def query(*, retries=3, backoff_seconds=8.0, timeout_seconds=90):
    return "[out:json][timeout:45];"
'''
    issues = source_control_literal_issues(
        source,
        label="quwoquan_data/scripts/governance/coverage/sample.py",
    )
    assert sum("runtime control default" in issue for issue in issues) == 3
    assert any("provider query timeout" in issue for issue in issues)


def test_control_literals_reject_mutable_target_and_partial_delivery_contracts() -> None:
    source = "\n".join(
        (
            'STATE_FIELDS = ("' + "abandoned" + 'Objects", "' + "replacement" + 'Objects")',
            'COMPLETION_MODE = "' + "best_effort_with_reasoned" + '_rejects"',
        )
    )

    issues = source_control_literal_issues(
        source,
        label="quwoquan_data/scripts/content/execution/example.py",
    )

    assert len([issue for issue in issues if "retired mutable-target" in issue]) == 3
