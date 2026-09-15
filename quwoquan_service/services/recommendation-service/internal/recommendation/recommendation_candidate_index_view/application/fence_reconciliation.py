"""Content提交的纯对账流程；依赖显式port，不写候选或选择active。"""
from datetime import datetime, timezone
from .release_candidate import canonical, digest, valid_digest, ReleaseCandidateError


def validate_fence(fence, environment):
    if fence.environment != environment or fence.sourceOwner != "qwq_data":
        raise ReleaseCandidateError("Content fence deployment mismatch")
    if not fence.found:
        if fence.releaseId or fence.manifestDigest or fence.revision != 0 or fence.projectionVersion != 0 or fence.activatedAt is not None:
            raise ReleaseCandidateError("nonempty absent fence")
    elif not fence.releaseId or not valid_digest(fence.manifestDigest) or fence.revision <= 0 or fence.projectionVersion <= 0 or fence.activatedAt is None:
        raise ReleaseCandidateError("incomplete active fence")


class FenceReconciler:
    def __init__(self, *, model, store, content, proof_reader, environment):
        if any(value is None for value in (model, store, content, proof_reader)) or not environment:
            raise ReleaseCandidateError("fence reconciliation dependencies required")
        self.model, self.store, self.content = model, store, content
        self.proof_reader, self.environment = proof_reader, environment

    def apply(self, values):
        import json
        raw = json.loads(values["payload"])
        if not isinstance(raw, dict) or set(raw) != {"before", "after"}:
            raise ReleaseCandidateError("exact fence shape required")
        keys = {"found", "environment", "sourceOwner", "releaseId", "manifestDigest", "revision", "projectionVersion", "activatedAt"}
        for fence in raw.values():
            if not isinstance(fence, dict) or set(fence) != keys:
                raise ReleaseCandidateError("fence presence differs")
            if type(fence["found"]) is not bool or any(type(fence[k]) is not int for k in ("revision", "projectionVersion")):
                raise ReleaseCandidateError("fence scalar types differ")
        event = self.model.model_validate_json(values["payload"])
        before, after = event.before, event.after
        validate_fence(before, self.environment); validate_fence(after, self.environment)
        if not after.found or after.revision != before.revision + 1:
            raise ReleaseCandidateError("fence transition revision differs")
        identity = "content-release-fence:" + digest([after.environment, after.sourceOwner, after.revision])[7:]
        # Content规范序列化固定before/after字段顺序，摘要使用原DTO规范字节而非另造排序规则。
        wire_digest = content_payload_digest(event)
        if (values.get("eventId") != identity or values.get("eventType") != "ContentReleaseFenceChanged"
                or values.get("aggregateType") != "Post" or values.get("aggregateId") != after.environment + "/" + after.sourceOwner
                or values.get("aggregateVersion") != str(after.revision)
                or datetime.fromisoformat(values["occurredAt"].replace("Z", "+00:00")) != after.activatedAt):
            raise ReleaseCandidateError("fence envelope mismatch")
        key = digest(identity)
        old = self.store.find(key)
        if old is not None:
            if old["payloadDigest"] != wire_digest:
                raise ReleaseCandidateError("event digest conflict")
            return
        current = self.content.read_active(after.environment, after.sourceOwner)
        validate_fence(current, self.environment)
        if current.revision < after.revision:
            raise ReleaseCandidateError("future fence")
        receipt = self.content.read_commit(canonical(after), canonical(before))
        if receipt["eventId"] != identity or receipt["payloadDigest"] != wire_digest or receipt["transition"] != canonical(event):
            raise ReleaseCandidateError("exact committed receipt differs")
        outcome, proof_digest = "superseded", wire_digest
        if current.revision == after.revision:
            if canonical(current) != canonical(after):
                raise ReleaseCandidateError("same revision another tuple")
            proof_digest = self.proof_reader(canonical(after))
            if not valid_digest(proof_digest):
                raise ReleaseCandidateError("query proof evidence missing")
            outcome = "reconciled"
        self.store.save(dict(eventDigest=key, scopeDigest=digest([after.environment, after.sourceOwner]), revision=after.revision,
                             payloadDigest=wire_digest, proofEvidenceDigest=proof_digest, outcome=outcome))


def content_payload_digest(event):
    import hashlib
    import json
    # 源Go struct按声明字段顺序输出，nullable显式保留；时间沿现役canonical函数。
    raw = json.dumps(canonical(event), ensure_ascii=False, separators=(",", ":"))
    raw = raw.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()
