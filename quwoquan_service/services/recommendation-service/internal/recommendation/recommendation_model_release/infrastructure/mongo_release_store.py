from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from ..domain.model import ActivateRelease, CommandResult, StageRelease
from ..domain.outbox import (
    OutboxClaimLostError,
    OutboxEvent,
    build_model_release_event_payload,
)


class ModelReleaseConflictError(RuntimeError):
    pass


class MongoRecommendationModelReleaseStore:
    RECEIPT_RETENTION = timedelta(days=30)

    def __init__(self, database: Any) -> None:
        self._database = database
        self._releases = database["rec_model_registry"]
        self._receipts = database["rec_model_release_command_receipts"]
        self._outbox = database["rec_model_release_outbox"]

    def ensure_indexes(self) -> None:
        self._releases.create_index(
            [("scenario", ASCENDING), ("modelDigest", ASCENDING)],
            unique=True,
            name="uq_model_registry_scenario_digest",
        )
        self._releases.create_index(
            [("scenario", ASCENDING)],
            unique=True,
            partialFilterExpression={"status": "active"},
            name="uq_model_registry_active_scenario",
        )
        self._releases.create_index(
            [("scenario", ASCENDING), ("status", ASCENDING), ("updatedAt", DESCENDING)],
            name="idx_model_registry_scenario_status_updated",
        )
        self._receipts.create_index(
            [("expiresAt", ASCENDING)],
            expireAfterSeconds=0,
            name="ttl_model_release_command_receipt",
        )
        self._outbox.create_index(
            [("aggregateId", ASCENDING), ("aggregateVersion", ASCENDING), ("eventType", ASCENDING)],
            unique=True,
            name="uq_model_release_outbox_aggregate_version_event",
        )
        self._outbox.create_index(
            [
                ("publishedAt", ASCENDING),
                ("nextAttemptAt", ASCENDING),
                ("occurredAt", ASCENDING),
                ("_id", ASCENDING),
            ],
            name="idx_model_release_outbox_delivery_head",
        )

    def claim_pending_outbox(
        self,
        owner_id: str,
        now: datetime,
        lease_seconds: float,
    ) -> OutboxEvent | None:
        owner = owner_id.strip()
        if not owner or now.tzinfo is None or lease_seconds <= 0:
            raise ValueError("model release outbox claim is invalid")
        instant = now.astimezone(UTC)
        candidate = self._outbox.find_one(
            {"publishedAt": None},
            {"_id": 1},
            sort=[("occurredAt", ASCENDING), ("_id", ASCENDING)],
        )
        if candidate is None:
            return None
        record = self._outbox.find_one_and_update(
            {
                "_id": candidate["_id"],
                "publishedAt": None,
                "$and": [
                    {
                        "$or": [
                            {"nextAttemptAt": {"$exists": False}},
                            {"nextAttemptAt": {"$lte": instant}},
                        ]
                    },
                    {
                        "$or": [
                            {"leaseOwner": {"$exists": False}},
                            {"leaseExpiresAt": {"$lte": instant}},
                        ]
                    },
                ],
            },
            {
                "$set": {
                    "leaseOwner": owner,
                    "leaseExpiresAt": instant + timedelta(seconds=lease_seconds),
                },
                "$inc": {"attemptCount": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if record is None:
            return None
        payload = record.get("payloadJson")
        if not isinstance(payload, dict):
            payload = {}
        return OutboxEvent(
            event_id=str(record.get("_id") or ""),
            event_type=str(record.get("eventType") or ""),
            aggregate_id=str(record.get("aggregateId") or ""),
            aggregate_version=int(record.get("aggregateVersion") or 0),
            payload=dict(payload),
            occurred_at=record.get("occurredAt"),
            attempt_count=int(record.get("attemptCount") or 0),
        )

    def mark_outbox_published(
        self,
        event_id: str,
        owner_id: str,
        published_at: datetime,
    ) -> None:
        result = self._outbox.update_one(
            {
                "_id": event_id.strip(),
                "leaseOwner": owner_id.strip(),
                "publishedAt": None,
            },
            {
                "$set": {"publishedAt": published_at.astimezone(UTC)},
                "$unset": {
                    "leaseOwner": "",
                    "leaseExpiresAt": "",
                    "nextAttemptAt": "",
                    "lastErrorCode": "",
                },
            },
        )
        if result.matched_count != 1:
            raise OutboxClaimLostError("model release outbox claim was lost")

    def schedule_outbox_retry(
        self,
        event_id: str,
        owner_id: str,
        next_attempt_at: datetime,
        failure_code: str,
    ) -> None:
        normalized_failure = failure_code.strip()
        if not normalized_failure or len(normalized_failure) > 64:
            normalized_failure = "delivery_failed"
        result = self._outbox.update_one(
            {
                "_id": event_id.strip(),
                "leaseOwner": owner_id.strip(),
                "publishedAt": None,
            },
            {
                "$set": {
                    "nextAttemptAt": next_attempt_at.astimezone(UTC),
                    "lastErrorCode": normalized_failure,
                },
                "$unset": {"leaseOwner": "", "leaseExpiresAt": ""},
            },
        )
        if result.matched_count != 1:
            raise OutboxClaimLostError("model release outbox claim was lost")

    @staticmethod
    def _receipt_id(operation: str, idempotency_key: str) -> str:
        return f"{operation}\x1f{idempotency_key}"

    @staticmethod
    def _result_from_receipt(
        receipt: dict[str, Any] | None,
        *,
        command_digest: str,
    ) -> CommandResult | None:
        if receipt is None:
            return None
        if receipt.get("commandDigest") != command_digest:
            raise ModelReleaseConflictError(
                "Idempotency-Key was already used with another command"
            )
        return CommandResult.from_document(receipt["result"], replayed=True)

    def _receipt(
        self,
        *,
        receipt_id: str,
        command_digest: str,
        session: Any = None,
    ) -> CommandResult | None:
        receipt = self._receipts.find_one({"_id": receipt_id}, session=session)
        return self._result_from_receipt(
            receipt,
            command_digest=command_digest,
        )

    def _insert_receipt(
        self,
        *,
        receipt_id: str,
        command_digest: str,
        result: CommandResult,
        now: datetime,
        session: Any,
    ) -> None:
        self._receipts.insert_one(
            {
                "_id": receipt_id,
                "commandDigest": command_digest,
                "releaseId": result.release_id,
                "scenario": result.scenario,
                "aggregateVersion": result.version,
                "result": result.as_document(),
                "createdAt": now,
                "expiresAt": now + self.RECEIPT_RETENTION,
            },
            session=session,
        )

    def _insert_outbox(
        self,
        *,
        event_type: str,
        aggregate_id: str,
        aggregate_version: int,
        payload: dict[str, Any],
        occurred_at: datetime,
        session: Any,
    ) -> None:
        self._outbox.insert_one(
            {
                "_id": f"{aggregate_id}\x1f{aggregate_version}\x1f{event_type}",
                "eventType": event_type,
                "aggregateId": aggregate_id,
                "aggregateVersion": aggregate_version,
                "payloadJson": payload,
                "occurredAt": occurred_at,
            },
            session=session,
        )

    def _run_transaction(
        self,
        callback: Callable[[Any], CommandResult],
        *,
        receipt_id: str,
        command_digest: str,
    ) -> CommandResult:
        try:
            with self._database.client.start_session() as session:
                return session.with_transaction(callback)
        except DuplicateKeyError as error:
            replayed = self._receipt(
                receipt_id=receipt_id,
                command_digest=command_digest,
            )
            if replayed is not None:
                return replayed
            raise ModelReleaseConflictError(
                "model release identity or active scenario already exists"
            ) from error

    @staticmethod
    def _same_immutable_release(
        document: dict[str, Any], command: StageRelease
    ) -> bool:
        return all(
            (
                document.get("scenario") == command.scenario,
                document.get("modelDigest") == command.model_digest,
                document.get("featureContractDigest")
                == command.feature_contract_digest,
                document.get("artifactUri") == command.artifact_uri,
                document.get("verificationDigest") == command.verification_digest,
                document.get("evaluationMetrics") == command.evaluation_metrics,
            )
        )

    def stage(self, command: StageRelease) -> CommandResult:
        receipt_id = self._receipt_id("stage", command.idempotency_key)
        command_digest = command.command_digest()

        def transaction(session: Any) -> CommandResult:
            replayed = self._receipt(
                receipt_id=receipt_id,
                command_digest=command_digest,
                session=session,
            )
            if replayed is not None:
                return replayed

            now = datetime.now(UTC)
            existing = self._releases.find_one(
                {"_id": command.release_id}, session=session
            )
            if existing is not None:
                if not self._same_immutable_release(existing, command):
                    raise ModelReleaseConflictError(
                        "releaseId already identifies another immutable release"
                    )
                version = int(existing["version"])
                status = str(existing["status"])
            else:
                version = 1
                status = "staged"
                self._releases.insert_one(
                    {
                        "_id": command.release_id,
                        "scenario": command.scenario,
                        "modelDigest": command.model_digest,
                        "featureContractDigest": command.feature_contract_digest,
                        "artifactUri": command.artifact_uri,
                        "verificationDigest": command.verification_digest,
                        "evaluationMetrics": command.evaluation_metrics,
                        "status": status,
                        "version": version,
                        "createdAt": now,
                        "activatedAt": None,
                        "retiredAt": None,
                        "updatedAt": now,
                    },
                    session=session,
                )
                self._insert_outbox(
                    event_type="RecommendationModelReleaseStaged",
                    aggregate_id=command.release_id,
                    aggregate_version=version,
                    payload=build_model_release_event_payload(
                        "RecommendationModelReleaseStaged",
                        release_id=command.release_id,
                        scenario=command.scenario,
                        model_digest=command.model_digest,
                        feature_contract_digest=command.feature_contract_digest,
                        occurred_at=now,
                    ),
                    occurred_at=now,
                    session=session,
                )

            active = self._releases.find_one(
                {"scenario": command.scenario, "status": "active"},
                {"_id": 1},
                session=session,
            )
            result = CommandResult(
                release_id=command.release_id,
                scenario=command.scenario,
                status=status,
                version=version,
                active_release_id=str(active["_id"]) if active else None,
            )
            self._insert_receipt(
                receipt_id=receipt_id,
                command_digest=command_digest,
                result=result,
                now=now,
                session=session,
            )
            return result

        return self._run_transaction(
            transaction,
            receipt_id=receipt_id,
            command_digest=command_digest,
        )

    def activate(self, command: ActivateRelease) -> CommandResult:
        receipt_id = self._receipt_id("activate", command.idempotency_key)
        command_digest = command.command_digest()

        def transaction(session: Any) -> CommandResult:
            replayed = self._receipt(
                receipt_id=receipt_id,
                command_digest=command_digest,
                session=session,
            )
            if replayed is not None:
                return replayed

            now = datetime.now(UTC)
            current = self._releases.find_one(
                {"scenario": command.scenario, "status": "active"},
                session=session,
            )
            current_id = str(current["_id"]) if current else None
            if current_id != command.expected_active_release_id:
                raise ModelReleaseConflictError(
                    "expectedActiveReleaseId does not match the active release"
                )

            target = self._releases.find_one(
                {"_id": command.release_id}, session=session
            )
            if target is None or target.get("scenario") != command.scenario:
                raise ModelReleaseConflictError(
                    "target release does not exist in the requested scenario"
                )
            if not all(
                str(target.get(field) or "").strip()
                for field in (
                    "modelDigest",
                    "featureContractDigest",
                    "artifactUri",
                    "verificationDigest",
                )
            ):
                raise ModelReleaseConflictError(
                    "target release is not a staged verified release"
                )

            if current_id == command.release_id:
                result = CommandResult(
                    release_id=command.release_id,
                    scenario=command.scenario,
                    status="active",
                    version=int(target["version"]),
                    active_release_id=command.release_id,
                )
                self._insert_receipt(
                    receipt_id=receipt_id,
                    command_digest=command_digest,
                    result=result,
                    now=now,
                    session=session,
                )
                return result

            if target.get("status") not in {"staged", "retired"}:
                raise ModelReleaseConflictError(
                    "target release is not eligible for activation"
                )

            if current is not None:
                current_version = int(current["version"])
                retired = self._releases.update_one(
                    {
                        "_id": current["_id"],
                        "status": "active",
                        "version": current_version,
                    },
                    {
                        "$set": {
                            "status": "retired",
                            "retiredAt": now,
                            "updatedAt": now,
                        },
                        "$inc": {"version": 1},
                    },
                    session=session,
                )
                if retired.modified_count != 1:
                    raise ModelReleaseConflictError(
                        "active release changed during compare-and-swap"
                    )
                self._insert_outbox(
                    event_type="RecommendationModelReleaseRetired",
                    aggregate_id=current_id,
                    aggregate_version=current_version + 1,
                    payload=build_model_release_event_payload(
                        "RecommendationModelReleaseRetired",
                        release_id=current_id,
                        scenario=command.scenario,
                        occurred_at=now,
                    ),
                    occurred_at=now,
                    session=session,
                )

            target_version = int(target["version"])
            activated = self._releases.update_one(
                {
                    "_id": command.release_id,
                    "scenario": command.scenario,
                    "status": target["status"],
                    "version": target_version,
                },
                {
                    "$set": {
                        "status": "active",
                        "activatedAt": now,
                        "retiredAt": None,
                        "updatedAt": now,
                    },
                    "$inc": {"version": 1},
                },
                session=session,
            )
            if activated.modified_count != 1:
                raise ModelReleaseConflictError(
                    "target release changed during compare-and-swap"
                )
            activated_version = target_version + 1
            self._insert_outbox(
                event_type="RecommendationModelReleaseActivated",
                aggregate_id=command.release_id,
                aggregate_version=activated_version,
                payload=build_model_release_event_payload(
                    "RecommendationModelReleaseActivated",
                    release_id=command.release_id,
                    scenario=command.scenario,
                    model_digest=target["modelDigest"],
                    feature_contract_digest=target["featureContractDigest"],
                    occurred_at=now,
                ),
                occurred_at=now,
                session=session,
            )
            result = CommandResult(
                release_id=command.release_id,
                scenario=command.scenario,
                status="active",
                version=activated_version,
                active_release_id=command.release_id,
            )
            self._insert_receipt(
                receipt_id=receipt_id,
                command_digest=command_digest,
                result=result,
                now=now,
                session=session,
            )
            return result

        return self._run_transaction(
            transaction,
            receipt_id=receipt_id,
            command_digest=command_digest,
        )
