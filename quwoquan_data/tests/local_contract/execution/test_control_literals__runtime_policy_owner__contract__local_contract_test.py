from __future__ import annotations

from verify.verify_control_literals import source_control_literal_issues


def test_control_literals__runtime_default__contract__local_contract() -> None:
    issues = source_control_literal_issues(
        "def fetch(timeout_seconds=30):\n    return timeout_seconds\n",
        label="sample.py",
    )
    assert any("runtime policy" in issue for issue in issues)


def test_control_literals__typed_policy_read__contract__local_contract() -> None:
    issues = source_control_literal_issues(
        "def fetch(policy):\n    return policy.provider_timeouts.mediawiki_seconds\n",
        label="sample.py",
    )
    assert issues == []


def test_control_literals__retired_rollout_field__contract__local_contract() -> None:
    issues = source_control_literal_issues(
        "rolloutMilestone = 'scale'\n",
        label="sample.py",
    )
    assert any("retired task-specific" in issue for issue in issues)
