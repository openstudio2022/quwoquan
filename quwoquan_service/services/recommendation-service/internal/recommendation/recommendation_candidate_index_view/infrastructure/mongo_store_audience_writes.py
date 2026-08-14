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
        ):
            raise ValueError("candidate persona relationship event is incomplete")

        directions = ((source_id, target_id),)
        if normalized_name in {"PersonaBlocked", "PersonaUnblocked"}:
            directions = ((source_id, target_id), (target_id, source_id))

        with self._database.client.start_session() as session:
            with session.start_transaction():
                receipt = self._persona_relationship_inbox.find_one(
                    {"_id": normalized_event_id},
                    session=session,
                )
                if receipt is not None:
                    if receipt.get("eventDigest") != normalized_digest:
                        raise RuntimeError(
                            "candidate persona relationship event identity conflict"
                        )
                    return bool(receipt.get("changed"))

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
                        "changed": changed,
                        "appliedAt": datetime.now(timezone.utc),
                    },
                    session=session,
                )
                return changed
