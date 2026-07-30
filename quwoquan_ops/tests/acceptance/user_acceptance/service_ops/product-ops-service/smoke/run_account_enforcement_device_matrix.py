#!/usr/bin/env python3
"""Run one account-enforcement App phase on physical Android and iPhone."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "quwoquan_app").is_dir() and (
            candidate / "quwoquan_service"
        ).is_dir():
            return candidate
    raise RuntimeError("cannot locate quwoquan repository root")


REPO_ROOT = _find_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)


SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "quwoquan_ops"
    / "tests"
    / "acceptance"
    / "user_acceptance"
    / "service_ops"
    / "product-ops-service"
    / "smoke"
    / "account_enforcement_gamma_uat_manifest.json"
)
PHASES = ("suspended", "restored")
PHASE_TOKEN_ENVIRONMENTS = {
    "suspended": (
        "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_SUSPENDED_ACCESS_TOKEN",
        "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_SUSPENDED_REFRESH_TOKEN",
    ),
    "restored": (
        "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_RESTORED_ACCESS_TOKEN",
        "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_RESTORED_REFRESH_TOKEN",
    ),
}
OWNER_ENV = "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_OWNER_ID"
PERSONA_ENV = "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_PERSONA_ID"


def _output_root() -> Path:
    configured = os.environ.get("QWQ_OUTPUT_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (REPO_ROOT / ".qwq_output").resolve()


def _report_path(raw: str, phase: str) -> Path:
    candidate = Path(raw).expanduser() if raw.strip() else (
        _output_root()
        / "env"
        / "gamma"
        / "runs"
        / "account-enforcement-gamma-uat"
        / f"{phase}-device-report.json"
    )
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(_output_root())
    except ValueError as exc:
        raise ValueError("device report must stay below QWQ_OUTPUT_ROOT") from exc
    return candidate


def _write_gate_block(path: Path, phase: str, candidate_digest: str, issue: str) -> None:
    if path.exists():
        raise ValueError(f"device report already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "suiteId": "account_enforcement_gamma_device_matrix",
                "status": "gate_block",
                "runtimeEnv": "gamma",
                "apiContractEnv": "gamma",
                "composition": "production_remote",
                "phase": phase,
                "candidateDigest": candidate_digest,
                "devices": [],
                "runs": [],
                "caseResults": [],
                "failureReason": issue,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _required_url(public_bases: dict[str, Any], key: str) -> str:
    value = str(public_bases.get(key) or "").strip()
    if not value:
        raise ValueError(f"gamma-local topology is missing publicBases.{key}")
    return value


def _patrol_target(manifest_path: Path, phase: str) -> str:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"account-enforcement UAT manifest is unreadable: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("account-enforcement UAT manifest must be a JSON object")
    reports = manifest.get("deviceReports")
    target = str(reports.get(phase) or "").strip() if isinstance(reports, dict) else ""
    if (
        manifest.get("schema") != "qwq.account-enforcement-gamma-uat-manifest"
        or manifest.get("environment") != "gamma"
        or manifest.get("target") != "gamma-local"
        or manifest.get("composition") != "production_remote"
        or not target.startswith("test/user_acceptance/patrol/user/")
        or not target.endswith("__user_acceptance_test.dart")
    ):
        raise ValueError("account-enforcement UAT manifest identity or Patrol target drift")
    return target


def build_command(args: argparse.Namespace, report: Path) -> tuple[list[str], dict[str, str]]:
    candidate_digest = str(args.candidate_digest or "").strip()
    if SHA256_RE.fullmatch(candidate_digest) is None:
        raise ValueError("candidateDigest must be canonical sha256")
    access_env, refresh_env = PHASE_TOKEN_ENVIRONMENTS[args.phase]
    required_inputs = {
        access_env: os.environ.get(access_env, "").strip(),
        refresh_env: os.environ.get(refresh_env, "").strip(),
        OWNER_ENV: os.environ.get(OWNER_ENV, "").strip(),
        PERSONA_ENV: os.environ.get(PERSONA_ENV, "").strip(),
    }
    missing = sorted(name for name, value in required_inputs.items() if not value)
    if missing:
        raise ValueError(
            "missing controlled account-enforcement device inputs: "
            + ", ".join(missing)
        )
    if not args.device_id:
        raise ValueError(
            "account-enforcement UAT requires explicit physical Android and iPhone device ids"
        )

    target = get_target(load_environment_topology(), "gamma-local")
    public_bases = target.get("publicBases")
    if not isinstance(public_bases, dict):
        raise ValueError("gamma-local topology has no publicBases")
    command = [
        sys.executable,
        "quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py",
        "--env-name",
        "local-gamma",
        "--runtime-env",
        "gamma",
        "--api-contract-env",
        "gamma",
        "--gateway-base-url",
        _required_url(public_bases, "api"),
        "--product-ops-base-url",
        _required_url(public_bases, "productOps"),
        "--media-avatar-base-url",
        _required_url(public_bases, "mediaAvatar"),
        "--media-image-base-url",
        _required_url(public_bases, "mediaImage"),
        "--media-video-base-url",
        _required_url(public_bases, "mediaVideo"),
        "--media-upload-base-url",
        _required_url(public_bases, "mediaUpload"),
        "--rtc-media-connection-url",
        _required_url(public_bases, "rtc"),
        "--target",
        _patrol_target(Path(args.manifest).expanduser().resolve(), args.phase),
        "--platform",
        "all",
        "--candidate-digest",
        candidate_digest,
        "--report",
        str(report),
    ]
    for device_id in args.device_id:
        normalized = str(device_id).strip()
        if normalized:
            command.extend(("--device-id", normalized))
    environment = dict(os.environ)
    environment.update(
        {
            "TEST_AUTH_TOKEN": required_inputs[access_env],
            "TEST_REFRESH_TOKEN": required_inputs[refresh_env],
            "APP_CURRENT_OWNER_ID": required_inputs[OWNER_ENV],
            "APP_CURRENT_PERSONA_ID": required_inputs[PERSONA_ENV],
        }
    )
    return command, environment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument(
        "--candidate-digest",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_CANDIDATE_DIGEST", ""
        ),
    )
    parser.add_argument("--device-id", action="append", default=[])
    parser.add_argument("--report", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    candidate_digest = str(args.candidate_digest or "").strip()
    try:
        report = _report_path(args.report, args.phase)
        if report.exists():
            raise ValueError(f"device report already exists: {report}")
        command, environment = build_command(args, report)
    except ValueError as exc:
        issue = str(exc)
        try:
            report = _report_path(args.report, args.phase)
            _write_gate_block(report, args.phase, candidate_digest, issue)
        except ValueError as report_error:
            print(f"GATE_BLOCK: {issue}; report error: {report_error}", file=sys.stderr)
            return 2
        print(f"GATE_BLOCK: {issue}", file=sys.stderr)
        return 2
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=environment,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
