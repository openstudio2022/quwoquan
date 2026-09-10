"""聚合校验只检查，不在读操作前隐式回填内容库。"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-041
from __future__ import annotations

import pytest

from verify import handler as verify_handler


def test_verify_all_runs_each_gate_once_without_implicit_repair(monkeypatch):
    observed = []
    from content.release.canonical import rehydrate_media_holdings

    def forbidden_repair():
        pytest.fail("verify must not repair or admit library bytes")

    monkeypatch.setattr(rehydrate_media_holdings, "main", forbidden_repair)
    monkeypatch.setattr(verify_handler, "_run", lambda name, _argv=None: observed.append(name) or 0)
    assert verify_handler.handle_all() == list(verify_handler._GATES)
    assert len(observed) == len(set(observed))
    assert observed.count("publish-closure") == 1
    assert "active-runtime-preflight" not in observed


def test_source_scope_never_loads_runtime_outputs_and_retains_source_failures(monkeypatch):
    observed = []

    def gate(name, _argv=None):
        assert name not in verify_handler._RUNTIME_GATES
        observed.append(name)
        return int(name == "cli-first")

    monkeypatch.setattr(verify_handler, "_run", gate)
    with pytest.raises(SystemExit, match="cli-first"):
        verify_handler.handle_all(scope="source")
    assert observed == list(verify_handler._STATIC_GATES)
    assert {"content-execution-layout", "runtime-input-ownership", "publish-closure"} <= verify_handler._RUNTIME_GATES.keys()


def test_source_scope_is_explicit_and_invalid_scope_is_rejected(monkeypatch):
    import argparse

    parser = argparse.ArgumentParser()
    verify_handler.register_parser(parser.add_subparsers(dest="command", required=True))
    observed = []
    monkeypatch.setattr(verify_handler, "_run", lambda name, _argv=None: observed.append(name) or 0)
    args = parser.parse_args(["verify", "all", "--scope", "source"])
    args.handler(args)
    assert observed == list(verify_handler._STATIC_GATES)
    assert parser.parse_args(["verify", "all"]).scope == "all"
    with pytest.raises(ValueError, match="invalid verification scope"):
        verify_handler.handle_all(scope="unknown")


def test_verify_all_retains_failed_gate_without_repair(monkeypatch):
    observed = []

    def gate(name, _argv=None):
        observed.append(name)
        return int(name == "publish-closure")

    monkeypatch.setattr(verify_handler, "_run", gate)
    with pytest.raises(SystemExit, match="publish-closure"):
        verify_handler.handle_all()
    assert observed == list(verify_handler._GATES)
