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


def test_control_literals__module_worker_count__contract__local_contract() -> None:
    issues = source_control_literal_issues(
        "REVIEW_WORKER_COUNT = 1\n",
        label="sample.py",
    )
    assert any("module control" in issue and "runtime policy" in issue for issue in issues)


def test_control_literals__retired_rollout_field__contract__local_contract() -> None:
    issues = source_control_literal_issues(
        "rolloutMilestone = 'scale'\n",
        label="sample.py",
    )
    assert any("retired task-specific" in issue for issue in issues)


def test_control_literals__historical_digest_reader__contract__local_contract() -> None:
    issues = source_control_literal_issues(
        "def source_digest_at_git_revision(revision):\n    return revision\n",
        label="sample.py",
    )
    assert any("retired single-track contract token" in issue for issue in issues)
