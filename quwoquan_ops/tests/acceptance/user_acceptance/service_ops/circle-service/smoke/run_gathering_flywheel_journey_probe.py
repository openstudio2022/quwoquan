#!/usr/bin/env python3
# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-008
# spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
# readiness_case: gathering_flywheel_journey_probe_ops_env
"""交集飞轮九步旅程黑盒探针（SIT-008 / SIT-003 回流分支的真实环境锚点）。

双隔离 Actor（PRIMARY=发起人 A / MEMBER=同好 B）只来自 `stackctl verify`
的 ActorLease handoff；每步走真实公开 HTTP 契约并输出可审计 step 证据：

  1. wishlist_intent      —— A/B 各自对同一 release 实体「想去」（真实行为事实）。
  2. co_wishlisted        —— A 视角对象交集出现 `coWishlistedEntity`（对 B）。
  3. create_and_publish   —— A 从交集发起 Gathering（sourceRefs 携带实体），
                             等 room ready 后 publish。
  4. member_join          —— B 申请，A 审批通过（active Participation）。
  5. recap_a / recap_b    —— 双方各发布一条关联 `gatheringRef` 的公开回顾。
  6. co_experienced       —— A 视角对象交集出现 `coExperiencedGathering`（对 B）。
  7. social_proof_plus    —— 实体锚点四锚点计数 formed/experienced 相对基线 +1。
  8. control_group        —— 对照组：另一次成形但无内容的行动永远不进经历级
                             （experienced 计数不因它增加）。
  9. honest_zero          —— 无关锚点计数诚实为零。

失败与超时如实分类（release_data_missing / contract_mismatch / auth_failed /
projection_timeout / http_error），不伪造、不重试掩盖。
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


sys.dont_write_bytecode = True

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
    open_test_data_acceptance_session,
    request_local_environment_json,
)
from managed_circle_journey_handoff import (  # noqa: E402
    ManagedJourneyActor,
    load_journey_handoff_from_environment,
)

SCHEMA = "gathering-flywheel-journey-probe-report"
SCENARIO = "intersection.sit008.gathering_flywheel_nine_steps"
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
    parser.add_argument(
        "--self-provision-instance-id",
        default="",
        help=(
            "无 stackctl verify handoff 时经受管 OTP 通道自建双隔离 Actor 的"
            " testDataInstanceId（nonprod only；同一 id 幂等复开）"
        ),
    )
    parser.add_argument("--projection-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--room-timeout-seconds", type=float, default=60.0)
    parser.add_argument(
        "--report",
        default=".qwq_output/env/alpha/runs/gathering-flywheel-journey/report.json",
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
    def __init__(self, base_url: str, session: LocalAcceptanceSession) -> None:
        self.base_url = base_url
        self.persona_id = session.persona_id
        self.session = session

    @staticmethod
    def from_managed_actor(base_url: str, actor: ManagedJourneyActor) -> "ActorClient":
        return ActorClient(
            base_url,
            LocalAcceptanceSession(
                owner_id=actor.owner_id,
                persona_id=actor.persona_id,
                access_token=actor.access_token,
                refresh_token=actor.refresh_token,
            ),
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
                timeout_seconds=15.0,
            )
        except LocalEnvironmentHTTPError as exc:
            category = "auth_failed" if exc.status in {401, 403} else "http_error"
            raise ProbeFailure(
                category,
                f"{method} {path} returned HTTP {exc.status}: {exc}",
            ) from exc


def _wishlist_add(client: ActorClient, homepage_id: str, name: str, tag: str) -> None:
    client.request(
        "POST",
        "/content/behaviors",
        body={
            "events": [
                {
                    "clientEventId": f"flywheel-{tag}-{client.persona_id[:8]}",
                    "occurredAt": _utc_now(),
                    "action": "wishlist_add",
                    "objectId": homepage_id,
                    "objectKind": "homepage",
                    "displayName": name,
                    "sourceSurface": "homepageDetail",
                    "entityRefs": [homepage_id],
                }
            ]
        },
        operation_id="flywheel.journey.ReportBehaviors",
        idempotency_key=f"flywheel-{tag}-wishlist-{client.persona_id[:8]}",
    )


def _object_reason_kinds(
    client: ActorClient,
    object_id: str,
    object_type: str,
) -> set[str]:
    payload = client.request(
        "GET",
        "/content/intersections/object?objectId="
        + urllib.parse.quote(object_id)
        + "&objectType="
        + urllib.parse.quote(object_type)
        + "&limit=10",
        operation_id="flywheel.journey.GetObjectIntersections",
    )
    reasons = _data(payload).get("items") or _data(payload).get("reasons") or []
    if not isinstance(reasons, list):
        return set()
    return {
        str(reason.get("kind") or "").strip()
        for reason in reasons
        if isinstance(reason, dict)
    }


def _await_reason(
    client: ActorClient,
    *,
    object_id: str,
    object_type: str,
    kind: str,
    timeout_seconds: float,
    step: str,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if kind in _object_reason_kinds(client, object_id, object_type):
            return
        time.sleep(3.0)
    raise ProbeFailure(
        "projection_timeout",
        f"{step}: intersection kind {kind!r} did not appear within {timeout_seconds}s",
    )


def _social_proof(client: ActorClient, anchor: str, object_id: str) -> dict[str, int]:
    payload = _data(
        client.request(
            "GET",
            "/content/social-proof/"
            + urllib.parse.quote(anchor)
            + "/"
            + urllib.parse.quote(object_id),
            operation_id="flywheel.journey.GetGatheringSocialProof",
        )
    )
    return {
        "published": int(payload.get("publishedCount") or 0),
        "formed": int(payload.get("formedCount") or 0),
        "experienced": int(payload.get("experiencedCount") or 0),
    }


def _publish_recap(
    client: ActorClient,
    *,
    gathering_id: str,
    title: str,
    tag: str,
) -> None:
    client.request(
        "POST",
        "/content/posts:publish",
        body={
            "publishIntentId": f"flywheel-{tag}-{client.persona_id[:8]}",
            "contentType": "article",
            "title": title,
            "body": "共同行动回顾（旅程验收 Actor 发布）。",
            "articleMarkdown": f"# {title}\n\n共同行动回顾（旅程验收 Actor 发布）。\n",
            "markdownDialect": "qwq-rich-md",
            "articleAssetManifest": {
                "schema": "article-asset-manifest",
                "assets": [],
            },
            "articleRenderProfile": {"template": "journal", "fontPreset": "clean"},
            "gatheringRef": gathering_id,
            "visibility": "public",
        },
        operation_id="flywheel.journey.SubmitPostPublication",
        idempotency_key=f"flywheel-{tag}-recap-{client.persona_id[:8]}",
    )


def _create_published_gathering(
    primary: ActorClient,
    *,
    homepage_id: str,
    homepage_name: str,
    run_tag: str,
    suffix: str,
    room_timeout_seconds: float,
    duo: bool = False,
) -> tuple[str, int]:
    start_at = (
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
    ).replace(hour=6, minute=0, second=0, microsecond=0)
    draft = _data(
        primary.request(
            "POST",
            "/gatherings",
            body={
                "hostBinding": {
                    "hostSubjectKind": "persona",
                    "hostSubjectId": primary.persona_id,
                    "authorityEvidenceRef": f"persona:{primary.persona_id}:self",
                    "authorityVersion": 1,
                },
                "creatorParticipates": True,
                "purpose": {
                    "title": f"一起去{homepage_name}-{suffix}-{run_tag}",
                    "summary": "交集飞轮九步旅程验收（隔离 Actor 创建）。",
                    "topicRefs": [],
                    "requirementRefs": [],
                    "sourceObjectRefs": [
                        {
                            "objectRef": {
                                "objectTypeRef": "homepage",
                                "objectId": homepage_id,
                            },
                            "routeId": "homepageDetail",
                            "sourceDigest": "intersection:coWishlistedEntity",
                        }
                    ],
                },
                "schedule": {
                    "timezone": "Asia/Shanghai",
                    "startAt": start_at.isoformat().replace("+00:00", "Z"),
                    "endAt": (start_at + dt.timedelta(hours=2))
                    .isoformat()
                    .replace("+00:00", "Z"),
                },
                "place": {
                    "mode": "physical",
                    "coarsePlaceLabel": homepage_name,
                    "exactMeetingPoint": "正门集合",
                },
                "policySet": {
                    "audiencePolicy": "invite_only" if duo else "public",
                    "admissionPolicy": "invite_only" if duo else "approval",
                    "capacityPolicy": {"maxParticipants": 2 if duo else 4},
                    "disclosurePolicy": {
                        "timeDisclosure": "exact",
                        "placeDisclosure": "after_join",
                        "rosterDisclosure": "count_only",
                    },
                    "applicationQuestions": [],
                    "riskControlPolicyRef": "risk/standard-day-public-v1",
                },
            },
            operation_id="flywheel.journey.CreateGatheringDraft",
            idempotency_key=f"flywheel-{run_tag}-{suffix}-create",
        )
    )
    gathering_id = str(draft.get("gatheringId") or "")
    version = int(draft.get("aggregateVersion") or 0)
    if not gathering_id or version <= 0:
        raise ProbeFailure("contract_mismatch", "gathering draft result lacks identity")

    # room ready 是 publish 前置：轮询 owner 读面等待 chat 绑定收敛。
    deadline = time.monotonic() + room_timeout_seconds
    while True:
        current = _data(
            primary.request(
                "GET",
                "/gatherings/" + urllib.parse.quote(gathering_id),
                operation_id="flywheel.journey.GetGathering",
            )
        )
        room = str(
            current.get("roomBindingStatus")
            or (current.get("gathering") or {}).get("roomBindingStatus")
            or ""
        )
        version = int(
            current.get("aggregateVersion")
            or (current.get("gathering") or {}).get("aggregateVersion")
            or version
        )
        if room == "ready":
            break
        if time.monotonic() >= deadline:
            raise ProbeFailure(
                "projection_timeout",
                f"gathering {suffix} room binding not ready within {room_timeout_seconds}s",
            )
        time.sleep(3.0)

    published = _data(
        primary.request(
            "POST",
            "/gatherings/" + urllib.parse.quote(gathering_id) + ":publish",
            body={
                "gatheringId": gathering_id,
                "expectedGatheringVersion": version,
            },
            operation_id="flywheel.journey.PublishGathering",
            idempotency_key=f"flywheel-{run_tag}-{suffix}-publish",
        )
    )
    return gathering_id, int(published.get("aggregateVersion") or version)


def _join_via_approval(
    primary: ActorClient,
    member: ActorClient,
    *,
    gathering_id: str,
    gathering_version: int,
    run_tag: str,
    suffix: str,
) -> int:
    applied = _data(
        member.request(
            "POST",
            "/gatherings/" + urllib.parse.quote(gathering_id) + ":apply",
            body={
                "gatheringId": gathering_id,
                "expectedGatheringVersion": gathering_version,
                "expectedParticipationVersion": 0,
                "answers": [],
            },
            operation_id="flywheel.journey.ApplyToGathering",
            idempotency_key=f"flywheel-{run_tag}-{suffix}-apply",
        )
    )
    version = int(applied.get("aggregateVersion") or gathering_version)
    participation_version = int(applied.get("participationVersion") or 1)
    approved = _data(
        primary.request(
            "POST",
            "/gatherings/" + urllib.parse.quote(gathering_id) + ":review-application",
            body={
                "gatheringId": gathering_id,
                "participantPersonaId": member.persona_id,
                "decision": "approve",
                "expectedGatheringVersion": version,
                "expectedParticipationVersion": participation_version,
            },
            operation_id="flywheel.journey.ReviewGatheringApplication",
            idempotency_key=f"flywheel-{run_tag}-{suffix}-approve",
        )
    )
    return int(approved.get("aggregateVersion") or version)


def _resolve_actor_clients(
    args: argparse.Namespace,
    report: dict[str, Any],
) -> tuple[ActorClient, ActorClient]:
    """Actor 来源二选一（都只产生真实非生产账号，Prod 被底层拒绝）：

    1. `stackctl verify` 注入的 ActorLease handoff（canonical 通道）；
    2. `--self-provision-instance-id`：经受管 OTP 通道按 testDataInstanceId
       幂等自建 PRIMARY/MEMBER 双隔离 Actor（verify profile 接线前的执行通道，
       报告如实标注 actor 来源）。
    """
    instance_id = args.self_provision_instance_id.strip()
    if instance_id:
        actors: list[ActorClient] = []
        for role, index in (("primary", 0), ("member", 1)):
            actor = open_test_data_acceptance_session(
                args.base_url,
                environment=args.env,
                target_name=LOCAL_TARGETS[args.env],
                test_data_instance_id=instance_id,
                actor_role=role,
                actor_index=index,
            )
            actors.append(ActorClient(args.base_url, actor.session))
        report["testDataLifecycle"] = {
            "actorSource": "self_provision_otp",
            "testDataInstanceId": instance_id,
            "roles": ["primary", "member"],
        }
        return actors[0], actors[1]
    handoff = load_journey_handoff_from_environment()
    report["testDataLifecycle"] = handoff.public_document()
    return (
        ActorClient.from_managed_actor(args.base_url, handoff.actor("primary")),
        ActorClient.from_managed_actor(args.base_url, handoff.actor("member")),
    )


def _run_journey(
    args: argparse.Namespace,
    report: dict[str, Any],
) -> None:
    primary, member = _resolve_actor_clients(args, report)
    run_tag = uuid.uuid4().hex[:8]

    def step(name: str, evidence: dict[str, Any]) -> None:
        report["steps"].append({"name": name, "status": "passed", **evidence})

    # 0. release 实体发现（不书写固定业务 ID）。
    search = primary.request(
        "GET",
        "/homepages/search?query="
        + urllib.parse.quote(args.homepage_query)
        + "&limit=5",
        operation_id="flywheel.journey.SearchHomepages",
    )
    homepage_rows = _items(search, "homepage search")
    if not homepage_rows:
        raise ProbeFailure(
            "release_data_missing",
            f"homepage search {args.homepage_query!r} returned no release entities",
        )
    homepage_id = str(
        homepage_rows[0].get("homepageId") or homepage_rows[0].get("id") or ""
    )
    homepage_name = str(
        homepage_rows[0].get("displayName") or homepage_rows[0].get("name") or "目的地"
    )
    if not homepage_id:
        raise ProbeFailure("contract_mismatch", "homepage search row lacks id")

    # 社会证明基线（步骤 7 的 +1 对照）。
    baseline = _social_proof(primary, "entity", homepage_id)
    step("social_proof_baseline", {"baseline": baseline})

    # 1. 想去意图（真实行为事实，双方）。
    _wishlist_add(primary, homepage_id, homepage_name, f"{run_tag}-a")
    _wishlist_add(member, homepage_id, homepage_name, f"{run_tag}-b")
    step("wishlist_intent", {"homepageIdDigest": homepage_id[:12]})

    # 2. 意图交集出现（A 视角对 B）。
    _await_reason(
        primary,
        object_id=member.persona_id,
        object_type="person",
        kind="coWishlistedEntity",
        timeout_seconds=args.projection_timeout_seconds,
        step="co_wishlisted",
    )
    step("co_wishlisted", {"kind": "coWishlistedEntity"})

    # 3. 发起并发布（room ready 前置）。
    gathering_id, gathering_version = _create_published_gathering(
        primary,
        homepage_id=homepage_id,
        homepage_name=homepage_name,
        run_tag=run_tag,
        suffix="main",
        room_timeout_seconds=args.room_timeout_seconds,
    )
    step("create_and_publish", {"gatheringIdDigest": gathering_id[:12]})

    # 4. B 申请 → A 审批（active Participation）。
    gathering_version = _join_via_approval(
        primary,
        member,
        gathering_id=gathering_id,
        gathering_version=gathering_version,
        run_tag=run_tag,
        suffix="main",
    )
    step("member_join", {"participants": 2})

    # 对照组行动：成形（双人 active）但永不发布内容。
    control_id, control_version = _create_published_gathering(
        primary,
        homepage_id=homepage_id,
        homepage_name=homepage_name,
        run_tag=run_tag,
        suffix="ctrl",
        room_timeout_seconds=args.room_timeout_seconds,
    )
    _join_via_approval(
        primary,
        member,
        gathering_id=control_id,
        gathering_version=control_version,
        run_tag=run_tag,
        suffix="ctrl",
    )
    step("control_group_formed", {"gatheringIdDigest": control_id[:12]})

    # 5. 双方公开回顾（gatheringRef 回流，服务端参与校验 fail-closed）。
    _publish_recap(
        primary,
        gathering_id=gathering_id,
        title=f"回顾-{run_tag}-A",
        tag=f"{run_tag}-a",
    )
    _publish_recap(
        member,
        gathering_id=gathering_id,
        title=f"回顾-{run_tag}-B",
        tag=f"{run_tag}-b",
    )
    step("recap_published", {"authors": 2})

    # 6. 经历交集出现。
    _await_reason(
        primary,
        object_id=member.persona_id,
        object_type="person",
        kind="coExperiencedGathering",
        timeout_seconds=args.projection_timeout_seconds,
        step="co_experienced",
    )
    step("co_experienced", {"kind": "coExperiencedGathering"})

    # 7+8. 四锚点两级诚实计数：主行动进 formed+experienced，对照组只进 formed。
    deadline = time.monotonic() + args.projection_timeout_seconds
    proof = _social_proof(primary, "entity", homepage_id)
    while (
        proof["formed"] < baseline["formed"] + 2
        or proof["experienced"] < baseline["experienced"] + 1
    ) and time.monotonic() < deadline:
        time.sleep(3.0)
        proof = _social_proof(primary, "entity", homepage_id)
    if proof["formed"] != baseline["formed"] + 2:
        raise ProbeFailure(
            "projection_timeout",
            f"entity formed count expected +2, baseline={baseline} now={proof}",
        )
    if proof["experienced"] != baseline["experienced"] + 1:
        raise ProbeFailure(
            "contract_mismatch",
            "experienced tier must count only the recap-backed gathering "
            f"(control group must stay out): baseline={baseline} now={proof}",
        )
    step("social_proof_plus", {"baseline": baseline, "now": proof})

    # 9. 无关锚点诚实归零。
    unrelated = _social_proof(primary, "entity", f"homepage-unrelated-{run_tag}")
    if unrelated != {"published": 0, "formed": 0, "experienced": 0}:
        raise ProbeFailure(
            "contract_mismatch",
            f"unrelated anchor must be honestly zero, got {unrelated}",
        )
    step("honest_zero", {"anchor": "entity"})

    # 10. organizer 锚点随两次成形递增（发起人卡口径）。
    organizer_proof = _social_proof(primary, "organizer", primary.persona_id)
    if organizer_proof["formed"] < 2 or organizer_proof["experienced"] < 1:
        raise ProbeFailure(
            "contract_mismatch",
            f"organizer anchor must reflect both gatherings: {organizer_proof}",
        )
    step("organizer_anchor", {"proof": organizer_proof})

    # 11. 场景二延伸：1对1 邀约 decline → 发起方回执 → 再邀 → accept 成行。
    duo_evidence = _run_duo_invitation_loop(
        args,
        primary,
        member,
        homepage_id=homepage_id,
        homepage_name=homepage_name,
        run_tag=run_tag,
    )
    step("duo_invitation_loop", duo_evidence)

    report["journeyEvidence"] = {
        "homepageIdDigest": homepage_id[:12],
        "gatheringIdDigest": gathering_id[:12],
        "controlGatheringIdDigest": control_id[:12],
        "socialProofBaseline": baseline,
        "socialProofNow": proof,
        "organizerProof": organizer_proof,
        "duo": duo_evidence,
    }


def _await_inviter_receipt(
    client: ActorClient,
    *,
    gathering_id: str,
    status: str,
    timeout_seconds: float,
) -> None:
    """轮询发起方 AppMessage inbox，等待邀请回执投影收敛。"""
    expected_source_id = f"{gathering_id}:{status}"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        payload = client.request(
            "GET",
            "/app-messages?limit=50",
            operation_id="flywheel.journey.ListAppMessages",
        )
        for item in _data(payload).get("items") or []:
            if not isinstance(item, dict):
                continue
            if (
                str(item.get("source") or "") == "gathering_invitation_receipt"
                and str(item.get("sourceId") or "") == expected_source_id
            ):
                return
        time.sleep(3.0)
    raise ProbeFailure(
        "projection_timeout",
        f"inviter receipt {expected_source_id!r} did not appear within {timeout_seconds}s",
    )


def _run_duo_invitation_loop(
    args: argparse.Namespace,
    primary: ActorClient,
    member: ActorClient,
    *,
    homepage_id: str,
    homepage_name: str,
    run_tag: str,
) -> dict[str, Any]:
    """1对1 同好邀约闭环：invite → decline → 发起方婉拒回执 → 再邀 → accept。"""
    duo_id, duo_version = _create_published_gathering(
        primary,
        homepage_id=homepage_id,
        homepage_name=homepage_name,
        run_tag=run_tag,
        suffix="duo",
        room_timeout_seconds=args.room_timeout_seconds,
        duo=True,
    )

    def invite(attempt: str, participation_version: int) -> dict[str, Any]:
        nonlocal duo_version
        seat_hold = (
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=48)
        ).isoformat().replace("+00:00", "Z")
        result = _data(
            primary.request(
                "POST",
                "/gatherings/" + urllib.parse.quote(duo_id) + ":invite",
                body={
                    "gatheringId": duo_id,
                    "participantPersonaId": member.persona_id,
                    "seatHoldUntil": seat_hold,
                    "expectedGatheringVersion": duo_version,
                    "expectedParticipationVersion": participation_version,
                },
                operation_id="flywheel.journey.InviteToGathering",
                idempotency_key=f"flywheel-{run_tag}-duo-invite-{attempt}",
            )
        )
        duo_version = int(result.get("aggregateVersion") or duo_version)
        return result

    first = invite("first", 0)
    first_participation = int(first.get("participationVersion") or 1)

    declined = _data(
        member.request(
            "POST",
            "/gatherings/" + urllib.parse.quote(duo_id) + ":decline-invitation",
            body={
                "gatheringId": duo_id,
                "expectedGatheringVersion": duo_version,
                "expectedParticipationVersion": first_participation,
            },
            operation_id="flywheel.journey.DeclineGatheringInvitation",
            idempotency_key=f"flywheel-{run_tag}-duo-decline",
        )
    )
    duo_version = int(declined.get("aggregateVersion") or duo_version)
    _await_inviter_receipt(
        primary,
        gathering_id=duo_id,
        status="declined",
        timeout_seconds=args.projection_timeout_seconds,
    )

    second = invite("second", int(declined.get("participationVersion") or 0))
    second_participation = int(second.get("participationVersion") or 0)
    accepted = _data(
        member.request(
            "POST",
            "/gatherings/" + urllib.parse.quote(duo_id) + ":accept-invitation",
            body={
                "gatheringId": duo_id,
                "expectedGatheringVersion": duo_version,
                "expectedParticipationVersion": second_participation,
            },
            operation_id="flywheel.journey.AcceptGatheringInvitation",
            idempotency_key=f"flywheel-{run_tag}-duo-accept",
        )
    )
    if str(accepted.get("participationState") or "") != "active":
        raise ProbeFailure(
            "contract_mismatch",
            f"duo acceptance must yield active participation: {accepted}",
        )
    _await_inviter_receipt(
        primary,
        gathering_id=duo_id,
        status="accepted",
        timeout_seconds=args.projection_timeout_seconds,
    )
    return {
        "gatheringIdDigest": duo_id[:12],
        "declinedReceipt": True,
        "acceptedReceipt": True,
        "finalParticipationState": "active",
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
        _run_journey(args, report)
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
