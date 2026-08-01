from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from ..domain.model import ActivateRelease, CommandResult, StageRelease


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

            now = datetime.now(timezone.utc)
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
                    payload={
                        "releaseId": command.release_id,
                        "scenario": command.scenario,
                        "modelDigest": command.model_digest,
                        "featureContractDigest": command.feature_contract_digest,
                        "artifactUri": command.artifact_uri,
                        "verificationDigest": command.verification_digest,
                    },
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

            now = datetime.now(timezone.utc)
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
                    payload={
                        "releaseId": current_id,
                        "scenario": command.scenario,
                        "activatedReleaseId": command.release_id,
                    },
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
                payload={
                    "releaseId": command.release_id,
                    "scenario": command.scenario,
                    "previousActiveReleaseId": current_id,
                    "modelDigest": target["modelDigest"],
                    "featureContractDigest": target["featureContractDigest"],
                    "artifactUri": target["artifactUri"],
                    "verificationDigest": target["verificationDigest"],
                },
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
