"""stackctl `docker-dependencies`：基础镜像预热、校验与过期检测。"""

from __future__ import annotations

import argparse
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "docker-dependencies",
        help="prepare/verify/check-outdated local Docker base-image cache",
    )
    parser.add_argument(
        "--action",
        choices=("prepare", "verify", "check-outdated"),
        default="prepare",
    )
    parser.add_argument("--report-dir", default=argparse.SUPPRESS)


def command_docker_dependencies(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.lib.docker_dependencies import (
        DockerDependencyError,
        check_outdated,
        ensure_prepared,
        verify_cache,
    )

    started_monotonic, started_at = _stackctl._start_timing()
    action = str(getattr(args, "action", "prepare") or "prepare")
    report_dir = _stackctl.resolve_report_dir(args, "repo", "docker-dependencies")
    details: list[str] = []
    evidence: dict[str, Any] = {"action": action}
    exit_code = 0
    try:
        if action == "prepare":
            evidence.update(ensure_prepared())
            details.append("docker base images ready")
        elif action == "verify":
            ok, missing = verify_cache()
            evidence["missing"] = missing
            evidence["status"] = "cached" if ok else "missing"
            if not ok:
                raise DockerDependencyError(
                    "docker dependency cache missing: " + ", ".join(missing)
                )
            details.append("docker base-image cache is complete")
        else:
            evidence.update(check_outdated())
            details.append("docker dependency outdated check completed")
    except DockerDependencyError as exc:
        exit_code = 2
        details.append(str(exc))
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    status = "passed" if exit_code == 0 else "gate_block"
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "docker-dependencies",
            "action": action,
            "status": status,
            "evidence": evidence,
            "details": details,
            **timing,
        },
    )
    return {
        "exitCode": exit_code,
        "summary": f"stackctl docker-dependencies {action} {status}",
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
        **evidence,
    }
