"""Retired EnvironmentAcceptanceFact writer command surface."""

from __future__ import annotations

import argparse

import pytest

from quwoquan_ops.cli.commands import app_uat_evidence as subject


def test_environment_acceptance_append_is_not_registered_or_dispatched() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subject.register_parser(subparsers)

    assert "environment-acceptance-append" not in subject.COMMAND_HANDLERS
    assert not hasattr(subject, "build_environment_acceptance_append_command")
    assert not hasattr(subject, "command_environment_acceptance_append")
    with pytest.raises(SystemExit):
        parser.parse_args(["environment-acceptance-append"])
