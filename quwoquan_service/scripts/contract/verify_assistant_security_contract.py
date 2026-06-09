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
SERVICE_PATH = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "assistant"
    / "assistant_run"
    / "service.yaml"
)

REQUIRED_AUTH_OPERATIONS = {
    "SearchXiaoquResults",
    "CreateAssistantConversation",
    "GetAssistantConversation",
    "CreateAssistantTurn",
    "GetAssistantTurn",
    "StreamAssistantTurn",
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
    data = yaml.safe_load(SERVICE_PATH.read_text(encoding="utf-8"))
    routes = data.get("api_routes") if isinstance(data, dict) else None
    if not isinstance(routes, list):
        print(f"FAIL: {SERVICE_PATH} missing api_routes", file=sys.stderr)
        return 1

    by_operation = {
        str(route.get("operation")): route
        for route in routes
        if isinstance(route, dict) and route.get("operation")
    }
    failures: list[str] = []
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
