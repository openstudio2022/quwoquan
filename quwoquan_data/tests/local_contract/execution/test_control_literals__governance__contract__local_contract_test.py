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


def test_control_literals_reject_mapping_execution_documents_and_raw_state_status() -> None:
    source = '''
from collections.abc import Mapping
class ExecutionState(Mapping):
    pass
state["status"] = "repairing"
'''

    issues = source_control_literal_issues(
        source,
        label="quwoquan_data/scripts/content/execution/sample.py",
    )

    assert any("not Mapping inheritance" in issue for issue in issues)
    assert any("must use ExecutionStateStatus" in issue for issue in issues)


def test_control_literals_accept_typed_execution_state_status() -> None:
    source = '''
from core.control_types import ExecutionStateStatus
state.status = ExecutionStateStatus.REPAIRING
'''

    assert source_control_literal_issues(
        source,
        label="quwoquan_data/scripts/content/execution/sample.py",
    ) == []


def test_control_literals_reject_mapping_style_workflow_state_and_wire_status() -> None:
    source = '''
from core.control_types import ExecutionStateStatus
def update_state(state: dict):
    state.get("status")
    state.pop("waitingCheckpoint", None)
    state["status"] = ExecutionStateStatus.REPAIRING.value
'''

    issues = source_control_literal_issues(
        source,
        label="quwoquan_data/scripts/content/execution/sample.py",
    )

    assert any("must use ExecutionStateTransition" in issue for issue in issues)
    assert any("not mapping get()" in issue for issue in issues)
    assert any("not mapping pop()" in issue for issue in issues)
    assert any("not mapping subscripts" in issue for issue in issues)


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


def test_control_literals_reject_argparse_and_getattr_runtime_fallbacks() -> None:
    source = '''
parser.add_argument("--max-workers", type=int, default=10)
workers = int(getattr(args, "max_workers", 3) or 3)
'''
    issues = source_control_literal_issues(
        source,
        label="quwoquan_data/scripts/content/execution/sample.py",
    )
    assert any("argparse runtime default" in issue for issue in issues)
    assert any("runtime getattr fallback" in issue for issue in issues)


def test_control_literals_reject_runtime_function_defaults_in_core() -> None:
    source = '''
def invoke(*, timeout_seconds=20, max_retries=3, max_workers=4):
    return timeout_seconds + max_retries + max_workers
'''
    issues = source_control_literal_issues(
        source,
        label="quwoquan_data/scripts/core/sample.py",
    )
    assert sum("runtime control default" in issue for issue in issues) == 3


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


def test_control_literals_reject_versioned_contracts_and_version_fields() -> None:
    # 拼接构造退役键名，避免仓库静态扫描把负例字面量误判为双轨残留。
    retired_envelope = "schema" + "Version"
    source = f'''
CONTRACT = "quwoquan_data.release"
payload = {{"schema": "execution-model-readiness-v1", "{retired_envelope}": 1}}
'''

    issues = source_control_literal_issues(
        source,
        label="quwoquan_data/scripts/content/release/example.py",
    )

    assert any("versioned data contract" in issue for issue in issues)
    assert any("explicit contract version field" in issue for issue in issues)


def test_control_literals_accept_single_unversioned_contract() -> None:
    source = '''
CONTRACT = "quwoquan_data.release"
payload = {"schema": "quwoquan_data.release"}
'''

    assert source_control_literal_issues(
        source,
        label="quwoquan_data/scripts/content/release/example.py",
    ) == []
