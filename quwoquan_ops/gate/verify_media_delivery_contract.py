#!/usr/bin/env python3
"""阻断媒体 URL 环境分支、路径替换与跨环境交付漂移。"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import ENVIRONMENTS, load_environment_topology
from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.media_delivery_manifest import load_media_delivery_manifest
from quwoquan_ops.cli.lib.output_paths import DEFAULT_DEPLOY_TARGET_BY_ENV


MEDIA_ROOT = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "_shared"
    / "test_fixtures"
    / "media"
)
# CAS object paths may still appear in creator docs as non-public references.
# Public test media fields are validated separately via FIXTURE_MEDIA_FIELD_FORBIDDEN.
FORBIDDEN_TOKENS = (
    "media/video/s/mock/",
    "mock/example",
    "beta-sample.mp4",
    "_rewriteArchivedSeed",
    "_archivedSeed",
)
FIXTURE_MEDIA_FIELD_FORBIDDEN = (
    ".test",
    "118.31.239.122",
    ":17100",
    ":18100",
    ":19100",
    ":19130",
    "http://",
    "media/objects/sha256/",
)
MEDIA_FIELD_KEYS = frozenset(
    {
        "coverUrl",
        "thumbnailUrl",
        "videoUrl",
        "avatarUrl",
        "authorAvatarUrl",
        "authorBackgroundUrl",
        "mediaDeliveryUrl",
        "imageUrls",
        "mediaUrls",
        "url",
        "backgroundUrl",
    }
)
FEED_RELATIVE_MEDIA_FIELDS = frozenset(
    {
        "coverUrl",
        "thumbnailUrl",
        "videoUrl",
        "imageUrls",
        "mediaUrls",
        "avatarUrl",
        "authorAvatarUrl",
        "authorBackgroundUrl",
        "backgroundUrl",
        "mediaDeliveryUrl",
    }
)
PUBLIC_SLICE_PREFIX_RE = re.compile(
    r"^media/(avatar|image|video|background|attachment)/s/"
)
PUBLIC_SLICE_VERSION_SEGMENT_RE = re.compile(r"^v([1-9][0-9]*)$")
MOCK_SEED_PATH_RE = re.compile(r"media/[^/]+/s/mock/seed/")
DART_STRING_RE = re.compile(r"""(['"])((?:media/|https?://|//)[^'"]+)\1""")
TEXT_SUFFIXES = {".dart", ".py", ".sh", ".json", ".yaml", ".yml"}
SCAN_ROOTS = (
    ROOT / "quwoquan_app" / "lib",
    ROOT / "quwoquan_app" / "scripts",
    ROOT / "quwoquan_ops",
    ROOT / "quwoquan_service" / "contracts" / "metadata",
)
SKIP_PATHS = {
    Path(__file__).resolve(),
}
METADATA_ROOT = ROOT / "quwoquan_service" / "contracts" / "metadata"
APP_RUNTIME_CONFIG_DIR = ROOT / "quwoquan_app" / "configs"
APP_RUNTIME_CONFIG_SOURCE = (
    ROOT / "quwoquan_app" / "lib" / "runtime" / "config" / "cloud_runtime_config.dart"
)
APP_RUNTIME_DEFINE_SCRIPT = (
    ROOT / "quwoquan_app" / "scripts" / "env" / "print_app_env_dart_defines.py"
)
APP_RUNTIME_CONFIG_MEDIA_FIELDS = {
    "mediaAvatarCdnBaseUrl": ("mediaAvatar", "MEDIA_AVATAR_CDN_BASE_URL"),
    "mediaImageCdnBaseUrl": ("mediaImage", "MEDIA_IMAGE_CDN_BASE_URL"),
    "mediaVideoCdnBaseUrl": ("mediaVideo", "MEDIA_VIDEO_CDN_BASE_URL"),
    "mediaUploadBaseUrl": ("mediaUpload", "MEDIA_UPLOAD_BASE_URL"),
}


def _is_ip_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _looks_like_media_ref(value: str) -> bool:
    lowered = value.lower()
    return "media/" in lowered or "http" in lowered or value.startswith("//")


def _public_slice_identity(value: str) -> tuple[str, str, str] | None:
    parsed = urlsplit(value.strip())
    path = parsed.path.lstrip("/")
    if not PUBLIC_SLICE_PREFIX_RE.match(path):
        return None
    return path, parsed.query, parsed.fragment


def _public_slice_version(path: str) -> int | None:
    matches = [
        match
        for segment in Path(path).parts
        if (match := PUBLIC_SLICE_VERSION_SEGMENT_RE.fullmatch(segment)) is not None
    ]
    if len(matches) != 1:
        return None
    return int(matches[0].group(1))


@lru_cache(maxsize=None)
def _fixture_public_slice_sha256(media_root: Path, public_path: str) -> str | None:
    physical = media_root / public_path
    if not physical.is_file():
        return None
    return f"sha256:{hashlib.sha256(physical.read_bytes()).hexdigest()}"


def _has_bare_ip(value: str) -> bool:
    for match in re.finditer(r"(?:https?://)?([^/:\"'\s]+)", value):
        host = match.group(1)
        if _is_ip_host(host):
            return True
    return False


def _validate_media_field_value(
    *,
    rel_path: str,
    field_key: str,
    value: str,
    manifest_keys: set[str],
    force_mock_seed_ban: bool,
    issues: list[str],
    seen: set[str],
) -> None:
    text = value.strip()
    if not text or not _looks_like_media_ref(text):
        return

    def _add(message: str) -> None:
        key = f"{rel_path}|{field_key}|{text}|{message}"
        if key in seen:
            return
        seen.add(key)
        issues.append(f"{rel_path} 媒体字段 {field_key}={text!r}: {message}")

    for token in FIXTURE_MEDIA_FIELD_FORBIDDEN:
        if token in text:
            _add(f"禁止出现 {token}")
    if _has_bare_ip(text):
        _add("禁止出现裸 IP authority")
    if force_mock_seed_ban and MOCK_SEED_PATH_RE.search(text):
        _add("禁止出现 media/*/s/mock/seed/")
    elif "mock/seed" in text:
        _add("禁止出现 mock/seed 媒体路径")

    public_identity = _public_slice_identity(text)
    if public_identity is not None:
        public_path, query, fragment = public_identity
        if query:
            _add("public slice fixture 引用必须 query-free")
        if fragment:
            _add("public slice fixture 引用必须 fragment-free")
        version_segments = [
            segment
            for segment in Path(public_path).parts
            if PUBLIC_SLICE_VERSION_SEGMENT_RE.fullmatch(segment)
        ]
        if len(version_segments) != 1:
            _add("public slice fixture 引用必须恰有一个 /vN/ 路径段")
        elif version_segments[0] != "v1":
            _add("public slice fixture 当前唯一 canonical 版本必须是 /v1/")

    if text.startswith("media/") and field_key in FEED_RELATIVE_MEDIA_FIELDS:
        in_manifest = text in manifest_keys
        canonical_public = bool(PUBLIC_SLICE_PREFIX_RE.match(text)) and "mock/seed" not in text
        if not in_manifest and not canonical_public:
            _add("Feed 相对媒体引用必须属于 manifest publicSliceKey 或合法 public slice path")
def _walk_json_media_fields(
    node: object,
    *,
    rel_path: str,
    field_key: str | None,
    manifest_keys: set[str],
    force_mock_seed_ban: bool,
    issues: list[str],
    seen: set[str],
) -> None:
    if isinstance(node, dict):
        _validate_public_slice_record(
            node,
            rel_path=rel_path,
            issues=issues,
            seen=seen,
        )
        for key, value in node.items():
            key_name = str(key)
            public_slice_value = (
                isinstance(value, str) and _public_slice_identity(value) is not None
            )
            if key_name in MEDIA_FIELD_KEYS or public_slice_value:
                if isinstance(value, str):
                    _validate_media_field_value(
                        rel_path=rel_path,
                        field_key=key_name,
                        value=value,
                        manifest_keys=manifest_keys,
                        force_mock_seed_ban=force_mock_seed_ban,
                        issues=issues,
                        seen=seen,
                    )
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str) and (
                            key_name in MEDIA_FIELD_KEYS
                            or _public_slice_identity(item) is not None
                        ):
                            _validate_media_field_value(
                                rel_path=rel_path,
                                field_key=key_name,
                                value=item,
                                manifest_keys=manifest_keys,
                                force_mock_seed_ban=force_mock_seed_ban,
                                issues=issues,
                                seen=seen,
                            )
                        else:
                            _walk_json_media_fields(
                                item,
                                rel_path=rel_path,
                                field_key=key_name,
                                manifest_keys=manifest_keys,
                                force_mock_seed_ban=force_mock_seed_ban,
                                issues=issues,
                                seen=seen,
                            )
                else:
                    _walk_json_media_fields(
                        value,
                        rel_path=rel_path,
                        field_key=key_name,
                        manifest_keys=manifest_keys,
                        force_mock_seed_ban=force_mock_seed_ban,
                        issues=issues,
                        seen=seen,
                    )
                continue
            _walk_json_media_fields(
                value,
                rel_path=rel_path,
                field_key=field_key,
                manifest_keys=manifest_keys,
                force_mock_seed_ban=force_mock_seed_ban,
                issues=issues,
                seen=seen,
            )
        return
    if isinstance(node, list):
        for item in node:
            _walk_json_media_fields(
                item,
                rel_path=rel_path,
                field_key=field_key,
                manifest_keys=manifest_keys,
                force_mock_seed_ban=force_mock_seed_ban,
                issues=issues,
                seen=seen,
            )
        return
    if isinstance(node, str) and _public_slice_identity(node) is not None:
        _validate_media_field_value(
            rel_path=rel_path,
            field_key=field_key or "<value>",
            value=node,
            manifest_keys=manifest_keys,
            force_mock_seed_ban=force_mock_seed_ban,
            issues=issues,
            seen=seen,
        )


def _validate_public_slice_record(
    node: dict[object, object],
    *,
    rel_path: str,
    issues: list[str],
    seen: set[str],
) -> None:
    for field_key in ("objectKey", "publicSliceKey"):
        raw_value = node.get(field_key)
        if not isinstance(raw_value, str):
            continue
        identity = _public_slice_identity(raw_value)
        if identity is None:
            # Private CAS objectKey is intentionally outside this public fixture gate.
            continue
        public_path, _, _ = identity
        version = _public_slice_version(public_path)
        declared_version = node.get("version")
        if declared_version is not None and version is not None:
            if isinstance(declared_version, bool) or not isinstance(declared_version, int):
                issue = (
                    f"{rel_path} 媒体记录 {field_key}={raw_value!r}: "
                    "version 必须是与 /vN/ 相同的正整数"
                )
                if issue not in seen:
                    seen.add(issue)
                    issues.append(issue)
            elif declared_version != version:
                issue = (
                    f"{rel_path} 媒体记录 {field_key}={raw_value!r}: "
                    f"version={declared_version} 与路径 v{version} 不一致"
                )
                if issue not in seen:
                    seen.add(issue)
                    issues.append(issue)
        source_hash = node.get("sourceHash")
        if not isinstance(source_hash, str) or not source_hash.startswith("sha256:"):
            continue
        actual = _fixture_public_slice_sha256(MEDIA_ROOT, public_path)
        if actual is None:
            issue = f"{rel_path} 媒体记录 {field_key}={raw_value!r}: fixture 实体文件不存在"
        else:
            issue = "" if actual == source_hash.lower() else (
                f"{rel_path} 媒体记录 {field_key}={raw_value!r}: "
                f"sourceHash={source_hash} 与实体摘要 {actual} 不一致"
            )
        if issue and issue not in seen:
            seen.add(issue)
            issues.append(issue)


def _validate_dart_media_literals(
    path: Path,
    *,
    manifest_keys: set[str],
    issues: list[str],
    seen: set[str],
) -> None:
    rel_path = str(path.relative_to(ROOT))
    text = path.read_text(encoding="utf-8")
    if MOCK_SEED_PATH_RE.search(text) or "mock/seed" in text:
        key = f"{rel_path}|mock-seed"
        if key not in seen:
            seen.add(key)
            issues.append(f"{rel_path}: 禁止出现 media/*/s/mock/seed/")
    for match in DART_STRING_RE.finditer(text):
        value = match.group(2)
        # Interpolated Dart strings can be split into adjacent literal fragments;
        # a trailing slash is not a complete media reference. Forbidden mock/seed
        # tokens are still checked against the full source above.
        if value.endswith("/") or "$" in value:
            continue
        field_key = "url"
        if "avatar" in value:
            field_key = "avatarUrl"
        elif "video" in value:
            field_key = "videoUrl"
        elif "cover" in value or "image" in value or "thumbnail" in value:
            field_key = "coverUrl"
        _validate_media_field_value(
            rel_path=rel_path,
            field_key=field_key,
            value=value,
            manifest_keys=manifest_keys,
            force_mock_seed_ban=True,
            issues=issues,
            seen=seen,
        )


def _fixture_media_scan_paths() -> list[Path]:
    # Contract examples remain service-owned. App local_contract media references
    # live in object-level Dart builders/doubles and must be checked as literals.
    paths = set(METADATA_ROOT.glob("**/test_fixtures/**/*.json"))
    paths.update(
        (ROOT / "quwoquan_service" / "services").glob(
            "*/tests/support/contract_fixtures/**/*.json"
        )
    )
    app_support = ROOT / "quwoquan_app" / "test" / "support"
    paths.update(app_support.glob("**/*builder*.dart"))
    paths.update(app_support.glob("**/*typed_double*.dart"))
    return sorted(paths)


def _validate_fixture_public_slice_files(issues: list[str]) -> None:
    versions_by_logical_key: dict[str, set[str]] = {}
    for path in sorted(item for item in MEDIA_ROOT.rglob("*") if item.is_file()):
        key = path.relative_to(MEDIA_ROOT).as_posix()
        if not PUBLIC_SLICE_PREFIX_RE.match(key):
            continue
        if MOCK_SEED_PATH_RE.search(key) or "mock/seed" in key:
            issues.append(f"{key}: public fixture 实体禁止使用 mock/seed 命名空间")
        version_segments = [
            segment
            for segment in Path(key).parts
            if PUBLIC_SLICE_VERSION_SEGMENT_RE.fullmatch(segment)
        ]
        if len(version_segments) != 1:
            issues.append(f"{key}: public fixture 实体必须恰有一个 /vN/ 路径段")
            continue
        version = version_segments[0]
        if version != "v1":
            issues.append(f"{key}: public fixture 当前唯一 canonical 版本必须是 /v1/")
        parts = list(Path(key).parts)
        parts.remove(version)
        logical_key = "/".join(parts)
        versions_by_logical_key.setdefault(logical_key, set()).add(version)
    for logical_key, versions in sorted(versions_by_logical_key.items()):
        if len(versions) > 1:
            issues.append(
                f"{logical_key}: public fixture 同一逻辑资产禁止多版本并存: "
                f"{sorted(versions)}"
            )


def _validate_fixture_media_fields(issues: list[str]) -> None:
    try:
        assets = load_media_delivery_manifest()
    except ValueError as exc:
        issues.append(f"无法加载 media delivery manifest: {exc}")
        return
    manifest_keys = {str(asset["publicSliceKey"]) for asset in assets}
    seen: set[str] = set()
    for path in _fixture_media_scan_paths():
        if not path.is_file():
            issues.append(f"缺少 fixture 媒体扫描文件: {path.relative_to(ROOT)}")
            continue
        rel_path = str(path.relative_to(ROOT))
        force_mock_seed_ban = path.suffix == ".dart"
        if path.suffix == ".dart":
            _validate_dart_media_literals(
                path,
                manifest_keys=manifest_keys,
                issues=issues,
                seen=seen,
            )
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"{rel_path}: 无法解析 JSON: {exc}")
            continue
        _walk_json_media_fields(
            document,
            rel_path=rel_path,
            field_key=None,
            manifest_keys=manifest_keys,
            force_mock_seed_ban=force_mock_seed_ban,
            issues=issues,
            seen=seen,
        )


def _validate_topology_urls(issues: list[str]) -> None:
    topology = load_environment_topology()
    for env_name in ENVIRONMENTS:
        environment = topology["environments"][env_name]
        public_bases = environment.get("publicBases") or {}
        for key in ("mediaAvatar", "mediaImage", "mediaVideo", "mediaUpload"):
            raw = str(public_bases.get(key) or "")
            parsed = urlsplit(raw)
            if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
                issues.append(f"{env_name}.{key} 必须是无 query/fragment 的 HTTPS public base")
            if _is_ip_host(parsed.hostname or ""):
                issues.append(f"{env_name}.{key} 不得使用裸 IP authority")
            if env_name == "prod" and "prod" in (parsed.hostname or "").lower():
                issues.append(f"{env_name}.{key} 生产域名不得包含 prod 标记")
def _validate_playback_canary_topology(issues: list[str]) -> None:
    topology = load_environment_topology()
    targets = topology.get("targets")
    if not isinstance(targets, dict):
        issues.append("environment topology 缺少 targets")
        return
    for target_name in ("alpha-local", "beta-local", "gamma-local", "prod-sim", "prod-hosted"):
        target = targets.get(target_name)
        playback_canary = target.get("playbackCanary") if isinstance(target, dict) else None
        if not isinstance(playback_canary, dict):
            issues.append(f"{target_name}: 必须声明 published-release playbackCanary")
            continue
        if str(playback_canary.get("source") or "").strip() != "published-release":
            issues.append(f"{target_name}: playbackCanary 必须来自 published-release")
        for field, expected in (
            ("workIdEnv", "VIDEO_PLAYBACK_CANARY_WORK_ID"),
            ("publicSliceKeyEnv", "VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY"),
        ):
            if str(playback_canary.get(field) or "").strip() != expected:
                issues.append(
                    f"{target_name}: playbackCanary.{field} 必须为 {expected}",
                )


def _validate_test_fixture_manifest_sources(issues: list[str]) -> None:
    assets = load_media_delivery_manifest()
    for asset in assets:
        key = str(asset["publicSliceKey"])
        local_path = MEDIA_ROOT / key
        if not local_path.is_file():
            issues.append(f"{key}: test fixture manifest 引用的本地媒体不存在")
            continue
        digest = hashlib.sha256(local_path.read_bytes()).hexdigest()
        if str(asset["sha256"]).lower() != f"sha256:{digest}":
            issues.append(f"{key}: test fixture media sha256 与 manifest 不一致")


def _scan_forbidden_paths(issues: list[str]) -> None:
    for scan_root in SCAN_ROOTS:
        for path in scan_root.rglob("*"):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES or path in SKIP_PATHS:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for token in FORBIDDEN_TOKENS:
                if token in text:
                    issues.append(
                        f"{path.relative_to(ROOT)} 包含禁止的媒体路径/重写标记: {token}"
                    )


def _validate_consumer_boundary(issues: list[str]) -> None:
    player = (
        ROOT
        / "quwoquan_app"
        / "lib"
        / "service"
        / "content_service"
        / "media"
        / "media_asset"
        / "presentation"
        / "video_player_widget.dart"
    )
    player_api = player.with_name("video_player_widget_api.dart")
    text = player.read_text(encoding="utf-8")
    if player_api.is_file():
        text += "\n" + player_api.read_text(encoding="utf-8")
    if "final String videoUrl;" in text or "videoUrlCandidates" in text:
        issues.append("VideoPlayerWidget 仍接收 raw videoUrl/videoUrlCandidates")
    if "resolveContentVideoUrlCandidates" in text:
        issues.append("VideoPlayerWidget 不得解析业务媒体引用")
    if "final MediaDeliveryReference deliveryReference;" not in text:
        issues.append("VideoPlayerWidget 必须接收 MediaDeliveryReference")

    resolver = (
        ROOT
        / "quwoquan_app"
        / "lib"
        / "runtime"
        / "transport"
        / "media"
        / "content_media_url.dart"
    )
    resolver_text = resolver.read_text(encoding="utf-8")
    prohibited_resolver_symbols = (
        "_localHostBaseCandidates",
        "_rewriteHost",
        "_rewriteArchivedSeedContentPath",
        "_alignCandidatesToConfiguredTransport",
    )
    for symbol in prohibited_resolver_symbols:
        if symbol in resolver_text:
            issues.append(f"content_media_url.dart 重新引入禁止分支: {symbol}")


def _validate_runtime_config_authority_parity(
    issues: list[str],
    environments: tuple[str, ...] = tuple(ENVIRONMENTS),
    *,
    launch_policy: str = "prod_release",
) -> None:
    topology = load_environment_topology()
    for env_name in environments:
        config_path = APP_RUNTIME_CONFIG_DIR / env_name / "app_runtime.yaml"
        if not config_path.is_file():
            issues.append(f"{env_name}: 缺少 App runtime config: {config_path.relative_to(ROOT)}")
            continue
        try:
            document = load_json_yaml(config_path)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{config_path.relative_to(ROOT)}: 无法解析: {exc}")
            continue
        runtime = document.get("runtime") if isinstance(document, dict) else None
        if not isinstance(runtime, dict):
            issues.append(f"{config_path.relative_to(ROOT)}: runtime 必须是对象")
            continue
        expected_bases = (
            (topology.get("environments") or {}).get(env_name, {}).get("publicBases") or {}
        )
        if str(runtime.get("appRuntimeEnv") or "") != env_name:
            issues.append(
                f"{config_path.relative_to(ROOT)}: appRuntimeEnv 必须为 {env_name}"
            )
        for runtime_field in APP_RUNTIME_CONFIG_MEDIA_FIELDS:
            actual = str(runtime.get(runtime_field) or "").rstrip("/")
            if actual:
                issues.append(
                    f"{config_path.relative_to(ROOT)}: {runtime_field} 必须保持空模板，"
                    "公开 URL 只能由 topology resolver 投影"
                )
        define_command = [
            sys.executable,
            str(APP_RUNTIME_DEFINE_SCRIPT),
            "--env",
            env_name,
            "--target",
            DEFAULT_DEPLOY_TARGET_BY_ENV[env_name],
            "--format",
            "json",
            "--launch-policy",
            launch_policy,
        ]
        try:
            result = subprocess.run(
                define_command,
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            issues.append(f"{env_name}: 无法执行 App Dart define 解析器: {exc}")
            continue
        if result.returncode != 0:
            issues.append(
                f"{env_name}: App Dart define 解析失败: "
                f"{(result.stderr or result.stdout).strip()}"
            )
            continue
        try:
            defines = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            issues.append(f"{env_name}: App Dart define 输出不是 JSON: {exc}")
            continue
        for runtime_field, (topology_field, define_key) in APP_RUNTIME_CONFIG_MEDIA_FIELDS.items():
            expected = str(expected_bases.get(topology_field) or "").rstrip("/")
            if str(defines.get(define_key) or "").rstrip("/") != expected:
                issues.append(
                    f"{env_name}: Dart define {define_key} 未与 topology "
                    f"{topology_field} 保持一致"
                )

    runtime_config_source = APP_RUNTIME_CONFIG_SOURCE.read_text(encoding="utf-8")
    for define_key in (
        "CLOUD_GATEWAY_BASE_URL",
        *(define_key for _, define_key in APP_RUNTIME_CONFIG_MEDIA_FIELDS.values()),
    ):
        default_pattern = re.compile(
            rf"'{re.escape(define_key)}'\s*,\s*defaultValue:\s*''",
            re.DOTALL,
        )
        if not default_pattern.search(runtime_config_source):
            issues.append(
                f"cloud_runtime_config.dart: {define_key} 必须无 endpoint 默认值，"
                "由环境 launcher 显式注入"
            )

    patrol_source = (
        ROOT
        / "quwoquan_ops"
        / "cli"
        / "smoke"
        / "run_environment_patrol_smoke.py"
    ).read_text(encoding="utf-8")
    app_instance_source = (
        ROOT
        / "quwoquan_app"
        / "scripts"
        / "device"
        / "run_app_instance.sh"
    ).read_text(encoding="utf-8")
    for source_path, source in (
        ("run_environment_patrol_smoke.py", patrol_source),
        ("run_app_instance.sh", app_instance_source),
    ):
        if "--media-base-url" in source or re.search(r"\bmedia_base_url\b", source):
            issues.append(
                f"{source_path}: 正式 launcher/Patrol 禁止单一 media base fallback"
            )
        for _, define_key in APP_RUNTIME_CONFIG_MEDIA_FIELDS.values():
            if define_key not in source:
                issues.append(f"{source_path}: 缺少显式注入 {define_key} 的路径")


def _validate_video_playback_patrol_contract(issues: list[str]) -> None:
    """防止环境 smoke 退回只验证页面节点出现的通用测试。"""

    target = (
        "test/user_acceptance/journeys/home_video_playback/"
        "video_playback_canary__user_acceptance_test.dart"
    )
    patrol_runner_path = (
        ROOT / "quwoquan_ops" / "cli" / "smoke" / "run_environment_patrol_smoke.py"
    )
    # stackctl 主体已拆分：环境 smoke 的 canary target 由 verify_profiles 域模块承载。
    stackctl_path = ROOT / "quwoquan_ops" / "cli" / "commands" / "verify_profiles.py"
    patrol_test_path = ROOT / "quwoquan_app" / target
    patrol_runner_source = patrol_runner_path.read_text(encoding="utf-8")
    stackctl_source = stackctl_path.read_text(encoding="utf-8")

    if "video_playback_canary__user_acceptance_test.dart" not in patrol_runner_source:
        issues.append("环境 Patrol 默认 target 必须是 video playback canary")
    if target not in stackctl_source:
        issues.append("stackctl runtime-media 环境 smoke 必须执行 video playback canary")
    if not patrol_test_path.is_file():
        issues.append(f"视频播放 Patrol target 缺失: {target}")
        return

    patrol_test_source = patrol_test_path.read_text(encoding="utf-8")
    required_tokens = (
        "VIDEO_PLAYBACK_CANARY_WORK_ID",
        "video-player-ready",
        "video-player-error",
    )
    for token in required_tokens:
        if token not in patrol_test_source:
            issues.append(f"视频播放 Patrol target 缺少必需断言: {token}")


def _validate_avatar_media_patrol_contract(issues: list[str]) -> None:
    target = (
        ROOT
        / "quwoquan_app"
        / "test"
        / "user_acceptance"
        / "journeys"
        / "app_startup"
        / "basic_viability__user_acceptance_test.dart"
    )
    if not target.is_file():
        issues.append(f"头像媒体 Patrol target 缺失: {target.relative_to(ROOT)}")
        return
    source = target.read_text(encoding="utf-8")
    for token in (
        "MEDIA_AVATAR_CANARY_REQUIRED",
        "profile-header-avatar-image",
        "trusted image pipeline",
    ):
        if token not in source:
            issues.append(f"头像媒体 Patrol target 缺少必需断言: {token}")


def _validate_public_ca_tls_boundary(issues: list[str]) -> None:
    """所有 App 可见 HTTPS 必须依赖系统公共 CA，不得注入私有信任根。"""

    forbidden_files = (
        ROOT / "quwoquan_ops" / "cli" / "lib" / "local_target_tls.py",
        ROOT / "quwoquan_app" / "scripts" / "ios" / "prepare_alpha_local_https.sh",
        ROOT
        / "quwoquan_app"
        / "scripts"
        / "ios"
        / "prepare_local_https_trust_bundle.sh",
        ROOT / "quwoquan_app" / "lib" / "core" / "platform" / "local_dev_https_trust.dart",
    )
    for path in forbidden_files:
        if path.exists():
            issues.append(f"私有 CA/本地信任注入入口必须删除: {path.relative_to(ROOT)}")

    scan_paths = (
        ROOT / "quwoquan_app" / "lib",
        ROOT / "quwoquan_app" / "android",
        ROOT / "quwoquan_app" / "ios",
        ROOT / "quwoquan_app" / "scripts",
        ROOT / "quwoquan_ops" / "cli",
    )
    forbidden_tokens = (
        "QWQ_ANDROID_LOCAL_ENV_CA",
        "local_env_debug_root",
        "install-ios-simulator-ca",
        "materialize-app-trust-bundle",
        "badCertificateCallback",
    )
    for scan_root in scan_paths:
        for path in scan_root.rglob("*"):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            source = path.read_text(encoding="utf-8", errors="ignore")
            for token in forbidden_tokens:
                if token in source:
                    issues.append(
                        f"{path.relative_to(ROOT)} 禁止私有 CA/证书绕过符号: {token}"
                    )


def main() -> int:
    parser = argparse.ArgumentParser()
    environment_mode = parser.add_mutually_exclusive_group()
    environment_mode.add_argument("--env", choices=tuple(ENVIRONMENTS))
    environment_mode.add_argument(
        "--component-environment",
        action="append",
        choices=("alpha", "beta", "gamma"),
        default=[],
        help=(
            "validate a non-production source component against canonical test_live "
            "topology without reading a packaged runtime; repeat for each environment"
        ),
    )
    args = parser.parse_args()
    component_environments = tuple(dict.fromkeys(args.component_environment))
    selected_environments = (
        component_environments
        or ((args.env,) if args.env else tuple(ENVIRONMENTS))
    )
    launch_policy = "test_live" if component_environments else "prod_release"
    issues: list[str] = []
    _validate_topology_urls(issues)
    _validate_playback_canary_topology(issues)
    _validate_fixture_public_slice_files(issues)
    _validate_test_fixture_manifest_sources(issues)
    _scan_forbidden_paths(issues)
    _validate_fixture_media_fields(issues)
    _validate_consumer_boundary(issues)
    _validate_runtime_config_authority_parity(
        issues,
        selected_environments,
        launch_policy=launch_policy,
    )
    _validate_video_playback_patrol_contract(issues)
    _validate_avatar_media_patrol_contract(issues)
    _validate_public_ca_tls_boundary(issues)
    if issues:
        print("[verify_media_delivery_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_media_delivery_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
