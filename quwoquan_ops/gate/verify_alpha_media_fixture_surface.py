#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
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
from quwoquan_ops.cli.lib.local_target_tls import (
    LocalTargetTlsError,
    resolve_local_target_root_ca,
)


BUNDLE_PATH = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "content-service"
    / "environments"
    / "gamma"
    / "resources"
    / "artifacts"
    / "media"
    / "gamma_curated_media_bundle.json"
)
MEDIA_DELIVERY_MANIFEST_PATH = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "content-service"
    / "resources"
    / "static"
    / "media"
    / "media_delivery_manifest.json"
)
FIXTURE_ROOT = ROOT / "quwoquan_service" / "contracts" / "metadata"
SERVICE_FIXTURE_ROOT = ROOT / "quwoquan_service" / "services"
CHAT_SCENARIO_FIXTURE_PATH = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "chat-service"
    / "tests"
    / "support"
    / "contract_fixtures"
    / "scenarios"
    / "chat_scenarios.json"
)
APP_PROTOTYPE_MOCK_DATA_PATH = (
    ROOT / "quwoquan_app" / "lib" / "core" / "mock" / "prototype_mock_data.dart"
)
MEDIA_AVATAR_LITERAL_RE = re.compile(r"['\"](media/avatar/[^'\"]+)['\"]")
MEDIA_OBJECT_LITERAL_RE = re.compile(
    r"""media/(?:avatar|image|video|background)/[^\s"'`<>\[\](){},]+"""
)
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
    "prod": "prod-sim",
}
MEDIA_PREFIXES = (
    "media/avatar/",
    "media/image/",
    "media/video/",
    "media/background/",
)
TRACKED_TEXT_SUFFIXES = frozenset(
    {
        ".dart",
        ".go",
        ".java",
        ".json",
        ".kt",
        ".kts",
        ".md",
        ".py",
        ".sh",
        ".swift",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)
RETIRED_MEDIA_TREE_PREFIXES = (
    "cold_start/creators/travel_batch_100_v1/",
    "media/avatar/circle/",
    "media/avatar/conversation/",
    "media/avatar/default/",
    "media/avatar/group/",
    "media/avatar/user/",
    "media/avatar/s/conversation/",
    "media/background/user/",
    "media/image/circle/",
    "media/image/post/",
)
REACHABILITY_CHECKED_ARCHIVE_PREFIXES = (
    "media/avatar/s/archived-avatar/",
    "media/background/s/archived-avatar/",
    "media/image/s/archived-image/",
)
MEDIA_FILE_SUFFIXES = frozenset(
    {".gif", ".jpeg", ".jpg", ".json", ".m3u8", ".m4s", ".m4v", ".mov", ".mp4", ".png", ".webp"}
)
OPERATIONAL_REQUIRED_MEDIA_REFS = frozenset(
    {
        "media/avatar/s/default/group/v1/default.png",
        "media/avatar/s/archived-avatar/circle/fixture_circle_coffee_04/v1/avatar.png",
        "media/background/s/archived-avatar/user/fixture_user_current/v1/background.png",
    }
)


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
        "--files-only",
        action="store_true",
        help="只校验媒体引用闭包与本地文件，不启动 HTTPS 探测",
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
    paths.extend(
        sorted(
            SERVICE_FIXTURE_ROOT.glob(
                "*/tests/support/contract_fixtures/**/*.json"
            )
        )
    )
    if CHAT_SCENARIO_FIXTURE_PATH.is_file():
        paths.append(CHAT_SCENARIO_FIXTURE_PATH)
    if BUNDLE_PATH.is_file():
        paths.append(BUNDLE_PATH)
    if MEDIA_DELIVERY_MANIFEST_PATH.is_file():
        paths.append(MEDIA_DELIVERY_MANIFEST_PATH)
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


def _collect_app_prototype_avatar_refs() -> set[str]:
    return _collect_dart_media_avatar_literals(APP_PROTOTYPE_MOCK_DATA_PATH)


def _collect_tracked_media_literal_refs() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    refs: set[str] = set()
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative = Path(raw_path.decode("utf-8", errors="surrogateescape"))
        path = ROOT / relative
        if not path.is_file() or path.is_relative_to(MEDIA_ROOT):
            continue
        if path.suffix.lower() not in TRACKED_TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in MEDIA_OBJECT_LITERAL_RE.finditer(text):
            object_key = urlsplit(match.group(0).rstrip(".;:。；：")).path.lstrip("/")
            if Path(object_key).suffix.lower() in MEDIA_FILE_SUFFIXES:
                refs.add(object_key)
    return refs


def _collect_authoritative_media_refs() -> set[str]:
    fixture_refs, _ = _collect_all_seeded_media_refs()
    refs = set(fixture_refs)
    refs.update(_collect_app_prototype_avatar_refs())
    refs.update(OPERATIONAL_REQUIRED_MEDIA_REFS)
    return refs


def _collect_global_media_refs() -> set[str]:
    refs = _collect_authoritative_media_refs()
    refs.update(_collect_tracked_media_literal_refs())
    return refs


def _legacy_unreferenced_media_paths(
    referenced: set[str] | None = None,
) -> list[Path]:
    referenced = referenced if referenced is not None else _collect_global_media_refs()
    issues: list[Path] = []
    for path in MEDIA_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(MEDIA_ROOT).as_posix()
        if relative.startswith(RETIRED_MEDIA_TREE_PREFIXES):
            issues.append(path)
            continue
        if relative.startswith(REACHABILITY_CHECKED_ARCHIVE_PREFIXES):
            object_key = urlsplit(relative).path.lstrip("/")
            if object_key not in referenced:
                issues.append(path)
    return sorted(issues)


def _expected_content_type_prefix(object_key: str) -> str | None:
    path = urlsplit(object_key).path.lower()
    if path.endswith((".webp", ".png", ".jpg", ".jpeg", ".gif")):
        return "image/"
    if path.endswith(".json"):
        return "application/json"
    if path.endswith((".mp4", ".m4v", ".mov", ".m3u8", ".m4s")):
        return "video/"
    if object_key.startswith(("media/avatar/", "media/image/", "media/background/")):
        return "image/"
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
    return resolve_local_target_root_ca(target_name)


def _base_url_for_object_key(object_key: str, base_urls: dict[str, str]) -> str:
    if object_key.startswith("media/video/"):
        return base_urls["video"]
    if object_key.startswith("media/avatar/"):
        return base_urls["avatar"]
    return base_urls["image"]


def _probe_seeded_media_objects(
    object_keys: list[str],
    *,
    base_urls: dict[str, str],
    cacert: Path,
    resolve_local: bool,
) -> dict[str, tuple[str, str]]:
    """并发探测独立媒体对象，保留每个对象的完整 HTTP/MIME 验证。"""

    def probe(object_key: str) -> tuple[str, str]:
        is_video = _expected_content_type_prefix(object_key) == "video/"
        return _curl_probe(
            f"{_base_url_for_object_key(object_key, base_urls)}/{object_key}",
            cacert=cacert,
            range_probe=is_video,
            resolve_local=resolve_local,
        )

    if not object_keys:
        return {}
    max_workers = min(16, len(object_keys))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            object_key: executor.submit(probe, object_key)
            for object_key in object_keys
        }
        return {
            object_key: futures[object_key].result()
            for object_key in object_keys
        }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    env_name = str(args.env)
    target_name = _resolve_target_name(env_name, str(args.target or ""))
    issues: list[str] = []
    if not BUNDLE_PATH.is_file():
        issues.append(f"media bundle missing: {BUNDLE_PATH}")
    if not FIXTURE_ROOT.is_dir():
        issues.append(f"fixture root missing: {FIXTURE_ROOT}")
    if not CHAT_SCENARIO_FIXTURE_PATH.is_file():
        issues.append(f"chat scenario fixture missing: {CHAT_SCENARIO_FIXTURE_PATH}")
    if not MEDIA_ROOT.is_dir():
        issues.append(f"shared media root missing: {MEDIA_ROOT}")
    legacy_unreferenced_paths: list[Path] = []
    global_media_refs: set[str] = set()
    authoritative_media_refs: set[str] = set()
    if (
        MEDIA_ROOT.is_dir()
        and FIXTURE_ROOT.is_dir()
        and CHAT_SCENARIO_FIXTURE_PATH.is_file()
    ):
        authoritative_media_refs = _collect_authoritative_media_refs()
        global_media_refs = _collect_global_media_refs()
        legacy_unreferenced_paths = _legacy_unreferenced_media_paths(global_media_refs)
        for path in legacy_unreferenced_paths[:50]:
            issues.append(
                "unreferenced legacy media must be retired: "
                f"{path.relative_to(ROOT).as_posix()}"
            )
        if len(legacy_unreferenced_paths) > 50:
            issues.append(
                f"... {len(legacy_unreferenced_paths) - 50} more unreferenced legacy media files"
            )
        for object_key in sorted(authoritative_media_refs):
            source_file = MEDIA_ROOT / urlsplit(object_key).path
            if not source_file.is_file():
                issues.append(f"{object_key} authoritative source file missing: {source_file}")
    if args.files_only:
        if issues:
            print("[verify_alpha_media_fixture_surface] FAIL")
            for issue in issues:
                print(f"  - {issue}")
            return 1
        print(
            "[verify_alpha_media_fixture_surface] OK "
            f"filesOnly=true authoritativeRefs={len(authoritative_media_refs)} "
            f"globalRefs={len(global_media_refs)} "
            f"legacyUnreferenced={len(legacy_unreferenced_paths)}"
        )
        return 0

    base_urls = _resolve_public_bases(env_name, target_name, args)
    local_root_ca: Path | None
    try:
        local_root_ca = _resolve_local_root_ca(target_name, str(args.cacert or ""))
    except LocalTargetTlsError as exc:
        local_root_ca = None
        issues.append(str(exc))
    if local_root_ca is not None and not local_root_ca.is_file():
        issues.append(f"{target_name} local root CA missing: {local_root_ca}")
    for label, base_url in base_urls.items():
        if not base_url.startswith("https://"):
            issues.append(f"{target_name} {label} base URL must be https: {base_url or '<empty>'}")
    if issues:
        print("[verify_alpha_media_fixture_surface] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    assert local_root_ca is not None

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

    app_prototype_refs = _collect_app_prototype_avatar_refs()
    object_keys.update(app_prototype_refs)
    for object_key in app_prototype_refs:
        object_origins.setdefault(object_key, set()).add(
            APP_PROTOTYPE_MOCK_DATA_PATH.relative_to(ROOT).as_posix()
        )

    probe_keys: list[str] = []
    for object_key in sorted(object_keys):
        source_file = MEDIA_ROOT / urlsplit(object_key).path
        if not source_file.is_file():
            origins = ", ".join(sorted(object_origins.get(object_key, set()))[:3])
            suffix = f" referenced by {origins}" if origins else ""
            issues.append(f"{object_key} source file missing: {source_file}{suffix}")
            continue
        checked += 1
        probe_keys.append(object_key)

    probe_results = _probe_seeded_media_objects(
        probe_keys,
        base_urls=base_urls,
        cacert=local_root_ca,
        resolve_local=target_name in DEFAULT_TARGET_BY_ENV.values(),
    )
    for object_key in probe_keys:
        is_video = _expected_content_type_prefix(object_key) == "video/"
        status, content_type = probe_results[object_key]
        base_url = _base_url_for_object_key(object_key, base_urls)
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
        f"fixtureRefs={len(fixture_refs)} "
        f"chatScenarioRefs={len(_collect_media_refs_from_json(CHAT_SCENARIO_FIXTURE_PATH))} "
        f"appPrototypeAvatarRefs={len(app_prototype_refs)} "
        f"videoRange={video_checked} avatarBase={base_urls['avatar']} "
        f"imageBase={base_urls['image']} videoBase={base_urls['video']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
