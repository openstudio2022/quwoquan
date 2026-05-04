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


ROOT = Path(__file__).resolve().parents[1]
MEDIA_ROOT = ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "test_fixtures" / "media"


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    try:
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def get_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def get_headers(url: str) -> dict[str, str]:
    with urllib.request.urlopen(url, timeout=10) as response:
        response.read()
        return {key.lower(): value for key, value in response.headers.items()}


def wait_ok(url: str, label: str) -> None:
    deadline = time.monotonic() + 15
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                response.read()
                if response.status < 500:
                    return
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(0.2)
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


def main() -> int:
    media_port = free_port()
    gateway_port = free_port()
    media_base = f"http://127.0.0.1:{media_port}"
    gateway_base = f"http://127.0.0.1:{gateway_port}"
    processes: list[subprocess.Popen[str]] = []
    try:
        media = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(media_port), "--bind", "127.0.0.1", "--directory", str(MEDIA_ROOT)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        processes.append(media)
        wait_ok(f"{media_base}/media/avatar/user/fixture_user_current/v1/avatar.png", "media server")

        gateway = subprocess.Popen(
            [
                sys.executable,
                "scripts/dev_assistant_beta_gateway.py",
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

        content = get_json(f"{gateway_base}/v1/content/feed")
        user = get_json(f"{gateway_base}/v1/user/profile")
        contacts = get_json(f"{gateway_base}/v1/chat/contacts")
        inbox = get_json(f"{gateway_base}/v1/chat/inbox")
        messages = get_json(f"{gateway_base}/v1/chat/conversations/fixture_conv_direct/messages")
        members = get_json(f"{gateway_base}/v1/chat/conversations/fixture_conv_direct/members")

        avatar_values = []
        for payload in (content, user, contacts, inbox, messages, members):
            avatar_values.extend(collect_strings(payload, "avatarUrl"))
            avatar_values.extend(collect_strings(payload, "authorAvatarUrl"))
            avatar_values.extend(collect_strings(payload, "senderAvatarUrlSnapshot"))
            avatar_values.extend(collect_strings(payload, "senderAvatar"))
        require(avatar_values, "expected avatar values from gateway fixtures")
        require(
            all(value.startswith(f"{media_base}/media/avatar/") for value in avatar_values),
            f"all avatar values must be media-base URLs, got {avatar_values}",
        )

        cover_values = collect_strings(content, "coverUrl") + collect_strings(content, "thumbnailUrl")
        require(cover_values, "expected post cover values from gateway content fixture")
        require(
            all(value.startswith(f"{media_base}/media/image/post/") for value in cover_values),
            f"all cover values must be media image URLs, got {cover_values}",
        )

        avatar_headers = get_headers(f"{gateway_base}/media/avatar/user/fixture_user_current/v1/avatar.png")
        cover_headers = get_headers(f"{gateway_base}/media/image/post/fixture_photo_001/v1/cover.png")
        require(avatar_headers.get("content-type", "").startswith("image/png"), "gateway avatar proxy must return image/png")
        require(cover_headers.get("content-type", "").startswith("image/png"), "gateway post cover proxy must return image/png")
        print("avatar user pool beta gateway probe passed")
        return 0
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(processes):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
