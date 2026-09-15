# spec_ref: specs/feature-tree/discovery-content/spec.md#req-002
"""post-safety-runtime canonical stackctl 入口的 plan/apply/verify 契约。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import post_safety_runtime as entry


def args(action, **values):
    result = argparse.Namespace(action=action, target="alpha-local", plan_ref="",
        confirm_post_safety_runtime=False, report_dir="", command="post-safety-runtime")
    for key, value in values.items():
        setattr(result, key, value)
    return result


def context():
    return {"candidate": {"manifest": {"packageDigest": "sha256:" + "a" * 64}},
        "candidateBytesDigest": "sha256:" + "b" * 64, "startupMaterialDigest": "sha256:" + "c" * 64,
        "targetBinding": {"target": "alpha-local"}, "sourceBinding": {"target": "alpha-local"},
        "postSafetyMaterialRoot": "/canonical/post-safety/generation"}


def test_parser_exposes_single_plan_apply_verify_surface():
    for action in ("plan", "apply", "verify"):
        parsed = stackctl.build_parser().parse_args(["post-safety-runtime", action, "--target", "alpha-local"])
        assert parsed.command == "post-safety-runtime"
        assert parsed.action == action


def test_plan_is_zero_write_and_apply_requires_exact_confirmation(tmp_path, monkeypatch):
    report = tmp_path / "output/env/alpha/runs/post-safety"
    monkeypatch.setattr(entry.output_paths, "output_root", lambda: tmp_path / "output")
    monkeypatch.setattr(stackctl, "resolve_report_dir", lambda args, env, target: report)
    startup = mock.Mock(postSafetyCurrent=None)
    monkeypatch.setattr(entry, "_runtime_dependencies", lambda: {})
    monkeypatch.setattr(entry, "_candidate_context", lambda target, dependencies: (context(), None, None, None, startup, b"{}", None))
    planned = entry.command_post_safety_runtime(args("plan", report_dir=str(report)))
    assert planned["exitCode"] == 0 and planned["resourceMutation"] is False
    path, digest = planned["planRef"].rsplit("=", 1)
    assert Path(path).read_bytes() and digest == entry._digest(Path(path).read_bytes())
    assert entry.command_post_safety_runtime(args("apply", plan_ref=planned["planRef"]))["exitCode"] == 2


def test_apply_revalidates_plan_inside_canonical_lock(tmp_path, monkeypatch):
    report = tmp_path / "output/env/alpha/runs/post-safety"
    monkeypatch.setattr(entry.output_paths, "output_root", lambda: tmp_path / "output")
    monkeypatch.setattr(stackctl, "resolve_report_dir", lambda args, env, target: report)
    startup = mock.Mock(postSafetyCurrent=None)
    monkeypatch.setattr(entry, "_runtime_dependencies", lambda: {})
    monkeypatch.setattr(entry, "_candidate_context", lambda target, dependencies: (context(), None, None, None, startup, b"{}", None))
    planned = entry.command_post_safety_runtime(args("plan", report_dir=str(report)))
    calls = []
    class Lock:
        def __enter__(self): calls.append("locked")
        def __exit__(self, *unused): pass
    monkeypatch.setattr(entry, "local_stack_operation_lock", lambda target: Lock())
    original = entry._load_plan
    def drifting(value):
        loaded = original(value)
        if calls:
            changed = dict(loaded[2]); changed["context"] = {**changed["context"], "candidateBytesDigest": "sha256:" + "d" * 64}
            return loaded[0], loaded[1], changed
        return loaded
    monkeypatch.setattr(entry, "_load_plan", drifting)
    rejected = entry.command_post_safety_runtime(args("apply", plan_ref=planned["planRef"], confirm_post_safety_runtime=True))
    assert rejected["exitCode"] == 2 and calls == ["locked"]


def test_prod_and_evidence_cli_inputs_are_not_parseable():
    for argv in (["post-safety-runtime", "plan", "--target", "prod-hosted"],
                 ["post-safety-runtime", "apply", "--target", "alpha-local", "--evidence-ref", "x"]):
        try:
            stackctl.build_parser().parse_args(argv)
        except SystemExit:
            pass
        else:
            raise AssertionError("unsafe post safety CLI input accepted")
