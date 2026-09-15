"""本owner Mongo fence凭据；受信Content HTTP只读，无候选写入。"""
import json
import urllib.request
from pymongo.errors import DuplicateKeyError
from ..application.release_candidate import ReleaseCandidateError


def content_service_authorization():
    import os, time, uuid, base64, hmac, hashlib
    required = {key: os.environ.get(key, "").strip() for key in ("AUTH_JWT_SECRET", "AUTH_JWT_ISSUER", "AUTH_JWT_AUDIENCE", "AUTH_JWT_TOKEN_VERSION")}
    if any(not value for value in required.values()) or len(required["AUTH_JWT_SECRET"].encode()) < 32 or int(required["AUTH_JWT_TOKEN_VERSION"]) <= 0:
        raise ReleaseCandidateError("managed service authorization config missing")
    def authorize():
        now = int(time.time())
        def segment(value): return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":"), sort_keys=True).encode()).rstrip(b"=").decode()
        head = segment({"alg": "HS256", "typ": "JWT"})
        body = segment(dict(iss=required["AUTH_JWT_ISSUER"], aud=required["AUTH_JWT_AUDIENCE"], sub="service:recommendation-service", tkn="access", ver=int(required["AUTH_JWT_TOKEN_VERSION"]), scope="content.release.fence.read", roles=["service"], jti=str(uuid.uuid4()), iat=now, nbf=now, exp=now + 60))
        sig = base64.urlsafe_b64encode(hmac.new(required["AUTH_JWT_SECRET"].encode(), (head + "." + body).encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
        return "Bearer " + head + "." + body + "." + sig
    return authorize


class CandidateFenceReceipts:
    def __init__(self, database):
        self.collection = database["recommendation_candidate_content_fence_receipts"]
        self.collection.create_index([("eventDigest", 1)], unique=True, name="uq_rec_candidate_fence_event")
        self.collection.create_index([("scopeDigest", 1), ("revision", 1)], unique=True, name="uq_rec_candidate_fence_revision")

    def find(self, key):
        return self.collection.find_one({"eventDigest": key})

    def save(self, receipt):
        from datetime import datetime, timezone
        try:
            self.collection.insert_one({**receipt, "consumedAt": datetime.now(timezone.utc)})
        except DuplicateKeyError:
            old = self.find(receipt["eventDigest"])
            if old is None or old["payloadDigest"] != receipt["payloadDigest"]:
                raise ReleaseCandidateError("Content fence revision conflict")


class ContentReceiptClient:
    def __init__(self, base_url, authorization, fence_model):
        from urllib.parse import urlsplit
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.query or parsed.fragment or authorization is None:
            raise ReleaseCandidateError("managed Content receipt binding required")
        self.base = base_url.rstrip("/")
        self.authorization = authorization
        self.fence_model = fence_model

    def _call(self, path, payload=None):
        data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        request = urllib.request.Request(self.base + path, data=data, headers={"Authorization": self.authorization(), "Content-Type": "application/json"})
        # 不携带redirect到另一信任域；urllib默认redirect必须关闭。
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        with urllib.request.build_opener(NoRedirect).open(request, timeout=0.5) as response:
            if response.status != 200:
                raise ReleaseCandidateError("Content receipt unavailable")
            return json.loads(response.read(65537))

    def read_active(self, environment, owner):
        from urllib.parse import urlencode
        raw = self._call("/internal/content/active-release-fence?" + urlencode({"environment": environment, "sourceOwner": owner}))
        required = {"found", "environment", "sourceOwner", "releaseId", "manifestDigest", "revision", "projectionVersion", "activatedAt"}
        if set(raw) != required:
            raise ReleaseCandidateError("active fence presence mismatch")
        return self.fence_model.model_validate(raw)

    def read_commit(self, after, before):
        release = {key: after[key] for key in ("environment", "sourceOwner", "releaseId", "manifestDigest")}
        raw = self._call("/internal/content/release-commit-receipts:query", {"release": release, "expected": before})
        if set(raw) != {"eventId", "transition", "payloadDigest"}:
            raise ReleaseCandidateError("commit receipt shape mismatch")
        return raw
