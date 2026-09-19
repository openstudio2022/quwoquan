"""受众约束投影写入（``MongoCandidateIndexStore`` mixin）。

拆分自原 ``mongo_store.py``（行数治理）：账号限制事件与人物关系
（关注/拉黑）事件投影，含各自收件箱幂等与版本冲突裁决。
"""
from __future__ import annotations

from datetime import datetime, timezone


class MongoCandidateAudienceWriteOps:
    """受众约束写操作；集合属性由组合根 ``__init__`` 装配。"""

    def apply_account_restriction_event(
        self,
        *,
        event_id: str,
        event_digest: str,
        account_id: str,
        account_version: int,
        subject_ids: tuple[str, ...],
        restricted: bool,
        terminal: bool = False,
    ) -> int:
        normalized_event_id = event_id.strip()
        normalized_digest = event_digest.strip()
        normalized_account_id = account_id.strip()
        normalized_subjects = tuple(
            dict.fromkeys(value.strip() for value in subject_ids if value.strip())
        )
        if (
            not normalized_event_id
            or len(normalized_digest) != 64
            or any(value not in "0123456789abcdef" for value in normalized_digest)
            or not normalized_account_id
            or account_version <= 0
            or normalized_account_id not in normalized_subjects
        ):
            raise ValueError("candidate account restriction event is incomplete")
        with self._database.client.start_session() as session:
            with session.start_transaction():
                receipt = self._account_restriction_inbox.find_one(
                    {"_id": normalized_event_id},
                    session=session,
                )
                if receipt is not None:
                    if receipt.get("eventDigest") != normalized_digest:
                        raise RuntimeError(
                            "candidate account restriction event identity conflict"
                        )
                    return int(receipt.get("affected") or 0)

                affected = 0
                stale = terminal
                current = self._account_restrictions.find_one(
                    {"_id": normalized_account_id},
                    session=session,
                )
                if not terminal and current is not None:
                    current_version = int(current.get("accountVersion") or 0)
                    if current_version > account_version:
                        stale = True
                    elif current_version == account_version:
                        if current.get("eventDigest") != normalized_digest:
                            raise RuntimeError(
                                "candidate account restriction version conflict"
                            )
                        stale = True

                if not stale:
                    result = self._candidates.update_many(
                        {"authorId": {"$in": list(normalized_subjects)}},
                        {
                            "$set": {
                                "accountRestricted": restricted,
                                "accountRestrictionVersion": account_version,
                                "accountRestrictionUpdatedAt": datetime.now(
                                    timezone.utc
                                ),
                            }
                        },
                        session=session,
                    )
                    affected = int(result.modified_count)
                    self._account_restrictions.replace_one(
                        {"_id": normalized_account_id},
                        {
                            "_id": normalized_account_id,
                            "subjectIds": list(normalized_subjects),
                            "restricted": restricted,
                            "accountVersion": account_version,
                            "eventDigest": normalized_digest,
                            "updatedAt": datetime.now(timezone.utc),
                        },
                        upsert=True,
                        session=session,
                    )

                self._account_restriction_inbox.insert_one(
                    {
                        "_id": normalized_event_id,
                        "eventDigest": normalized_digest,
                        "accountVersion": account_version,
                        "restricted": restricted,
                        "terminal": terminal,
                        "stale": stale,
                        "affected": affected,
                        "appliedAt": datetime.now(timezone.utc),
                    },
                    session=session,
                )
                return affected

    @staticmethod
    def _relationship_identity(source_persona_id: str, target_persona_id: str) -> str:
        return f"{source_persona_id.strip()}\x1f{target_persona_id.strip()}"

    def apply_persona_relationship_event(
        self,
        *,
        event_id: str,
        event_digest: str,
        event_name: str,
        source_persona_id: str,
        target_persona_id: str,
        following: bool,
        version: int,
        occurred_at: datetime,
        partition_id: int,
        partition_sequence: int,
    ) -> bool:
        normalized_event_id = event_id.strip()
        normalized_digest = event_digest.strip()
        normalized_name = event_name.strip()
        source_id = source_persona_id.strip()
        target_id = target_persona_id.strip()
        if (
            not normalized_event_id
            or len(normalized_digest) != 64
            or any(value not in "0123456789abcdef" for value in normalized_digest)
            or normalized_name
            not in {"PersonaFollowStateChanged", "PersonaBlocked", "PersonaUnblocked"}
            or not source_id
            or not target_id
            or source_id == target_id
            or version <= 0
            or occurred_at.tzinfo is None
            or partition_id < 0 or partition_sequence <= 0
        ):
            raise ValueError("candidate persona relationship event is incomplete")

        directions = ((source_id, target_id),)
        if normalized_name in {"PersonaBlocked", "PersonaUnblocked"}:
            directions = ((source_id, target_id), (target_id, source_id))

        with self._database.client.start_session() as session:
            with session.start_transaction():
                checkpoint = self._persona_relationship_checkpoints.find_one(
                    {"partitionId": partition_id}, session=session
                ) or {}
                current_sequence = int(checkpoint.get("sequence") or 0)
                receipt = self._persona_relationship_inbox.find_one(
                    {"_id": normalized_event_id}, session=session
                )
                if receipt is not None:
                    if (
                        receipt.get("eventDigest") != normalized_digest
                        or int(receipt.get("partitionId") or -1) != partition_id
                        or int(receipt.get("partitionSequence") or 0)
                        != partition_sequence
                    ):
                        raise RuntimeError(
                            "candidate persona relationship event identity conflict"
                        )
                    if current_sequence < partition_sequence:
                        raise RuntimeError(
                            "candidate relationship receipt is ahead of checkpoint"
                        )
                    return bool(receipt.get("changed"))
                if partition_sequence != current_sequence + 1:
                    raise RuntimeError(
                        "candidate relationship partition checkpoint is not contiguous"
                    )

                changed = False
                for direction_source, direction_target in directions:
                    identity = self._relationship_identity(
                        direction_source,
                        direction_target,
                    )
                    current = self._persona_relationships.find_one(
                        {"_id": identity},
                        session=session,
                    ) or {}
                    current_version = int(current.get("version") or 0)
                    if current_version > version:
                        continue
                    if current_version == version:
                        if current.get("eventDigest") != normalized_digest:
                            raise RuntimeError(
                                "candidate persona relationship version conflict"
                            )
                        continue

                    next_following = bool(current.get("following"))
                    next_blocked = bool(current.get("blocked"))
                    if normalized_name == "PersonaFollowStateChanged":
                        next_following = following
                    elif normalized_name == "PersonaBlocked":
                        next_following = False
                        next_blocked = True
                    else:
                        # Unblocking never restores the follow state that the
                        # block command cleared.
                        next_following = False
                        next_blocked = False
                    self._persona_relationships.replace_one(
                        {"_id": identity},
                        {
                            "_id": identity,
                            "sourcePersonaId": direction_source,
                            "targetPersonaId": direction_target,
                            "following": next_following,
                            "blocked": next_blocked,
                            "version": version,
                            "eventDigest": normalized_digest,
                            "updatedAt": occurred_at.astimezone(timezone.utc),
                        },
                        upsert=True,
                        session=session,
                    )
                    changed = True

                self._persona_relationship_inbox.insert_one(
                    {
                        "_id": normalized_event_id,
                        "eventDigest": normalized_digest,
                        "eventName": normalized_name,
                        "version": version,
                        "partitionId": partition_id,
                        "partitionSequence": partition_sequence,
                        "changed": changed,
                        "appliedAt": datetime.now(timezone.utc),
                    },
                    session=session,
                )
                self._persona_relationship_checkpoints.update_one(
                    {"partitionId": partition_id},
                    {"$set": {"sequence": partition_sequence, "updatedAt": datetime.now(timezone.utc)}},
                    upsert=True,
                    session=session,
                )
                return changed

    def read_relationship_causal_watermark(self, subject_id: str) -> dict[str, int]:
        subject = subject_id.strip()
        if not subject:
            raise ValueError("subjectId is required")
        return {str(row["partitionId"]): int(row.get("sequence") or 0) for row in self._persona_relationship_checkpoints.find({}, {"partitionId": 1, "sequence": 1})}

    def apply_content_reaction_event(
        self, *, event_id: str, event_digest: str, reaction_id: str,
        target_kind: str, target_id: str, actor_dimension: str, actor_id: str,
        reaction: str, version: int, partition_id: int,
        partition_sequence: int, occurred_at: datetime,
    ) -> bool:
        if (
            not event_id.strip() or len(event_digest) != 64
            or target_kind not in {"post", "comment"}
            or reaction not in {"none", "like", "dislike"}
            or version <= 0 or partition_id < 0 or partition_sequence <= 0
            or occurred_at.tzinfo is None
        ):
            raise ValueError("candidate content reaction event is incomplete")
        with self._database.client.start_session() as session:
            with session.start_transaction():
                checkpoint = self._content_reaction_checkpoints.find_one(
                    {"partitionId": partition_id}, session=session
                ) or {}
                current_sequence = int(checkpoint.get("sequence") or 0)
                receipt = self._content_reaction_inbox.find_one(
                    {"_id": event_id}, session=session
                )
                if receipt is not None:
                    if (
                        receipt.get("eventDigest") != event_digest
                        or int(receipt.get("partitionId") or -1) != partition_id
                        or int(receipt.get("partitionSequence") or 0)
                        != partition_sequence
                    ):
                        raise RuntimeError("candidate reaction event identity conflict")
                    if current_sequence < partition_sequence:
                        raise RuntimeError("candidate reaction receipt is ahead of checkpoint")
                    return bool(receipt.get("changed"))
                if partition_sequence != current_sequence + 1:
                    raise RuntimeError(
                        "candidate reaction partition checkpoint is not contiguous"
                    )
                current = self._content_reaction_members.find_one(
                    {"_id": reaction_id}, session=session
                ) or {}
                current_version = int(current.get("version") or 0)
                if current and any((
                    current.get("targetKind") != target_kind,
                    current.get("targetId") != target_id,
                    current.get("actorDimension") != actor_dimension,
                    current.get("actorId") != actor_id,
                )):
                    raise RuntimeError("candidate reaction identity changed across versions")
                changed = False
                if current_version < version:
                    old_like = int(current.get("reaction") == "like")
                    new_like = int(reaction == "like")
                    delta = new_like - old_like
                    self._content_reaction_members.replace_one(
                        {"_id": reaction_id},
                        {"_id": reaction_id, "targetKind": target_kind,
                         "targetId": target_id, "actorDimension": actor_dimension,
                         "actorId": actor_id, "reaction": reaction,
                         "version": version, "eventDigest": event_digest,
                         "updatedAt": occurred_at.astimezone(timezone.utc)},
                        upsert=True, session=session,
                    )
                    if delta:
                        stats = self._content_reaction_stats.find_one_and_update(
                            {"_id": target_id},
                            {"$inc": {"likeCount": delta, "statsVersion": 1},
                             "$set": {"updatedAt": occurred_at.astimezone(timezone.utc)},
                             "$setOnInsert": {"generationSequence": 1}},
                            upsert=True, return_document=True, session=session,
                        )
                        like_count = int(stats.get("likeCount") or 0)
                        if like_count < 0:
                            raise RuntimeError("candidate reaction likeCount became negative")
                        self._candidates.update_many(
                            {"contentId": target_id},
                            {"$set": {"likeCount": like_count,
                                      "likeStatsVersion": int(stats.get("statsVersion") or 0),
                                      "likeGenerationSequence": int(stats.get("generationSequence") or 1)}},
                            session=session,
                        )
                    changed = True
                elif current_version == version and current.get("eventDigest") != event_digest:
                    raise RuntimeError("candidate reaction member version conflict")
                self._content_reaction_inbox.insert_one(
                    {"_id": event_id, "eventDigest": event_digest,
                     "partitionId": partition_id,
                     "partitionSequence": partition_sequence,
                     "changed": changed, "version": version,
                     "appliedAt": datetime.now(timezone.utc)},
                    session=session,
                )
                self._content_reaction_checkpoints.update_one(
                    {"partitionId": partition_id},
                    {"$set": {"sequence": partition_sequence,
                              "updatedAt": datetime.now(timezone.utc)}},
                    upsert=True, session=session,
                )
                return changed

    def current_like_actors_for_target(self, target_id: str) -> tuple[str, ...]:
        return tuple(sorted(
            str(row["actorId"])
            for row in self._content_reaction_members.find(
                {"targetId": target_id.strip(), "actorDimension": "persona", "reaction": "like"},
                {"actorId": 1},
            )
        ))

    def current_co_liked_targets(self, actor_id: str) -> tuple[str, ...]:
        return tuple(sorted(str(row["targetId"]) for row in self._content_reaction_members.find({"actorDimension":"persona","actorId":actor_id.strip(),"reaction":"like"},{"targetId":1})))
