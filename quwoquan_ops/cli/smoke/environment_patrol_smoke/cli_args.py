# CLI 参数解析与输出脱敏（parse_args、release UAT case 装载、redaction、输出摘要）。
# 正文自 run_environment_patrol_smoke.py 逐字搬入。
# 注意：本模块 docstring 被 parse_args 的 ``argparse.ArgumentParser(description=__doc__)``
# 逐字消费，必须与拆分前入口文件的 docstring 保持一致，不得改写成中文职责说明。
"""Run page-level Patrol smoke tests for one environment target."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

from .constants import (
    DEFAULT_REPORT,
    DEFAULT_TARGET,
    RELEASE_APP_UAT_DEFINES,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument(
        "--remote-api-evidence-report",
        default="",
        help="已通过的 Remote API UAT report；写入同一设备 CaseResult 的 requestId/traceId 证据。",
    )
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--env-name", "--environment-alias", dest="env_name", default="local-gamma")
    parser.add_argument(
        "--rollout-stage",
        choices=("canary", "5", "20", "50", "100"),
        default="",
        help="Prod rollout stage; it is evidence metadata, never a fifth environment.",
    )
    parser.add_argument("--runtime-env", default="")
    parser.add_argument(
        "--runtime-mode",
        choices=("immutable_candidate", "test_live"),
        default="",
        help="Explicit stackctl-selected Provider runtime rail.",
    )
    parser.add_argument("--api-contract-env", default="")
    parser.add_argument(
        "--candidate-digest",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_CANDIDATE_DIGEST", ""
        ).strip(),
        help=(
            "Immutable candidate digest required by the Gamma account-enforcement "
            "physical-device UAT."
        ),
    )
    parser.add_argument("--gateway-base-url", default="")
    parser.add_argument("--product-ops-base-url", default="")
    parser.add_argument("--media-avatar-base-url", default="")
    parser.add_argument("--media-image-base-url", default="")
    parser.add_argument("--media-video-base-url", default="")
    parser.add_argument("--media-upload-base-url", default="")
    parser.add_argument("--rtc-media-connection-url", default="")
    parser.add_argument(
        "--video-playback-canary-work-id",
        default=os.environ.get("VIDEO_PLAYBACK_CANARY_WORK_ID", "").strip(),
    )
    for destination, define_name in RELEASE_APP_UAT_DEFINES:
        parser.add_argument(
            f"--{destination.replace('_', '-')}",
            dest=destination,
            default=os.environ.get(define_name, "").strip(),
        )
    parser.add_argument(
        "--patrol-install-id",
        default=os.environ.get("QWQ_PATROL_INSTALL_ID", "").strip(),
        help=(
            "Optional one-run install identity template. Destructive account-closure "
            "journeys require a {device} placeholder."
        ),
    )
    parser.add_argument(
        "--account-closure-disposable-ack",
        action="store_true",
        help="Acknowledge irreversible closure of the injected disposable prod account.",
    )
    parser.add_argument(
        "--unauthenticated-auth-entry",
        action="store_true",
        help="Run a login Provider journey without preloading an authenticated session.",
    )
    parser.add_argument(
        "--persisted-device-session",
        action="store_true",
        help=(
            "Use the production auth restore path on a pre-provisioned physical "
            "device; valid only for the runtime-recovery UAT target."
        ),
    )
    parser.add_argument("--test-auth-token", default=os.environ.get("TEST_AUTH_TOKEN", "").strip())
    parser.add_argument(
        "--test-refresh-token",
        default=os.environ.get("TEST_REFRESH_TOKEN", "").strip(),
    )
    parser.add_argument(
        "--release-uat-cases",
        default="",
        help="Gamma data-release 生成的 homepage_verification_cases.json；用于 release-bound 实体主页真实消费验证",
    )
    parser.add_argument(
        "--current-owner-id",
        default=os.environ.get("APP_CURRENT_OWNER_ID", "").strip(),
    )
    parser.add_argument(
        "--current-persona-id",
        default=os.environ.get("APP_CURRENT_PERSONA_ID", "").strip(),
    )
    parser.add_argument("--platform", choices=("android", "ios", "all"), default="all")
    parser.add_argument("--device-id", action="append", default=[])
    parser.add_argument(
        "--stackctl-controlled-edge-fault",
        action="store_true",
        help=(
            "Internal app-content-uat mode: stop the receipt-bound local API Edge "
            "and restore it when the Patrol recovery handshake is observed."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _load_release_uat_cases_b64(path_value: str) -> str:
    """Validate a runtime-only Gamma UAT manifest before injecting it into Patrol."""
    path = Path(path_value).expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"release UAT cases unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("release UAT cases must be an object")
    allowed = {
        "schema",
        "environment",
        "releaseId",
        "runId",
        "importerReportRef",
        "generatedAt",
        "cases",
    }
    if set(payload) != allowed:
        raise ValueError("release UAT cases has an invalid field set")
    if payload.get("schema") != "quwoquan_data.homepage_verification_case_manifest":
        raise ValueError("release UAT cases schema is invalid")
    if payload.get("environment") != "gamma":
        raise ValueError("release UAT cases must target gamma")
    for field in ("releaseId", "runId", "importerReportRef", "generatedAt"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise ValueError(f"release UAT cases {field} is invalid")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("release UAT cases must contain at least one case")
    entity_refs: set[str] = set()
    homepage_ids: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or set(case) != {"entityRef", "homepageId", "title"}:
            raise ValueError(f"release UAT case {index} has an invalid field set")
        entity_ref = case.get("entityRef")
        homepage_id = case.get("homepageId")
        title = case.get("title")
        if not all(isinstance(value, str) and value.strip() for value in (entity_ref, homepage_id, title)):
            raise ValueError(f"release UAT case {index} has invalid values")
        if entity_ref in entity_refs or homepage_id in homepage_ids:
            raise ValueError(f"release UAT case {index} duplicates entity or homepage identity")
        entity_refs.add(entity_ref)
        homepage_ids.add(homepage_id)
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _redact_command(command: list[str]) -> list[str]:
    secret_defines = {
        "--dart-define=TEST_AUTH_TOKEN=": "--dart-define=TEST_AUTH_TOKEN=<redacted>",
        "--dart-define=TEST_REFRESH_TOKEN=": "--dart-define=TEST_REFRESH_TOKEN=<redacted>",
        "--dart-define=APP_CURRENT_OWNER_ID=": (
            "--dart-define=APP_CURRENT_OWNER_ID=<redacted>"
        ),
        "--dart-define=APP_CURRENT_PERSONA_ID=": (
            "--dart-define=APP_CURRENT_PERSONA_ID=<redacted>"
        ),
        "--dart-define=APP_CURRENT_USER_ID=": (
            "--dart-define=APP_CURRENT_USER_ID=<redacted>"
        ),
    }
    redacted: list[str] = []
    for item in command:
        if item.startswith("--dart-define-from-file="):
            replacement = "--dart-define-from-file=<ephemeral-secret-file>"
        else:
            replacement = next(
                (
                    placeholder
                    for prefix, placeholder in secret_defines.items()
                    if item.startswith(prefix)
                ),
                item,
            )
        redacted.append(replacement)
    return redacted


def _redact_text(output: str, secret_values: tuple[str, ...]) -> str:
    redacted = output
    representations: set[str] = set()
    for value in secret_values:
        if not value:
            continue
        raw = value.encode("utf-8")
        standard = base64.b64encode(raw).decode("ascii")
        urlsafe = base64.urlsafe_b64encode(raw).decode("ascii")
        representations.update(
            {value, standard, standard.rstrip("="), urlsafe, urlsafe.rstrip("=")}
        )
    for value in sorted(representations, key=len, reverse=True):
        redacted = redacted.replace(value, "<redacted>")
    return redacted


def summarize_output(output: str, *, max_lines: int = 120) -> str:
    lines = output.splitlines()
    if len(lines) <= max_lines:
        return output
    return "\n".join(
        [
            f"... omitted {len(lines) - max_lines} earlier lines ...",
            *lines[-max_lines:],
        ]
    )
