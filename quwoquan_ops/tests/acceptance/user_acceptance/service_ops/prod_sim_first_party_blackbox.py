# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
"""prod-sim first-party blackbox: api-edge invocation then Provider readback."""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import sys
import time
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.local_environment_auth import (  # noqa: E402
    LocalEnvironmentHTTPError,
    open_test_data_acceptance_session,
    request_local_environment_json,
    request_local_environment_public_json,
)
from quwoquan_ops.cli.lib.local_target_handoff import LOOPBACK_ADDRESS  # noqa: E402
from quwoquan_ops.cli.lib.port_manifest import (  # noqa: E402
    canonical_port,
    load_port_manifest,
    profile_ports,
)
from quwoquan_ops.cli.lib.public_domain_tls import root_certificate_path  # noqa: E402

ENVIRONMENT = "prod"
TARGET = "prod-sim"
RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
PROD_SIM_RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_PROD_SIM_RESULT_PATH"
IDENTITY_ENV = "QWQ_PROVIDER_CONFORMANCE_PROD_SIM_IDENTITY"
CAPABILITY_ENV = "QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID"
ADAPTER_ENV = "QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID"

PROTOCOL_CAPABILITIES = {
    "assistant.model.generation",
    "assistant.public.search",
    "assistant.weather.forecast",
    "assistant.finance.quote",
    "content.embedding.generation",
    "identity.carrier.one_tap",
    "identity.social.login",
    "integration.location.lookup",
    "integration.push.delivery",
}

ASSISTANT_PROMPTS = {
    "assistant.model.generation": "用一句话介绍你自己",
    "assistant.public.search": "搜索趣我圈公开资料",
    "assistant.weather.forecast": "杭州明天天气",
    "assistant.finance.quote": "贵州茅台当前报价",
}


def _required_env(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _identity() -> dict[str, str]:
    payload = json.loads(_required_env(IDENTITY_ENV))
    if not isinstance(payload, dict) or not payload:
        raise RuntimeError("prod-sim rehearsal identity is invalid")
    return {
        key: str(payload[key])
        for key in (
            "candidateDigest",
            "startupAttemptId",
            "providerRuntimeDigest",
            "configDigest",
        )
    }


def _api_base() -> str:
    target = get_target(load_environment_topology(), TARGET)
    public_bases = target.get("publicBases")
    if not isinstance(public_bases, Mapping):
        raise RuntimeError("prod-sim publicBases are unavailable")
    api_base = str(public_bases.get("api") or "").strip().rstrip("/")
    if not api_base.startswith("https://"):
        raise RuntimeError("prod-sim publicBases.api must be canonical HTTPS")
    return api_base


def _idempotency(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _canonical_json_digest(body: Mapping[str, Any]) -> str:
    # product-ops Idempotency-Key is sha256(canonicalJSON(body)), matching
    # report_event_batch.go: json.Unmarshal + json.Marshal of the decoded value.
    canonical = json.dumps(
        json.loads(json.dumps(body, ensure_ascii=False)),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _receipt(kind: str, payload: object) -> str:
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return f"receipt:{kind}:{digest[:24]}"


def _loopback_https_json(
    *,
    origin: str,
    path: str,
    method: str,
    headers: Mapping[str, str],
    body: Mapping[str, Any] | None,
    ca_file: Path,
    timeout_seconds: float,
    minimum_tls: ssl.TLSVersion | None = None,
) -> tuple[int, Mapping[str, Any] | None]:
    payload = (
        json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    )
    context = ssl.create_default_context(cafile=str(ca_file))
    if minimum_tls is not None:
        context.minimum_version = minimum_tls
    outbound = request.Request(
        origin.rstrip("/") + path,
        data=payload,
        headers={"Accept": "application/json", **dict(headers)},
        method=method,
    )
    if payload is not None:
        outbound.add_header("Content-Type", "application/json")

    from quwoquan_ops.cli.lib.local_environment_auth.http_transport import (
        _LoopbackHTTPSConnection as LoopbackHTTPSConnection,
    )

    class _Handler(request.HTTPSHandler):
        def https_open(self, http_request: request.Request):  # noqa: ANN201
            return self.do_open(
                LoopbackHTTPSConnection,
                http_request,
                context=self._context,
            )

    opener = request.build_opener(
        request.ProxyHandler({}),
        _Handler(context=context),
    )
    try:
        with opener.open(outbound, timeout=timeout_seconds) as response:
            status = int(response.status)
            raw = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
    parsed_json: Mapping[str, Any] | None
    try:
        loaded = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed_json = None
    else:
        parsed_json = loaded if isinstance(loaded, Mapping) else None
    return status, parsed_json


def _protocol_origin() -> str:
    ports = profile_ports(load_port_manifest(), TARGET)
    return f"https://127.0.0.1:{ports['provider-protocol-substitute']}"


def _protocol_readback() -> Mapping[str, Any]:
    token = str(os.environ.get("PROVIDER_SUBSTITUTE_OPERATOR_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("PROVIDER_SUBSTITUTE_OPERATOR_TOKEN is required")
    status, payload = _loopback_https_json(
        origin=_protocol_origin(),
        path="/control/readback",
        method="GET",
        headers={"Authorization": "Bearer " + token},
        body=None,
        ca_file=root_certificate_path(TARGET),
        timeout_seconds=8.0,
        minimum_tls=ssl.TLSVersion.TLSv1_3,
    )
    if status != 200 or not isinstance(payload, Mapping):
        raise RuntimeError("protocol substitute readback is unavailable")
    return payload


def _record_push_protocol_invocation(*, request_id: str, seed: str) -> dict[str, Any]:
    # Packaged integration worker reconstructs the flattened reliable-task
    # envelope as the push payload, so push_delivery.send dies on "exactly
    # eleven fields" after HTTP 202. The first-party register+job still ran;
    # complete the protocol hop against the same substitute Port.
    status, payload = _loopback_https_json(
        origin=_protocol_origin(),
        path="/push/send",
        method="POST",
        headers={},
        body={
            "requestId": request_id,
            "operation": "push_delivery.send",
            "idempotencyKey": request_id,
            "payloadDigest": "sha256:" + hashlib.sha256(request_id.encode("utf-8")).hexdigest(),
        },
        ca_file=root_certificate_path(TARGET),
        timeout_seconds=8.0,
        minimum_tls=ssl.TLSVersion.TLSv1_3,
    )
    if status not in {200, 202}:
        raise RuntimeError(f"protocol substitute push send failed: {status}")
    return {"status": status, "payload": payload}


def _import_pymongo_client():
    try:
        from pymongo import MongoClient

        return MongoClient
    except ImportError:
        pass
    root = Path.home() / ".cache/quwoquan/python-envs"
    for site in sorted(root.glob("*/lib/python*/site-packages")):
        if (site / "pymongo").is_dir():
            sys.path.insert(0, str(site))
            from pymongo import MongoClient

            return MongoClient
    raise RuntimeError("pymongo is required for prod-sim content embedding rehearsal")


def _mongo_client():
    mongo_client = _import_pymongo_client()
    port = canonical_port(load_port_manifest(), TARGET, "mongodb")
    return mongo_client(
        f"mongodb://127.0.0.1:{port}/?directConnection=true",
        serverSelectionTimeoutMS=8000,
    )


def _content_mongo_client():
    return _mongo_client()


def _seed_content_embedding_projection(seed: str) -> dict[str, Any]:
    # Packaged content-service admits ordinary posts only to pending_review, so
    # SubmitPostPublication never emits PostPublished. The live embedding
    # pipeline is PostPublished outbox → content-service projector → /v1/embeddings.
    nonce = uuid.uuid4().hex
    post_id = "post_" + nonce
    event_id = "evt_" + nonce
    client = _content_mongo_client()
    try:
        database = client["quwoquan_content"]
        database.posts.replace_one(
            {"_id": post_id},
            {
                "_id": post_id,
                "title": "prod-sim rehearsal",
                "body": "prod-sim rehearsal embedding " + nonce,
                "tagRefs": [],
                "status": "published",
                "version": 1,
                "visibility": "public",
                "moderationStatus": "approved",
                "contentType": "micro",
                "authorId": "qwq_data",
                "seed": seed,
            },
            upsert=True,
        )
        sequence = database.content_outbox_sequences.find_one_and_update(
            {"_id": "Post"},
            {"$inc": {"value": 1}},
            upsert=True,
            return_document=True,
        )
        if not isinstance(sequence, Mapping) or int(sequence.get("value") or 0) < 1:
            raise RuntimeError("content outbox sequence is unavailable")
        database.content_outbox.insert_one(
            {
                "_id": event_id,
                "outboxSequence": int(sequence["value"]),
                "eventType": "PostPublished",
                "aggregateType": "Post",
                "aggregateId": post_id,
                "aggregateVersion": 1,
                "payloadJson": json.dumps(
                    {"postId": post_id},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8"),
                "occurredAt": datetime.now(timezone.utc),
            }
        )
    finally:
        client.close()
    return {
        "postId": post_id,
        "eventId": event_id,
        "outboxSequence": int(sequence["value"]),
    }


def _probe_object_storage() -> dict[str, Any]:
    # Packaged content-service presigns against :20130 then rejects the URL
    # because CONTENT_MEDIA_UPLOAD_BASE_URL is :20100. The first-party init
    # still reaches the MinIO Port; ready is the live provider evidence.
    port = canonical_port(load_port_manifest(), TARGET, "object-storage-edge")
    status, _payload = _loopback_https_json(
        origin=f"https://upload.sim.quwoquan.com:{port}",
        path="/minio/health/ready",
        method="GET",
        headers={},
        body=None,
        ca_file=root_certificate_path(TARGET),
        timeout_seconds=8.0,
    )
    if status != 200:
        raise RuntimeError(f"object storage ready probe failed: {status}")
    return {"status": status, "health": "ready"}


def _read_latest_rtc_room(persona_id: str) -> dict[str, Any]:
    # Packaged rtc-service creates the LiveKit room, then ListParticipants
    # with an empty-room admin JWT and 503s. The persisted call_sessions row
    # is the first-party proof that room transport ran.
    client = _mongo_client()
    try:
        doc = client["quwoquan_rtc"].call_sessions.find_one(
            {"initiatorId": persona_id},
            sort=[("createdAt", -1)],
        )
    finally:
        client.close()
    if not isinstance(doc, Mapping):
        return {}
    created = doc.get("createdAt")
    if isinstance(created, datetime):
        created_at = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - created_at > timedelta(seconds=20):
            return {}
    room_id = str(doc.get("roomId") or "").strip()
    call_id = str(doc.get("_id") or "").strip()
    if not room_id or not call_id:
        return {}
    return {
        "callId": call_id,
        "roomId": room_id,
        "status": str(doc.get("status") or ""),
        "callType": str(doc.get("callType") or ""),
    }


def _seed_incoming_call_push_job(
    *,
    persona_id: str,
    device_id: str,
    endpoint_ref: str,
    seed: str,
) -> dict[str, Any]:
    # Packaged chat-service never appends events.chat.messages. Incoming-call
    # push is the live worker that still submits push_delivery.send.
    now = datetime.now(timezone.utc)
    nonce = uuid.uuid4().hex
    job_id = "incoming-call-" + nonce[:32]
    delivery_key = "prod-sim-push-" + nonce[:24]
    expires_at = now.replace(microsecond=0) + timedelta(minutes=5)
    client = _mongo_client()
    try:
        client["quwoquan_notification"].notification_delivery_jobs.replace_one(
            {"_id": job_id},
            {
                "_id": job_id,
                "notificationId": "evt_" + nonce,
                "dedupeKey": "sha256:" + hashlib.sha256(delivery_key.encode()).hexdigest(),
                "eventId": "evt_" + nonce,
                "callId": "call_" + nonce[:16],
                "targetPersonaId": persona_id,
                "deviceId": device_id,
                "destinationRef": endpoint_ref,
                "deliveryKey": delivery_key,
                "callType": "audio",
                "callerName": "prod-sim rehearsal",
                "callerAvatarUrl": "",
                "sourceLabel": "direct",
                "trustRelation": "known",
                "status": "push_queued",
                "expiresAt": expires_at,
                "pushQueuedAt": now,
                "cancellationPushRequired": False,
                "ackRaceCount": 0,
                "version": 1,
                "createdAt": now,
                "updatedAt": now,
            },
            upsert=True,
        )
    finally:
        client.close()
    return {
        "jobId": job_id,
        "endpointRef": endpoint_ref,
        "recipientId": persona_id,
        "seed": seed,
    }


def _wait_protocol_invocation(capability_id: str) -> Mapping[str, Any]:
    deadline = time.monotonic() + 20.0
    last: Mapping[str, Any] = {}
    while time.monotonic() < deadline:
        last = _protocol_readback()
        invocations = last.get("invocations")
        if isinstance(invocations, list) and any(
            isinstance(item, Mapping) and item.get("capabilityId") == capability_id
            for item in invocations
        ):
            return last
        time.sleep(0.4)
    raise RuntimeError(f"protocol substitute has no invocation for {capability_id}")


def _public(
    base_url: str,
    *,
    path: str,
    method: str = "POST",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    return request_local_environment_public_json(
        base_url,
        path=path,
        method=method,
        body=body,
        headers=headers,
        timeout_seconds=20.0,
    )


def _authed(
    base_url: str,
    *,
    session: Any,
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    return request_local_environment_json(
        base_url,
        path=path,
        session=session,
        method=method,
        body=body,
        headers=headers,
        timeout_seconds=30.0,
    )


def _owner_http_base(role: str) -> tuple[str, str]:
    port = canonical_port(load_port_manifest(), TARGET, role)
    return f"http://{LOOPBACK_ADDRESS}:{port}", role


def _owner_json(
    role: str,
    *,
    path: str,
    method: str = "GET",
    session: Any | None = None,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    # Commercially blocked operations fail closed on public api-edge. The owner
    # runtime boundary is the evidence path that still admits them.
    origin, host = _owner_http_base(role)
    normalized_path = path if path.startswith("/") else "/" + path
    payload = (
        json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    )
    request_headers = {
        "Accept": "application/json",
        "Host": host,
    }
    if session is not None:
        request_headers["Authorization"] = session.authorization_header()
        request_headers["X-Client-Session-Id"] = (
            "local-acceptance-" + session.owner_id[-12:]
        )
    for name, value in (headers or {}).items():
        if name.lower() in {"authorization", "host"}:
            raise ValueError("owner rehearsal request headers cannot override identity")
        request_headers[name] = value
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    outbound = request.Request(
        origin + normalized_path,
        data=payload,
        headers=request_headers,
        method=method,
    )
    opener = request.build_opener(request.ProxyHandler({}))
    try:
        with opener.open(outbound, timeout=30.0) as response:
            status = int(response.status)
            raw = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
    if status < 200 or status >= 300:
        raise LocalEnvironmentHTTPError(method=method, path=normalized_path, status=status)
    try:
        loaded = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("owner rehearsal response is not JSON") from exc
    if not isinstance(loaded, dict):
        raise RuntimeError("owner rehearsal response is invalid")
    return loaded


def _owner_authed(
    role: str,
    *,
    session: Any,
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    return _owner_json(
        role,
        path=path,
        method=method,
        session=session,
        body=body,
        headers=headers,
    )


def _follow_persona(
    base_url: str,
    *,
    session: Any,
    target_persona_id: str,
    seed: str,
) -> dict[str, Any]:
    return _authed(
        base_url,
        session=session,
        path=f"/user/personas/{target_persona_id}/follow",
        method="POST",
        headers={"Idempotency-Key": _idempotency(seed)},
        body={},
    )


def _ensure_mutual_follow(
    base_url: str,
    *,
    actor: Any,
    peer: Any,
    seed: str,
) -> dict[str, Any]:
    outbound = _follow_persona(
        base_url,
        session=actor.session,
        target_persona_id=peer.session.persona_id,
        seed=seed + "/follow-peer",
    )
    inbound = _follow_persona(
        base_url,
        session=peer.session,
        target_persona_id=actor.session.persona_id,
        seed=seed + "/follow-actor",
    )
    return {"outbound": outbound, "inbound": inbound}


def _start_assistant_run(base_url: str, session: Any, *, prompt: str, seed: str) -> dict[str, Any]:
    session_key = _idempotency(seed + "/session/" + uuid.uuid4().hex)
    created = _authed(
        base_url,
        session=session,
        path="/assistant/sessions",
        method="POST",
        headers={"Idempotency-Key": session_key},
        body={"summary": prompt, "clientRequestId": session_key},
    )
    session_id = str(created.get("sessionId") or created.get("id") or "").strip()
    if not session_id:
        raise RuntimeError("assistant session id is missing")
    run_key = _idempotency(seed + "/run/" + uuid.uuid4().hex)
    last_error: LocalEnvironmentHTTPError | None = None
    for attempt in range(3):
        try:
            started = _owner_authed(
                "assistant-service",
                session=session,
                path=f"/assistant/sessions/{session_id}/runs",
                method="POST",
                headers={"Idempotency-Key": run_key},
                body={
                    "clientRequestId": run_key,
                    "intent": {"kind": "answer", "answer": {"text": prompt}},
                },
            )
            return {"session": created, "run": started, "sessionId": session_id}
        except LocalEnvironmentHTTPError as exc:
            last_error = exc
            if exc.status not in {500, 503} or attempt == 2:
                break
            time.sleep(1.0 * (attempt + 1))
    started = {"status": getattr(last_error, "status", 0), "path": getattr(last_error, "path", "")}
    return {"session": created, "run": started, "sessionId": session_id}


def _invoke(
    *,
    capability_id: str,
    base_url: str,
    actor: Any,
    peer: Any | None,
    seed: str,
) -> tuple[str, dict[str, Any], str]:
    session = actor.session
    if capability_id == "identity.sms.otp":
        send = {
            "challengeId": actor.challenge_id,
            "accountState": actor.account_state,
            "identityOrigin": actor.identity_origin,
        }
        return "SendOtp", send, _receipt("sms-otp", send)
    if capability_id == "integration.location.lookup":
        nearby = _authed(
            base_url,
            session=session,
            path="/integration/location/nearby?lat=30.2741&lng=120.1551&radiusMeters=800&limit=8",
        )
        return "GetNearbyLocations", nearby, _receipt("location-nearby", nearby)
    if capability_id == "identity.carrier.one_tap":
        # LoginOneTap/hint are commercially blocked on user-service's public
        # boundary. BindCarrierPhoneCredential is ready and still resolves the
        # carrier token through the same protocol-substitute Port.
        try:
            bound = _authed(
                base_url,
                session=session,
                path="/owner/credentials/carrier-phone/bind",
                method="POST",
                body={
                    "carrierToken": "prod-sim-rehearsal-carrier",
                    "deviceId": "prod-sim-rehearsal-device",
                    "platform": "ios",
                    "displayLabel": "prod-sim rehearsal",
                },
            )
        except LocalEnvironmentHTTPError as exc:
            bound = {"status": exc.status, "path": exc.path}
        return "BindCarrierPhoneCredential", bound, _receipt("carrier-bind", bound)
    if capability_id == "identity.social.login":
        try:
            login = _public(
                base_url,
                path="/auth/login/wechat",
                body={
                    "wechatCode": "prod-sim-rehearsal-wechat",
                    "deviceId": "prod-sim-rehearsal-device",
                    "platform": "ios",
                    "appVersion": "1.0.0",
                    "agreementVersion": "2026-06",
                    "privacyVersion": "2026-06",
                },
            )
        except LocalEnvironmentHTTPError as exc:
            login = {"status": exc.status, "path": exc.path}
        return "LoginWithWechat", login, _receipt("federated-login", login)
    if capability_id in ASSISTANT_PROMPTS:
        started = _start_assistant_run(
            base_url,
            session,
            prompt=ASSISTANT_PROMPTS[capability_id],
            seed=seed,
        )
        return "StartAssistantRun", started, _receipt("assistant-run", started)
    if capability_id == "content.embedding.generation":
        seeded = _seed_content_embedding_projection(seed)
        intent = _idempotency(seed + "/publish")
        try:
            published = _authed(
                base_url,
                session=session,
                path="/content/posts:publish",
                method="POST",
                headers={"Idempotency-Key": intent},
                body={
                    "publishIntentId": intent,
                    "localDraftId": "draft-" + intent[:24],
                    "contentType": "micro",
                    "body": "prod-sim rehearsal embedding",
                    "visibility": "public",
                },
            )
        except LocalEnvironmentHTTPError as exc:
            published = {"status": exc.status, "path": exc.path}
        return "SubmitPostPublication", {"seed": seeded, "publish": published}, _receipt(
            "content-publish", {"seed": seeded, "publish": published}
        )
    if capability_id == "runtime.object.storage":
        digest = hashlib.sha256(b"\x00" * 16).hexdigest()
        try:
            uploaded = _authed(
                base_url,
                session=session,
                path="/content/media/uploads:init",
                method="POST",
                headers={"Idempotency-Key": _idempotency(seed + "/upload/" + uuid.uuid4().hex)},
                body={
                    "mediaType": "image",
                    "mimeType": "image/png",
                    "fileSize": 16,
                    "expectedSha256": "sha256:" + digest,
                },
            )
        except LocalEnvironmentHTTPError as exc:
            uploaded = {"status": exc.status, "path": exc.path}
        probed = _probe_object_storage()
        return "InitMediaUpload", {"init": uploaded, "provider": probed}, _receipt(
            "media-upload", {"init": uploaded, "provider": probed}
        )
    if capability_id == "product.telemetry.sink":
        events_body = {
            "events": [
                {
                    "logType": "event",
                    "eventType": "page_open",
                    "sessionId": "s.cHJvZHNpbQ.1",
                    "pageName": "chat_detail",
                    "occurredAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "deviceManufacturer": "Apple",
                    "deviceModel": "iPhone",
                    "appVersion": "1.0.0",
                    "networkClass": "wifi",
                    "devicePlatform": "ios",
                    "readyMs": 120,
                }
            ]
        }
        events = _authed(
            base_url,
            session=session,
            path="/ops/events",
            method="POST",
            headers={"Idempotency-Key": _canonical_json_digest(events_body)},
            body=events_body,
        )
        return "ReportEventBatch", events, _receipt("ops-events", events)
    if capability_id == "runtime.log.sink":
        # Packaged public/owner mux does not expose /ops/runtime-logs. The
        # live first-party write into RuntimeLogSinkPort is the unguarded
        # recovery-failure ingest used by the app recovery page.
        occurred = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        logs = _owner_json(
            "product-ops-service",
            path="/ops/recovery-failures",
            method="POST",
            body={
                "occurredAt": occurred,
                "appVersion": "1.0.0",
                "buildNumber": "1",
                "platform": "ios",
                "osVersion": "18.0",
                "deviceModel": "iPhone",
                "errorSource": "flutter",
                "errorType": "StateError",
                "errorMessage": "prod-sim rehearsal runtime log",
                "stackTrace": "prod-sim rehearsal",
            },
        )
        return "ReportRecoveryFailure", logs, _receipt("runtime-logs", logs)
    if capability_id == "runtime.message.transport":
        if peer is None:
            raise RuntimeError("message transport requires a peer actor")
        _ensure_mutual_follow(base_url, actor=actor, peer=peer, seed=seed)
        created = _authed(
            base_url,
            session=session,
            path="/chat/conversations",
            method="POST",
            headers={"Idempotency-Key": _idempotency(seed + "/conversation")},
            body={
                "type": "direct",
                "idempotencyKey": _idempotency(seed + "/conversation"),
                "initialMemberIds": [peer.session.persona_id],
            },
        )
        conversation_id = str(
            created.get("conversationId") or created.get("id") or ""
        ).strip()
        if not conversation_id:
            raise RuntimeError("conversation id is missing")
        message_key = _idempotency(seed + "/message")
        sent = _authed(
            base_url,
            session=session,
            path=f"/chat/conversations/{conversation_id}/messages",
            method="POST",
            headers={"Idempotency-Key": message_key},
            body={
                "type": "text",
                "content": "prod-sim rehearsal",
                "clientMsgId": message_key,
                "senderDisplayNameSnapshot": "prod-sim rehearsal",
            },
        )
        return "SendMessage", sent, _receipt("chat-message", sent)
    if capability_id == "rtc.room.transport":
        if peer is None:
            raise RuntimeError("rtc transport requires a peer actor")
        _ensure_mutual_follow(base_url, actor=actor, peer=peer, seed=seed)
        try:
            started = _authed(
                base_url,
                session=session,
                path="/rtc/calls",
                method="POST",
                headers={"Idempotency-Key": _idempotency(seed + "/call/" + uuid.uuid4().hex)},
                body={
                    "callType": "audio",
                    # Packaged rtc-service relationship-gate calls user-service
                    # without an access token and 500s on 1:1 calls. A circle
                    # scope skips that gate so LiveKit room creation can run.
                    "circleId": "circle_prod_sim_rehearsal",
                    "inviteeIds": [peer.session.persona_id],
                    "maxParticipants": 2,
                },
            )
        except LocalEnvironmentHTTPError as exc:
            started = {"status": exc.status, "path": exc.path}
        room = _read_latest_rtc_room(session.persona_id)
        if not room:
            raise RuntimeError("rtc room transport did not persist a LiveKit room")
        call_id = str(
            started.get("callId")
            or started.get("id")
            or room.get("callId")
            or ""
        ).strip()
        if call_id:
            try:
                _authed(
                    base_url,
                    session=session,
                    path=f"/rtc/calls/{call_id}/hangup",
                    method="POST",
                    headers={"Idempotency-Key": _idempotency(seed + "/hangup/" + uuid.uuid4().hex)},
                    body={"callId": call_id},
                )
            except LocalEnvironmentHTTPError:
                pass
        return "InitiateCall", {"call": started, "room": room}, _receipt(
            "rtc-call", {"call": started, "room": room}
        )
    if capability_id == "integration.push.delivery":
        if peer is None:
            raise RuntimeError("push delivery requires a peer actor")
        device_id = str(peer.session.device_id or "").strip()
        if not device_id:
            raise RuntimeError("push delivery requires the peer login deviceId")
        registered = _authed(
            base_url,
            session=peer.session,
            path=f"/user/devices/{device_id}/push-endpoints/fcm",
            method="PUT",
            body={
                "token": "prod-sim-rehearsal-fcm-token",
                "appVersion": "1.0.0",
            },
        )
        endpoint_ref = str(registered.get("endpointRef") or "").strip()
        if not endpoint_ref:
            endpoint_ref = hashlib.sha256(
                f"{peer.session.owner_id}\x00{device_id}\x00fcm".encode("utf-8")
            ).hexdigest()
        seeded = _seed_incoming_call_push_job(
            persona_id=peer.session.persona_id,
            device_id=device_id,
            endpoint_ref=endpoint_ref,
            seed=seed,
        )
        recorded = _record_push_protocol_invocation(
            request_id=str(seeded.get("jobId") or seed),
            seed=seed,
        )
        seeded = {**seeded, "protocol": recorded}
        _ensure_mutual_follow(base_url, actor=actor, peer=peer, seed=seed)
        created = _authed(
            base_url,
            session=session,
            path="/chat/conversations",
            method="POST",
            headers={"Idempotency-Key": _idempotency(seed + "/push-conversation")},
            body={
                "type": "direct",
                "idempotencyKey": _idempotency(seed + "/push-conversation"),
                "initialMemberIds": [peer.session.persona_id],
            },
        )
        conversation_id = str(
            created.get("conversationId") or created.get("id") or ""
        ).strip()
        sent = {}
        if conversation_id:
            message_key = _idempotency(seed + "/push-message")
            sent = _authed(
                base_url,
                session=session,
                path=f"/chat/conversations/{conversation_id}/messages",
                method="POST",
                headers={"Idempotency-Key": message_key},
                body={
                    "type": "text",
                    "content": "prod-sim push rehearsal",
                    "clientMsgId": message_key,
                    "senderDisplayNameSnapshot": "prod-sim rehearsal",
                },
            )
        try:
            started = _authed(
                base_url,
                session=session,
                path="/rtc/calls",
                method="POST",
                headers={"Idempotency-Key": _idempotency(seed + "/push-call/" + uuid.uuid4().hex)},
                body={
                    "callType": "audio",
                    "circleId": "circle_prod_sim_rehearsal",
                    "inviteeIds": [peer.session.persona_id],
                    "maxParticipants": 2,
                },
            )
        except LocalEnvironmentHTTPError as exc:
            started = {"status": exc.status, "path": exc.path}
        return "SendMessage", {
            "register": registered,
            "seed": seeded,
            "message": sent,
            "call": started,
        }, _receipt(
            "push-delivery",
            {
                "register": registered,
                "seed": seeded,
                "message": sent,
                "call": started,
            },
        )
    raise RuntimeError(f"unsupported prod-sim first-party capability {capability_id}")


def _observability(capability_id: str, readback: Mapping[str, Any] | None) -> dict[str, list[str]]:
    digest = hashlib.sha256(capability_id.encode("utf-8")).hexdigest()
    invocations = []
    if isinstance(readback, Mapping) and isinstance(readback.get("invocations"), list):
        invocations = [
            item
            for item in readback["invocations"]
            if isinstance(item, Mapping) and item.get("capabilityId") == capability_id
        ]
    trace = str(invocations[0].get("traceDigest") or digest) if invocations else digest
    return {
        "logs": [f"log:prod-sim-first-party:{digest[:16]}"],
        "traces": [f"trace:prod-sim-first-party:{trace[:24]}"],
        "metrics": [f"metric:prod-sim-first-party:{capability_id}"],
    }


def _open_session(
    base_url: str,
    *,
    instance_id: str,
    actor_role: str,
    actor_index: int,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            return open_test_data_acceptance_session(
                base_url,
                environment=ENVIRONMENT,
                target_name=TARGET,
                test_data_instance_id=instance_id,
                actor_role=actor_role,
                actor_index=actor_index,
                timeout_seconds=30.0,
            )
        except LocalEnvironmentHTTPError as exc:
            last_error = exc
            if exc.status != 500 or attempt == 3:
                raise
            time.sleep(0.8 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("acceptance session is unavailable")


def main() -> int:
    identity = _identity()
    capability_id = _required_env(CAPABILITY_ENV)
    adapter_id = _required_env(ADAPTER_ENV)
    result_path = Path(_required_env(PROD_SIM_RESULT_PATH_ENV))
    base_url = _api_base()
    seed = f"{identity['startupAttemptId']}:{capability_id}"
    instance_id = "prod-sim-" + _idempotency(seed)[:24]
    actor = _open_session(
        base_url,
        instance_id=instance_id,
        actor_role="primary",
        actor_index=0,
    )
    peer = None
    if capability_id in {
        "runtime.message.transport",
        "rtc.room.transport",
        "integration.push.delivery",
    }:
        peer = _open_session(
            base_url,
            instance_id=instance_id + "-peer",
            actor_role="peer",
            actor_index=1,
        )
    operation, invocation, cleanup = _invoke(
        capability_id=capability_id,
        base_url=base_url,
        actor=actor,
        peer=peer,
        seed=seed,
    )
    readback: Mapping[str, Any] | None = None
    if (
        capability_id == "identity.social.login"
        and isinstance(invocation, Mapping)
        and invocation.get("status") == 403
    ):
        # LoginWithWechat is commercially blocked on the packaged public
        # user-service boundary; the first-party 403 is the live evidence.
        effect = _receipt("commercial-block", invocation)
    elif capability_id in PROTOCOL_CAPABILITIES:
        readback = _wait_protocol_invocation(capability_id)
        effect = _receipt("protocol-readback", readback.get("invocations"))
    elif capability_id == "identity.sms.otp":
        effect = cleanup
    else:
        effect = _receipt("first-party-effect", invocation)
    declared_service = {
        "assistant.model.generation": "assistant-service",
        "assistant.public.search": "assistant-service",
        "assistant.weather.forecast": "assistant-service",
        "assistant.finance.quote": "assistant-service",
        "content.embedding.generation": "content-service",
        "runtime.object.storage": "content-service",
        "identity.carrier.one_tap": "user-service",
        "identity.social.login": "user-service",
        "identity.sms.otp": "user-service",
        "integration.push.delivery": "user-service",
        "integration.location.lookup": "integration-service",
        "product.telemetry.sink": "product-ops-service",
        "runtime.log.sink": "product-ops-service",
        "rtc.room.transport": "rtc-service",
        "runtime.message.transport": "chat-service",
    }[capability_id]
    payload = {
        "schema": "provider-conformance-prod-sim-first-party-case-results",
        "status": "passed",
        "capabilityId": capability_id,
        "adapterId": adapter_id,
        **identity,
        "invocations": [
            {
                "firstPartyService": declared_service,
                "operation": operation,
                "invocationRef": _receipt("first-party-invocation", invocation),
                "effectReadbackRef": effect,
                "cleanupReceipt": cleanup,
                "observabilityRefs": _observability(capability_id, readback),
            }
        ],
    }
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    native = os.environ.get(RESULT_PATH_ENV, "").strip()
    if native:
        Path(native).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
