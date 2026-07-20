#!/usr/bin/env python3
"""Probe beta gateway media derivation for the shared avatar user pool."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "quwoquan_app").is_dir() and (candidate / "quwoquan_service").is_dir():
            return candidate
    raise RuntimeError("cannot locate quwoquan repo root")


ROOT = _find_repo_root()
SHARED = ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "test_fixtures"
MEDIA_ROOT = SHARED / "media"
USER_POOL_PATH = SHARED / "user_pool.json"
HTTP_TIMEOUT_SECONDS = 10
READY_TIMEOUT_SECONDS = 20
READY_PROBE_TIMEOUT_SECONDS = 2
READY_POLL_SECONDS = 0.2
PROCESS_SHUTDOWN_TIMEOUT_SECONDS = 5
CORE_PNG_COVER_KEY = "media/image/s/archived-image/post/fixture_photo_001/cover.png"
CANONICAL_COVER_PREFIXES = ("media/image/s/", "media/video/s/")


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    try:
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def get_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def get_headers(url: str) -> dict[str, str]:
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_SECONDS) as response:
        response.read()
        return {key.lower(): value for key, value in response.headers.items()}


def wait_ok(url: str, label: str) -> None:
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=READY_PROBE_TIMEOUT_SECONDS) as response:
                response.read()
                if response.status < 500:
                    return
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(READY_POLL_SECONDS)
    raise RuntimeError(f"{label} did not become ready: {last_error}")


def collect_strings(value: Any, key_name: str) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == key_name and isinstance(nested, str):
                found.append(nested)
            found.extend(collect_strings(nested, key_name))
    elif isinstance(value, list):
        for nested in value:
            found.extend(collect_strings(nested, key_name))
    return found


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_pool() -> dict[str, Any]:
    return json.loads(USER_POOL_PATH.read_text(encoding="utf-8"))


def first_object_key(pool: dict[str, Any], prefix: str | tuple[str, ...], *, exclude_suffix: str | None = None) -> str:
    prefixes = (prefix,) if isinstance(prefix, str) else prefix
    candidates: list[str] = []
    for user in pool.get("users", []):
        for field in ("avatarObjectKey", "backgroundObjectKey"):
            value = str(user.get(field) or "")
            if value.startswith(prefixes):
                candidates.append(value)
    for bundle in (pool.get("postMedia") or {}).values():
        for asset in (bundle.get("images") or []):
            value = str(asset.get("objectKey") or "")
            if value.startswith(prefixes):
                candidates.append(value)
    for bundle in (pool.get("circleMedia") or {}).values():
        for key in ("avatar", "cover"):
            value = str((bundle.get(key) or {}).get("objectKey") or "")
            if value.startswith(prefixes):
                candidates.append(value)
    for bundle in (pool.get("groupAvatarMedia") or {}).values():
        value = str((bundle.get("composite") or {}).get("objectKey") or "")
        if value.startswith(prefixes):
            candidates.append(value)
    for candidate in candidates:
        if exclude_suffix and candidate.endswith(exclude_suffix):
            continue
        return candidate
    raise RuntimeError(f"no objectKey found for prefix={prefixes!r}")


def main() -> int:
    pool = load_pool()
    media_port = free_port()
    gateway_port = free_port()
    media_base = f"http://127.0.0.1:{media_port}"
    gateway_base = f"http://127.0.0.1:{gateway_port}"
    processes: list[subprocess.Popen[str]] = []
    avatar_object_key = first_object_key(pool, ("media/avatar/s/archived-avatar/user/", "media/preset/avatar/"))
    group_avatar_key = first_object_key(pool, "media/avatar/s/archived-avatar/group/")
    png_cover_key = CORE_PNG_COVER_KEY
    mixed_cover_key = first_object_key(pool, "media/image/s/archived-image/post/", exclude_suffix=".png")
    try:
        media = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(media_port), "--bind", "127.0.0.1", "--directory", str(MEDIA_ROOT)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        processes.append(media)
        wait_ok(f"{media_base}/{avatar_object_key}", "media server")

        gateway = subprocess.Popen(
            [
                sys.executable,
                "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/smoke/dev_assistant_beta_gateway.py",
                "--listen-host",
                "127.0.0.1",
                "--listen-port",
                str(gateway_port),
                "--avatar-cdn-base-url",
                media_base,
                "--image-cdn-base-url",
                media_base,
                "--video-cdn-base-url",
                media_base,
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        processes.append(gateway)
        wait_ok(f"{gateway_base}/healthz", "beta gateway")

        content = get_json(f"{gateway_base}/content/feed")
        user = get_json(f"{gateway_base}/user/profile")
        contacts = get_json(f"{gateway_base}/chat/contacts")
        inbox = get_json(f"{gateway_base}/chat/inbox")
        messages = get_json(f"{gateway_base}/chat/conversations/fixture_conv_direct/messages")
        members = get_json(f"{gateway_base}/chat/conversations/fixture_conv_direct/members")

        avatar_values = []
        for payload in (content, user, contacts, inbox, messages, members):
            avatar_values.extend(collect_strings(payload, "avatarUrl"))
            avatar_values.extend(collect_strings(payload, "authorAvatarUrl"))
            avatar_values.extend(collect_strings(payload, "senderAvatarUrlSnapshot"))
            avatar_values.extend(collect_strings(payload, "senderAvatar"))
        require(avatar_values, "expected avatar values from gateway fixtures")
        require(
            all(
                value.startswith(("media/avatar/", "media/preset/avatar/"))
                for value in avatar_values
            ),
            f"all avatar values must remain canonical object keys, got {avatar_values}",
        )

        cover_values = collect_strings(content, "coverUrl") + collect_strings(content, "thumbnailUrl")
        require(cover_values, "expected post cover values from gateway content fixture")
        require(
        all(
            value.startswith(CANONICAL_COVER_PREFIXES)
            and "?" not in value
            and "#" not in value
            for value in cover_values
        ),
            f"all cover values must remain canonical object keys, got {cover_values}",
        )

        avatar_headers = get_headers(f"{gateway_base}/{avatar_object_key}")
        png_cover_headers = get_headers(f"{gateway_base}/{png_cover_key}")
        mixed_cover_headers = get_headers(f"{gateway_base}/{mixed_cover_key}")
        group_avatar_headers = get_headers(f"{gateway_base}/{group_avatar_key}")
        require(avatar_headers.get("content-type", "").startswith("image/"), "gateway avatar proxy must return image/*")
        require(png_cover_headers.get("content-type", "").startswith("image/png"), "core png post cover must return image/png")
        require(mixed_cover_headers.get("content-type", "").startswith("image/"), "mixed-format post cover must return image/*")
        require(group_avatar_headers.get("content-type", "").startswith("image/png"), "group avatar composite must remain image/png")
        print("avatar user pool beta gateway probe passed")
        return 0
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(processes):
            try:
                process.wait(timeout=PROCESS_SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
