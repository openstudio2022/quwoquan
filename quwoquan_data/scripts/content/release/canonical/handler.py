"""data publish — assemble release package from content outputs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.control_types import EXECUTION_MILESTONES, RolloutMilestone
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, execution_root
from content.release.canonical.baseline_release import build_empty_baseline_release
from content.release.canonical.aggregate_release import build_aggregate_release
from content.release.canonical.two_province_closure import TwoProvinceClosureError, build_pre_environment_attestations
from content.release.canonical.two_province_environment_closure import (
    TwoProvinceEnvironmentClosureError,
    build_environment_attestations,
)
from content.release.canonical.rollout_attestation import build_rollout_milestone_attestation
from content.release.canonical.rollout_milestone import RolloutMilestoneError


def handle_aggregate_release(args: argparse.Namespace) -> None:
    execution_ids = [item.strip() for item in str(args.execution_ids).split(",") if item.strip()]
    if not execution_ids:
        raise SystemExit("[publish aggregate] --execution-ids 不能为空")
    report = build_aggregate_release(
        publish_root=Path(args.publish_root or PUBLISH_ROOT),
        release_root=Path(args.release_root or (OUTPUT_ROOT / "data/releases")),
        release_id=str(args.release_id),
        execution_roots=[execution_root(item) for item in execution_ids],
        rollout_milestone=str(args.rollout_milestone),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_baseline_release(args: argparse.Namespace) -> None:
    report = build_empty_baseline_release(
        publish_root=Path(args.publish_root or PUBLISH_ROOT),
        release_root=Path(args.release_root or (OUTPUT_ROOT / "data/releases")),
        release_id=str(args.release_id),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_attest_two_province(args: argparse.Namespace) -> None:
    release_root = Path(args.release_root or (OUTPUT_ROOT / "data/releases")) / str(args.release_id)
    try:
        report = build_pre_environment_attestations(release_root)
    except (FileNotFoundError, TwoProvinceClosureError, ValueError) as exc:
        raise SystemExit(f"[publish attest-two-province] GATE_BLOCK: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_attest_two_province_environment(args: argparse.Namespace) -> None:
    release_root = Path(args.release_root or (OUTPUT_ROOT / "data/releases")) / str(args.release_id)
    try:
        report = build_environment_attestations(
            release_root=release_root,
            import_run_id=str(args.import_run_id),
            api_run_id=str(args.api_run_id),
            app_uat_report=Path(args.app_uat_report),
            rollback_target_release_id=str(args.rollback_target_release_id),
            rollback_run_id=str(args.rollback_run_id),
            replay_run_id=str(args.replay_run_id),
        )
    except (FileNotFoundError, TwoProvinceClosureError, TwoProvinceEnvironmentClosureError, ValueError) as exc:
        raise SystemExit(f"[publish attest-two-province-environment] GATE_BLOCK: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_attest_rollout_milestone(args: argparse.Namespace) -> None:
    release_root = Path(args.release_root or (OUTPUT_ROOT / "data/releases")) / str(args.release_id)
    try:
        report = build_rollout_milestone_attestation(
            release_root=release_root,
            import_run_id=str(args.import_run_id),
            api_run_id=str(args.api_run_id),
            app_uat_report=Path(args.app_uat_report),
            rollback_target_release_id=str(args.rollback_target_release_id),
            rollback_run_id=str(args.rollback_run_id),
            replay_run_id=str(args.replay_run_id),
        )
    except (FileNotFoundError, RolloutMilestoneError, ValueError) as exc:
        raise SystemExit(f"[publish attest-rollout-milestone] GATE_BLOCK: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("release", help="从 canonical publish 构建 immutable release")
    commands = p.add_subparsers(dest="release_command", required=True)
    aggregate = commands.add_parser(
        "aggregate",
        help="从 approved executions 与 canonical publish 构建唯一不可变发布包",
    )
    aggregate.add_argument("--release-id", required=True)
    aggregate.add_argument("--execution-ids", required=True, help="逗号分隔 executionId")
    aggregate.add_argument(
        "--rollout-milestone",
        required=True,
        choices=tuple(
            item.value for item in (*EXECUTION_MILESTONES, RolloutMilestone.LAUNCH)
        ),
        help="该累计 immutable release 对应的 rollout 里程碑",
    )
    aggregate.add_argument("--publish-root")
    aggregate.add_argument("--release-root")
    aggregate.set_defaults(handler=handle_aggregate_release)
    baseline = commands.add_parser(
        "baseline",
        help="创建用于真实 sync rollback 的 immutable 空 desired-state release",
    )
    baseline.add_argument("--release-id", required=True)
    baseline.add_argument("--publish-root")
    baseline.add_argument("--release-root")
    baseline.set_defaults(handler=handle_baseline_release)
    closure = commands.add_parser(
        "attest-two-province",
        help="仅在 rollout contract 的全部 execution/source/media/review 闭合后写入最终静态 attestations",
    )
    closure.add_argument("--release-id", required=True)
    closure.add_argument("--release-root")
    closure.set_defaults(handler=handle_attest_two_province)
    environment_closure = commands.add_parser(
        "attest-two-province-environment",
        help="仅从 Gamma importer/API/Patrol/rollback-replay 运行证据写最终环境 attestations",
    )
    environment_closure.add_argument("--release-id", required=True)
    environment_closure.add_argument("--release-root")
    environment_closure.add_argument("--import-run-id", required=True)
    environment_closure.add_argument("--api-run-id", required=True)
    environment_closure.add_argument("--app-uat-report", required=True)
    environment_closure.add_argument("--rollback-target-release-id", required=True)
    environment_closure.add_argument("--rollback-run-id", required=True)
    environment_closure.add_argument("--replay-run-id", required=True)
    environment_closure.set_defaults(handler=handle_attest_two_province_environment)
    rollout_closure = commands.add_parser(
        "attest-rollout-milestone",
        help="从 Gamma import/API/App UAT/rollback/replay 证据冻结 canary/M1/M2/M3/H10K 准出",
    )
    rollout_closure.add_argument("--release-id", required=True)
    rollout_closure.add_argument("--release-root")
    rollout_closure.add_argument("--import-run-id", required=True)
    rollout_closure.add_argument("--api-run-id", required=True)
    rollout_closure.add_argument("--app-uat-report", required=True)
    rollout_closure.add_argument("--rollback-target-release-id", required=True)
    rollout_closure.add_argument("--rollback-run-id", required=True)
    rollout_closure.add_argument("--replay-run-id", required=True)
    rollout_closure.set_defaults(handler=handle_attest_rollout_milestone)
