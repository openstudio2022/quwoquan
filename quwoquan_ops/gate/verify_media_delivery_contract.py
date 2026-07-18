#!/usr/bin/env python3
"""阻断媒体 URL 环境分支、路径替换与跨环境交付漂移。"""

from __future__ import annotations

import ipaddress
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import ENVIRONMENTS, load_environment_topology
from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.media_delivery_manifest import (
    build_media_delivery_url,
    load_media_delivery_manifest,
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
CURATED_BUNDLE = ROOT / "quwoquan_ops" / "environments" / "gamma_curated_media_bundle.json"
# CAS object paths may still appear in seed/creator docs as non-public references.
# Public fixture media fields are validated separately via FIXTURE_MEDIA_FIELD_FORBIDDEN.
FORBIDDEN_TOKENS = (
    "media/video/s/mock/",
    "mock/example",
    "beta-sample.mp4",
    "_rewriteArchivedSeed",
    "_archivedSeed",
)
FIXTURE_MEDIA_FIELD_FORBIDDEN = (
    "quwoquan-env.test",
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
MOCK_SEED_PATH_RE = re.compile(r"media/[^/]+/s/mock/seed/")
DART_STRING_RE = re.compile(r"""(['"])((?:media/|https?://|//)[^'"]+)\1""")
TEXT_SUFFIXES = {".dart", ".py", ".sh", ".json", ".yaml", ".yml"}
SCAN_ROOTS = (
    ROOT / "quwoquan_app" / "lib",
    ROOT / "quwoquan_app" / "scripts",
    ROOT / "quwoquan_ops",
    ROOT / "quwoquan_service" / "contracts" / "metadata",
    ROOT / "quwoquan_service" / "services" / "seed-box",
)
SKIP_PATHS = {
    Path(__file__).resolve(),
    ROOT
    / "quwoquan_app"
    / "packages"
    / "quwoquan_cloud_mock"
    / "lib"
    / "src"
    / "generated"
    / "alpha_fixture_bundle.g.dart",
    ROOT
    / "quwoquan_app"
    / "lib"
    / "cloud"
    / "services"
    / "content"
    / "mock"
    / "generated"
    / "home_showcase_core_fixture.g.dart",
}
METADATA_ROOT = ROOT / "quwoquan_service" / "contracts" / "metadata"
APP_RUNTIME_CONFIG_DIR = ROOT / "quwoquan_app" / "configs"
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

    if text.startswith("media/") and field_key in FEED_RELATIVE_MEDIA_FIELDS:
        in_manifest = text in manifest_keys
        canonical_public = bool(PUBLIC_SLICE_PREFIX_RE.match(text)) and "mock/seed" not in text
        if not in_manifest and not canonical_public:
            _add("Feed 相对媒体引用必须属于 manifest publicSliceKey 或合法 public slice path")
        if force_mock_seed_ban and not in_manifest and text.startswith("media/"):
            # content_mock_data 强制 Feed 引用收敛到 manifest
            if field_key in {"coverUrl", "thumbnailUrl", "videoUrl", "imageUrls", "avatarUrl", "authorAvatarUrl", "authorBackgroundUrl", "backgroundUrl"}:
                if text not in manifest_keys:
                    _add("content_mock_data Feed 媒体引用必须属于 manifest publicSliceKey")


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
        for key, value in node.items():
            key_name = str(key)
            if key_name in MEDIA_FIELD_KEYS:
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
                        if isinstance(item, str):
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
    paths = sorted(METADATA_ROOT.glob("**/test_fixtures/**/*.json"))
    paths.append(
        ROOT
        / "quwoquan_app"
        / "lib"
        / "cloud"
        / "services"
        / "content"
        / "mock"
        / "content_mock_data.dart"
    )
    return paths


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
        force_mock_seed_ban = path.name == "content_mock_data.dart"
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
    assets = load_media_delivery_manifest()
    path_query_by_asset: dict[str, tuple[str, str]] = {}
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
        for asset in assets:
            try:
                url = build_media_delivery_url(public_bases, asset)
            except ValueError as exc:
                issues.append(f"{env_name}.{asset['logicalAssetId']}: {exc}")
                continue
            parsed = urlsplit(url)
            identity = str(asset["logicalAssetId"])
            current = (parsed.path, parsed.query)
            previous = path_query_by_asset.setdefault(identity, current)
            if current != previous:
                issues.append(
                    f"{identity}: {env_name} path/query 漂移，"
                    f"expected {previous}, got {current}"
                )


def _validate_playback_canary_topology(issues: list[str]) -> None:
    topology = load_environment_topology()
    targets = topology.get("targets")
    if not isinstance(targets, dict):
        issues.append("environment topology 缺少 targets")
        return
    for target_name in ("alpha-local", "beta-local", "gamma-local"):
        target = targets.get(target_name)
        playback_canary = target.get("playbackCanary") if isinstance(target, dict) else None
        work_id = (
            str(playback_canary.get("workId") or "").strip()
            if isinstance(playback_canary, dict)
            else ""
        )
        if not work_id:
            issues.append(f"{target_name}: 必须配置本地播放 canary workId")
    for target_name in ("prod-sim", "prod-hosted"):
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


def _validate_manifest_sources(issues: list[str]) -> None:
    assets = load_media_delivery_manifest()
    try:
        curated = json.loads(CURATED_BUNDLE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(f"无法读取 curated media bundle: {exc}")
        return
    bundle_by_key = {
        str(item.get("objectKey") or "").strip(): item
        for item in curated.get("mediaObjects", [])
        if isinstance(item, dict)
    }
    for asset in assets:
        key = str(asset["publicSliceKey"])
        local_path = MEDIA_ROOT / key
        if not local_path.is_file():
            issues.append(f"{key}: manifest 引用的本地媒体不存在")
        bundle_item = bundle_by_key.get(key)
        if bundle_item is None:
            issues.append(f"{key}: curated bundle 未登记 manifest 资产")
            continue
        if str(bundle_item.get("sourceHash") or "").lower() != str(asset["sha256"]).lower():
            issues.append(f"{key}: curated bundle sha256 与 manifest 不一致")
        if str(bundle_item.get("mimeType") or "").lower() != str(asset["mimeType"]).lower():
            issues.append(f"{key}: curated bundle MIME 与 manifest 不一致")


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
        / "components"
        / "media"
        / "video"
        / "player"
        / "video_player_widget.dart"
    )
    text = player.read_text(encoding="utf-8")
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
        / "core"
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


def _validate_runtime_config_authority_parity(issues: list[str]) -> None:
    topology = load_environment_topology()
    for env_name in ENVIRONMENTS:
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
        for runtime_field, (topology_field, define_key) in APP_RUNTIME_CONFIG_MEDIA_FIELDS.items():
            actual = str(runtime.get(runtime_field) or "").rstrip("/")
            expected = str(expected_bases.get(topology_field) or "").rstrip("/")
            if actual != expected:
                issues.append(
                    f"{config_path.relative_to(ROOT)}: {runtime_field}={actual or '<empty>'} "
                    f"必须与 topology {env_name}.{topology_field}={expected or '<empty>'} 一致"
                )
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(APP_RUNTIME_DEFINE_SCRIPT),
                    "--env",
                    env_name,
                    "--format",
                    "json",
                ],
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
        for runtime_field, (_, define_key) in APP_RUNTIME_CONFIG_MEDIA_FIELDS.items():
            if str(defines.get(define_key) or "").rstrip("/") != str(
                runtime.get(runtime_field) or ""
            ).rstrip("/"):
                issues.append(
                    f"{env_name}: Dart define {define_key} 未与 {runtime_field} 保持一致"
                )

    runtime_config_source = (
        ROOT / "quwoquan_app" / "lib" / "cloud" / "runtime" / "cloud_runtime_config.dart"
    ).read_text(encoding="utf-8")
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
        / "start_app_instance.sh"
    ).read_text(encoding="utf-8")
    for source_path, source in (
        ("run_environment_patrol_smoke.py", patrol_source),
        ("start_app_instance.sh", app_instance_source),
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
        "test/user_acceptance/patrol/environment/"
        "video_playback_canary__user_acceptance_test.dart"
    )
    patrol_runner_path = (
        ROOT / "quwoquan_ops" / "cli" / "smoke" / "run_environment_patrol_smoke.py"
    )
    beta_gateway_path = (
        ROOT
        / "quwoquan_ops"
        / "tests"
        / "acceptance"
        / "user_acceptance"
        / "service_ops"
        / "assistant-service"
        / "smoke"
        / "dev_assistant_beta_gateway.py"
    )
    stackctl_path = ROOT / "quwoquan_ops" / "cli" / "stackctl.py"
    patrol_test_path = ROOT / "quwoquan_app" / target
    patrol_runner_source = patrol_runner_path.read_text(encoding="utf-8")
    stackctl_source = stackctl_path.read_text(encoding="utf-8")
    beta_gateway_source = beta_gateway_path.read_text(encoding="utf-8")

    if "video_playback_canary__user_acceptance_test.dart" not in patrol_runner_source:
        issues.append("环境 Patrol 默认 target 必须是 video playback canary")
    if target not in stackctl_source:
        issues.append("stackctl T4 环境 smoke 必须执行 video playback canary")
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
    for forbidden in ("_rewrite_media_urls", "_join_media_base"):
        if forbidden in beta_gateway_source:
            issues.append(
                "beta fixture gateway 不得按环境 authority 重写 publicSliceKey: "
                f"{forbidden}"
            )


def _validate_avatar_media_patrol_contract(issues: list[str]) -> None:
    target = (
        ROOT
        / "quwoquan_app"
        / "test"
        / "user_acceptance"
        / "patrol"
        / "environment"
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


def _validate_local_simulator_tls_preflight(issues: list[str]) -> None:
    """本地 iOS Simulator 的根证书失败必须在播放器启动前阻断。"""

    alpha_stack_path = ROOT / "quwoquan_ops" / "cli" / "alpha" / "start_alpha_mock_stack.sh"
    alpha_prepare_path = (
        ROOT / "quwoquan_app" / "scripts" / "ios" / "prepare_alpha_local_https.sh"
    )
    app_instance_path = (
        ROOT / "quwoquan_app" / "scripts" / "device" / "start_app_instance.sh"
    )
    patrol_path = (
        ROOT / "quwoquan_ops" / "cli" / "smoke" / "run_environment_patrol_smoke.py"
    )
    alpha_stack = alpha_stack_path.read_text(encoding="utf-8")
    alpha_prepare = alpha_prepare_path.read_text(encoding="utf-8")
    app_instance = app_instance_path.read_text(encoding="utf-8")
    patrol = patrol_path.read_text(encoding="utf-8")

    for target_name in ("alpha-local", "beta-local", "gamma-local", "prod-sim"):
        if target_name not in patrol:
            issues.append(f"Patrol TLS preflight 缺少本地 target: {target_name}")
    if "best_effort_failed" in patrol:
        issues.append("Patrol TLS preflight 不得将 Simulator CA 安装失败降级为 best_effort")
    for token in (
        "install_ios_simulator_root_ca",
        "LocalTargetTlsError",
        "preflightFailed",
    ):
        if token not in patrol:
            issues.append(f"Patrol TLS preflight 缺少 fail-closed 证据: {token}")

    for token in (
        "QWQ_IOS_SIMULATOR_CA_REQUIRED",
        "GATE_BLOCK: iOS Simulator root-CA installation requires an explicit UDID",
        "install-ios-simulator-ca",
    ):
        if token not in alpha_stack:
            issues.append(f"alpha stack 缺少 Simulator CA fail-fast 合同: {token}")
    for token in (
        "QWQ_IOS_SIMULATOR_CA_REQUIRED=1",
        "TARGET_DEVICE_IDENTIFIER",
        "GATE_BLOCK: Simulator CA trust needs",
    ):
        if token not in alpha_prepare:
            issues.append(f"alpha iOS prepare 缺少 Simulator UDID 阻断: {token}")
    for token in (
        "is-ios-simulator",
        "install-ios-simulator-ca",
        "QWQ_IOS_SIMULATOR_UDID",
    ):
        if token not in app_instance:
            issues.append(f"共享 App launcher 缺少 Simulator CA preflight: {token}")


def main() -> int:
    issues: list[str] = []
    _validate_topology_urls(issues)
    _validate_playback_canary_topology(issues)
    _validate_manifest_sources(issues)
    _scan_forbidden_paths(issues)
    _validate_fixture_media_fields(issues)
    _validate_consumer_boundary(issues)
    _validate_runtime_config_authority_parity(issues)
    _validate_video_playback_patrol_contract(issues)
    _validate_avatar_media_patrol_contract(issues)
    _validate_local_simulator_tls_preflight(issues)
    if issues:
        print("[verify_media_delivery_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_media_delivery_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
