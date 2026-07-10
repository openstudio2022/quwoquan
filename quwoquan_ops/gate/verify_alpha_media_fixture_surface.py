#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology


BUNDLE_PATH = ROOT / "quwoquan_ops" / "environments" / "gamma_curated_media_bundle.json"
FIXTURE_ROOT = ROOT / "quwoquan_service" / "contracts" / "metadata"
APP_CHAT_MOCK_DATA_PATH = (
    ROOT
    / "quwoquan_app"
    / "lib"
    / "cloud"
    / "services"
    / "chat"
    / "mock"
    / "chat_mock_data.dart"
)
APP_PROTOTYPE_MOCK_DATA_PATH = (
    ROOT / "quwoquan_app" / "lib" / "core" / "mock" / "prototype_mock_data.dart"
)
MEDIA_AVATAR_LITERAL_RE = re.compile(r"['\"](media/avatar/[^'\"]+)['\"]")
MEDIA_ROOT = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "_shared"
    / "test_fixtures"
    / "media"
)
DEFAULT_BASE_URL = "https://localhost:17100"
DEFAULT_TARGET_BY_ENV = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
}
LOCAL_ROOT_CA_BY_TARGET = {
    "alpha-local": ROOT
    / ".qwq_output"
    / "env"
    / "alpha"
    / "local"
    / "alpha-local"
    / "tls"
    / "ca"
    / "root.crt",
    "beta-local": ROOT
    / ".qwq_output"
    / "env"
    / "beta"
    / "local"
    / "beta-local"
    / "caddy"
    / "data"
    / "caddy"
    / "pki"
    / "authorities"
    / "local"
    / "root.crt",
    "gamma-local": ROOT
    / ".qwq_output"
    / "env"
    / "gamma"
    / "local"
    / "gamma-local"
    / "caddy"
    / "data"
    / "caddy"
    / "pki"
    / "authorities"
    / "local"
    / "root.crt",
}
MEDIA_PREFIXES = (
    "media/avatar/",
    "media/image/",
    "media/video/",
    "media/background/",
)
GROUP_AVATAR_CALL_RE = re.compile(r"groupAvatarFor\('([^']+)'\)")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify every seeded avatar/image/background/video object is "
            "materialized and reachable from an environment HTTPS media plane."
        ),
    )
    parser.add_argument("--env", choices=tuple(DEFAULT_TARGET_BY_ENV), default="alpha")
    parser.add_argument("--target", choices=tuple(DEFAULT_TARGET_BY_ENV.values()), default="")
    parser.add_argument("--avatar-base-url", default="")
    parser.add_argument("--media-base-url", default="")
    parser.add_argument("--video-base-url", default="")
    parser.add_argument("--cacert", default="")
    parser.add_argument(
        "--include-app-mock-group-avatars",
        choices=("auto", "true", "false"),
        default="auto",
    )
    return parser


def _curl_probe(
    url: str,
    *,
    cacert: Path,
    range_probe: bool = False,
    resolve_local: bool = False,
) -> tuple[str, str]:
    cmd = [
        "curl",
        "-fsS",
        "--http1.1",
        "--connect-timeout",
        "3",
        "--max-time",
        "8",
        "--retry",
        "5",
        "--retry-delay",
        "1",
        "--retry-all-errors",
        "--cacert",
        str(cacert),
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}|%{content_type}",
    ]
    if resolve_local:
        parsed = urlsplit(url)
        if parsed.hostname and parsed.port:
            cmd.extend(["--resolve", f"{parsed.hostname}:{parsed.port}:127.0.0.1"])
    if range_probe:
        cmd.extend(["-H", "Range: bytes=0-1"])
    else:
        cmd.extend(["-H", "Range: bytes=0-0"])
    cmd.append(url)
    last_failure: tuple[str, str] = ("curl-failed:unknown", "")
    for attempt in range(3):
        result = subprocess.run(cmd, text=True, capture_output=True, check=False)
        if result.returncode == 0:
            status, _, content_type = result.stdout.strip().partition("|")
            return (status, content_type)
        detail = (result.stderr or result.stdout).strip().splitlines()
        last_failure = (f"curl-failed:{detail[-1] if detail else result.returncode}", "")
        if attempt < 2:
            time.sleep(0.2)
    return last_failure


def _load_media_objects() -> list[dict[str, Any]]:
    data = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    objects = data.get("mediaObjects")
    if not isinstance(objects, list):
        raise ValueError(f"{BUNDLE_PATH} missing mediaObjects list")
    return [item for item in objects if isinstance(item, dict)]


def _collect_media_refs_from_json(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    refs: set[str] = set()

    def add(value: Any) -> None:
        if not isinstance(value, str):
            return
        object_key = value.strip().lstrip("/")
        if object_key.startswith(MEDIA_PREFIXES):
            refs.add(object_key)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)
        else:
            add(value)

    walk(data)
    return refs


def _fixture_json_paths() -> list[Path]:
    paths = sorted(FIXTURE_ROOT.glob("**/test_fixtures/**/*.json"))
    if BUNDLE_PATH.is_file():
        paths.append(BUNDLE_PATH)
    return paths


def _collect_all_seeded_media_refs() -> tuple[set[str], dict[str, set[str]]]:
    refs: set[str] = set()
    origins: dict[str, set[str]] = {}
    for path in _fixture_json_paths():
        try:
            path_refs = _collect_media_refs_from_json(path)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} is not valid JSON: {exc}") from exc
        relative = path.relative_to(ROOT).as_posix()
        for object_key in path_refs:
            refs.add(object_key)
            origins.setdefault(object_key, set()).add(relative)
    return refs, origins


def _collect_app_mock_group_avatar_refs() -> set[str]:
    text = APP_CHAT_MOCK_DATA_PATH.read_text(encoding="utf-8")
    conversation_ids = {
        match.group(1)
        for match in GROUP_AVATAR_CALL_RE.finditer(text)
        if "$" not in match.group(1)
    }
    if "groupAvatarFor('conv_grid_$n')" in text:
        conversation_ids.update(f"conv_grid_{index}" for index in range(1, 17))
    return {
        f"media/avatar/s/archived-avatar/conversation/{conversation_id}/v1/mock.png"
        for conversation_id in conversation_ids
    }


def _collect_dart_media_avatar_literals(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8")
    refs: set[str] = set()
    for match in MEDIA_AVATAR_LITERAL_RE.finditer(text):
        object_key = match.group(1).strip().lstrip("/")
        if object_key.startswith("media/avatar/"):
            refs.add(object_key)
    return refs


def _collect_app_chat_and_prototype_avatar_refs() -> set[str]:
    refs = _collect_dart_media_avatar_literals(APP_CHAT_MOCK_DATA_PATH)
    refs.update(_collect_dart_media_avatar_literals(APP_PROTOTYPE_MOCK_DATA_PATH))
    return refs


def _expected_content_type_prefix(object_key: str) -> str | None:
    if object_key.startswith(("media/avatar/", "media/image/", "media/background/")):
        return "image/"
    if object_key.startswith("media/video/"):
        return "video/"
    return None


def _resolve_target_name(env_name: str, explicit_target: str) -> str:
    if explicit_target:
        return explicit_target
    return DEFAULT_TARGET_BY_ENV[env_name]


def _resolve_public_bases(
    env_name: str,
    target_name: str,
    args: argparse.Namespace,
) -> dict[str, str]:
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    avatar_base_url = str(
        args.avatar_base_url
        or public_bases.get("mediaAvatar")
        or public_bases.get("mediaImage")
        or ""
    )
    media_base_url = str(args.media_base_url or public_bases.get("mediaImage") or avatar_base_url)
    video_base_url = str(args.video_base_url or public_bases.get("mediaVideo") or media_base_url)
    if env_name == "alpha" and not any(
        (args.avatar_base_url, args.media_base_url, args.video_base_url)
    ):
        # The local runtime media gate can run with host-file/DNS mutation disabled.
        # stackctl T4 still passes explicit topology public bases for env validation.
        avatar_base_url = media_base_url = video_base_url = DEFAULT_BASE_URL
    return {
        "avatar": avatar_base_url.rstrip("/"),
        "image": media_base_url.rstrip("/"),
        "video": video_base_url.rstrip("/"),
    }


def _resolve_local_root_ca(target_name: str, explicit_cacert: str) -> Path:
    if explicit_cacert:
        return Path(explicit_cacert)
    direct = LOCAL_ROOT_CA_BY_TARGET[target_name]
    if direct.is_file():
        return direct
    env_prefix = target_name.split("-", maxsplit=1)[0]
    candidates = sorted((ROOT / ".qwq_output" / "env" / env_prefix / "local").glob("**/root.crt"))
    return candidates[0] if candidates else direct


def _base_url_for_object_key(object_key: str, base_urls: dict[str, str]) -> str:
    if object_key.startswith("media/video/"):
        return base_urls["video"]
    if object_key.startswith("media/avatar/"):
        return base_urls["avatar"]
    return base_urls["image"]


def _include_app_mock_group_avatars(env_name: str, mode: str) -> bool:
    if mode == "true":
        return True
    if mode == "false":
        return False
    return env_name == "alpha"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    env_name = str(args.env)
    target_name = _resolve_target_name(env_name, str(args.target or ""))
    base_urls = _resolve_public_bases(env_name, target_name, args)
    local_root_ca = _resolve_local_root_ca(target_name, str(args.cacert or ""))

    issues: list[str] = []
    if not BUNDLE_PATH.is_file():
        issues.append(f"media bundle missing: {BUNDLE_PATH}")
    if not FIXTURE_ROOT.is_dir():
        issues.append(f"fixture root missing: {FIXTURE_ROOT}")
    if not APP_CHAT_MOCK_DATA_PATH.is_file():
        issues.append(f"app chat mock data missing: {APP_CHAT_MOCK_DATA_PATH}")
    if not MEDIA_ROOT.is_dir():
        issues.append(f"shared media root missing: {MEDIA_ROOT}")
    if not local_root_ca.is_file():
        issues.append(f"{target_name} local root CA missing: {local_root_ca}")
    for label, base_url in base_urls.items():
        if not base_url.startswith("https://"):
            issues.append(f"{target_name} {label} base URL must be https: {base_url or '<empty>'}")
    if issues:
        print("[verify_alpha_media_fixture_surface] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    checked = 0
    video_checked = 0
    object_keys: set[str] = set()
    object_origins: dict[str, set[str]] = {}
    for item in _load_media_objects():
        object_key = str(item.get("objectKey") or "").strip().lstrip("/")
        relative_path = str(item.get("relativePath") or "").strip()
        if not object_key:
            issues.append(f"empty objectKey in {BUNDLE_PATH}")
            continue
        if relative_path and not (ROOT / relative_path).is_file():
            issues.append(f"{object_key} source file missing: {relative_path}")
            continue
        object_keys.add(object_key)
        object_origins.setdefault(object_key, set()).add(BUNDLE_PATH.relative_to(ROOT).as_posix())

    fixture_refs, fixture_origins = _collect_all_seeded_media_refs()
    object_keys.update(fixture_refs)
    for object_key, origins in fixture_origins.items():
        object_origins.setdefault(object_key, set()).update(origins)

    app_mock_group_refs: set[str] = set()
    app_chat_prototype_refs: set[str] = set()
    if _include_app_mock_group_avatars(env_name, str(args.include_app_mock_group_avatars)):
        app_mock_group_refs = _collect_app_mock_group_avatar_refs()
        object_keys.update(app_mock_group_refs)
        for object_key in app_mock_group_refs:
            object_origins.setdefault(object_key, set()).add(
                APP_CHAT_MOCK_DATA_PATH.relative_to(ROOT).as_posix()
            )
        app_chat_prototype_refs = _collect_app_chat_and_prototype_avatar_refs()
        object_keys.update(app_chat_prototype_refs)
        for object_key in app_chat_prototype_refs:
            object_origins.setdefault(object_key, set()).add(
                APP_CHAT_MOCK_DATA_PATH.relative_to(ROOT).as_posix()
            )
            if APP_PROTOTYPE_MOCK_DATA_PATH.is_file():
                object_origins.setdefault(object_key, set()).add(
                    APP_PROTOTYPE_MOCK_DATA_PATH.relative_to(ROOT).as_posix()
                )

    for object_key in sorted(object_keys):
        source_file = MEDIA_ROOT / object_key
        if not source_file.is_file():
            origins = ", ".join(sorted(object_origins.get(object_key, set()))[:3])
            suffix = f" referenced by {origins}" if origins else ""
            issues.append(f"{object_key} source file missing: {source_file}{suffix}")
            continue
        checked += 1
        is_video = object_key.startswith("media/video/")
        base_url = _base_url_for_object_key(object_key, base_urls)
        status, content_type = _curl_probe(
            f"{base_url}/{object_key}",
            cacert=local_root_ca,
            range_probe=is_video,
            resolve_local=target_name in LOCAL_ROOT_CA_BY_TARGET,
        )
        expected_statuses = {"206"} if is_video else {"200", "206"}
        if is_video:
            video_checked += 1
        if status not in expected_statuses:
            issues.append(
                f"{object_key} expected HTTP {sorted(expected_statuses)}, "
                f"got {status}: {base_url}/{object_key}"
            )
            continue
        expected_content_type = _expected_content_type_prefix(object_key)
        if expected_content_type and not content_type.startswith(expected_content_type):
            issues.append(
                f"{object_key} expected Content-Type {expected_content_type}*, "
                f"got {content_type or '<empty>'}: {base_url}/{object_key}"
            )

    if issues:
        print("[verify_alpha_media_fixture_surface] FAIL")
        for issue in issues[:50]:
            print(f"  - {issue}")
        if len(issues) > 50:
            print(f"  - ... {len(issues) - 50} more")
        return 1

    print(
        "[verify_alpha_media_fixture_surface] OK "
        f"env={env_name} target={target_name} checked={checked} "
        f"fixtureRefs={len(fixture_refs)} appMockGroupRefs={len(app_mock_group_refs)} "
        f"appChatPrototypeAvatarRefs={len(app_chat_prototype_refs)} "
        f"videoRange={video_checked} avatarBase={base_urls['avatar']} "
        f"imageBase={base_urls['image']} videoBase={base_urls['video']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
