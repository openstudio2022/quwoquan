#!/usr/bin/env python3
"""本地 beta 网关：转发 assistant，并为业务对象提供 contract fixture 只读 API。"""

from __future__ import annotations

import argparse
import copy
import json
import signal
import threading
from pathlib import Path
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "quwoquan_service" / "contracts" / "metadata"
FORWARDED_PREFIXES = ("/v1/assistant",)


def load_fixture(relative_path: str) -> dict:
    return json.loads((METADATA / relative_path).read_text(encoding="utf-8"))


def seed_set(relative_path: str, ref: str) -> dict:
    return load_fixture(relative_path)["seedSets"][ref]


def user_profile_wire(profile: dict) -> dict:
    stats = profile.get("stats") or {}
    user_id = profile.get("userId", "")
    return {
        "profileSubjectId": user_id,
        "ownerUserId": user_id,
        "subAccountId": "",
        "userHandle": user_id,
        "username": user_id,
        "nickname": profile.get("displayName", user_id),
        "displayName": profile.get("displayName", user_id),
        "subjectType": "user",
        "avatarUrl": profile.get("avatarUrl", ""),
        "backgroundUrl": profile.get("backgroundUrl", ""),
        "bio": profile.get("bio", ""),
        "followingCount": stats.get("followingCount", 0),
        "followerCount": stats.get("followerCount", 0),
        "postCount": stats.get("postCount", 0),
        "circleCount": stats.get("circleCount", 0),
        "likeCount": stats.get("likeCount", 0),
        "profileVisibility": "public",
        "isolationLevel": "open",
        "inheritsFromOwner": False,
        "overriddenFields": [],
    }


def work_item_wire(post: dict) -> dict:
    return {
        "id": post.get("id") or post.get("postId", ""),
        "type": post.get("type") or post.get("contentType", ""),
        "title": post.get("title") or post.get("body") or post.get("summary", ""),
        "coverUrl": post.get("coverUrl") or post.get("thumbnailUrl", ""),
        "likeCount": post.get("likeCount", 0),
        "date": post.get("createdAt") or post.get("publishedAt", ""),
        "desc": post.get("summary") or post.get("body") or "",
    }


class AssistantBetaGateway(BaseHTTPRequestHandler):
    upstream_host: str = "127.0.0.1"
    upstream_port: int = 18087
    avatar_cdn_base_url: str = ""
    image_cdn_base_url: str = ""
    video_cdn_base_url: str = ""

    def do_GET(self) -> None:
        self._forward()

    def do_POST(self) -> None:
        self._forward()

    def do_PUT(self) -> None:
        self._forward()

    def do_PATCH(self) -> None:
        self._forward()

    def do_DELETE(self) -> None:
        self._forward()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def _forward(self) -> None:
        parsed = urlsplit(self.path)
        fixture_payload = self._fixture_response(parsed.path, parsed.query)
        if fixture_payload is not None:
            self._send_json(fixture_payload)
            return
        if not parsed.path.startswith(FORWARDED_PREFIXES):
            self.send_error(404, "route is not available in local beta gateway")
            return

        body_len = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(body_len) if body_len > 0 else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection"}
        }

        stream_response = parsed.path.endswith("/stream")
        conn = HTTPConnection(self.upstream_host, self.upstream_port, timeout=240 if stream_response else 30)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            upstream = conn.getresponse()
            if self._is_streaming_response(upstream, stream_response):
                self._send_upstream_headers(upstream)
                while True:
                    chunk = upstream.readline()
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
                return
            payload = upstream.read()
        except Exception as exc:  # noqa: BLE001
            self.send_error(502, f"assistant beta gateway upstream failed: {exc}")
            return
        finally:
            conn.close()

        self._send_upstream_headers(upstream)
        self.wfile.write(payload)

    def _is_streaming_response(self, upstream, stream_path: bool) -> bool:
        content_type = upstream.getheader("Content-Type", "")
        return stream_path or content_type.lower().startswith("text/event-stream")

    def _send_upstream_headers(self, upstream) -> None:
        self.send_response(upstream.status)
        for key, value in upstream.getheaders():
            if key.lower() in {"connection", "transfer-encoding"}:
                continue
            self.send_header(key, value)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _fixture_response(self, path: str, query: str = "") -> object | None:
        if path == "/healthz":
            return {"status": "ok", "gateway": "business-beta"}

        content = seed_set("content/test_fixtures/scenarios/content_scenarios.json", "content_discovery_core")
        chat = seed_set("messages/chat/test_fixtures/scenarios/chat_scenarios.json", "chat_core")
        chat_contacts = seed_set("messages/chat/test_fixtures/scenarios/chat_scenarios.json", "chat_contacts_core")
        circle = seed_set("social/circle/test_fixtures/scenarios/circle_scenarios.json", "circle_core")
        circle_home = seed_set("social/circle/test_fixtures/scenarios/circle_scenarios.json", "circle_home_feed_core")
        user = seed_set("user/test_fixtures/scenarios/user_scenarios.json", "user_profile_core")
        user_feed = seed_set("user/test_fixtures/scenarios/user_scenarios.json", "profile_feed_core")
        entity = seed_set("entity/test_fixtures/scenarios/entity_scenarios.json", "entity_homepage_core")
        integration = seed_set("integration/test_fixtures/scenarios/integration_scenarios.json", "location_poi_core")
        notification = seed_set("notification/test_fixtures/scenarios/notification_scenarios.json", "notification_core")
        rtc = seed_set("rtc/test_fixtures/scenarios/rtc_scenarios.json", "rtc_core")

        if path == "/v1/content/feed":
            params = parse_qs(query)
            items = list(content.get("posts", []))
            identity = (params.get("identity") or [""])[0]
            content_type = (params.get("type") or [""])[0]
            limit_raw = (params.get("limit") or [""])[0]
            if identity:
                items = [p for p in items if (p.get("identity") or p.get("contentIdentity")) == identity]
            if content_type:
                items = [p for p in items if (p.get("type") or p.get("contentType")) == content_type]
            if limit_raw.isdigit():
                items = items[: int(limit_raw)]
            return {"items": items}
        if path == "/v1/config/app":
            return {
                "content": {
                    "feature_flags": {},
                    "gray_release": {"enabled": False},
                    "client_state_sync": {"enabled": True},
                }
            }
        if path == "/v1/content/behaviors":
            return {"accepted": True}
        if path.startswith("/v1/content/profile-subjects/") and path.endswith("/posts"):
            profile_subject_id = path.split("/")[-2]
            selected_ids = (
                user_feed.get("myPostIds", [])
                if profile_subject_id == "fixture_user_current"
                else user_feed.get("authorPostIds", [])
            )
            return {"items": [p for p in content.get("posts", []) if (p.get("id") or p.get("postId")) in selected_ids]}
        if path.startswith("/v1/content/posts/"):
            post_id = path.split("/")[-1]
            posts = [p for p in content.get("posts", []) if p.get("id") == post_id or p.get("postId") == post_id]
            return posts[0] if posts else {}
        if path == "/v1/chat/inbox":
            return {"items": chat.get("conversations", [])}
        if path == "/v1/chat/conversations":
            return {"items": chat.get("conversations", [])}
        if path == "/v1/chat/contacts":
            return {"items": chat_contacts.get("contacts", [])}
        if path.startswith("/v1/chat/conversations/") and path.count("/") == 4:
            conv_id = path.split("/")[-1]
            conversations = [c for c in chat.get("conversations", []) if c.get("conversationId") == conv_id or c.get("id") == conv_id]
            return conversations[0] if conversations else {}
        if path.startswith("/v1/chat/conversations/") and path.endswith("/messages"):
            conv_id = path.split("/")[-2]
            return {"items": chat.get("messages", {}).get(conv_id, [])}
        if path.startswith("/v1/chat/conversations/") and path.endswith("/members"):
            conv_id = path.split("/")[-2]
            return {"items": chat.get("members", {}).get(conv_id, [])}
        if path == "/v1/circles":
            return {"items": circle.get("circles", [])}
        if path.startswith("/v1/circles/") and path.endswith("/feed"):
            circle_id = path.split("/")[-2]
            post_ids = circle_home.get("groupFeedPostIds", [])
            return {"items": [p for p in content.get("posts", []) if (p.get("id") or p.get("postId")) in post_ids]}
        if path.startswith("/v1/circles/") and path.endswith("/groups"):
            circle_id = path.split("/")[-2]
            return {"items": circle.get("groups", {}).get(circle_id, [])}
        if path.startswith("/v1/circles/") and path.endswith("/members"):
            circle_id = path.split("/")[-2]
            return {"items": circle.get("members", {}).get(circle_id, [])}
        if path.startswith("/v1/circles/"):
            circle_id = path.split("/")[-1]
            circles = [c for c in circle.get("circles", []) if c.get("id") == circle_id]
            return {"data": circles[0] if circles else {}}
        if path == "/v1/me":
            return user_profile_wire(user.get("profiles", [])[0])
        if path == "/v1/user/personas/active":
            profile = user_profile_wire(user.get("profiles", [])[0])
            return {
                "personaId": profile["profileSubjectId"],
                "profileSubjectId": profile["profileSubjectId"],
                "ownerUserId": profile["ownerUserId"],
                "subAccountId": profile["profileSubjectId"],
                "subjectType": profile["subjectType"],
                "displayName": profile["displayName"],
                "avatarUrl": profile["avatarUrl"],
                "personaContextVersion": "beta-fixture-v1",
                "personaSnapshotVersion": 1,
                "sourceSurfaceId": "beta.manual",
                "explicitOverride": False,
                "isPrimary": True,
            }
        if path == "/v1/user/settings/appearance":
            return {
                "themeMode": "system",
                "fontSizePreset": "md",
                "source": "owner_default",
                "ownerDefaultThemeMode": "system",
                "ownerDefaultFontSizePreset": "md",
                "hasSubAccountOverride": False,
                "version": 1,
                "updatedAt": "2026-01-01T00:00:00Z",
            }
        if path.startswith("/v1/user/profile-subjects/") and path.endswith("/relationship/capability"):
            target_id = path.split("/")[-3]
            return {
                "viewerProfileSubjectId": "fixture_user_current",
                "targetProfileSubjectId": target_id,
                "relationState": "none",
                "relationTier": "public",
                "canFollow": target_id != "fixture_user_current",
                "canUnfollow": False,
                "canMessage": True,
                "canFollowBack": False,
                "canGreet": True,
                "canOpenConversation": True,
                "canAddSameInterest": True,
                "canSetCloseFriend": False,
                "canStartVoiceCall": False,
                "canStartVideoCall": False,
                "isBlocked": False,
                "isBlockedBy": False,
            }
        if path.startswith("/v1/user/") and path.count("/") == 3:
            user_id = path.split("/")[-1]
            profiles = [p for p in user.get("profiles", []) if p.get("userId") == user_id]
            return user_profile_wire(profiles[0]) if profiles else {}
        if path == "/v1/user/profile":
            return {"items": user.get("profiles", [])}
        if path.startswith("/v1/users/") and path.endswith("/works"):
            user_id = path.split("/")[-2]
            selected_ids = (
                user_feed.get("myPostIds", [])
                if user_id == "fixture_user_current"
                else user_feed.get("authorPostIds", [])
            )
            return {"items": [work_item_wire(p) for p in content.get("posts", []) if (p.get("id") or p.get("postId")) in selected_ids]}
        if path.startswith("/v1/users/") and path.endswith("/life-items"):
            return {"items": []}
        if path.startswith("/v1/users/") and path.endswith("/circles"):
            return {"items": circle.get("circles", [])}
        if path == "/v1/entity/homepages":
            return {"items": entity.get("homepages", [])}
        if path == "/v1/integration/locations/pois":
            return {"items": integration.get("pois", [])}
        if path == "/v1/app-messages":
            return {"items": notification.get("appMessages", []), "unreadCount": notification.get("unreadCount", 0)}
        if path == "/v1/rtc/calls":
            return {"items": rtc.get("sessions", []), "participants": rtc.get("participants", [])}
        if path == "/v1/ops/events":
            return {"acceptedCount": 1, "duplicateCount": 0}
        if path == "/v1/ops/visits":
            return {"accepted": True}
        return None

    def _send_json(self, payload: object) -> None:
        raw = json.dumps(self._rewrite_media_urls(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[business-beta-gateway] {self.address_string()} {fmt % args}")

    @classmethod
    def _rewrite_media_urls(cls, payload: object) -> object:
        avatar = cls.avatar_cdn_base_url.rstrip("/")
        image = cls.image_cdn_base_url.rstrip("/")
        video = cls.video_cdn_base_url.rstrip("/")

        def walk(value: object) -> object:
            if isinstance(value, list):
                return [walk(item) for item in value]
            if not isinstance(value, dict):
                return value
            out = {str(k): walk(v) for k, v in value.items()}
            if avatar and "avatarUrl" in out:
                out["avatarUrl"] = f"{avatar}/media/avatar/beta-avatar.png"
            if image and "coverUrl" in out:
                out["coverUrl"] = f"{image}/media/image/beta-cover.png"
            if video and str(out.get("type", "")).lower() == "video":
                out["mediaUrl"] = f"{video}/media/video/beta-sample.mp4"
            return out

        return walk(copy.deepcopy(payload))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local beta gateway.")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=18080)
    parser.add_argument("--upstream-host", default="127.0.0.1")
    parser.add_argument("--upstream-port", type=int, default=18087)
    parser.add_argument("--avatar-cdn-base-url", default="")
    parser.add_argument("--image-cdn-base-url", default="")
    parser.add_argument("--video-cdn-base-url", default="")
    args = parser.parse_args()

    AssistantBetaGateway.upstream_host = args.upstream_host
    AssistantBetaGateway.upstream_port = args.upstream_port
    AssistantBetaGateway.avatar_cdn_base_url = args.avatar_cdn_base_url
    AssistantBetaGateway.image_cdn_base_url = args.image_cdn_base_url
    AssistantBetaGateway.video_cdn_base_url = args.video_cdn_base_url
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), AssistantBetaGateway)

    def request_shutdown(signum: int, _frame: object) -> None:
        print(f"[business-beta-gateway] shutdown signal received: {signum}", flush=True)
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    print(
        "[business-beta-gateway] listening "
        f"http://{args.listen_host}:{args.listen_port} -> "
        f"http://{args.upstream_host}:{args.upstream_port}"
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        print("[business-beta-gateway] shutdown complete", flush=True)


if __name__ == "__main__":
    main()
