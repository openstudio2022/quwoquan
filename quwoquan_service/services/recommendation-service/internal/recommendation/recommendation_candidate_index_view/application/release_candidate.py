"""候选准备使用生成值，摘要按owner canonical JSON，不创造第二wire。"""
from datetime import datetime, timezone
import hashlib
import json
import math
from pydantic import BaseModel
from generated.recommendation.recommendation_candidate_index_view.events.content_post_PostReleaseCandidatePrepared import PostReleaseCandidatePrepared


class ReleaseCandidateError(ValueError):
    code = "RECOMMENDATION.RELEASE.invalid_candidate"


class ReleaseNotReady(RuntimeError):
    code = "RECOMMENDATION.RELEASE.not_ready"


def canonical(value):
    if isinstance(value, BaseModel):
        return canonical(value.model_dump(mode="python"))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ReleaseCandidateError("timezone required")
        text = value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if "." in text:
            text = text[:-1].rstrip("0").rstrip(".") + "Z"
        return text
    if isinstance(value, dict):
        return {key: canonical(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(child) for child in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ReleaseCandidateError("nonfinite value")
        if value.is_integer():
            return int(value)
    return value


def digest(value, omit=None):
    value = canonical(value)
    if omit:
        value = {k: v for k, v in value.items() if k != omit}
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def valid_digest(value):
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(c in "0123456789abcdef" for c in value[7:])


def validate_binding(binding):
    release = binding.release
    if (binding.slice != "recommendation" or release.environment not in {"alpha", "beta", "gamma", "prod"}
            or release.sourceOwner != "qwq_data" or not release.releaseId.strip()
            or not all(valid_digest(v) for v in (release.manifestDigest, binding.providerBindingGeneration, binding.schemaGeneration))):
        raise ReleaseCandidateError("invalid candidate binding")


def validate_prepared(event: PostReleaseCandidatePrepared):
    if event.occurredAt.tzinfo is None:
        raise ReleaseCandidateError("publication time timezone required")
    validate_binding(event.binding)
    snapshot = event.snapshot
    if canonical(event.binding.release) != canonical(snapshot.release) or event.sourceVersion <= 0:
        raise ReleaseCandidateError("source binding mismatch")
    if len(snapshot.posts) > 1000:
        raise ReleaseCandidateError("candidate exceeds bound")
    ids = [post.identity.objectId for post in snapshot.posts]
    if ids != sorted(set(ids)):
        raise ReleaseCandidateError("candidate identities must be sorted and unique")
    for post in snapshot.posts:
        identity = post.identity
        if (not post.postRef or not post.authorId or not post.authorDisplayName or not post.deepLink
                or post.status != "published" or post.visibility != "public" or post.moderationStatus != "approved"
                or post.contentType not in {"article", "image", "video", "micro"} or post.contentIdentity not in {"work", "moment"}
                or min(post.width, post.height, post.durationMs) < 0):
            raise ReleaseCandidateError("invalid canonical Post source")
        if (identity.objectType != "content.post" or not identity.objectId or identity.sourceVersion <= 0
                or canonical(identity.release) != canonical(snapshot.release) or not valid_digest(identity.sourceDigest)
                or digest(post, "documentDigest") != post.documentDigest):
            raise ReleaseCandidateError("Post candidate digest mismatch")
        if post.primaryHomepage is not None:
            home = post.primaryHomepage
            if canonical(home.identity.release) != canonical(snapshot.release) or digest(home, "documentDigest") != home.documentDigest:
                raise ReleaseCandidateError("Homepage candidate mismatch")
    expected_set = digest([{"objectType": "content.post", "objectId": value} for value in ids])
    if (snapshot.objectSetDigest != expected_set or digest(snapshot, "snapshotDigest") != snapshot.snapshotDigest
            or not valid_digest(snapshot.sourceClosureDigest) or not valid_digest(snapshot.mediaClosureDigest)):
        raise ReleaseCandidateError("source closure mismatch")
    if event.publicationId != digest({"binding": event.binding, "snapshotDigest": snapshot.snapshotDigest}):
        raise ReleaseCandidateError("publication identity mismatch")
