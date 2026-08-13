#!/usr/bin/env python3
# spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/spec.md#sit-001
# spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/spec.md#open-003
# readiness_case: circle_journey_probe_ops_env
"""SCN-014 主旅程公开读写面探针：实体主页 → 近期行动读面 → 建圈 → 加入 →
建群 → owner 名册投影 → 申请/审批 → 名册收敛 → 群会话绑定回读。

双隔离 Actor（PRIMARY/MEMBER）只来自 `stackctl verify` 的 ActorLease handoff；
每步走真实公开 HTTP 契约并输出可审计 step 证据，失败与超时如实分类，不伪造。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "quwoquan_app").is_dir() and (candidate / "quwoquan_service").is_dir():
            return candidate
    raise RuntimeError("cannot locate quwoquan repo root")


REPO_ROOT = _find_repo_root()
sys.path.insert(0, str(REPO_ROOT))
SUPPORT_DIR = Path(__file__).resolve().parents[1] / "support"
if str(SUPPORT_DIR) not in sys.path:
    sys.path.insert(0, str(SUPPORT_DIR))

from quwoquan_ops.cli.lib.local_environment_auth import (  # noqa: E402
    LocalAcceptanceSession,
    LocalEnvironmentHTTPError,
    request_local_environment_json,
)
from managed_circle_journey_handoff import (  # noqa: E402
    ManagedCircleJourneyHandoff,
    ManagedJourneyActor,
    load_journey_handoff_from_environment,
)

SCHEMA = "circle-journey-probe-report"
SCENARIO = "circle.scn014.homepage_to_group_conversation"
LOCAL_TARGETS = {"alpha": "alpha-local", "beta": "beta-local", "gamma": "gamma-local"}


class ProbeFailure(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=tuple(LOCAL_TARGETS), required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--homepage-query",
        default="西湖",
        help="公开发现面搜索词；probe 不书写固定业务对象 ID",
    )
    parser.add_argument("--binding-timeout-seconds", type=float, default=45.0)
    parser.add_argument("--roster-timeout-seconds", type=float, default=45.0)
    parser.add_argument(
        "--report",
        default=".qwq_output/env/gamma/runs/circle-journey/report.json",
    )
    return parser.parse_args()


def _data(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("data")
    return nested if isinstance(nested, dict) else payload


def _items(payload: dict[str, Any], step: str) -> list[dict[str, Any]]:
    raw = _data(payload).get("items")
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise ProbeFailure("contract_mismatch", f"{step} response has no object items")
    return raw


class ActorClient:
    def __init__(self, base_url: str, actor: ManagedJourneyActor) -> None:
        self.base_url = base_url
        self.persona_id = actor.persona_id
        self.session = LocalAcceptanceSession(
            owner_id=actor.owner_id,
            persona_id=actor.persona_id,
            access_token=actor.access_token,
            refresh_token=actor.refresh_token,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        operation_id: str,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        headers = {"X-Client-Operation-Id": operation_id}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            return request_local_environment_json(
                self.base_url,
                path=path,
                session=self.session,
                method=method,
                body=body,
                headers=headers,
                timeout_seconds=12.0,
            )
        except LocalEnvironmentHTTPError as exc:
            category = "auth_failed" if exc.status in {401, 403} else "http_error"
            raise ProbeFailure(
                category, f"{method} {path} returned HTTP {exc.status}"
            ) from exc


def _run_journey(
    args: argparse.Namespace,
    handoff: ManagedCircleJourneyHandoff,
    report: dict[str, Any],
) -> None:
    primary = ActorClient(args.base_url, handoff.actor("primary"))
    member = ActorClient(args.base_url, handoff.actor("member"))
    run_tag = uuid.uuid4().hex[:8]

    def step(name: str, evidence: dict[str, Any]) -> None:
        report["steps"].append({"name": name, "status": "passed", **evidence})

    # 1. 实体发现：公开搜索读面（release 实体，不书写固定 ID）。
    search = primary.request(
        "GET",
        "/homepages/search?query="
        + urllib.parse.quote(args.homepage_query)
        + "&limit=5",
        operation_id="circle.journey.SearchHomepages",
    )
    homepage_rows = _items(search, "homepage search")
    if not homepage_rows:
        raise ProbeFailure(
            "release_data_missing",
            f"homepage search {args.homepage_query!r} returned no release entities",
        )
    homepage_id = str(homepage_rows[0].get("homepageId") or homepage_rows[0].get("id") or "")
    if not homepage_id:
        raise ProbeFailure("contract_mismatch", "homepage search row lacks id")
    step("homepage_search", {"homepageIdDigest": homepage_id[:12]})

    # 2. 实体详情公开读面。
    detail = _data(
        primary.request(
            "GET",
            "/homepages/" + urllib.parse.quote(homepage_id),
            operation_id="circle.journey.GetHomepageDetail",
        )
    )
    if not detail:
        raise ProbeFailure("contract_mismatch", "homepage detail is empty")
    step("homepage_detail", {"hasDetail": True})

    # 3. 近期行动公开读面（typed page；空页合法，形状必须成立）。
    by_source = primary.request(
        "GET",
        "/gatherings/by-source?sourceObjectTypeRef=homepage&sourceObjectId="
        + urllib.parse.quote(homepage_id)
        + "&limit=3",
        operation_id="circle.journey.ListGatheringsBySource",
    )
    step("recent_gatherings_readface", {"items": len(_items(by_source, "by-source"))})

    # 4. PRIMARY 建圈（真实公开 command）。
    circle = _data(
        primary.request(
            "POST",
            "/circles",
            body={
                "name": f"旅程验收圈-{run_tag}",
                "description": "SCN-014 主旅程验收（隔离 Actor 创建）",
            },
            operation_id="circle.circle.CreateCircle",
            idempotency_key=f"journey-{run_tag}-create-circle",
        )
    )
    circle_id = str(circle.get("circleId") or circle.get("id") or "")
    if not circle_id:
        raise ProbeFailure("contract_mismatch", "create circle returned no circleId")
    step("create_circle", {"circleIdDigest": circle_id[:12]})

    # 5. MEMBER 加入圈子。
    member.request(
        "POST",
        f"/circles/{circle_id}/memberships",
        body={},
        operation_id="circle.circle_membership.JoinCircle",
        idempotency_key=f"journey-{run_tag}-member-join-circle",
    )
    step("member_join_circle", {})

    # 6. PRIMARY 建群（self_built / apply_only）。
    group = _data(
        primary.request(
            "POST",
            f"/circles/{circle_id}/groups",
            body={
                "groupType": "self_built",
                "name": f"旅程小组-{run_tag}",
                "description": "主旅程验收小组",
                "visibility": "public",
                "joinPolicy": "apply_only",
                "storageEnabled": False,
                "noticeEnabled": False,
            },
            operation_id="circle.circle_group.CreateCircleGroup",
            idempotency_key=f"journey-{run_tag}-create-group",
        )
    )
    group_id = str(group.get("groupId") or "")
    if not group_id:
        raise ProbeFailure("contract_mismatch", "create group returned no groupId")
    step("create_group", {"groupIdDigest": group_id[:12]})

    # 7. owner 名册投影 readback（真实 outbox relay，受控轮询）。
    deadline = time.monotonic() + args.roster_timeout_seconds
    owner_state = ""
    while time.monotonic() < deadline:
        try:
            mine = _data(
                primary.request(
                    "GET",
                    f"/circles/{circle_id}/groups/{group_id}/memberships/self",
                    operation_id="circle.circle_group_membership.GetMyCircleGroupMembership",
                )
            )
            owner_state = str(mine.get("state") or "")
            if owner_state == "active" and str(mine.get("role") or "") == "owner":
                break
        except ProbeFailure:
            pass
        time.sleep(1.5)
    else:
        raise ProbeFailure(
            "projection_timeout",
            f"owner roster projection did not converge, last state={owner_state!r}",
        )
    step("owner_roster_projection", {"state": "active", "role": "owner"})

    # 8. MEMBER 申请入群 → PRIMARY 审批 → 名册收敛为 2 个 active。
    member.request(
        "POST",
        f"/circles/{circle_id}/groups/{group_id}/memberships",
        body={},
        operation_id="circle.circle_group_membership.ApplyJoinCircleGroup",
        idempotency_key=f"journey-{run_tag}-member-apply-group",
    )
    step("member_apply_group", {})
    approved = _data(
        primary.request(
            "POST",
            f"/circles/{circle_id}/groups/{group_id}/memberships/"
            + urllib.parse.quote(member.persona_id)
            + ":approve",
            body={},
            operation_id="circle.circle_group_membership.ApproveCircleGroupMember",
            idempotency_key=f"journey-{run_tag}-approve-member",
        )
    )
    if str(approved.get("state") or "") != "active":
        raise ProbeFailure("contract_mismatch", "approve did not converge to active")
    step("owner_approve_member", {"state": "active"})
    roster = _items(
        primary.request(
            "GET",
            f"/circles/{circle_id}/groups/{group_id}/memberships?state=active&limit=20",
            operation_id="circle.circle_group_membership.ListCircleGroupMemberships",
        ),
        "active roster",
    )
    if len(roster) != 2:
        raise ProbeFailure(
            "contract_mismatch", f"active roster must converge to 2, got {len(roster)}"
        )
    step("roster_converged", {"activeMembers": len(roster)})

    # 9. 群会话绑定回读（chat provision 反向回写，受控轮询；超时如实分类）。
    deadline = time.monotonic() + args.binding_timeout_seconds
    conversation_id = ""
    while time.monotonic() < deadline:
        detail = _data(
            primary.request(
                "GET",
                f"/circles/{circle_id}/groups/{group_id}",
                operation_id="circle.circle_group.GetCircleGroup",
            )
        )
        conversation_id = str(detail.get("conversationId") or "")
        if conversation_id:
            break
        time.sleep(1.5)
    else:
        raise ProbeFailure(
            "binding_timeout",
            "bound conversationId was not written back within the timeout",
        )
    step("conversation_binding_readback", {"conversationIdDigest": conversation_id[:12]})

    report["journeyEvidence"] = {
        "homepageIdDigest": homepage_id[:12],
        "circleIdDigest": circle_id[:12],
        "groupIdDigest": group_id[:12],
        "conversationIdDigest": conversation_id[:12],
        "activeMembers": len(roster),
    }


def main() -> int:
    args = _parse_args()
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "scenario": SCENARIO,
        "status": "running",
        "failureCategory": "",
        "blockingReason": "",
        "startedAt": _utc_now(),
        "endedAt": "",
        "environment": {
            "env": args.env,
            "runtimeKind": LOCAL_TARGETS[args.env],
            "gatewayBaseUrl": args.base_url.rstrip("/"),
        },
        "testDataLifecycle": {},
        "journeyEvidence": {},
        "steps": [],
    }
    report_path = REPO_ROOT / args.report
    exit_code = 0
    try:
        handoff = load_journey_handoff_from_environment()
        report["testDataLifecycle"] = handoff.public_document()
        _run_journey(args, handoff, report)
        report["status"] = "passed"
    except ProbeFailure as failure:
        report["status"] = "failed"
        report["failureCategory"] = failure.category
        report["blockingReason"] = str(failure)
        exit_code = 1
    except ValueError as exc:
        report["status"] = "blocked"
        report["failureCategory"] = "handoff_invalid"
        report["blockingReason"] = str(exc)
        exit_code = 2
    finally:
        report["endedAt"] = _utc_now()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"report: {report_path}")
        print(f"status: {report['status']} {report['blockingReason']}".rstrip())
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
