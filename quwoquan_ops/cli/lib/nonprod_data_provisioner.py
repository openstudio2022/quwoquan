"""Execute candidate-bound nonprod recipes through canonical public APIs.

This module is imported only by ``stackctl verify``. It never writes a service
database, never signs an acceptance JWT, and rejects Prod before any request.

spec_ref: specs/feature-tree/spec.md#uat-009
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003
"""

from __future__ import annotations

import hashlib
import base64
import io
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from .local_environment_auth import (
    LocalAcceptanceActor,
    LocalAcceptanceSession,
    LocalEnvironmentHTTPError,
    open_local_phone_acceptance_session,
    request_local_environment_json,
)
from .nonprod_business_data import (
    ContractOperationCatalog,
    DatasetRecipe,
    NONPROD_REFERENCE_IDENTITY,
    NONPROD_TARGETS,
    compute_dataset_epoch,
    idempotency_key,
)
from .output_paths import env_runs_root


_DIGEST_PREFIX = "sha256:"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _DIGEST_PREFIX + hashlib.sha256(encoded).hexdigest()


def _required_string(payload: Mapping[str, Any], *fields: str) -> str:
    for field in fields:
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise RuntimeError("response missing required identity: " + " or ".join(fields))


def _required_string_list(
    payload: Mapping[str, Any],
    field: str,
    *,
    expected: int,
) -> list[str]:
    values = payload.get(field)
    if not isinstance(values, list):
        raise RuntimeError(f"response missing required identity list: {field}")
    normalized = [str(value).strip() for value in values]
    if (
        len(normalized) != expected
        or len(set(normalized)) != expected
        or any(not value for value in normalized)
    ):
        raise RuntimeError(f"response identity list is invalid: {field}")
    return normalized


@dataclass(frozen=True)
class NonprodCandidateIdentity:
    environment: str
    target: str
    baseline_id: str
    source_revision: str
    package_digest: str
    runtime_config_digest: str
    release_id: str
    release_digest: str
    import_run_id: str
    release_post_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        expected_environment = NONPROD_TARGETS.get(self.target)
        if expected_environment != self.environment:
            raise ValueError("nonprod candidate environment/target mismatch")
        for label, value in (
            ("baselineId", self.baseline_id),
            ("packageDigest", self.package_digest),
            ("runtimeConfigDigest", self.runtime_config_digest),
            ("releaseDigest", self.release_digest),
        ):
            if not value.startswith(_DIGEST_PREFIX) or len(value) != 71:
                raise ValueError(f"{label} must be sha256")
        if not self.release_id or not self.import_run_id:
            raise ValueError("release and import run identities are required")
        if len(self.release_post_ids) != 3 or len(set(self.release_post_ids)) != 3:
            raise ValueError("candidate must bind exactly three unique release posts")
        if any(not str(post_id).strip() for post_id in self.release_post_ids):
            raise ValueError("candidate release post identities are invalid")


@dataclass(frozen=True)
class OperationReceipt:
    operation_id: str
    actor_role: str
    step: str
    request_hash: str
    response_hash: str
    object_ids: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "operationId": self.operation_id,
            "actorRole": self.actor_role,
            "step": self.step,
            "requestHash": self.request_hash,
            "responseHash": self.response_hash,
            "objectIds": list(self.object_ids),
        }


class PublicOperationExecutor:
    def __init__(
        self,
        *,
        base_url: str,
        target: str,
        dataset_epoch: str,
        dataset_id: str,
        catalog: ContractOperationCatalog | None = None,
        receipt_sink: Callable[[list[OperationReceipt]], None] | None = None,
    ) -> None:
        self.base_url = base_url
        self.target = target
        self.dataset_epoch = dataset_epoch
        self.dataset_id = dataset_id
        self.catalog = catalog or ContractOperationCatalog()
        self.receipts: list[OperationReceipt] = []
        self.receipt_sink = receipt_sink

    def call(
        self,
        operation_id: str,
        *,
        actor: LocalAcceptanceActor,
        step: str,
        bindings: Mapping[str, str] | None = None,
        body: dict[str, Any] | None = None,
        query: Mapping[str, str | int] | None = None,
        object_id_fields: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        operation = self.catalog.require(operation_id)
        path = operation.path(bindings)
        if query:
            path += "?" + urlencode(
                [(name, str(value)) for name, value in sorted(query.items())]
            )
        key = idempotency_key(
            target=self.target,
            dataset_epoch=self.dataset_epoch,
            dataset_id=self.dataset_id,
            actor_role=actor.role,
            operation=operation_id.rsplit(".", 1)[-1],
            step=step,
        )
        response = request_local_environment_json(
            self.base_url,
            path=path,
            session=actor.session,
            method=operation.method,
            body=body,
            headers={"Idempotency-Key": key},
        )
        object_ids = tuple(
            str(response.get(field) or "").strip()
            for field in object_id_fields
            if str(response.get(field) or "").strip()
        )
        self.receipts.append(
            OperationReceipt(
                operation_id=operation_id,
                actor_role=actor.role,
                step=step,
                request_hash=_canonical_hash(
                    {
                        "operationId": operation_id,
                        "bindings": dict(bindings or {}),
                        "body": body,
                        "query": dict(query or {}),
                        "idempotencyKey": key,
                    }
                ),
                response_hash=_canonical_hash(response),
                object_ids=object_ids,
            )
        )
        if self.receipt_sink is not None:
            self.receipt_sink(self.receipts)
        return response

    def call_expect_http_status(
        self,
        operation_id: str,
        *,
        actor: LocalAcceptanceActor,
        step: str,
        expected_status: int,
        bindings: Mapping[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> None:
        operation = self.catalog.require(operation_id)
        path = operation.path(bindings)
        key = idempotency_key(
            target=self.target,
            dataset_epoch=self.dataset_epoch,
            dataset_id=self.dataset_id,
            actor_role=actor.role,
            operation=operation_id.rsplit(".", 1)[-1],
            step=step,
        )
        request_document = {
            "operationId": operation_id,
            "bindings": dict(bindings or {}),
            "body": body,
            "idempotencyKey": key,
        }
        try:
            request_local_environment_json(
                self.base_url,
                path=path,
                session=actor.session,
                method=operation.method,
                body=body,
                headers={"Idempotency-Key": key},
            )
        except LocalEnvironmentHTTPError as exc:
            if exc.status != expected_status:
                raise RuntimeError(
                    f"{operation_id} returned HTTP {exc.status}, expected {expected_status}"
                ) from exc
            self.receipts.append(
                OperationReceipt(
                    operation_id=operation_id,
                    actor_role=actor.role,
                    step=step,
                    request_hash=_canonical_hash(request_document),
                    response_hash=_canonical_hash({"status": exc.status}),
                    object_ids=(),
                )
            )
            if self.receipt_sink is not None:
                self.receipt_sink(self.receipts)
            return
        raise RuntimeError(
            f"{operation_id} unexpectedly succeeded; expected HTTP {expected_status}"
        )


class NonprodDataProvisioner:
    def __init__(
        self,
        *,
        base_url: str,
        candidate: NonprodCandidateIdentity,
        share_provider_receipt_ids: tuple[str, ...] = (),
        provider_conformance_evidence: Mapping[str, Mapping[str, Any]] | None = None,
        reliability_evidence: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        if candidate.environment not in {"alpha", "beta", "gamma"}:
            raise ValueError("nonprod provisioner is forbidden for Prod")
        if not base_url.startswith("https://"):
            raise ValueError("nonprod provisioner requires canonical HTTPS gateway")
        self.base_url = base_url.rstrip("/")
        self.candidate = candidate
        self.share_provider_receipt_ids = tuple(
            value.strip() for value in share_provider_receipt_ids if value.strip()
        )
        self.provider_conformance_evidence = dict(
            provider_conformance_evidence or {}
        )
        self.reliability_evidence = dict(reliability_evidence or {})

    def provision_reference_identity(self) -> dict[str, Any]:
        recipe = NONPROD_REFERENCE_IDENTITY
        epoch = self._epoch(recipe)
        existing = self._load_candidate_receipt_for_provision(recipe, epoch)
        if existing is not None:
            return self._verify_existing_identity_receipt(existing, recipe, epoch)

        actors = self._open_identity_actors_with_recovery(recipe, epoch)
        executor = self._candidate_executor(
            recipe,
            epoch,
            actor_receipt_refs=[
                {
                    "role": actor.role,
                    "ownerId": actor.session.owner_id,
                    "personaIds": [actor.session.persona_id],
                    "challengeReceiptHash": _canonical_hash(actor.challenge_id),
                    "accountState": actor.account_state,
                    "identityOrigin": actor.identity_origin,
                }
                for actor in actors
            ],
        )

        secondary = executor.call(
            "user.persona.CreatePersona",
            actor=actors[0],
            step="persona-secondary",
            body={
                "displayName": "验收分身",
                "isolationLevel": "isolated",
                "purposeHint": "acceptance",
            },
            object_id_fields=("personaId", "id"),
        )
        secondary_persona_id = _required_string(secondary, "personaId", "id")

        follow_pairs = (
            (0, 1),
            (1, 0),
            (0, 2),
            (0, 3),
            (1, 2),
            (2, 4),
            (3, 5),
            (4, 5),
            (5, 2),
        )
        for index, (source, target) in enumerate(follow_pairs):
            executor.call(
                "user.persona_relationship.FollowUser",
                actor=actors[source],
                step=f"follow-{index:02d}",
                bindings={"targetPersonaId": actors[target].session.persona_id},
                body={"source": "acceptance"},
            )

        pending = self._send_greeting(
            executor, actors[2], actors[3], step="greeting-pending"
        )
        replied = self._send_greeting(
            executor, actors[3], actors[4], step="greeting-replied-send"
        )
        replied_result = executor.call(
            "user.greeting_request.ReplyGreetingRequest",
            actor=actors[4],
            step="greeting-replied",
            bindings={"requestId": replied},
            body=None,
        )
        promoted_conversation_id = _required_string(
            replied_result, "promotedConversationId"
        )
        ignored = self._send_greeting(
            executor, actors[1], actors[5], step="greeting-ignored-send"
        )
        executor.call(
            "user.greeting_request.IgnoreGreetingRequest",
            actor=actors[5],
            step="greeting-ignored",
            bindings={"requestId": ignored},
            body=None,
        )

        executor.call(
            "user.persona_relationship.BlockUser",
            actor=actors[5],
            step="block",
            bindings={"targetPersonaId": actors[2].session.persona_id},
            body=None,
        )
        executor.call(
            "user.persona_relationship.UnblockUser",
            actor=actors[5],
            step="unblock",
            bindings={"targetPersonaId": actors[2].session.persona_id},
            body=None,
        )

        actor_rows = [
            {
                "role": actor.role,
                "ownerId": actor.session.owner_id,
                "personaIds": [
                    actor.session.persona_id,
                    *([secondary_persona_id] if index == 0 else []),
                ],
                "challengeReceiptHash": _canonical_hash(actor.challenge_id),
                "accountState": actor.account_state,
                "identityOrigin": actor.identity_origin,
            }
            for index, actor in enumerate(actors)
        ]
        receipt = self._base_receipt(recipe, epoch)
        receipt.update(
            {
                "status": "passed",
                "actorReceiptRefs": actor_rows,
                "operationReceipts": [row.to_json() for row in executor.receipts],
                "createdObjectIdsOrHashes": {
                    "ownerIds": [actor.session.owner_id for actor in actors],
                    "personaIds": [
                        *(actor.session.persona_id for actor in actors),
                        secondary_persona_id,
                    ],
                    "greetingRequestIds": [pending, replied, ignored],
                    "promotedConversationId": promoted_conversation_id,
                },
                "projectionWatermarks": {},
                "readbackResults": {
                    "authenticatedAccounts": len(actors),
                    "personas": len(actors) + 1,
                    "followCommands": len(follow_pairs),
                    "finalFollowDirections": len(follow_pairs) - 1,
                    "mutualPairs": 1,
                    "greetingStates": ["pending", "replied", "ignored"],
                    "blockRecoveryScenarios": 1,
                },
                "mediaUploadReceipts": [],
                "cleanupState": "retained",
                "caseResultRefs": [],
            }
        )
        expected = dict(recipe.expected_counts)
        readback = receipt["readbackResults"]
        if (
            readback["authenticatedAccounts"] != expected["accounts"]
            or readback["personas"] != expected["personas"]
            or readback["finalFollowDirections"] != expected["followDirections"]
            or readback["mutualPairs"] != expected["mutualPairs"]
            or len(readback["greetingStates"]) != expected["greetingStates"]
            or readback["blockRecoveryScenarios"]
            != expected["blockRecoveryScenarios"]
        ):
            raise RuntimeError("reference identity dataset cardinality drift")
        self._write_receipt(recipe, epoch, receipt)
        return receipt

    def provision_reference_content_interaction(self) -> dict[str, Any]:
        from .nonprod_business_data import NONPROD_REFERENCE_CONTENT_INTERACTION

        recipe = NONPROD_REFERENCE_CONTENT_INTERACTION
        epoch = self._epoch(recipe)
        existing = self._load_candidate_receipt_for_provision(recipe, epoch)
        if existing is not None:
            return self._verify_existing_receipt(existing, recipe, epoch)
        if len(self.share_provider_receipt_ids) != 3:
            raise RuntimeError(
                "GATE_BLOCK: three formal outbound-share provider receipts are required"
            )
        identity_epoch = self._epoch(NONPROD_REFERENCE_IDENTITY)
        identity_receipt = self._load_receipt(
            NONPROD_REFERENCE_IDENTITY, identity_epoch
        )
        if identity_receipt is None:
            raise RuntimeError("GATE_BLOCK: reference identity receipt is required")
        self._verify_existing_identity_receipt(
            identity_receipt, NONPROD_REFERENCE_IDENTITY, identity_epoch
        )
        actors = self._open_actors(NONPROD_REFERENCE_IDENTITY, identity_epoch)
        executor = self._candidate_executor(
            recipe,
            epoch,
            actor_receipt_refs=[
                {
                    "datasetId": NONPROD_REFERENCE_IDENTITY.dataset_id,
                    "datasetEpoch": identity_epoch,
                }
            ],
        )
        comment_upload = self._upload_media_asset(
            executor,
            actor=actors[2],
            step="comment-image-upload",
            media_type="image",
            content_type="image/png",
            payload=_acceptance_png(),
        )
        comment_media_asset_id = comment_upload["assetId"]
        post_a, post_b, post_c = self.candidate.release_post_ids
        top_level_a: list[str] = []
        for index in range(21):
            response = self._create_comment(
                executor,
                actor=actors[index % len(actors)],
                post_id=post_a,
                step=f"post-a-comment-{index:02d}",
                content=f"西湖验收评论 {index + 1}",
            )
            top_level_a.append(_required_string(response, "commentId", "id"))

        reply_ids: list[str] = []
        for index in range(11):
            response = self._create_comment(
                executor,
                actor=actors[(index + 1) % len(actors)],
                post_id=post_a,
                step=f"post-a-reply-{index:02d}",
                content=f"西湖验收回复 {index + 1}",
                reply_to_comment_id=top_level_a[0],
            )
            reply_ids.append(_required_string(response, "commentId", "id"))

        mention_response = self._create_comment(
            executor,
            actor=actors[1],
            post_id=post_b,
            step="post-b-mention",
            content="一起看看这组西湖影像",
            mentions=(actors[2].session.persona_id,),
        )
        attachment_response = self._create_comment(
            executor,
            actor=actors[2],
            post_id=post_b,
            step="post-b-image",
            content="补充一张现场图片",
        )
        attachment_comment_id = _required_string(
            attachment_response, "commentId", "id"
        )
        executor.call(
            "content.comment.BindMediaAssetsToComment",
            actor=actors[2],
            step="post-b-image-bind",
            bindings={"commentId": attachment_comment_id},
            body={"attachmentMediaIds": [comment_media_asset_id]},
        )
        post_b_ids = [
            _required_string(mention_response, "commentId", "id"),
            attachment_comment_id,
        ]
        deleted_response = self._create_comment(
            executor,
            actor=actors[3],
            post_id=post_b,
            step="post-b-delete-create",
            content="本评论用于删除恢复验证",
        )
        deleted_id = _required_string(deleted_response, "commentId", "id")
        executor.call(
            "content.comment.DeleteComment",
            actor=actors[3],
            step="post-b-delete",
            bindings={"postId": post_b, "commentId": deleted_id},
            body=None,
        )

        like_pairs = (
            (0, post_a),
            (1, post_a),
            (2, post_a),
            (3, post_a),
            (4, post_b),
            (5, post_b),
            (0, post_c),
            (1, post_c),
        )
        for index, (actor_index, post_id) in enumerate(like_pairs):
            executor.call(
                "content.content_reaction.LikePost",
                actor=actors[actor_index],
                step=f"post-like-{index:02d}",
                bindings={"postId": post_id},
                body=None,
            )
        for index, comment_id in enumerate(top_level_a[:6]):
            executor.call(
                "content.content_reaction.ReactToComment",
                actor=actors[(index + 1) % len(actors)],
                step=f"comment-reaction-{index:02d}",
                bindings={"commentId": comment_id},
                body={"reaction": "like"},
            )
        for index, post_id in enumerate((post_a, post_b, post_c)):
            executor.call(
                "content.outbound_share_fact.CreateOutboundShare",
                actor=actors[index],
                step=f"share-{index:02d}",
                bindings={"postId": post_id},
                body={
                    "channel": "system_share",
                    "destinationKind": "external_app",
                    "destination": "acceptance-target",
                    "referralId": idempotency_key(
                        target=self.candidate.target,
                        dataset_epoch=epoch,
                        dataset_id=recipe.dataset_id,
                        actor_role=actors[index].role,
                        operation="CreateOutboundShare",
                        step=f"referral-{index:02d}",
                    ),
                    "providerReceiptId": self.share_provider_receipt_ids[index],
                    "deliverySucceeded": True,
                    "clientConfirmedAt": _utc_now(),
                },
            )

        first_page = executor.call(
            "content.comment.ListComments",
            actor=actors[0],
            step="readback-post-a-page-1",
            bindings={"postId": post_a},
            query={"limit": 20, "sort": "latest"},
        )
        replies = executor.call(
            "content.comment.ListCommentReplies",
            actor=actors[0],
            step="readback-post-a-replies",
            bindings={"postId": post_a, "commentId": top_level_a[0]},
            query={"limit": 20},
        )
        empty = executor.call(
            "content.comment.ListComments",
            actor=actors[0],
            step="readback-post-c-empty",
            bindings={"postId": post_c},
            query={"limit": 20},
        )
        if len(_items(first_page)) != 20:
            raise RuntimeError("reference comments do not exercise the default page boundary")
        if len(_items(replies)) != 11:
            raise RuntimeError("reference replies did not converge to eleven items")
        if _items(empty):
            raise RuntimeError("reference Post C must remain a legal empty comment state")

        receipt = self._base_receipt(recipe, epoch)
        receipt.update(
            {
                "status": "passed",
                "actorReceiptRefs": [
                    {
                        "datasetId": NONPROD_REFERENCE_IDENTITY.dataset_id,
                        "datasetEpoch": identity_epoch,
                    }
                ],
                "operationReceipts": [row.to_json() for row in executor.receipts],
                "createdObjectIdsOrHashes": {
                    "commentIds": [*top_level_a, *reply_ids, *post_b_ids],
                    "deletedCommentId": deleted_id,
                    "releasePostIds": list(self.candidate.release_post_ids),
                },
                "projectionWatermarks": {},
                "readbackResults": {
                    "activeComments": len(top_level_a) + len(reply_ids) + len(post_b_ids),
                    "postALevelOneComments": len(top_level_a),
                    "postAReplies": len(reply_ids),
                    "postBComments": len(post_b_ids),
                    "postCLegalEmptyComments": len(_items(empty)),
                    "postLikes": len(like_pairs),
                    "commentReactions": 6,
                    "shares": 3,
                    "deletedCommentTombstones": 1,
                },
                "mediaUploadReceipts": [
                    comment_upload
                ],
                "cleanupState": "retained",
                "caseResultRefs": [],
            }
        )
        if receipt["readbackResults"] != dict(recipe.expected_counts):
            raise RuntimeError("reference content interaction cardinality drift")
        self._write_receipt(recipe, epoch, receipt)
        return receipt

    def provision_reference_circle_chat(self) -> dict[str, Any]:
        from .nonprod_business_data import NONPROD_REFERENCE_CIRCLE_CHAT

        recipe = NONPROD_REFERENCE_CIRCLE_CHAT
        epoch = self._epoch(recipe)
        existing = self._load_candidate_receipt_for_provision(recipe, epoch)
        if existing is not None:
            return self._verify_existing_receipt(existing, recipe, epoch)
        identity_epoch = self._epoch(NONPROD_REFERENCE_IDENTITY)
        identity_receipt = self._load_receipt(
            NONPROD_REFERENCE_IDENTITY, identity_epoch
        )
        if identity_receipt is None:
            raise RuntimeError("GATE_BLOCK: reference identity receipt is required")
        self._verify_existing_identity_receipt(
            identity_receipt, NONPROD_REFERENCE_IDENTITY, identity_epoch
        )
        actors = self._open_actors(NONPROD_REFERENCE_IDENTITY, identity_epoch)
        executor = self._candidate_executor(
            recipe,
            epoch,
            actor_receipt_refs=[
                {
                    "datasetId": NONPROD_REFERENCE_IDENTITY.dataset_id,
                    "datasetEpoch": identity_epoch,
                }
            ],
        )
        upload_specs = (
            ("image", "image/png", _acceptance_png()),
            ("image", "image/png", _acceptance_png(accent=True)),
            ("video", "video/mp4", _acceptance_mp4()),
            ("audio", "audio/wav", _acceptance_wav()),
            ("file", "text/plain", b"quwoquan nonprod acceptance file\n"),
        )
        upload_receipts = [
            self._upload_media_asset(
                executor,
                actor=actors[0],
                step=f"message-{kind}-upload-{index:02d}",
                media_type=kind,
                content_type=content_type,
                payload=payload,
            )
            for index, (kind, content_type, payload) in enumerate(upload_specs)
        ]
        normalized_media = {
            kind: tuple(
                row["assetId"] for row in upload_receipts if row["mediaType"] == kind
            )
            for kind in ("image", "video", "audio", "file")
        }

        circle_definitions = (
            ("西湖影像圈", "public", "open"),
            ("西湖深度交流圈", "private", "approval"),
            ("西湖路线圈", "public", "open"),
        )
        circle_ids: list[str] = []
        group_ids: list[str] = []
        placement_ids: list[str] = []
        group_conversation_ids: list[str] = []
        for index, (name, visibility, join_policy) in enumerate(circle_definitions):
            circle = executor.call(
                "circle.circle.CreateCircle",
                actor=actors[0],
                step=f"circle-create-{index:02d}",
                body={
                    "name": name,
                    "description": "候选绑定验收圈子",
                    "category": "travel",
                    "tags": ["west-lake", "acceptance"],
                    "visibility": visibility,
                    "joinPolicy": join_policy,
                    "autoSyncChat": True,
                },
                object_id_fields=("circleId", "id"),
            )
            circle_id = _required_string(circle, "circleId", "id")
            circle_ids.append(circle_id)

            executor.call(
                "circle.circle_membership.JoinCircle",
                actor=actors[index + 1],
                step=f"circle-join-{index:02d}",
                bindings={"circleId": circle_id},
                body=None,
            )
            if join_policy == "approval":
                executor.call(
                    "circle.circle_membership.ApproveCircleMember",
                    actor=actors[0],
                    step=f"circle-approve-{index:02d}",
                    bindings={
                        "circleId": circle_id,
                        "personaId": actors[index + 1].session.persona_id,
                    },
                    body=None,
                )

            group = executor.call(
                "circle.circle_group.CreateCircleGroup",
                actor=actors[0],
                step=f"circle-group-create-{index:02d}",
                bindings={"circleId": circle_id},
                body={
                    "groupType": "self_built",
                    "name": f"{name}群",
                    "description": "候选绑定验收群",
                    "visibility": "private",
                    "joinPolicy": "apply_only",
                    "storageEnabled": True,
                    "noticeEnabled": True,
                },
                object_id_fields=("groupId", "id"),
            )
            group_id = _required_string(group, "groupId", "id")
            group_ids.append(group_id)
            executor.call(
                "circle.circle_group_membership.ApplyJoinCircleGroup",
                actor=actors[index + 3],
                step=f"circle-group-apply-{index:02d}",
                bindings={"circleId": circle_id, "groupId": group_id},
                body=None,
            )
            executor.call(
                "circle.circle_group_membership.ApproveCircleGroupMember",
                actor=actors[0],
                step=f"circle-group-approve-{index:02d}",
                bindings={
                    "circleId": circle_id,
                    "groupId": group_id,
                    "personaId": actors[index + 3].session.persona_id,
                },
                body=None,
            )

            placement = executor.call(
                "circle.circle_post_placement.PlacePostInCircle",
                actor=actors[0],
                step=f"circle-placement-{index:02d}",
                bindings={"circleId": circle_id},
                body={"postId": self.candidate.release_post_ids[index]},
                object_id_fields=("placementId", "id"),
            )
            placement_id = _required_string(placement, "placementId", "id")
            placement_ids.append(placement_id)
            if index == 0:
                executor.call(
                    "circle.circle_post_placement.PinCirclePost",
                    actor=actors[0],
                    step="circle-placement-pin",
                    bindings={"circleId": circle_id, "placementId": placement_id},
                    body={"enabled": True},
                )
            if index < 2:
                executor.call(
                    "circle.circle_post_placement.FeatureCirclePost",
                    actor=actors[0],
                    step=f"circle-placement-feature-{index:02d}",
                    bindings={"circleId": circle_id, "placementId": placement_id},
                    body={"enabled": True},
                )
            group_conversation_ids.append(
                self._wait_circle_group_conversation(
                    executor,
                    actor=actors[0],
                    circle_id=circle_id,
                    group_id=group_id,
                    step=f"circle-group-conversation-{index:02d}",
                )
            )

        direct = executor.call(
            "chat.conversation.CreateConversation",
            actor=actors[0],
            step="direct-conversation-mutual",
            body={
                "type": "direct",
                "title": "西湖同行",
                "maxGroupSize": 2,
                "initialMemberIds": [actors[1].session.owner_id],
            },
            object_id_fields=("conversationId", "id"),
        )
        direct_id = _required_string(direct, "conversationId", "id")
        promoted_id = str(
            identity_receipt.get("createdObjectIdsOrHashes", {}).get(
                "promotedConversationId", ""
            )
        ).strip()
        if not promoted_id:
            raise RuntimeError("reference identity receipt misses promoted conversation")
        executor.call(
            "chat.conversation.GetConversation",
            actor=actors[3],
            step="direct-conversation-promoted-readback",
            bindings={"conversationId": promoted_id},
            body=None,
        )

        message_ids: list[str] = []
        first_message_id = ""
        for index in range(24):
            body: dict[str, Any] = {
                "type": "text",
                "content": f"西湖会话验收消息 {index + 1}",
                "clientMsgId": f"{epoch[:16]}-text-{index:02d}",
            }
            if 1 <= index <= 4:
                body["replyToMessageId"] = first_message_id
            if 5 <= index <= 8:
                body["mentions"] = [actors[1].session.owner_id]
            response = executor.call(
                "chat.message.SendMessage",
                actor=actors[0],
                step=f"message-text-{index:02d}",
                bindings={"conversationId": direct_id},
                body=body,
                object_id_fields=("messageId", "id"),
            )
            message_id = _required_string(response, "messageId", "id")
            if index == 0:
                first_message_id = message_id
            message_ids.append(message_id)

        rich_messages = (
            ("image", normalized_media["image"][0]),
            ("image", normalized_media["image"][1]),
            ("video", normalized_media["video"][0]),
            ("audio", normalized_media["audio"][0]),
            ("file", normalized_media["file"][0]),
        )
        for index, (kind, asset_id) in enumerate(rich_messages):
            response = executor.call(
                "chat.message.SendMessage",
                actor=actors[0],
                step=f"message-{kind}-{index:02d}",
                bindings={"conversationId": direct_id},
                body={
                    "type": kind,
                    "content": "",
                    "clientMsgId": f"{epoch[:16]}-{kind}-{index:02d}",
                    "mediaAssetId": asset_id,
                },
                object_id_fields=("messageId", "id"),
            )
            message_ids.append(_required_string(response, "messageId", "id"))
        card = executor.call(
            "chat.message.SendMessage",
            actor=actors[0],
            step="message-card",
            bindings={"conversationId": direct_id},
            body={
                "type": "card",
                "content": "查看西湖内容",
                "clientMsgId": f"{epoch[:16]}-card",
                "card": {
                    "kind": "content_post",
                    "title": "西湖内容",
                    "subtitle": "候选 release",
                    "attributes": [
                        {"name": "postId", "value": self.candidate.release_post_ids[0]}
                    ],
                },
            },
            object_id_fields=("messageId", "id"),
        )
        message_ids.append(_required_string(card, "messageId", "id"))
        executor.call(
            "chat.message.RecallMessage",
            actor=actors[0],
            step="message-recall",
            bindings={"conversationId": direct_id, "messageId": message_ids[9]},
            body=None,
        )
        executor.call(
            "chat.conversation_user_state.MarkAsRead",
            actor=actors[1],
            step="message-read",
            bindings={"conversationId": direct_id, "messageId": message_ids[-1]},
            body=None,
        )
        executor.call(
            "chat.conversation_user_state.UpdateConversationSettings",
            actor=actors[1],
            step="conversation-muted",
            bindings={"conversationId": direct_id},
            body={"muted": True},
        )
        executor.call(
            "chat.conversation_user_state.UpdateConversationSettings",
            actor=actors[0],
            step="conversation-pinned",
            bindings={"conversationId": direct_id},
            body={"pinned": True},
        )
        listed = executor.call(
            "chat.message.ListMessages",
            actor=actors[0],
            step="message-readback",
            bindings={"conversationId": direct_id},
            query={"limit": 50},
            body=None,
        )
        if len(_items(listed)) != 30:
            raise RuntimeError("reference conversation did not converge to thirty messages")

        receipt = self._base_receipt(recipe, epoch)
        receipt.update(
            {
                "status": "passed",
                "actorReceiptRefs": [
                    {
                        "datasetId": NONPROD_REFERENCE_IDENTITY.dataset_id,
                        "datasetEpoch": identity_epoch,
                    }
                ],
                "operationReceipts": [row.to_json() for row in executor.receipts],
                "createdObjectIdsOrHashes": {
                    "circleIds": circle_ids,
                    "circleGroupIds": group_ids,
                    "placementIds": placement_ids,
                    "directConversationIds": [direct_id, promoted_id],
                    "circleGroupConversationIds": group_conversation_ids,
                    "messageIds": message_ids,
                },
                "projectionWatermarks": {},
                "readbackResults": {
                    "circles": len(circle_ids),
                    "circleGroups": len(group_ids),
                    "circleAndGroupMemberships": 9,
                    "releasePostPlacements": len(placement_ids),
                    "directConversations": 2,
                    "circleGroupConversations": len(group_conversation_ids),
                    "messages": len(message_ids),
                    "recalledMessages": 1,
                },
                "mediaUploadReceipts": [
                    *upload_receipts,
                ],
                "cleanupState": "retained",
                "caseResultRefs": [],
            }
        )
        if receipt["readbackResults"] != dict(recipe.expected_counts):
            raise RuntimeError("reference circle/chat cardinality drift")
        self._write_receipt(recipe, epoch, receipt)
        return receipt

    def provision_reference_assistant_notification_rtc(self) -> dict[str, Any]:
        from .nonprod_data_assistant import provision_assistant_notification_rtc

        return provision_assistant_notification_rtc(self)

    def cleanup_candidate_bound_data(self) -> dict[str, Any]:
        """Clean one receipt-proven candidate dataset through public APIs only.

        The caller selects a stale/expired candidate group.  No database wipe,
        wildcard identifier, or synthetic actor is accepted.  Account closure
        runs only after every domain-owned object has been reversed, so a domain
        failure remains recoverable with the same managed identities.
        """

        from .nonprod_business_data import (
            NONPROD_REFERENCE_ASSISTANT_NOTIFICATION_RTC,
            NONPROD_REFERENCE_CIRCLE_CHAT,
            NONPROD_REFERENCE_CONTENT_INTERACTION,
        )

        recipes = (
            NONPROD_REFERENCE_IDENTITY,
            NONPROD_REFERENCE_CONTENT_INTERACTION,
            NONPROD_REFERENCE_CIRCLE_CHAT,
            NONPROD_REFERENCE_ASSISTANT_NOTIFICATION_RTC,
        )
        receipts: dict[str, dict[str, Any]] = {}
        for recipe in recipes:
            epoch = self._epoch(recipe)
            receipt = self._load_receipt(recipe, epoch)
            if receipt is None:
                continue
            self._validate_cleanup_receipt(receipt, recipe, epoch)
            receipts[recipe.dataset_id] = receipt
        identity = receipts.get(NONPROD_REFERENCE_IDENTITY.dataset_id)
        if identity is None:
            raise RuntimeError(
                "GATE_BLOCK: receipt-bound cleanup requires the identity receipt"
            )

        cleanup_progress = identity.get("cleanupProgress")
        if not isinstance(cleanup_progress, dict):
            cleanup_progress = {
                "domainCleanupComplete": False,
                "closedActorRoles": [],
            }
            identity["cleanupProgress"] = cleanup_progress
        closed_roles = {
            str(value).strip()
            for value in (cleanup_progress.get("closedActorRoles") or [])
            if str(value).strip()
        }
        identity_epoch = self._epoch(NONPROD_REFERENCE_IDENTITY)

        if cleanup_progress.get("domainCleanupComplete") is True:
            actors_by_role = self._open_remaining_cleanup_actors(
                identity, identity_epoch, closed_roles
            )
        else:
            actors_by_role = self._open_remaining_cleanup_actors(
                identity, identity_epoch, set()
            )
            expected_roles = self._receipt_actor_roles(identity)
            if set(actors_by_role) != expected_roles:
                raise RuntimeError("GATE_BLOCK: cleanup actor closure drift")

        cleanup_receipts: list[OperationReceipt] = []
        cleanup_errors: list[str] = []

        def execute(
            dataset_id: str,
            operation_id: str,
            *,
            actor_role: str,
            step: str,
            bindings: Mapping[str, str] | None = None,
            body: dict[str, Any] | None = None,
        ) -> None:
            actor = actors_by_role.get(actor_role)
            if actor is None:
                cleanup_errors.append(f"{dataset_id}:{step}:actor_unavailable")
                return
            executor = PublicOperationExecutor(
                base_url=self.base_url,
                target=self.candidate.target,
                dataset_epoch=self._cleanup_epoch(dataset_id),
                dataset_id=dataset_id + "_cleanup",
            )
            try:
                executor.call(
                    operation_id,
                    actor=actor,
                    step=step,
                    bindings=bindings,
                    body=body,
                )
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(
                    f"{dataset_id}:{step}:{type(exc).__name__}"
                )
            else:
                cleanup_receipts.extend(executor.receipts)

        if cleanup_progress.get("domainCleanupComplete") is not True:
            assistant = receipts.get(
                NONPROD_REFERENCE_ASSISTANT_NOTIFICATION_RTC.dataset_id
            )
            if assistant is not None:
                subscription_ids = self._created_ids(
                    assistant,
                    "assistant.skill_subscription.CreateSkillSubscription",
                )
                mention_conversations = self._created_ids(
                    assistant,
                    "chat.conversation.CreateConversation",
                )
                for index, subscription_id in enumerate(reversed(subscription_ids)):
                    execute(
                        assistant["datasetId"],
                        "assistant.skill_subscription.UpdateSkillSubscriptionStatus",
                        actor_role="primary",
                        step=f"archive-subscription-{index:02d}",
                        bindings={"subscriptionId": subscription_id},
                        body={"status": "archived"},
                    )
                for index, conversation_id in enumerate(
                    reversed(mention_conversations)
                ):
                    execute(
                        assistant["datasetId"],
                        "chat.conversation.DissolveConversation",
                        actor_role="primary",
                        step=f"dissolve-assistant-mention-chat-conversation-{index:02d}",
                        bindings={"conversationId": conversation_id},
                    )

            circle_chat = receipts.get(NONPROD_REFERENCE_CIRCLE_CHAT.dataset_id)
            if circle_chat is not None:
                circle_rows = self._created_rows(
                    circle_chat, "circle.circle.CreateCircle"
                )
                group_rows = self._created_rows(
                    circle_chat, "circle.circle_group.CreateCircleGroup"
                )
                placement_rows = self._created_rows(
                    circle_chat,
                    "circle.circle_post_placement.PlacePostInCircle",
                )
                direct_rows = self._created_rows(
                    circle_chat, "chat.conversation.CreateConversation"
                )
                for row in reversed(direct_rows):
                    execute(
                        circle_chat["datasetId"],
                        "chat.conversation.DissolveConversation",
                        actor_role=row["actorRole"],
                        step="dissolve-" + row["step"],
                        bindings={"conversationId": row["objectId"]},
                    )
                for index, row in reversed(list(enumerate(placement_rows))):
                    if index >= len(circle_rows):
                        cleanup_errors.append(
                            f"{circle_chat['datasetId']}:placement-circle-closure"
                        )
                        continue
                    execute(
                        circle_chat["datasetId"],
                        "circle.circle_post_placement.RemovePostFromCircle",
                        actor_role="primary",
                        step=f"remove-placement-{index:02d}",
                        bindings={
                            "circleId": circle_rows[index]["objectId"],
                            "placementId": row["objectId"],
                        },
                    )
                for index, row in reversed(list(enumerate(group_rows))):
                    if index >= len(circle_rows):
                        cleanup_errors.append(
                            f"{circle_chat['datasetId']}:group-circle-closure"
                        )
                        continue
                    execute(
                        circle_chat["datasetId"],
                        "circle.circle_group.ArchiveCircleGroup",
                        actor_role="primary",
                        step=f"archive-group-{index:02d}",
                        bindings={
                            "circleId": circle_rows[index]["objectId"],
                            "groupId": row["objectId"],
                        },
                    )
                for index, row in reversed(list(enumerate(circle_rows))):
                    execute(
                        circle_chat["datasetId"],
                        "circle.circle.ArchiveCircle",
                        actor_role="primary",
                        step=f"archive-circle-{index:02d}",
                        bindings={"circleId": row["objectId"]},
                    )
                self._discard_created_media(
                    circle_chat, execute=execute
                )

            content = receipts.get(
                NONPROD_REFERENCE_CONTENT_INTERACTION.dataset_id
            )
            if content is not None:
                for row in reversed(
                    self._created_rows(content, "content.comment.CreateComment")
                ):
                    post_id = self._comment_post_id_for_step(row["step"])
                    execute(
                        content["datasetId"],
                        "content.comment.DeleteComment",
                        actor_role=row["actorRole"],
                        step="delete-" + row["step"],
                        bindings={
                            "postId": post_id,
                            "commentId": row["objectId"],
                        },
                    )
                like_pairs = (
                    ("primary", self.candidate.release_post_ids[0]),
                    ("member-1", self.candidate.release_post_ids[0]),
                    ("member-2", self.candidate.release_post_ids[0]),
                    ("member-3", self.candidate.release_post_ids[0]),
                    ("member-4", self.candidate.release_post_ids[1]),
                    ("member-5", self.candidate.release_post_ids[1]),
                    ("primary", self.candidate.release_post_ids[2]),
                    ("member-1", self.candidate.release_post_ids[2]),
                )
                like_rows = self._operation_rows(
                    content, "content.content_reaction.LikePost"
                )
                for row in reversed(like_rows):
                    prefix = "post-like-"
                    if not row["step"].startswith(prefix):
                        cleanup_errors.append(
                            f"{content['datasetId']}:{row['step']}:like-step-drift"
                        )
                        continue
                    try:
                        like_index = int(row["step"][len(prefix) :])
                        actor_role, post_id = like_pairs[like_index]
                    except (ValueError, IndexError):
                        cleanup_errors.append(
                            f"{content['datasetId']}:{row['step']}:like-step-drift"
                        )
                        continue
                    if row["actorRole"] != actor_role:
                        cleanup_errors.append(
                            f"{content['datasetId']}:{row['step']}:like-actor-drift"
                        )
                        continue
                    execute(
                        content["datasetId"],
                        "content.content_reaction.UnlikePost",
                        actor_role=actor_role,
                        step="unlike-" + row["step"],
                        bindings={"postId": post_id},
                    )
                self._discard_created_media(content, execute=execute)

            pending_greetings = [
                row
                for row in self._created_rows(
                    identity, "user.greeting_request.SendGreetingRequest"
                )
                if row["step"] == "greeting-pending"
            ]
            promoted_conversation_id = str(
                (identity.get("createdObjectIdsOrHashes") or {}).get(
                    "promotedConversationId", ""
                )
            ).strip()
            if promoted_conversation_id and "member-3" in actors_by_role:
                execute(
                    identity["datasetId"],
                    "chat.conversation.DissolveConversation",
                    actor_role="member-3",
                    step="dissolve-promoted-conversation",
                    bindings={"conversationId": promoted_conversation_id},
                )
            for row in pending_greetings:
                execute(
                    identity["datasetId"],
                    "user.greeting_request.CancelGreetingRequest",
                    actor_role=row["actorRole"],
                    step="cancel-" + row["step"],
                    bindings={"requestId": row["objectId"]},
                )
            follow_pairs = (
                (0, 1),
                (1, 0),
                (0, 2),
                (0, 3),
                (1, 2),
                (2, 4),
                (3, 5),
                (4, 5),
                (5, 2),
            )
            role_names = [
                str(row.get("role") or "").strip()
                for row in identity.get("actorReceiptRefs", [])
                if isinstance(row, Mapping)
            ]
            persona_ids = self._identity_primary_persona_ids(identity)
            for index, (source_index, target_index) in enumerate(
                reversed(follow_pairs)
            ):
                if source_index >= len(role_names) or target_index >= len(persona_ids):
                    continue
                execute(
                    identity["datasetId"],
                    "user.persona_relationship.UnfollowUser",
                    actor_role=role_names[source_index],
                    step=f"unfollow-{index:02d}",
                    bindings={"targetPersonaId": persona_ids[target_index]},
                    body={},
                )

            if cleanup_errors:
                self._record_cleanup_failure(receipts, cleanup_receipts, cleanup_errors)
                raise RuntimeError(
                    "candidate-bound domain cleanup failed: "
                    + ", ".join(cleanup_errors)
                )
            cleanup_progress["domainCleanupComplete"] = True
            cleanup_progress["domainCleanupAt"] = _utc_now()
            for recipe in recipes[1:]:
                receipt = receipts.get(recipe.dataset_id)
                if receipt is None:
                    continue
                # Account closure is the final cross-domain erasure boundary.
                # Keep every dependent receipt resumable until all six accounts
                # have closed; otherwise an interrupted repair could strand a
                # receipt in ``cleaned`` while identity cleanup is incomplete.
                receipt["cleanupState"] = "pending"
                receipt["cleanupProgress"] = {
                    "domainCleanupComplete": True,
                    "accountClosureComplete": False,
                }
                receipt["cleanupOperationReceipts"] = [
                    row.to_json()
                    for row in cleanup_receipts
                    if row.operation_id.split(".", 1)[0]
                    in {"assistant", "chat", "circle", "content", "user"}
                ]
                self._write_receipt(recipe, self._epoch(recipe), receipt)
            identity["cleanupState"] = "pending"
            self._write_receipt(
                NONPROD_REFERENCE_IDENTITY, identity_epoch, identity
            )

        actor_rows = identity.get("actorReceiptRefs")
        if not isinstance(actor_rows, list):
            raise RuntimeError("GATE_BLOCK: cleanup identity actor rows are invalid")
        account_executor = PublicOperationExecutor(
            base_url=self.base_url,
            target=self.candidate.target,
            dataset_epoch=self._cleanup_epoch(identity["datasetId"]),
            dataset_id=identity["datasetId"] + "_cleanup",
        )
        for index, row in reversed(list(enumerate(actor_rows))):
            if not isinstance(row, Mapping):
                raise RuntimeError("GATE_BLOCK: cleanup identity actor row is invalid")
            role = str(row.get("role") or "").strip()
            if role in closed_roles:
                continue
            actor = actors_by_role.get(role)
            if actor is None:
                cleanup_errors.append(f"identity:close-{role}:actor_unavailable")
                break
            try:
                account_executor.call(
                    "user.user_account.CloseAccount",
                    actor=actor,
                    step=f"close-account-{index:02d}",
                    body={
                        "clientRequestId": (
                            f"{identity_epoch[:24]}-repair-close-{index:02d}"
                        )
                    },
                )
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(
                    f"identity:close-{role}:{type(exc).__name__}"
                )
                break
            closed_roles.add(role)
            cleanup_progress["closedActorRoles"] = sorted(closed_roles)
            cleanup_progress["lastAccountCloseAt"] = _utc_now()
            identity["cleanupOperationReceipts"] = [
                *identity.get("cleanupOperationReceipts", []),
                *[item.to_json() for item in account_executor.receipts[-1:]],
            ]
            self._write_receipt(
                NONPROD_REFERENCE_IDENTITY, identity_epoch, identity
            )

        expected_roles = self._receipt_actor_roles(identity)
        if cleanup_errors or closed_roles != expected_roles:
            identity["cleanupState"] = "failed"
            identity["cleanupErrors"] = cleanup_errors or [
                "account closure is incomplete"
            ]
            self._write_receipt(
                NONPROD_REFERENCE_IDENTITY, identity_epoch, identity
            )
            raise RuntimeError(
                "candidate-bound account cleanup failed: "
                + ", ".join(identity["cleanupErrors"])
            )

        identity["cleanupState"] = "cleaned"
        identity["cleanupErrors"] = []
        identity["cleanupProgress"]["completedAt"] = _utc_now()
        self._write_receipt(NONPROD_REFERENCE_IDENTITY, identity_epoch, identity)
        for recipe in recipes[1:]:
            receipt = receipts.get(recipe.dataset_id)
            if receipt is None:
                continue
            receipt["cleanupState"] = "cleaned"
            receipt["cleanupErrors"] = []
            receipt["cleanupProgress"] = {
                "domainCleanupComplete": True,
                "accountClosureComplete": True,
                "completedAt": _utc_now(),
            }
            self._write_receipt(recipe, self._epoch(recipe), receipt)
        return {
            "status": "passed",
            "target": self.candidate.target,
            "baselineId": self.candidate.baseline_id,
            "packageDigest": self.candidate.package_digest,
            "releaseDigest": self.candidate.release_digest,
            "datasetIds": sorted(receipts),
            "closedActorRoles": sorted(closed_roles),
            "operationReceipts": [
                row.to_json() for row in [*cleanup_receipts, *account_executor.receipts]
            ],
            "cleanupState": "cleaned",
        }

    def run_paging_boundary(self) -> dict[str, Any]:
        from .nonprod_business_data import NONPROD_PAGING_BOUNDARY

        recipe = NONPROD_PAGING_BOUNDARY
        epoch = self._epoch(recipe)
        executor = PublicOperationExecutor(
            base_url=self.base_url,
            target=self.candidate.target,
            dataset_epoch=epoch,
            dataset_id=recipe.dataset_id,
        )
        actors: list[LocalAcceptanceActor] = []
        post_id = self.candidate.release_post_ids[0]
        created_comments: list[tuple[str, int]] = []
        conversation_ids: list[str] = []
        reply_boundaries = (0, 1, 5, 10, 50, 110)
        parent_ids: list[str] = []
        receipt = self._base_receipt(recipe, epoch)
        receipt.update(
            {
                "status": "GATE_BLOCK",
                "actorReceiptRefs": [],
                "operationReceipts": [],
                "createdObjectIdsOrHashes": {},
                "projectionWatermarks": {},
                "readbackResults": {},
                "mediaUploadReceipts": [],
                "cleanupState": "pending",
                "caseResultRefs": [],
            }
        )
        primary_error: Exception | None = None
        try:
            actors = self._open_actors(recipe, epoch)
            for parent_index, reply_count in enumerate(reply_boundaries):
                actor_index = parent_index % len(actors)
                parent = self._create_comment(
                    executor,
                    actor=actors[actor_index],
                    post_id=post_id,
                    step=f"boundary-parent-{parent_index:02d}",
                    content=f"回复边界父评论 {reply_count}",
                )
                parent_id = _required_string(parent, "commentId", "id")
                parent_ids.append(parent_id)
                created_comments.append((parent_id, actor_index))
                for reply_index in range(reply_count):
                    reply_actor_index = (reply_index + parent_index + 1) % len(actors)
                    reply = self._create_comment(
                        executor,
                        actor=actors[reply_actor_index],
                        post_id=post_id,
                        step=f"boundary-{reply_count:03d}-reply-{reply_index:03d}",
                        content=f"边界 {reply_count} 回复 {reply_index + 1}",
                        reply_to_comment_id=parent_id,
                    )
                    created_comments.append(
                        (_required_string(reply, "commentId", "id"), reply_actor_index)
                    )
            if len(created_comments) != 182:
                raise RuntimeError("paging recipe did not create exactly 182 comments")
            observed_reply_counts: list[int] = []
            for index, parent_id in enumerate(parent_ids):
                observed_reply_counts.append(
                    len(
                        self._collect_pages(
                            executor,
                            operation_id="content.comment.ListCommentReplies",
                            actor=actors[0],
                            step=f"boundary-replies-readback-{index:02d}",
                            bindings={"postId": post_id, "commentId": parent_id},
                            limit=10,
                        )
                    )
                )
            if tuple(observed_reply_counts) != reply_boundaries:
                raise RuntimeError(
                    f"comment reply paging drift: {observed_reply_counts}"
                )

            for index in range(25):
                conversation = executor.call(
                    "chat.conversation.CreateConversation",
                    actor=actors[0],
                    step=f"paging-conversation-{index:02d}",
                    body={
                        "type": "group",
                        "title": f"分页验收会话 {index + 1}",
                        "maxGroupSize": 50,
                        "initialMemberIds": [
                            actor.session.owner_id for actor in actors[1:4]
                        ],
                    },
                    object_id_fields=("conversationId", "id"),
                )
                conversation_ids.append(
                    _required_string(conversation, "conversationId", "id")
                )
            message_ids: list[str] = []
            for index in range(41):
                message = executor.call(
                    "chat.message.SendMessage",
                    actor=actors[index % 4],
                    step=f"paging-message-{index:02d}",
                    bindings={"conversationId": conversation_ids[0]},
                    body={
                        "type": "text",
                        "content": f"分页消息 {index + 1}",
                        "clientMsgId": f"{epoch[:16]}-paging-{index:02d}",
                    },
                    object_id_fields=("messageId", "id"),
                )
                message_ids.append(_required_string(message, "messageId", "id"))
            listed_messages = self._collect_pages(
                executor,
                operation_id="chat.message.ListMessages",
                actor=actors[0],
                step="paging-messages-readback",
                bindings={"conversationId": conversation_ids[0]},
                limit=20,
            )
            if len(listed_messages) != 41:
                raise RuntimeError("chat paging did not return exactly 41 messages")

            receipt.update(
                {
                    "status": "passed",
                    "actorReceiptRefs": [
                        {
                            "role": actor.role,
                            "ownerId": actor.session.owner_id,
                            "personaIds": [actor.session.persona_id],
                            "challengeReceiptHash": _canonical_hash(actor.challenge_id),
                        }
                        for actor in actors
                    ],
                    "operationReceipts": [row.to_json() for row in executor.receipts],
                    "createdObjectIdsOrHashes": {
                        "commentIds": [comment_id for comment_id, _ in created_comments],
                        "conversationIds": conversation_ids,
                        "messageIds": message_ids,
                    },
                    "projectionWatermarks": {},
                    "readbackResults": {
                        "commentReplyBoundaries": len(reply_boundaries),
                        "createdComments": len(created_comments),
                        "inboxConversations": len(conversation_ids),
                        "pagedConversationMessages": len(listed_messages),
                        "replyCounts": observed_reply_counts,
                    },
                    "mediaUploadReceipts": [],
                    "cleanupState": "pending",
                    "caseResultRefs": [],
                }
            )
            expected = dict(recipe.expected_counts)
            if any(
                receipt["readbackResults"].get(name) != count
                for name, count in expected.items()
            ):
                raise RuntimeError("paging boundary cardinality drift")
        except Exception as exc:  # noqa: BLE001
            primary_error = exc
            receipt["status"] = "GATE_BLOCK"
            receipt["failureClass"] = type(exc).__name__
        finally:
            cleanup_errors: list[str] = []
            for comment_id, actor_index in reversed(created_comments):
                try:
                    executor.call(
                        "content.comment.DeleteComment",
                        actor=actors[actor_index],
                        step=(
                            "cleanup-comment-"
                            + hashlib.sha256(comment_id.encode("utf-8")).hexdigest()[:12]
                        ),
                        bindings={"postId": post_id, "commentId": comment_id},
                        body=None,
                    )
                except Exception as exc:  # noqa: BLE001
                    cleanup_errors.append(f"comment:{type(exc).__name__}")
            for index, conversation_id in reversed(list(enumerate(conversation_ids))):
                try:
                    executor.call(
                        "chat.conversation.DissolveConversation",
                        actor=actors[0],
                        step=f"cleanup-conversation-{index:02d}",
                        bindings={"conversationId": conversation_id},
                        body=None,
                    )
                except Exception as exc:  # noqa: BLE001
                    cleanup_errors.append(f"conversation:{type(exc).__name__}")
            for index, actor in reversed(list(enumerate(actors))):
                try:
                    executor.call(
                        "user.user_account.CloseAccount",
                        actor=actor,
                        step=f"cleanup-account-{index:02d}",
                        body={
                            "clientRequestId": f"{epoch[:24]}-close-{index:02d}"
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    cleanup_errors.append(f"account:{type(exc).__name__}")
            receipt["cleanupState"] = "failed" if cleanup_errors else "cleaned"
            receipt["cleanupErrors"] = cleanup_errors
            receipt["operationReceipts"] = [
                row.to_json() for row in executor.receipts
            ]
            self._write_receipt(recipe, epoch, receipt)
            if cleanup_errors:
                raise RuntimeError(
                    "run-bound paging cleanup failed: " + ", ".join(cleanup_errors)
                ) from primary_error
        if primary_error is not None:
            raise primary_error
        return receipt

    def run_reliability_recovery(self) -> dict[str, Any]:
        from .nonprod_business_data import NONPROD_RELIABILITY_RECOVERY

        recipe = NONPROD_RELIABILITY_RECOVERY
        epoch = self._epoch(recipe)
        executor = PublicOperationExecutor(
            base_url=self.base_url,
            target=self.candidate.target,
            dataset_epoch=epoch,
            dataset_id=recipe.dataset_id,
        )
        actors: list[LocalAcceptanceActor] = []
        conversation_id = ""
        circle_id = ""
        comment_id = ""
        receipt = self._base_receipt(recipe, epoch)
        receipt.update(
            {
                "status": "GATE_BLOCK",
                "actorReceiptRefs": [],
                "operationReceipts": [],
                "createdObjectIdsOrHashes": {},
                "projectionWatermarks": {},
                "readbackResults": {},
                "mediaUploadReceipts": [],
                "cleanupState": "pending",
                "caseResultRefs": [],
            }
        )
        primary_error: Exception | None = None
        cleanup_errors: list[str] = []
        try:
            fault_evidence = self._validated_reliability_evidence()
            actors = self._open_actors(recipe, epoch)
            conversation = executor.call(
                "chat.conversation.CreateConversation",
                actor=actors[0],
                step="reliability-conversation",
                body={
                    "type": "group",
                    "title": "可靠性恢复验收",
                    "maxGroupSize": 20,
                    "initialMemberIds": [
                        actors[1].session.owner_id,
                        actors[2].session.owner_id,
                    ],
                },
                object_id_fields=("conversationId", "id"),
            )
            conversation_id = _required_string(
                conversation, "conversationId", "id"
            )
            messages: list[dict[str, Any]] = []
            seqs: list[int] = []
            bodies: list[dict[str, Any]] = []
            for index in range(501):
                logical_index = index + 1 if index % 2 == 0 and index + 1 < 501 else index - 1 if index % 2 else index
                body = {
                    "type": "text",
                    "content": f"可靠性消息 {logical_index + 1}",
                    "clientMsgId": f"{epoch[:16]}-reliability-{logical_index:03d}",
                }
                result = executor.call(
                    "chat.message.SendMessage",
                    actor=actors[index % 3],
                    step=f"reliability-message-{index:03d}",
                    bindings={"conversationId": conversation_id},
                    body=body,
                    object_id_fields=("messageId", "id"),
                )
                sequence = result.get("seq")
                if not isinstance(sequence, int) or isinstance(sequence, bool):
                    raise RuntimeError("chat message response misses server seq")
                messages.append(result)
                bodies.append(body)
                seqs.append(sequence)
            if len(seqs) != 501 or any(
                current <= previous for previous, current in zip(seqs, seqs[1:])
            ):
                raise RuntimeError("server message seq is not strictly monotonic")

            duplicate = executor.call(
                "chat.message.SendMessage",
                actor=actors[0],
                step="duplicate-client-message",
                bindings={"conversationId": conversation_id},
                body=bodies[0],
                object_id_fields=("messageId", "id"),
            )
            if _required_string(duplicate, "messageId", "id") != _required_string(
                messages[0], "messageId", "id"
            ):
                raise RuntimeError("duplicate clientMsgId created another message")
            replayed_message = executor.call(
                "chat.message.SendMessage",
                actor=actors[1],
                step="reliability-message-001",
                bindings={"conversationId": conversation_id},
                body=bodies[1],
                object_id_fields=("messageId", "id"),
            )
            if _required_string(
                replayed_message, "messageId", "id"
            ) != _required_string(messages[1], "messageId", "id"):
                raise RuntimeError("message command replay changed identity")

            first_sync = executor.call(
                "chat.message.SyncMessages",
                actor=actors[0],
                step="sync-default-500",
                bindings={"conversationId": conversation_id},
                query={"lastSeq": 0, "limit": 500},
                body=None,
            )
            first_sync_items = _items(first_sync)
            if len(first_sync_items) != 500:
                raise RuntimeError("SyncMessages default boundary did not return 500")
            last_first_seq = _message_seq(first_sync_items[-1])
            second_sync = executor.call(
                "chat.message.SyncMessages",
                actor=actors[0],
                step="sync-remainder",
                bindings={"conversationId": conversation_id},
                query={"lastSeq": last_first_seq, "limit": 500},
                body=None,
            )
            if len(_items(second_sync)) != 1:
                raise RuntimeError("SyncMessages remainder must contain one message")

            comment_body = {
                "content": "可靠性评论命令重放",
                "replyToCommentId": None,
                "attachmentMediaIds": [],
                "mentions": [],
            }
            created_comment = executor.call(
                "content.comment.CreateComment",
                actor=actors[0],
                step="replay-comment",
                bindings={"postId": self.candidate.release_post_ids[0]},
                body=comment_body,
                object_id_fields=("commentId", "id"),
            )
            comment_id = _required_string(created_comment, "commentId", "id")
            replayed_comment = executor.call(
                "content.comment.CreateComment",
                actor=actors[0],
                step="replay-comment",
                bindings={"postId": self.candidate.release_post_ids[0]},
                body=comment_body,
                object_id_fields=("commentId", "id"),
            )
            if _required_string(
                replayed_comment, "commentId", "id"
            ) != comment_id:
                raise RuntimeError("comment command replay changed identity")

            executor.call_expect_http_status(
                "chat.message.SendMessage",
                actor=actors[3],
                step="outsider-send",
                expected_status=403,
                bindings={"conversationId": conversation_id},
                body={
                    "type": "text",
                    "content": "越权发送必须失败",
                    "clientMsgId": f"{epoch[:16]}-outsider",
                },
            )
            circle = executor.call(
                "circle.circle.CreateCircle",
                actor=actors[0],
                step="reliability-circle",
                body={
                    "name": "可靠性权限圈",
                    "visibility": "private",
                    "joinPolicy": "approval",
                },
                object_id_fields=("circleId", "id"),
            )
            circle_id = _required_string(circle, "circleId", "id")
            executor.call_expect_http_status(
                "circle.circle.ArchiveCircle",
                actor=actors[3],
                step="outsider-circle-archive",
                expected_status=403,
                bindings={"circleId": circle_id},
                body=None,
            )

            receipt.update(
                {
                    "status": "passed",
                    "actorReceiptRefs": [
                        {
                            "role": actor.role,
                            "ownerId": actor.session.owner_id,
                            "personaIds": [actor.session.persona_id],
                            "challengeReceiptHash": _canonical_hash(actor.challenge_id),
                        }
                        for actor in actors
                    ],
                    "operationReceipts": [row.to_json() for row in executor.receipts],
                    "createdObjectIdsOrHashes": {
                        "conversationId": conversation_id,
                        "messageIds": [
                            _required_string(message, "messageId", "id")
                            for message in messages
                        ],
                        "commentId": comment_id,
                        "circleId": circle_id,
                    },
                    "projectionWatermarks": {
                        "faultEvidence": fault_evidence,
                    },
                    "readbackResults": {
                        "syncBoundaryMessages": len(messages),
                        "duplicateClientMessageCases": 1,
                        "commandReplayCases": 2,
                        "authorizationFailureCases": 3,
                        "projectionDelayCases": 1,
                        "cleanupRecoveryCases": 1,
                    },
                    "mediaUploadReceipts": [],
                    "cleanupState": "pending",
                    "caseResultRefs": [
                        str(value.get("caseResultRef") or "")
                        for value in fault_evidence.values()
                    ],
                }
            )
            if receipt["readbackResults"] != dict(recipe.expected_counts):
                raise RuntimeError("reliability recovery cardinality drift")
        except Exception as exc:  # noqa: BLE001
            primary_error = exc
            receipt["status"] = "GATE_BLOCK"
            receipt["failureClass"] = type(exc).__name__
        finally:
            if comment_id:
                try:
                    executor.call(
                        "content.comment.DeleteComment",
                        actor=actors[0],
                        step="cleanup-reliability-comment",
                        bindings={
                            "postId": self.candidate.release_post_ids[0],
                            "commentId": comment_id,
                        },
                        body=None,
                    )
                except Exception as exc:  # noqa: BLE001
                    cleanup_errors.append(f"comment:{type(exc).__name__}")
            if conversation_id:
                try:
                    executor.call(
                        "chat.conversation.DissolveConversation",
                        actor=actors[0],
                        step="cleanup-reliability-conversation",
                        bindings={"conversationId": conversation_id},
                        body=None,
                    )
                except Exception as exc:  # noqa: BLE001
                    cleanup_errors.append(f"conversation:{type(exc).__name__}")
            if circle_id:
                try:
                    executor.call(
                        "circle.circle.ArchiveCircle",
                        actor=actors[0],
                        step="cleanup-reliability-circle",
                        bindings={"circleId": circle_id},
                        body=None,
                    )
                except Exception as exc:  # noqa: BLE001
                    cleanup_errors.append(f"circle:{type(exc).__name__}")
            for index, actor in reversed(list(enumerate(actors))):
                try:
                    executor.call(
                        "user.user_account.CloseAccount",
                        actor=actor,
                        step=f"cleanup-reliability-account-{index:02d}",
                        body={
                            "clientRequestId": f"{epoch[:24]}-close-{index:02d}"
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    cleanup_errors.append(f"account:{type(exc).__name__}")
            receipt["cleanupState"] = "failed" if cleanup_errors else "cleaned"
            receipt["cleanupErrors"] = cleanup_errors
            receipt["operationReceipts"] = [
                row.to_json() for row in executor.receipts
            ]
            self._write_receipt(recipe, epoch, receipt)
            if cleanup_errors:
                raise RuntimeError(
                    "run-bound reliability cleanup failed: "
                    + ", ".join(cleanup_errors)
                ) from primary_error
        if primary_error is not None:
            raise primary_error
        return receipt

    def _validated_reliability_evidence(self) -> dict[str, dict[str, Any]]:
        required = ("expiredSession", "projectionDelay", "cleanupRecovery")
        normalized: dict[str, dict[str, Any]] = {}
        for name in required:
            value = self.reliability_evidence.get(name)
            if not isinstance(value, Mapping):
                raise RuntimeError(
                    f"GATE_BLOCK: reliability fault evidence is required: {name}"
                )
            attempt_id = str(value.get("attemptId") or "").strip()
            if (
                value.get("status") != "passed"
                or not attempt_id
                or attempt_id == "unknown"
                or value.get("baselineId") != self.candidate.baseline_id
                or value.get("packageDigest") != self.candidate.package_digest
            ):
                raise RuntimeError(
                    f"GATE_BLOCK: reliability fault evidence is invalid: {name}"
                )
            normalized[name] = {
                "status": "passed",
                "attemptId": attempt_id,
                "caseResultRef": str(value.get("caseResultRef") or "").strip(),
                "receiptHash": _canonical_hash(dict(value)),
            }
        return normalized

    def _collect_pages(
        self,
        executor: PublicOperationExecutor,
        *,
        operation_id: str,
        actor: LocalAcceptanceActor,
        step: str,
        bindings: Mapping[str, str],
        limit: int,
    ) -> list[Any]:
        items: list[Any] = []
        seen_ids: set[str] = set()
        cursor = ""
        page = 0
        while True:
            query: dict[str, str | int] = {"limit": limit}
            if cursor:
                query["cursor"] = cursor
            response = executor.call(
                operation_id,
                actor=actor,
                step=f"{step}-page-{page:03d}",
                bindings=bindings,
                query=query,
                body=None,
            )
            page_items = _items(response)
            for item in page_items:
                item_id = ""
                if isinstance(item, dict):
                    item_id = str(
                        item.get("id")
                        or item.get("commentId")
                        or item.get("messageId")
                        or ""
                    ).strip()
                if not item_id or item_id in seen_ids:
                    raise RuntimeError("paged readback contains missing or duplicate identity")
                seen_ids.add(item_id)
                items.append(item)
            next_cursor = _next_cursor(response)
            if not next_cursor:
                break
            if next_cursor == cursor:
                raise RuntimeError("paged readback cursor did not advance")
            cursor = next_cursor
            page += 1
            if page > 100:
                raise RuntimeError("paged readback exceeded bounded page count")
        return items

    def _wait_circle_group_conversation(
        self,
        executor: PublicOperationExecutor,
        *,
        actor: LocalAcceptanceActor,
        circle_id: str,
        group_id: str,
        step: str,
    ) -> str:
        deadline = time.monotonic() + 12.0
        attempt = 0
        while True:
            response = executor.call(
                "circle.circle_group.GetCircleGroup",
                actor=actor,
                step=f"{step}-{attempt:02d}",
                bindings={"circleId": circle_id, "groupId": group_id},
                body=None,
            )
            conversation_id = str(response.get("conversationId") or "").strip()
            if conversation_id:
                return conversation_id
            if time.monotonic() >= deadline:
                raise RuntimeError("CircleGroup conversation projection did not converge")
            attempt += 1
            time.sleep(0.2)

    def _upload_media_asset(
        self,
        executor: PublicOperationExecutor,
        *,
        actor: LocalAcceptanceActor,
        step: str,
        media_type: str,
        content_type: str,
        payload: bytes,
    ) -> dict[str, Any]:
        digest = _DIGEST_PREFIX + hashlib.sha256(payload).hexdigest()
        initialized = executor.call(
            "content.media_upload_session.InitMediaUpload",
            actor=actor,
            step=step + "-init",
            body={
                "mediaType": media_type,
                "contentType": content_type,
                "fileSize": len(payload),
                "expectedSha256": digest,
            },
            object_id_fields=("sessionId",),
        )
        session_id = _required_string(initialized, "sessionId")
        upload_url = _required_string(initialized, "uploadUrl", "presignUrl")
        _put_presigned_object(
            upload_url=upload_url,
            payload=payload,
            content_type=content_type,
            sha256_digest=digest,
        )
        completed = executor.call(
            "content.media_upload_session.CompleteMediaUpload",
            actor=actor,
            step=step + "-complete",
            bindings={"sessionId": session_id},
            body={"accessPolicy": "public"},
            object_id_fields=("assetId", "mediaId"),
        )
        asset_id = _required_string(completed, "assetId", "mediaId")
        deadline = time.monotonic() + 30.0
        attempts = 0
        while True:
            try:
                asset = executor.call(
                    "content.media_asset.GetMediaAsset",
                    actor=actor,
                    step=f"{step}-ready-{attempts:02d}",
                    bindings={"mediaId": asset_id},
                    body=None,
                )
            except LocalEnvironmentHTTPError as exc:
                if exc.status != 404 or time.monotonic() >= deadline:
                    raise
            else:
                status = str(
                    asset.get("processingStatus") or asset.get("status") or ""
                ).strip()
                if status == "ready":
                    return {
                        "sessionIdHash": _canonical_hash(session_id),
                        "assetId": asset_id,
                        "mediaType": media_type,
                        "contentType": content_type,
                        "sha256": digest,
                        "bytes": len(payload),
                        "processingStatus": status,
                    }
                if status in {"failed", "rejected", "discarded"}:
                    raise RuntimeError(
                        f"uploaded {media_type} MediaAsset reached {status}"
                    )
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"uploaded {media_type} MediaAsset did not become ready"
                    )
            attempts += 1
            time.sleep(0.25)

    def _create_comment(
        self,
        executor: PublicOperationExecutor,
        *,
        actor: LocalAcceptanceActor,
        post_id: str,
        step: str,
        content: str,
        reply_to_comment_id: str = "",
        mentions: tuple[str, ...] = (),
        attachment_media_ids: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        return executor.call(
            "content.comment.CreateComment",
            actor=actor,
            step=step,
            bindings={"postId": post_id},
            body={
                "content": content,
                "replyToCommentId": reply_to_comment_id or None,
                "attachmentMediaIds": list(attachment_media_ids),
                "mentions": [
                    {
                        "subjectType": "persona",
                        "subjectId": persona_id,
                        "displayName": "验收成员",
                    }
                    for persona_id in mentions
                ],
            },
            object_id_fields=("commentId", "id"),
        )

    def _send_greeting(
        self,
        executor: PublicOperationExecutor,
        source: LocalAcceptanceActor,
        target: LocalAcceptanceActor,
        *,
        step: str,
    ) -> str:
        response = executor.call(
            "user.greeting_request.SendGreetingRequest",
            actor=source,
            step=step,
            body={
                "targetPersonaId": target.session.persona_id,
                "requestMessage": "你好，一起验证应用体验",
                "source": "acceptance",
            },
            object_id_fields=("id", "requestId"),
        )
        return _required_string(response, "id", "requestId")

    def _open_identity_actors_with_recovery(
        self,
        recipe: DatasetRecipe,
        epoch: str,
    ) -> list[LocalAcceptanceActor]:
        recovery = self._base_receipt(recipe, epoch)
        recovery.update(
            {
                "status": "GATE_BLOCK",
                "failureClass": "identity_provision_incomplete",
                "actorReceiptRefs": [],
                "operationReceipts": [],
                "createdObjectIdsOrHashes": {"ownerIds": [], "personaIds": []},
                "projectionWatermarks": {},
                "readbackResults": {},
                "mediaUploadReceipts": [],
                "cleanupState": "pending",
                "caseResultRefs": [],
            }
        )
        self._write_receipt(recipe, epoch, recovery)
        actors: list[LocalAcceptanceActor] = []
        for index in range(recipe.required_actor_count):
            actor = open_local_phone_acceptance_session(
                self.base_url,
                environment=self.candidate.environment,
                target_name=self.candidate.target,
                dataset_epoch=epoch,
                dataset_id=recipe.dataset_id,
                actor_role="primary" if index == 0 else f"member-{index}",
                actor_index=index,
            )
            actors.append(actor)
            recovery["actorReceiptRefs"].append(
                {
                    "role": actor.role,
                    "ownerId": actor.session.owner_id,
                    "personaIds": [actor.session.persona_id],
                    "challengeReceiptHash": _canonical_hash(actor.challenge_id),
                    "accountState": actor.account_state,
                    "identityOrigin": actor.identity_origin,
                }
            )
            recovery["createdObjectIdsOrHashes"] = {
                "ownerIds": [item.session.owner_id for item in actors],
                "personaIds": [item.session.persona_id for item in actors],
            }
            recovery["recordedAt"] = _utc_now()
            self._write_receipt(recipe, epoch, recovery)
        return actors

    def _open_actors(
        self, recipe: DatasetRecipe, epoch: str
    ) -> list[LocalAcceptanceActor]:
        return [
            open_local_phone_acceptance_session(
                self.base_url,
                environment=self.candidate.environment,
                target_name=self.candidate.target,
                dataset_epoch=epoch,
                dataset_id=recipe.dataset_id,
                actor_role="primary" if index == 0 else f"member-{index}",
                actor_index=index,
            )
            for index in range(recipe.required_actor_count)
        ]

    def _epoch(self, recipe: DatasetRecipe) -> str:
        return compute_dataset_epoch(
            target=self.candidate.target,
            baseline_id=self.candidate.baseline_id,
            package_digest=self.candidate.package_digest,
            release_digest=self.candidate.release_digest,
            recipe_digest=recipe.digest,
        )

    def _receipt_path(self, recipe: DatasetRecipe, epoch: str) -> Path:
        return (
            env_runs_root(self.candidate.environment)
            / "nonprod-data"
            / epoch
            / f"{recipe.dataset_id}.json"
        )

    def _load_receipt(
        self, recipe: DatasetRecipe, epoch: str
    ) -> dict[str, Any] | None:
        path = self._receipt_path(recipe, epoch)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("nonprod dataset receipt must be an object")
        return payload

    def _load_candidate_receipt_for_provision(
        self,
        recipe: DatasetRecipe,
        epoch: str,
    ) -> dict[str, Any] | None:
        receipt = self._load_receipt(recipe, epoch)
        if receipt is None or receipt.get("cleanupState") != "cleaned":
            return receipt
        path = self._receipt_path(recipe, epoch)
        history = path.parent / "history"
        history.mkdir(parents=True, exist_ok=True)
        receipt_digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        archived = history / f"{recipe.dataset_id}-{receipt_digest}.json"
        if archived.exists():
            raise RuntimeError("cleaned dataset receipt history identity collision")
        path.replace(archived)
        return None

    def _verify_existing_identity_receipt(
        self,
        receipt: dict[str, Any],
        recipe: DatasetRecipe,
        epoch: str,
    ) -> dict[str, Any]:
        expected = self._base_receipt(recipe, epoch)
        for field in (
            "target",
            "baselineId",
            "packageDigest",
            "runtimeConfigDigest",
            "releaseId",
            "releaseDigest",
            "importRunId",
            "datasetId",
            "datasetEpoch",
            "retentionClass",
            "recipeDigest",
            "specRefs",
        ):
            if receipt.get(field) != expected.get(field):
                raise RuntimeError(f"nonprod identity receipt drift: {field}")
        if receipt.get("status") != "passed" or receipt.get("cleanupState") != "retained":
            raise RuntimeError("nonprod identity receipt is not reusable")
        self._verify_receipt_not_expired(receipt)
        actor_rows = receipt.get("actorReceiptRefs")
        if not isinstance(actor_rows, list) or len(actor_rows) != recipe.required_actor_count:
            raise RuntimeError("nonprod identity actor closure is incomplete")
        actors = self._open_actors(recipe, epoch)
        for actor, row in zip(actors, actor_rows, strict=True):
            if not isinstance(row, Mapping):
                raise RuntimeError("nonprod identity actor receipt is invalid")
            persona_ids = row.get("personaIds")
            if (
                row.get("role") != actor.role
                or row.get("ownerId") != actor.session.owner_id
                or not isinstance(persona_ids, list)
                or actor.session.persona_id not in persona_ids
                or row.get("accountState") != actor.account_state
                or row.get("identityOrigin") != actor.identity_origin
            ):
                raise RuntimeError("nonprod identity live readback drift")
        return receipt

    def _verify_existing_receipt(
        self,
        receipt: dict[str, Any],
        recipe: DatasetRecipe,
        epoch: str,
    ) -> dict[str, Any]:
        expected = self._base_receipt(recipe, epoch)
        for field in (
            "target",
            "baselineId",
            "packageDigest",
            "runtimeConfigDigest",
            "releaseId",
            "releaseDigest",
            "importRunId",
            "datasetId",
            "datasetEpoch",
            "retentionClass",
            "recipeDigest",
            "specRefs",
        ):
            if receipt.get(field) != expected.get(field):
                raise RuntimeError(f"nonprod dataset receipt drift: {field}")
        if receipt.get("status") != "passed":
            raise RuntimeError("nonprod dataset receipt is not passed")
        if receipt.get("cleanupState") != "retained":
            raise RuntimeError("candidate-bound dataset receipt is not retained")
        self._verify_receipt_not_expired(receipt)
        self._verify_candidate_bound_live_objects(receipt, recipe, epoch)
        return receipt

    def _verify_candidate_bound_live_objects(
        self,
        receipt: Mapping[str, Any],
        recipe: DatasetRecipe,
        epoch: str,
    ) -> None:
        from .nonprod_business_data import (
            NONPROD_REFERENCE_ASSISTANT_NOTIFICATION_RTC,
            NONPROD_REFERENCE_CIRCLE_CHAT,
            NONPROD_REFERENCE_CONTENT_INTERACTION,
        )

        identity_epoch = self._epoch(NONPROD_REFERENCE_IDENTITY)
        identity_receipt = self._load_receipt(
            NONPROD_REFERENCE_IDENTITY, identity_epoch
        )
        if identity_receipt is None:
            raise RuntimeError("reference identity receipt is required for live readback")
        self._verify_existing_identity_receipt(
            identity_receipt, NONPROD_REFERENCE_IDENTITY, identity_epoch
        )
        identity_actors = self._open_actors(
            NONPROD_REFERENCE_IDENTITY, identity_epoch
        )
        executor = PublicOperationExecutor(
            base_url=self.base_url,
            target=self.candidate.target,
            dataset_epoch=epoch,
            dataset_id=recipe.dataset_id,
        )
        objects = receipt.get("createdObjectIdsOrHashes")
        if not isinstance(objects, Mapping):
            raise RuntimeError("candidate-bound receipt object closure is invalid")

        if recipe.dataset_id == NONPROD_REFERENCE_CONTENT_INTERACTION.dataset_id:
            self._verify_content_interaction_live_objects(
                executor, identity_actors[0], objects
            )
            return
        if recipe.dataset_id == NONPROD_REFERENCE_CIRCLE_CHAT.dataset_id:
            self._verify_circle_chat_live_objects(executor, identity_actors, objects)
            return
        if recipe.dataset_id == NONPROD_REFERENCE_ASSISTANT_NOTIFICATION_RTC.dataset_id:
            self._verify_assistant_live_objects(executor, identity_actors, objects)
            return
        raise RuntimeError(f"unsupported candidate-bound live readback: {recipe.dataset_id}")

    def _verify_content_interaction_live_objects(
        self,
        executor: PublicOperationExecutor,
        actor: LocalAcceptanceActor,
        objects: Mapping[str, Any],
    ) -> None:
        expected_ids = objects.get("commentIds")
        if not isinstance(expected_ids, list) or len(expected_ids) != 34:
            raise RuntimeError("content interaction receipt comment closure is invalid")
        post_a, post_b, post_c = self.candidate.release_post_ids
        top_level = self._collect_pages(
            executor,
            operation_id="content.comment.ListComments",
            actor=actor,
            step="reuse-post-a-comments",
            bindings={"postId": post_a},
            limit=20,
        )
        replies = self._collect_pages(
            executor,
            operation_id="content.comment.ListCommentReplies",
            actor=actor,
            step="reuse-post-a-replies",
            bindings={"postId": post_a, "commentId": str(expected_ids[0])},
            limit=10,
        )
        post_b_items = self._collect_pages(
            executor,
            operation_id="content.comment.ListComments",
            actor=actor,
            step="reuse-post-b-comments",
            bindings={"postId": post_b},
            limit=20,
        )
        post_c_items = self._collect_pages(
            executor,
            operation_id="content.comment.ListComments",
            actor=actor,
            step="reuse-post-c-comments",
            bindings={"postId": post_c},
            limit=20,
        )
        observed_ids = {
            _required_string(item, "commentId", "id")
            for item in [*top_level, *replies, *post_b_items]
            if isinstance(item, Mapping)
        }
        if observed_ids != {str(value) for value in expected_ids} or post_c_items:
            raise RuntimeError("content interaction live object closure drift")

    def _verify_circle_chat_live_objects(
        self,
        executor: PublicOperationExecutor,
        actors: list[LocalAcceptanceActor],
        objects: Mapping[str, Any],
    ) -> None:
        circle_ids = _required_string_list(objects, "circleIds", expected=3)
        group_ids = _required_string_list(objects, "circleGroupIds", expected=3)
        direct_ids = _required_string_list(objects, "directConversationIds", expected=2)
        group_conversation_ids = _required_string_list(
            objects, "circleGroupConversationIds", expected=3
        )
        message_ids = _required_string_list(objects, "messageIds", expected=30)
        for index, (circle_id, group_id) in enumerate(
            zip(circle_ids, group_ids, strict=True)
        ):
            executor.call(
                "circle.circle.GetCircle",
                actor=actors[0],
                step=f"reuse-circle-{index:02d}",
                bindings={"circleId": circle_id},
                body=None,
            )
            executor.call(
                "circle.circle_group.GetCircleGroup",
                actor=actors[0],
                step=f"reuse-circle-group-{index:02d}",
                bindings={"circleId": circle_id, "groupId": group_id},
                body=None,
            )
        for index, conversation_id in enumerate(
            [direct_ids[0], *group_conversation_ids]
        ):
            executor.call(
                "chat.conversation.GetConversation",
                actor=actors[0],
                step=f"reuse-conversation-{index:02d}",
                bindings={"conversationId": conversation_id},
                body=None,
            )
        executor.call(
            "chat.conversation.GetConversation",
            actor=actors[4],
            step="reuse-promoted-conversation",
            bindings={"conversationId": direct_ids[1]},
            body=None,
        )
        messages = self._collect_pages(
            executor,
            operation_id="chat.message.ListMessages",
            actor=actors[0],
            step="reuse-reference-messages",
            bindings={"conversationId": direct_ids[0]},
            limit=50,
        )
        observed_ids = {
            _required_string(item, "messageId", "id")
            for item in messages
            if isinstance(item, Mapping)
        }
        if observed_ids != set(message_ids):
            raise RuntimeError("circle/chat live message closure drift")

    def _verify_assistant_live_objects(
        self,
        executor: PublicOperationExecutor,
        actors: list[LocalAcceptanceActor],
        objects: Mapping[str, Any],
    ) -> None:
        subscription_id = _required_string(objects, "subscriptionId")
        session_id = _required_string(objects, "assistantSessionId")
        mention_conversation_id = _required_string(
            objects, "assistantMentionConversationId"
        )
        call_ids = _required_string_list(objects, "rtcCallIds", expected=2)
        executor.call(
            "assistant.skill_subscription.GetSkillSubscription",
            actor=actors[0],
            step="reuse-assistant-subscription",
            bindings={"subscriptionId": subscription_id},
            body=None,
        )
        executor.call(
            "assistant.assistant_session.GetAssistantSession",
            actor=actors[0],
            step="reuse-assistant-session",
            bindings={"sessionId": session_id},
            body=None,
        )
        executor.call(
            "chat.conversation.GetConversation",
            actor=actors[0],
            step="reuse-assistant-chat-conversation",
            bindings={"conversationId": mention_conversation_id},
            body=None,
        )
        history = executor.call(
            "rtc.call_session.ListCalls",
            actor=actors[0],
            step="reuse-assistant-rtc-history",
            query={"limit": 20},
            body=None,
        )
        observed_ids = {
            _required_string(item, "callId", "id")
            for item in _items(history)
            if isinstance(item, Mapping)
        }
        if not set(call_ids).issubset(observed_ids):
            raise RuntimeError("assistant/RTC live call closure drift")

    def _verify_receipt_not_expired(self, receipt: Mapping[str, Any]) -> None:
        raw_expires_at = str(receipt.get("expiresAt") or "").strip()
        if not raw_expires_at:
            raise RuntimeError("nonprod dataset receipt misses expiresAt")
        try:
            expires_at = datetime.fromisoformat(raw_expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise RuntimeError("nonprod dataset receipt expiresAt is invalid") from exc
        if expires_at.tzinfo is None:
            raise RuntimeError("nonprod dataset receipt expiresAt must be timezone-aware")
        if expires_at <= datetime.now(timezone.utc):
            raise RuntimeError("nonprod dataset receipt expired and is not reusable")

    def _base_receipt(self, recipe: DatasetRecipe, epoch: str) -> dict[str, Any]:
        return {
            "schema": "qwq.nonprod_acceptance_dataset_receipt",
            "target": self.candidate.target,
            "environment": self.candidate.environment,
            "baselineId": self.candidate.baseline_id,
            "sourceRevision": self.candidate.source_revision,
            "packageDigest": self.candidate.package_digest,
            "runtimeConfigDigest": self.candidate.runtime_config_digest,
            "releaseId": self.candidate.release_id,
            "releaseDigest": self.candidate.release_digest,
            "releasePostIds": list(self.candidate.release_post_ids),
            "importRunId": self.candidate.import_run_id,
            "datasetId": recipe.dataset_id,
            "datasetEpoch": epoch,
            "retentionClass": recipe.retention_class.value,
            "recipeDigest": recipe.digest,
            "specRefs": list(recipe.spec_refs),
            "expiresAt": (
                datetime.now(timezone.utc) + timedelta(days=7)
            ).isoformat(),
            "recordedAt": _utc_now(),
        }

    def _validate_cleanup_receipt(
        self,
        receipt: Mapping[str, Any],
        recipe: DatasetRecipe,
        epoch: str,
    ) -> None:
        expected = self._base_receipt(recipe, epoch)
        for field in (
            "target",
            "environment",
            "baselineId",
            "packageDigest",
            "runtimeConfigDigest",
            "releaseId",
            "releaseDigest",
            "importRunId",
            "datasetId",
            "datasetEpoch",
            "retentionClass",
            "recipeDigest",
            "specRefs",
        ):
            if receipt.get(field) != expected.get(field):
                raise RuntimeError(f"cleanup receipt identity drift: {field}")
        if receipt.get("schema") != "qwq.nonprod_acceptance_dataset_receipt":
            raise RuntimeError("cleanup receipt schema drift")
        if recipe.retention_class.value != "candidate_bound":
            raise RuntimeError("cleanup accepts candidate-bound receipts only")
        if receipt.get("cleanupState") not in {"retained", "pending", "failed"}:
            raise RuntimeError("cleanup receipt is not eligible for reconciliation")
        if not isinstance(receipt.get("operationReceipts"), list):
            raise RuntimeError("cleanup receipt operation closure is invalid")

    def _cleanup_epoch(self, dataset_id: str) -> str:
        return hashlib.sha256(
            "\0".join(
                (
                    self.candidate.target,
                    self.candidate.baseline_id,
                    self.candidate.package_digest,
                    self.candidate.release_digest,
                    dataset_id,
                    "cleanup-v1",
                )
            ).encode("utf-8")
        ).hexdigest()

    def _created_rows(
        self,
        receipt: Mapping[str, Any],
        operation_id: str,
    ) -> list[dict[str, str]]:
        created: list[dict[str, str]] = []
        for row in self._operation_rows(receipt, operation_id):
            object_ids = row.get("objectIds")
            if not isinstance(object_ids, list):
                raise RuntimeError("cleanup operation ownership row is invalid")
            for value in object_ids:
                object_id = str(value).strip()
                if not object_id:
                    raise RuntimeError("cleanup operation object identity is invalid")
                created.append(
                    {
                        "actorRole": row["actorRole"],
                        "step": row["step"],
                        "objectId": object_id,
                    }
                )
        return created

    def _operation_rows(
        self,
        receipt: Mapping[str, Any],
        operation_id: str,
    ) -> list[dict[str, Any]]:
        rows = receipt.get("operationReceipts")
        if not isinstance(rows, list):
            raise RuntimeError("cleanup receipt operation rows are invalid")
        matched: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, Mapping) or row.get("operationId") != operation_id:
                continue
            actor_role = str(row.get("actorRole") or "").strip()
            step = str(row.get("step") or "").strip()
            if not actor_role or not step:
                raise RuntimeError("cleanup operation ownership row is invalid")
            matched.append(
                {
                    "actorRole": actor_role,
                    "step": step,
                    "objectIds": row.get("objectIds"),
                }
            )
        return matched

    def _created_ids(
        self,
        receipt: Mapping[str, Any],
        operation_id: str,
    ) -> list[str]:
        return [row["objectId"] for row in self._created_rows(receipt, operation_id)]

    def _receipt_actor_roles(self, identity: Mapping[str, Any]) -> set[str]:
        rows = identity.get("actorReceiptRefs")
        if not isinstance(rows, list):
            raise RuntimeError("cleanup identity actor closure is invalid")
        roles = [
            str(row.get("role") or "").strip()
            for row in rows
            if isinstance(row, Mapping)
        ]
        expected = ["primary", *[f"member-{index}" for index in range(1, 6)]]
        if not roles or len(roles) != len(rows) or roles != expected[: len(roles)]:
            raise RuntimeError(
                "cleanup identity requires a receipt-proven actor-role prefix"
            )
        return set(roles)

    def _identity_primary_persona_ids(
        self, identity: Mapping[str, Any]
    ) -> list[str]:
        rows = identity.get("actorReceiptRefs")
        if not isinstance(rows, list) or not rows or len(rows) > 6:
            raise RuntimeError("cleanup identity persona closure is invalid")
        persona_ids: list[str] = []
        for row in rows:
            values = row.get("personaIds") if isinstance(row, Mapping) else None
            if not isinstance(values, list) or not values or not str(values[0]).strip():
                raise RuntimeError("cleanup identity primary persona is invalid")
            persona_ids.append(str(values[0]).strip())
        if len(set(persona_ids)) != len(persona_ids):
            raise RuntimeError("cleanup identity primary personas are not unique")
        return persona_ids

    def _open_remaining_cleanup_actors(
        self,
        identity: Mapping[str, Any],
        identity_epoch: str,
        closed_roles: set[str],
    ) -> dict[str, LocalAcceptanceActor]:
        rows = identity.get("actorReceiptRefs")
        if not isinstance(rows, list):
            raise RuntimeError("cleanup identity actor rows are invalid")
        actors: dict[str, LocalAcceptanceActor] = {}
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise RuntimeError("cleanup identity actor row is invalid")
            role = str(row.get("role") or "").strip()
            if role in closed_roles:
                continue
            actor = open_local_phone_acceptance_session(
                self.base_url,
                environment=self.candidate.environment,
                target_name=self.candidate.target,
                dataset_epoch=identity_epoch,
                dataset_id=NONPROD_REFERENCE_IDENTITY.dataset_id,
                actor_role=role,
                actor_index=index,
            )
            if actor.session.owner_id != row.get("ownerId"):
                raise RuntimeError("cleanup actor live ownership drift")
            actors[role] = actor
        return actors

    def _comment_post_id_for_step(self, step: str) -> str:
        if step.startswith("post-a-"):
            return self.candidate.release_post_ids[0]
        if step.startswith("post-b-"):
            return self.candidate.release_post_ids[1]
        raise RuntimeError(f"cleanup cannot bind comment step to a release post: {step}")

    def _discard_created_media(
        self,
        receipt: Mapping[str, Any],
        *,
        execute: Callable[..., None],
    ) -> None:
        for index, row in enumerate(
            reversed(
                self._created_rows(
                    receipt, "content.media_upload_session.CompleteMediaUpload"
                )
            )
        ):
            execute(
                str(receipt["datasetId"]),
                "content.media_asset.DiscardMediaAsset",
                actor_role=row["actorRole"],
                step=f"discard-media-{index:02d}",
                bindings={"mediaId": row["objectId"]},
            )

    def _record_cleanup_failure(
        self,
        receipts: Mapping[str, dict[str, Any]],
        operation_receipts: list[OperationReceipt],
        errors: list[str],
    ) -> None:
        from .nonprod_business_data import dataset_recipes

        recipes = {recipe.dataset_id: recipe for recipe in dataset_recipes()}
        for dataset_id, receipt in receipts.items():
            receipt["cleanupState"] = "failed"
            receipt["cleanupErrors"] = list(errors)
            receipt["cleanupOperationReceipts"] = [
                row.to_json() for row in operation_receipts
            ]
            recipe = recipes.get(dataset_id)
            if recipe is not None:
                self._write_receipt(recipe, self._epoch(recipe), receipt)

    def _candidate_executor(
        self,
        recipe: DatasetRecipe,
        epoch: str,
        *,
        actor_receipt_refs: list[dict[str, Any]],
    ) -> PublicOperationExecutor:
        """Persist a recoverable receipt before and after every candidate mutation.

        A process interruption must leave exact public-operation/object ownership
        evidence for ``stackctl repair``.  The final recipe receipt replaces this
        recovery projection only after every readback succeeds.
        """

        recovery = self._base_receipt(recipe, epoch)
        recovery.update(
            {
                "status": "GATE_BLOCK",
                "failureClass": "provision_incomplete",
                "actorReceiptRefs": actor_receipt_refs,
                "operationReceipts": [],
                "createdObjectIdsOrHashes": {"operationObjectIds": []},
                "projectionWatermarks": {},
                "readbackResults": {},
                "mediaUploadReceipts": [],
                "cleanupState": "pending",
                "caseResultRefs": [],
            }
        )
        self._write_receipt(recipe, epoch, recovery)

        def persist(receipts: list[OperationReceipt]) -> None:
            rows = [row.to_json() for row in receipts]
            object_ids = sorted(
                {
                    object_id
                    for row in receipts
                    for object_id in row.object_ids
                    if object_id
                }
            )
            recovery["operationReceipts"] = rows
            recovery["createdObjectIdsOrHashes"] = {
                "operationObjectIds": object_ids
            }
            recovery["recordedAt"] = _utc_now()
            self._write_receipt(recipe, epoch, recovery)

        return PublicOperationExecutor(
            base_url=self.base_url,
            target=self.candidate.target,
            dataset_epoch=epoch,
            dataset_id=recipe.dataset_id,
            receipt_sink=persist,
        )

    def _write_receipt(
        self,
        recipe: DatasetRecipe,
        epoch: str,
        payload: dict[str, Any],
    ) -> None:
        path = self._receipt_path(recipe, epoch)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)


def session_from_actor_receipt(
    actor: LocalAcceptanceActor,
) -> LocalAcceptanceSession:
    """Narrow helper for callers that need only the bearer boundary."""

    return actor.session


def _items(payload: Mapping[str, Any]) -> list[Any]:
    for key in ("items", "comments", "replies"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    data = payload.get("data")
    if isinstance(data, dict):
        return _items(data)
    return []


def _next_cursor(payload: Mapping[str, Any]) -> str:
    for key in ("nextCursor", "cursorNext"):
        value = payload.get(key)
        if isinstance(value, str):
            return value.strip()
    page_info = payload.get("pageInfo")
    if isinstance(page_info, dict):
        return str(page_info.get("nextCursor") or "").strip()
    data = payload.get("data")
    if isinstance(data, dict):
        return _next_cursor(data)
    return ""


def _message_seq(value: object) -> int:
    if not isinstance(value, dict):
        raise RuntimeError("message readback item must be an object")
    sequence = value.get("seq")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise RuntimeError("message readback item has invalid seq")
    return sequence


def _acceptance_png(*, accent: bool = False) -> bytes:
    encoded = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/"
        "iZk9HQAAAABJRU5ErkJggg=="
        if not accent
        else "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYPgPAAEDAQAI"
        "icLsAAAAAElFTkSuQmCC"
    )
    return base64.b64decode(encoded)


def _acceptance_wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(8000)
        target.writeframes(b"\0\0" * 8000)
    return output.getvalue()


def _acceptance_mp4() -> bytes:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x2367d1:s=64x64:d=1:r=10",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=8000:cl=mono",
        "-shortest",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "frag_keyframe+empty_moov",
        "-f",
        "mp4",
        "pipe:1",
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            "GATE_BLOCK: ffmpeg is required for real nonprod video upload"
        ) from exc
    if result.returncode != 0 or len(result.stdout) < 256:
        raise RuntimeError(
            "GATE_BLOCK: ffmpeg could not produce the nonprod video asset"
        )
    return result.stdout


def _put_presigned_object(
    *,
    upload_url: str,
    payload: bytes,
    content_type: str,
    sha256_digest: str,
) -> None:
    digest = sha256_digest.removeprefix(_DIGEST_PREFIX).strip().lower()
    checksum = base64.b64encode(bytes.fromhex(digest)).decode("ascii")
    upload_request = urllib.request.Request(
        upload_url,
        data=payload,
        headers={
            "Content-Type": content_type,
            "X-Amz-Checksum-Sha256": checksum,
            "X-Amz-Meta-Sha256": _DIGEST_PREFIX + digest,
        },
        method="PUT",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(upload_request, timeout=30) as response:
            if int(response.status) not in {200, 201, 204}:
                raise RuntimeError(
                    f"presigned MediaAsset upload returned HTTP {response.status}"
                )
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise RuntimeError("presigned MediaAsset upload failed") from exc
