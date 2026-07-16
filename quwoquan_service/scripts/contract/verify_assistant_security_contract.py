#!/usr/bin/env python3
"""Verify commercial Xiaoqu assistant routes do not regress to public auth."""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


ROOT = Path(__file__).resolve().parents[3]
SERVICE_DIR = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "assistant"
)

REQUIRED_AUTH_OPERATIONS = {
    "SearchXiaoquResults",
    "CreateAssistantConversation",
    "GetAssistantConversation",
    "StartAssistantRun",
    "GetAssistantRun",
    "ReportPageContext",
    "GetEntryPersonalization",
    "GetSuggestedActions",
    "ReportInteractionEvent",
    "ReportScorecard",
    "ListSkillSubscriptions",
    "CreateSkillSubscription",
    "GetSkillSubscription",
    "UpdateSkillSubscriptionStatus",
    "TickSkillSubscriptionCron",
    "ListAssistantTasks",
    "ListAssistantMemories",
    "GetLearningOpsSummary",
    "GrantSkillConsent",
    "RevokeSkillConsent",
    "ListConsents",
}


def route_auth_mode(route: dict) -> str:
    security = route.get("security")
    if isinstance(security, dict):
        return str(security.get("auth_mode") or "").strip().lower()
    if str(route.get("auth") or "").strip().lower() == "required":
        return "required"
    if route.get("auth_required") is True:
        return "required"
    return "public"


def main() -> int:
    by_operation: dict[str, dict] = {}
    failures: list[str] = []
    service_paths = sorted(SERVICE_DIR.glob("*/service.yaml"))
    if not service_paths:
        print(f"FAIL: {SERVICE_DIR} has no service metadata", file=sys.stderr)
        return 1
    for service_path in service_paths:
        data = yaml.safe_load(service_path.read_text(encoding="utf-8"))
        routes = data.get("api_routes") if isinstance(data, dict) else None
        if not isinstance(routes, list):
            failures.append(f"{service_path}: missing api_routes")
            continue
        for route in routes:
            if not isinstance(route, dict) or not route.get("operation"):
                continue
            operation = str(route["operation"])
            if operation in by_operation:
                failures.append(f"{operation}: duplicate metadata route")
                continue
            by_operation[operation] = route
    for operation in sorted(REQUIRED_AUTH_OPERATIONS):
        route = by_operation.get(operation)
        if route is None:
            failures.append(f"{operation}: missing route")
            continue
        mode = route_auth_mode(route)
        if mode != "required":
            failures.append(f"{operation}: auth_mode={mode!r}, want 'required'")
    if failures:
        print(
            "verify_assistant_security_contract: FAIL\n  " + "\n  ".join(failures),
            file=sys.stderr,
        )
        return 1
    print("verify_assistant_security_contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
