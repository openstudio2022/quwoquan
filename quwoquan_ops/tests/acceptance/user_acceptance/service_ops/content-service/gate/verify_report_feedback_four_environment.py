from __future__ import annotations

import json
from pathlib import Path


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "quwoquan_ops").is_dir()
)
OUTPUT_ROOT = ROOT / ".qwq_output" / "env"

EXPECTED_PROFILES = {
    "alpha": "smoke",
    "beta": "integration",
    "gamma": "release",
    "prod": "release",
}
FEATURE_PROBE_SCHEMA = "content-report-feedback-lifecycle-probe-report"
FEATURE_PROBE_MODES = {
    "beta": "lifecycle",
    "gamma": "lifecycle",
    "prod": "read-only",
}
READ_ONLY_STEPS = frozenset({"healthz", "list_my_reports_privacy"})
LIFECYCLE_STEPS = READ_ONLY_STEPS | frozenset(
    {
        "create_idempotent_and_list",
        "reporter_cannot_dismiss",
        "dislike_undo_idempotent",
        "operator_dismiss_to_reporter",
    }
)
LIFECYCLE_FACTS = frozenset(
    {
        "createIdempotent",
        "reporterIsolated",
        "operatorQueueProjected",
        "dismissedVisibleToReporter",
        "notificationProjected",
        "negativeFeedbackUndone",
    }
)

REQUIRED_CODE_EVIDENCE = (
    "quwoquan_app/test/local_contract/ui/content/more_action_popup__functional__local_contract_test.dart",
    "quwoquan_app/test/user_acceptance/patrol/settings/my_reports_page__user_acceptance_test.dart",
    "quwoquan_app/test/local_contract/ui/settings/pages/blocked_keywords/blocked_keywords_page__local_contract_test.dart",
    "quwoquan_service/services/content-service/tests/api_integration/content/post/report_crud_contract__api_integration_test.go",
    "quwoquan_service/services/content-service/tests/api_integration/content/post/report_dismiss_contract__api_integration_test.go",
    "quwoquan_service/services/notification-service/tests/api_integration/notification_delivery/notification/interaction_notification_stream__api_integration_test.go",
    "quwoquan_service/services/user-service/cmd/acceptance-session/main__local_contract_test.go",
    "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/content-service/smoke/run_report_feedback_lifecycle_probe.py",
    "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/content-service/smoke/report_feedback_probe_support.py",
)


def _latest_report(environment: str, profile: str) -> tuple[Path, dict[str, object]]:
    candidates: list[tuple[Path, dict[str, object]]] = []
    runs = OUTPUT_ROOT / environment / "runs"
    for report_path in runs.glob("*/report.json"):
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("command") == "verify" and payload.get("profile") == profile:
            candidates.append((report_path, payload))
    if not candidates:
        raise AssertionError(
            f"{environment} 缺少 stackctl verify profile={profile} 报告"
        )
    return max(candidates, key=lambda item: str(item[1].get("startedAt", "")))


def _feature_report_for_stack_run(
    stack_report_path: Path,
    environment: str,
    mode: str,
) -> tuple[Path, dict[str, object]]:
    report_path = stack_report_path.parent / "report-feedback-lifecycle.json"
    if not report_path.is_file():
        raise AssertionError(
            f"{environment} stackctl verify 报告缺少同次运行的举报反馈对象级探针 "
            f"mode={mode}"
        )
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssertionError(
            f"{environment} 举报反馈对象级探针报告不可解析: "
            f"{report_path.relative_to(ROOT)}"
        ) from exc
    environment_payload = payload.get("environment")
    if (
        payload.get("schema") != FEATURE_PROBE_SCHEMA
        or payload.get("mode") != mode
        or not isinstance(environment_payload, dict)
        or environment_payload.get("env") != environment
    ):
        raise AssertionError(
            f"{environment} stackctl verify 同次举报反馈探针契约不匹配"
        )
    return report_path, payload


def _passed_steps(report: dict[str, object]) -> frozenset[str]:
    raw_steps = report.get("steps")
    if not isinstance(raw_steps, list):
        return frozenset()
    return frozenset(
        str(step.get("name"))
        for step in raw_steps
        if isinstance(step, dict) and step.get("status") == "passed"
    )


def _feature_report_issues(
    environment: str,
    mode: str,
    report: dict[str, object],
) -> list[str]:
    issues: list[str] = []
    if report.get("status") != "passed":
        issues.append(
            f"{environment} 举报反馈探针 status={report.get('status', '')}"
        )
        return issues
    required_steps = LIFECYCLE_STEPS if mode == "lifecycle" else READ_ONLY_STEPS
    missing_steps = sorted(required_steps - _passed_steps(report))
    if missing_steps:
        issues.append(
            f"{environment} 举报反馈探针缺少步骤: {', '.join(missing_steps)}"
        )
    if mode == "lifecycle":
        facts = report.get("journeyEvidence")
        missing_facts = sorted(
            fact
            for fact in LIFECYCLE_FACTS
            if not isinstance(facts, dict) or facts.get(fact) is not True
        )
        if missing_facts:
            issues.append(
                f"{environment} 举报反馈探针缺少事实: {', '.join(missing_facts)}"
            )
    return issues


def verify() -> dict[str, dict[str, str]]:
    missing = [path for path in REQUIRED_CODE_EVIDENCE if not (ROOT / path).is_file()]
    if missing:
        raise AssertionError(f"举报反馈代码证据缺失: {missing}")

    newest_code_mtime = max((ROOT / path).stat().st_mtime for path in REQUIRED_CODE_EVIDENCE)
    evidence: dict[str, dict[str, str]] = {}
    failures: list[str] = []
    for environment, profile in EXPECTED_PROFILES.items():
        report_path, report = _latest_report(environment, profile)
        status = str(report.get("status", ""))
        evidence[environment] = {
            "stack": str(report_path.relative_to(ROOT)),
        }
        if status != "ok":
            failures.append(
                f"{environment} profile={profile} status={status} "
                f"report={evidence[environment]['stack']}"
            )
        elif report_path.stat().st_mtime < newest_code_mtime:
            failures.append(
                f"{environment} profile={profile} 报告早于当前举报反馈代码，必须重跑"
            )
        mode = FEATURE_PROBE_MODES.get(environment)
        if mode is None:
            continue
        try:
            feature_path, feature_report = _feature_report_for_stack_run(
                report_path,
                environment,
                mode,
            )
        except AssertionError as exc:
            failures.append(str(exc))
            continue
        evidence[environment]["feature"] = str(feature_path.relative_to(ROOT))
        if feature_path.stat().st_mtime < newest_code_mtime:
            failures.append(
                f"{environment} 举报反馈对象级探针报告早于当前代码，必须重跑"
            )
        failures.extend(
            _feature_report_issues(environment, mode, feature_report)
        )
    if failures:
        raise AssertionError("四环境举报反馈验收未闭合:\n- " + "\n- ".join(failures))
    return evidence


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
