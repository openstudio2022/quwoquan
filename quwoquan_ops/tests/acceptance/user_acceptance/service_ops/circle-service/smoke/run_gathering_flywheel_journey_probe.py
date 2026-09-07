#!/usr/bin/env python3
# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-008
# spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
# readiness_case: gathering_flywheel_journey_probe_ops_env
"""内容驱动 Gathering 双故事黑盒探针（SIT-008 / SIT-003）。

环境验收层只绑定 L2 SIT；AppRoot UAT 归 App 真机结果，不由 ops 探针冒领。

双隔离 Actor（PRIMARY=发起人 A / MEMBER=同好 B）只来自 `stackctl verify`
的 ActorLease handoff；每步走真实公开 HTTP 契约并输出可审计 step 证据：

  1. wishlist_intent      —— A/B 各自对同一 release 实体「想去」（真实行为事实）。
  2. co_wishlisted        —— A 视角对象交集出现 `coWishlistedEntity`（对 B）。
  3. create_and_publish   —— A 从交集发起 Gathering（sourceRefs 携带实体），
                             等 room ready 后 publish。
  4. member_join          —— B 申请，A 审批通过（active Participation）。
  5. recap_a / recap_b    —— 双方各发布一条关联 `gatheringRef` 的公开回顾。
  6. co_experienced       —— A 视角对象交集出现 `coExperiencedGathering`（对 B）。
  7. four_anchor_proof    —— 实体/内容/创作者/发起人锚点按来源精确增量。
  8. creator_notice       —— 创作者促成通知回链公开 Gathering 且不泄露参与者。
  9. control_group        —— 另一次成形但无内容的行动永远不进经历级。
 10. duo_invitation       —— 1:1 邀约 decline 回执后再邀并 accept 成行。
 11. honest_zero          —— 无关锚点计数诚实为零。

失败与超时如实分类（release_data_missing / contract_mismatch / auth_failed /
projection_timeout / http_error），不伪造、不重试掩盖。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
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
from quwoquan_ops.cli.lib.output_paths import (  # noqa: E402
    active_deployment_candidate_snapshot,
    assert_active_deployment_candidate_snapshot,
    output_root,
)
from quwoquan_ops.cli.lib.readiness_case_result import (  # noqa: E402
    ReadinessCaseResultError,
    validate_readiness_case_result,
    write_create_once_json,
)
from managed_circle_journey_handoff import (  # noqa: E402
    ManagedJourneyActor,
    load_journey_handoff_from_environment,
)

SCHEMA = "gathering-flywheel-journey-probe-report"
SCENARIO = "intersection.sit008.content_driven_gathering_two_stories"
CASE_ID = "gathering_flywheel_journey_probe_ops_env"
SPEC_REF = "specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-008"
OBJECT_ID = "circle.gathering"
RUNNER_SOURCE_PATH = (
    "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
    "circle-service/smoke/run_gathering_flywheel_journey_probe.py"
)
RUNNER_IDENTITY = "circle.gathering-flywheel.environment-probe"
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
        default="",
        help="当前执行的唯一 probe report 路径；缺省时按 env + 时间 + run id 生成",
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


def _publish_post(
    client: ActorClient,
    *,
    title: str,
    tag: str,
    gathering_id: str = "",
    primary_homepage_id: str = "",
    primary_homepage_name: str = "",
) -> str:
    publish_intent_id = f"flywheel-{tag}-{client.persona_id[:8]}"
    body: dict[str, Any] = {
        "publishIntentId": publish_intent_id,
        "localDraftId": f"flywheel-draft-{tag}-{client.persona_id[:8]}",
        "contentType": "article",
        "title": title,
        "body": "交集飞轮旅程验收内容。",
        "articleMarkdown": f"# {title}\n\n交集飞轮旅程验收内容。\n",
        "markdownDialect": "qwq-rich-md",
        "articleAssetManifest": {
            "schema": "article-asset-manifest",
            "assets": [],
        },
        "articleRenderProfile": {"template": "journal", "fontPreset": "clean"},
        "visibility": "public",
    }
    if gathering_id:
        body["gatheringRef"] = gathering_id
    if primary_homepage_id:
        body["primaryHomepageId"] = primary_homepage_id
        body["primaryHomepageType"] = "place"
        body["primaryHomepageSnapshot"] = {
            "title": primary_homepage_name or "目的地",
        }
    receipt = _data(
        client.request(
            "POST",
            "/content/posts:publish",
            body=body,
            operation_id="flywheel.journey.SubmitPostPublication",
            idempotency_key=publish_intent_id,
        )
    )
    post_id = str(receipt.get("postId") or "").strip()
    if not post_id:
        raise ProbeFailure("contract_mismatch", "post publication result lacks postId")
    if str(receipt.get("state") or "") != "published":
        raise ProbeFailure(
            "contract_mismatch",
            f"post publication must be public/published, got {receipt}",
        )
    return post_id


def _publish_recap(
    client: ActorClient,
    *,
    gathering_id: str,
    title: str,
    tag: str,
) -> str:
    return _publish_post(
        client,
        gathering_id=gathering_id,
        title=title,
        tag=f"{tag}-recap",
    )


def _create_published_gathering(
    primary: ActorClient,
    *,
    homepage_id: str,
    homepage_name: str,
    run_tag: str,
    suffix: str,
    room_timeout_seconds: float,
    seed_post_id: str = "",
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
                        *(
                            [
                                {
                                    "objectRef": {
                                        "objectTypeRef": "content",
                                        "objectId": seed_post_id,
                                    },
                                    "routeId": "workBrowser",
                                    "sourceDigest": "intersection:contentHost",
                                }
                            ]
                            if seed_post_id
                            else []
                        ),
                        {
                            "objectRef": {
                                "objectTypeRef": "homepage",
                                "objectId": homepage_id,
                            },
                            "routeId": "homepageDetail",
                            "sourceDigest": "intersection:coWishlistedEntity",
                        },
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

    # canonical 种草内容：主行动 sourceRefs 同时带 content + homepage，
    # 使内容锚点和创作者促成链可在真实环境被直接证明。
    seed_post_id = _publish_post(
        primary,
        title=f"想去{homepage_name}-{run_tag}",
        tag=f"{run_tag}-seed",
        primary_homepage_id=homepage_id,
        primary_homepage_name=homepage_name,
    )
    step("seed_content_published", {"postIdDigest": seed_post_id[:12]})

    # 社会证明基线（步骤 7 的 +1 对照）：四锚点分别取执行前快照。
    baselines = {
        "entity": _social_proof(primary, "entity", homepage_id),
        "content": _social_proof(primary, "content", seed_post_id),
        "creator": _social_proof(primary, "creator", primary.persona_id),
        "organizer": _social_proof(primary, "organizer", primary.persona_id),
    }
    step("social_proof_baseline", {"baselines": baselines})

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
        seed_post_id=seed_post_id,
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
    recap_post_ids = [
        _publish_recap(
            primary,
            gathering_id=gathering_id,
            title=f"回顾-{run_tag}-A",
            tag=f"{run_tag}-a",
        ),
        _publish_recap(
            member,
            gathering_id=gathering_id,
            title=f"回顾-{run_tag}-B",
            tag=f"{run_tag}-b",
        ),
    ]
    step(
        "recap_published",
        {"authors": 2, "postIdDigests": [value[:12] for value in recap_post_ids]},
    )

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

    # 7+8. 四锚点两级诚实计数：主行动进 formed+experienced；
    # 对照组只共享 entity/organizer 锚点且永不进 experienced。
    expected_deltas = {
        "entity": {"formed": 2, "experienced": 1},
        "content": {"formed": 1, "experienced": 1},
        "creator": {"formed": 1, "experienced": 1},
        "organizer": {"formed": 2, "experienced": 1},
    }
    identities = {
        "entity": homepage_id,
        "content": seed_post_id,
        "creator": primary.persona_id,
        "organizer": primary.persona_id,
    }
    deadline = time.monotonic() + args.projection_timeout_seconds
    proofs = {
        anchor: _social_proof(primary, anchor, identities[anchor])
        for anchor in expected_deltas
    }
    while time.monotonic() < deadline:
        if all(
            proofs[anchor][tier] == baselines[anchor][tier] + delta
            for anchor, deltas in expected_deltas.items()
            for tier, delta in deltas.items()
        ):
            break
        time.sleep(3.0)
        proofs = {
            anchor: _social_proof(primary, anchor, identities[anchor])
            for anchor in expected_deltas
        }
    for anchor, deltas in expected_deltas.items():
        for tier, delta in deltas.items():
            expected = baselines[anchor][tier] + delta
            if proofs[anchor][tier] != expected:
                raise ProbeFailure(
                    "projection_timeout" if proofs[anchor][tier] < expected else "contract_mismatch",
                    f"{anchor} {tier} count expected {expected}, "
                    f"baseline={baselines[anchor]} now={proofs[anchor]}",
                )
    step("four_anchor_social_proof", {"baselines": baselines, "now": proofs})

    # 创作者促成通知必须可见，且只回链公开 Gathering，不暴露参与者身份。
    _await_creator_facilitation_notice(
        primary,
        gathering_id=gathering_id,
        timeout_seconds=args.projection_timeout_seconds,
    )
    step("creator_facilitation_notice", {"source": "intersection_facilitation"})

    # 9. 无关锚点诚实归零。
    unrelated = _social_proof(primary, "entity", f"homepage-unrelated-{run_tag}")
    if unrelated != {"published": 0, "formed": 0, "experienced": 0}:
        raise ProbeFailure(
            "contract_mismatch",
            f"unrelated anchor must be honestly zero, got {unrelated}",
        )
    step("honest_zero", {"anchor": "entity"})

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
        "seedPostIdDigest": seed_post_id[:12],
        "recapPostIdDigests": [value[:12] for value in recap_post_ids],
        "socialProofBaselines": baselines,
        "socialProofNow": proofs,
        "creatorFacilitationNotice": True,
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


def _await_creator_facilitation_notice(
    client: ActorClient,
    *,
    gathering_id: str,
    timeout_seconds: float,
) -> None:
    """等待创作者促成通知，并验证公开目标与隐私边界。"""

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
            target = item.get("target")
            if (
                str(item.get("source") or "") == "intersection_facilitation"
                and isinstance(target, dict)
                and str(target.get("targetType") or "") == "gathering"
                and str(target.get("targetId") or "") == gathering_id
            ):
                encoded = json.dumps(item, ensure_ascii=False).lower()
                if "participant" in encoded or "personaids" in encoded:
                    raise ProbeFailure(
                        "contract_mismatch",
                        "creator facilitation notice exposed participant identity",
                    )
                return
        time.sleep(3.0)
    raise ProbeFailure(
        "projection_timeout",
        f"creator facilitation notice for gathering {gathering_id[:12]!r} "
        f"did not appear within {timeout_seconds}s",
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
    duo_seed_post_id = _publish_post(
        primary,
        title=f"想和同好去{homepage_name}-{run_tag}",
        tag=f"{run_tag}-duo-seed",
        primary_homepage_id=homepage_id,
        primary_homepage_name=homepage_name,
    )
    duo_id, duo_version = _create_published_gathering(
        primary,
        homepage_id=homepage_id,
        homepage_name=homepage_name,
        run_tag=run_tag,
        suffix="duo",
        room_timeout_seconds=args.room_timeout_seconds,
        seed_post_id=duo_seed_post_id,
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
        "seedPostIdDigest": duo_seed_post_id[:12],
        "declinedReceipt": True,
        "acceptedReceipt": True,
        "finalParticipationState": "active",
    }


def _contract_graph_source_hash(graph_path: Path) -> str:
    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list) or not sources:
        raise ValueError("candidate ContractGraph has no source identities")
    identities: list[tuple[str, str]] = []
    for item in sources:
        if not isinstance(item, dict):
            raise ValueError("candidate ContractGraph source identity is invalid")
        path = str(item.get("path") or "").strip()
        digest = str(item.get("sha256") or "").strip()
        if not path or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("candidate ContractGraph source identity is invalid")
        identities.append((path, digest))
    identities.sort()
    hasher = hashlib.sha256()
    previous = ""
    for path, digest in identities:
        if path == previous:
            raise ValueError(f"candidate ContractGraph duplicates source path {path!r}")
        previous = path
        hasher.update(path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(digest.encode("ascii"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def _candidate_identity(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], Path]:
    target = LOCAL_TARGETS[args.env]
    snapshot = active_deployment_candidate_snapshot(target)
    if not isinstance(snapshot, dict):
        raise ValueError(f"{target} has no active immutable candidate")
    manifest = snapshot.get("manifest")
    if not isinstance(manifest, dict):
        raise ValueError(f"{target} active candidate manifest is invalid")
    candidate_root = Path(str(snapshot.get("candidateDir") or "")).resolve()
    candidate_manifest = candidate_root / "manifest.json"
    contract_graph = (
        candidate_root / "input-capsule/repo/quwoquan_service/generated/contract_graph.json"
    )
    if candidate_manifest.is_symlink() or not candidate_manifest.is_file():
        raise ValueError("candidate manifest is missing or unsafe")
    if contract_graph.is_symlink() or not contract_graph.is_file():
        raise ValueError("candidate ContractGraph is missing or unsafe")
    assert_active_deployment_candidate_snapshot(snapshot)
    return snapshot, manifest, contract_graph


def _reason_code(report: dict[str, Any]) -> str:
    category = str(report.get("failureCategory") or "blocked").strip().lower()
    safe = "".join(ch if ch.isalnum() or ch in "._/-" else "_" for ch in category)
    return f"CIRCLE.GATHERING.{safe or 'blocked'}"


def _write_case_result(
    args: argparse.Namespace,
    report: dict[str, Any],
    *,
    report_path: Path,
    snapshot: dict[str, Any],
    manifest: dict[str, Any],
    contract_graph: Path,
) -> Path:
    encoded_report = report_path.read_bytes()
    status = str(report.get("status") or "blocked")
    result: dict[str, Any] = {
        "objectId": OBJECT_ID,
        "specRef": SPEC_REF,
        "caseId": CASE_ID,
        "producer": "ops",
        "layer": "environment_acceptance",
        "status": status if status in {"passed", "failed", "blocked", "skipped"} else "blocked",
        "target": {"kind": "object", "id": OBJECT_ID},
        "commitSha": str(manifest.get("sourceRevision") or ""),
        "contractGraphSourceHash": _contract_graph_source_hash(contract_graph),
        "deploymentTarget": LOCAL_TARGETS[args.env],
        "baselineId": str(snapshot.get("baselineId") or "").removeprefix("sha256:"),
        "packageDigest": str(manifest.get("packageDigest") or ""),
        "configurationDigest": str(manifest.get("configurationDigest") or ""),
        "candidateManifestSha256": hashlib.sha256(
            (Path(str(snapshot["candidateDir"])) / "manifest.json").read_bytes()
        ).hexdigest(),
        "candidateDigest": str(manifest.get("packageDigest") or ""),
        "environment": args.env,
        "platform": "linux",
        "deviceClass": "ci-runner",
        "provider": "first-party-https",
        "startedAt": str(report.get("startedAt") or ""),
        "completedAt": str(report.get("endedAt") or ""),
        "runnerIdentity": RUNNER_IDENTITY,
        "artifactSha256": hashlib.sha256(encoded_report).hexdigest(),
        "artifactPath": report_path.relative_to(output_root().resolve()).as_posix(),
    }
    if result["status"] != "passed":
        result["reasonCode"] = _reason_code(report)
    validate_readiness_case_result(result, generated_at=result["completedAt"])
    case_path = report_path.with_name("case-result.json")
    return write_create_once_json(case_path, result)


def main() -> int:
    args = _parse_args()
    run_id = uuid.uuid4().hex
    report_ref = args.report.strip() or (
        f".qwq_output/env/{args.env}/runs/gathering-flywheel-journey/"
        f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{run_id}/report.json"
    )
    report_path = (REPO_ROOT / report_ref).resolve()
    evidence_root = output_root().resolve()
    try:
        report_path.relative_to(evidence_root)
    except ValueError:
        print(f"status: blocked report path escapes QWQ_OUTPUT_ROOT: {report_path}")
        return 2
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "scenario": SCENARIO,
        "readinessCase": CASE_ID,
        "specRef": SPEC_REF,
        "runnerSourcePath": RUNNER_SOURCE_PATH,
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
    exit_code = 0
    snapshot: dict[str, Any] | None = None
    manifest: dict[str, Any] | None = None
    contract_graph: Path | None = None
    try:
        snapshot, manifest, contract_graph = _candidate_identity(args)
        _run_journey(args, report)
        assert_active_deployment_candidate_snapshot(snapshot)
        report["status"] = "passed"
    except ProbeFailure as failure:
        report["status"] = "failed"
        report["failureCategory"] = failure.category
        report["blockingReason"] = str(failure)
        exit_code = 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report["status"] = "blocked"
        report["failureCategory"] = "candidate_or_handoff_invalid"
        report["blockingReason"] = str(exc)
        exit_code = 2
    finally:
        report["endedAt"] = _utc_now()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        case_path: Path | None = None
        if snapshot is not None and manifest is not None and contract_graph is not None:
            try:
                # CaseResult 的 artifactSha256 绑定最终 report bytes；先冻结
                # report，再以 create-once 方式写结果，之后绝不改写 report。
                case_path = _write_case_result(
                    args,
                    report,
                    report_path=report_path,
                    snapshot=snapshot,
                    manifest=manifest,
                    contract_graph=contract_graph,
                )
            except (OSError, ValueError, json.JSONDecodeError, ReadinessCaseResultError) as exc:
                print(f"caseResult: blocked {exc}")
                exit_code = 2
        print(f"report: {report_path}")
        if case_path is not None:
            print(f"caseResult: {case_path}")
        print(f"status: {report['status']} {report['blockingReason']}".rstrip())
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
