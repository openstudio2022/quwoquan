"""Explicit prod-hosted read-only orchestration and mutation rejection."""

from __future__ import annotations

import argparse
from typing import Any

PROFILE = "hosted-read-only"
ALLOWED_CHECKS = ("status", "health", "verify", "inspect")
PROHIBITED_ACTIONS = (
    "up",
    "deploy",
    "repair",
    "rollout",
    "rollback",
    "restart",
    "device-patrol",
    "local-app",
    "actor-mutation",
)


def rejection(action: str) -> dict[str, Any]:
    normalized = str(action or "").strip()
    return {
        "exitCode": 2,
        "summary": f"prod-hosted {PROFILE} rejects mutation",
        "details": [
            f"action {normalized or '<empty>'} is prohibited by {PROFILE}",
            "allowed checks: status, health, release verify, inspect",
        ],
        "profile": PROFILE,
        "target": "prod-hosted",
        "status": "gate_block",
        "prohibitedAction": normalized,
    }


def command_hosted_read_only(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    checks = tuple(dict.fromkeys(str(item).strip() for item in args.check if str(item).strip()))
    if not checks:
        checks = ALLOWED_CHECKS
    invalid = sorted(set(checks) - set(ALLOWED_CHECKS))
    if invalid:
        return rejection(invalid[0])
    if args.target != "prod-hosted":
        return {
            "exitCode": 2,
            "summary": f"{PROFILE} requires prod-hosted",
            "details": ["--target must be prod-hosted"],
            "profile": PROFILE,
        }

    results: list[dict[str, Any]] = []
    for check in checks:
        if check == "status":
            child = _stackctl.command_status(
                argparse.Namespace(
                    command="status", target="prod-hosted", scope="full",
                    output_format="json", report_dir="",
                )
            )
        elif check == "health":
            child = _stackctl.command_health(
                argparse.Namespace(
                    command="health", target="prod-hosted", scope="full",
                    read_only=True, output_format="json", report_dir="",
                )
            )
        elif check == "verify":
            child = _stackctl.command_verify(
                argparse.Namespace(
                    command="verify", service="", kind="all", profile="release",
                    env="prod", target="prod-hosted", test_data_request="",
                    backup_recovery_receipt="", output_format="json", report_dir="",
                )
            )
        else:
            child = _stackctl.command_inspect(
                argparse.Namespace(
                    command="inspect", target="prod-hosted", kind="release",
                    scope="full", currentness=True, output_format="json", report_dir="",
                )
            )
        results.append({
            "check": check,
            "exitCode": child.get("exitCode"),
            "summary": child.get("summary", ""),
            "reportDir": child.get("reportDir", ""),
            "details": list(child.get("details") or []),
        })
    failed = [item for item in results if int(item.get("exitCode") or 0) != 0]
    return {
        "exitCode": 0 if not failed else 2,
        "summary": (
            "prod-hosted read-only inspection passed"
            if not failed
            else "prod-hosted read-only inspection is GATE_BLOCK"
        ),
        "details": [item["summary"] for item in results],
        "profile": PROFILE,
        "target": "prod-hosted",
        "readOnly": True,
        "remoteMutationPerformed": False,
        "devicePatrol": {"status": "not_executed", "reason": "hosted-read-only forbids device Patrol"},
        "localApp": {"status": "not_executed", "reason": "hosted-read-only forbids local App launch"},
        "actorMutation": {"status": "not_executed", "reason": "hosted-read-only forbids actor mutation"},
        "checks": results,
    }


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser("hosted-read-only")
    parser.add_argument("--target", choices=("prod-hosted",), default="prod-hosted")
    parser.add_argument("--check", action="append", choices=ALLOWED_CHECKS, default=[])
