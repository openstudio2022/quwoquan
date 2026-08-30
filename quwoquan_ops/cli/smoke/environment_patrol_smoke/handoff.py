"""test-live launcher handoff 的 canonical 构建、投影与 provider runtime 身份校验。

正文自 run_environment_patrol_smoke.py 逐字搬入。
"""
from __future__ import annotations

import argparse
import atexit
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from quwoquan_app.scripts.device.verify_flutter_run_defines import (
    RUNTIME_VALUE_DEFINE_KEYS,
)
from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.generated.app_launch_contract import (
    APP_EFFECTIVE_LAUNCH_MANIFEST_REQUIRED_FIELDS,
    APP_LAUNCHER_HANDOFF_REQUIRED_FIELDS,
    LAUNCH_PROVENANCES,
    RUNTIME_CONFIG_SUPPLY_MODES,
)

# 原入口的历史 import，运行时无调用点；保留在此供测试 patch 断言其不被调用。
from quwoquan_ops.cli.lib.test_live_startup_attempt_receipt import (  # noqa: F401
    load_test_live_startup_attempt,
)

from .constants import (
    APP_DIR,
    APP_LAUNCHER_HANDOFF_BUILDER,
    CANONICAL_DIGEST_PATTERN,
    CANONICAL_TEST_LIVE_DART_DEFINE_KEYS,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_COMMON_FIELDS,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_IMMUTABLE_FIELDS,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_MUTABLE_FIELDS,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_SCHEMA,
)
from .session import (
    _local_target_for_environment_alias,
    _resolved_media_base_urls,
    _runtime_env_for_alias,
)


def _effective_base_urls_for_device(
    args: argparse.Namespace,
    device: dict[str, Any],
) -> dict[str, str]:
    # 本地 target 也必须保留 topology 投影的 canonical public authority。
    # Android/iOS 由 DNS-01 公共证书和本地连接投影到运行栈；把 URL 改成
    # localhost 会破坏证书 hostname 校验，并重新引入已退役的私有 CA 路径。
    del device
    gateway_base_url = args.gateway_base_url.strip()
    product_ops_base_url = args.product_ops_base_url.strip()
    rtc_media_connection_url = args.rtc_media_connection_url.strip()
    media_urls = _resolved_media_base_urls(args)
    target_name = _local_target_for_environment_alias(args.env_name)
    public_bases = get_target(
        load_environment_topology(),
        target_name,
    )["publicBases"]
    supplied_by_role = {
        "api": gateway_base_url,
        "productOps": product_ops_base_url,
        "rtc": rtc_media_connection_url,
        "mediaAvatar": media_urls["mediaAvatarBaseUrl"],
        "mediaImage": media_urls["mediaImageBaseUrl"],
        "mediaVideo": media_urls["mediaVideoBaseUrl"],
        "mediaUpload": media_urls["mediaUploadBaseUrl"],
    }
    mismatched = [
        role
        for role, supplied in supplied_by_role.items()
        if supplied.rstrip("/") != str(public_bases[role]).rstrip("/")
    ]
    if mismatched:
        raise ValueError(
            "runtime URL arguments must equal canonical topology projection: "
            + ", ".join(sorted(mismatched))
        )
    return {
        "gatewayBaseUrl": gateway_base_url,
        "legalBaseUrl": str(public_bases["legal"]),
        "productOpsBaseUrl": product_ops_base_url,
        "rtcMediaConnectionUrl": rtc_media_connection_url,
        **media_urls,
    }


# App 运行面不读的 define，但 Patrol 测试宿主的 kernel 仍需要它们；取值同样只来自
# 签名 runtime package，不另立一份 endpoint 真相源。
_PATROL_HOST_DEFINE_KEYS = {"appDownloadBaseUrl": "APP_DOWNLOAD_BASE_URL"}


def _test_host_dart_defines(handoff: dict[str, Any]) -> dict[str, str]:
    """从签名 runtime package 投影出 Patrol 测试宿主的 endpoint define。

    App 运行时本身不读编译期 define——runtime config 走签名 package 的安装后
    激活——但 ``String.fromEnvironment`` 会冻进 Patrol 的测试 kernel，所以宿主
    必须在编译前拿到该打哪个 endpoint。取值只来自 handoff 携带的签名 package，
    键映射由 ``verify_flutter_run_defines`` 独占，两者都不在此处复制。
    """

    package = handoff.get("runtimeConfigPackage")
    if not isinstance(package, dict):
        raise ValueError("canonical launcher handoff runtime package is invalid")
    values = package.get("runtime")
    if not isinstance(values, dict):
        raise ValueError("canonical launcher handoff runtime values are invalid")
    defines: dict[str, str] = {
        "QWQ_APP_LAUNCH_PROVENANCE": str(
            handoff.get("launchProvenance") or ""
        ),
        "QWQ_RUNTIME_CONFIG_SUPPLY_MODE": str(
            handoff.get("runtimeConfigSupplyMode") or ""
        ),
        "APP_LAUNCH_POLICY": str(handoff.get("launchPolicy") or ""),
    }
    projected = {**RUNTIME_VALUE_DEFINE_KEYS, **_PATROL_HOST_DEFINE_KEYS}
    for value_key, define_key in projected.items():
        value = values.get(value_key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"canonical launcher handoff runtime value is missing: {value_key}"
            )
        defines[define_key] = value
    absent = sorted(key for key, value in defines.items() if not value)
    if absent:
        raise ValueError(
            "canonical launcher handoff Dart defines are invalid: " + ", ".join(absent)
        )
    return defines


def _canonical_handoff_projection(
    handoff: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    """Project one already-validated launcher handoff to Dart and native build."""

    if handoff.get("schema") != "app-launcher-handoff":
        raise ValueError("canonical launcher handoff schema is invalid")
    handoff_field_drift = sorted(
        set(APP_LAUNCHER_HANDOFF_REQUIRED_FIELDS) ^ handoff.keys()
    )
    if handoff_field_drift:
        raise ValueError(
            "canonical launcher handoff fields do not match generated contract: "
            + ", ".join(handoff_field_drift)
        )
    effective = handoff.get("effectiveLaunchManifest")
    if not isinstance(effective, dict) or effective.get("schema") != (
        "app-effective-launch-manifest"
    ):
        raise ValueError("canonical effective launch manifest is invalid")
    effective_field_drift = sorted(
        set(APP_EFFECTIVE_LAUNCH_MANIFEST_REQUIRED_FIELDS) ^ effective.keys()
    )
    if effective_field_drift:
        raise ValueError(
            "canonical effective launch manifest fields do not match generated contract: "
            + ", ".join(effective_field_drift)
        )
    for field, value in effective.items():
        if field != "schema" and handoff.get(field) != value:
            raise ValueError(
                "canonical launcher handoff/effective manifest mismatch: "
                f"{field}"
            )
    launch_provenance = str(handoff.get("launchProvenance") or "")
    if launch_provenance not in LAUNCH_PROVENANCES:
        raise ValueError("canonical launcher handoff launchProvenance is invalid")
    runtime_config_supply_mode = str(
        handoff.get("runtimeConfigSupplyMode") or ""
    )
    if runtime_config_supply_mode not in RUNTIME_CONFIG_SUPPLY_MODES:
        raise ValueError(
            "canonical launcher handoff runtimeConfigSupplyMode is invalid"
        )
    for field in (
        "runtimeConfigPackageDigest",
        "runtimeConfigTrustEnvelopeDigest",
        "effectiveLaunchManifestDigest",
    ):
        if CANONICAL_DIGEST_PATTERN.fullmatch(str(handoff.get(field) or "")) is None:
            raise ValueError(f"canonical launcher handoff {field} is invalid")
    defines = _test_host_dart_defines(handoff)
    missing_defines = sorted(CANONICAL_TEST_LIVE_DART_DEFINE_KEYS - defines.keys())
    if missing_defines:
        raise ValueError(
            "canonical launcher handoff Dart defines are incomplete: "
            + ", ".join(missing_defines)
        )
    build_environment = {
        "QWQ_APP_RUNTIME_ENV": str(handoff["environment"]),
        "QWQ_LAUNCH_TARGET": str(handoff["target"]),
        "QWQ_APP_LAUNCH_PROVENANCE": launch_provenance,
        "QWQ_RUNTIME_CONFIG_SUPPLY_MODE": runtime_config_supply_mode,
        "QWQ_APP_LAUNCH_POLICY": str(handoff["launchPolicy"]),
        "QWQ_APP_BUILD_CONTEXT": "runtime",
        "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST": str(
            handoff["runtimeConfigPackageDigest"]
        ),
        "QWQ_EXPECTED_RUNTIME_CONFIG_TRUST_DIGEST": str(
            handoff["runtimeConfigTrustEnvelopeDigest"]
        ),
        "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST": str(
            handoff["effectiveLaunchManifestDigest"]
        ),
        "QWQ_APP_RECOVERY_BASE_URL": defines["CLOUD_GATEWAY_BASE_URL"],
        "QWQ_APP_PUBLIC_WEB_URL": defines["PUBLIC_WEB_BASE_URL"],
        "QWQ_APP_DOWNLOAD_BASE_URL": defines["APP_DOWNLOAD_BASE_URL"],
        "QWQ_LAUNCH_HANDOFF_JSON": json.dumps(
            handoff,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    }
    return defines, build_environment


def _materialized_runtime_config_trust_root() -> Path:
    """在源码树外开一个只放 trust envelope 的 assets 根。

    与 run.sh 的 canonical 启动链同构：宿主原生侧要验签 runtime config package 就必须在
    构建产物里带上 trust envelope，而 target runtime package 不得随构建进入产物——目录里
    因此只允许出现 trust envelope 一个文件，这条判否由两个工程共用的 Gradle 校验脚本执行。
    """

    root = Path(tempfile.mkdtemp(prefix="qwq-patrol-runtime-config."))
    root.chmod(0o700)
    runtime_root = root / "qwq_runtime"
    runtime_root.mkdir()
    runtime_root.chmod(0o700)
    atexit.register(shutil.rmtree, root, True)
    return root


def _canonical_test_live_launcher_handoff(
    args: argparse.Namespace,
    device: dict[str, Any],
    command_env: dict[str, str],
) -> dict[str, Any]:
    """Render one run-bound canonical handoff for both Patrol and Gradle."""

    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    if runtime_env not in {"alpha", "beta", "gamma"}:
        raise ValueError("test_live launcher handoff requires alpha, beta, or gamma")
    target_name = _local_target_for_environment_alias(args.env_name)
    get_target(load_environment_topology(), target_name)
    base_urls = _effective_base_urls_for_device(args, device)
    trust_root = _materialized_runtime_config_trust_root()
    trust_path = trust_root / "qwq_runtime" / "runtime-config-trust.json"
    command = [
        sys.executable,
        str(APP_LAUNCHER_HANDOFF_BUILDER),
        "--runtime-config-trust-output",
        str(trust_path),
        "--env",
        runtime_env,
        "--target",
        target_name,
        "--launch-provenance",
        "canonical_launcher",
        "--launch-policy",
        "test_live",
        "--gateway-base-url",
        base_urls["gatewayBaseUrl"],
        "--legal-base-url",
        base_urls["legalBaseUrl"],
        "--media-avatar-base-url",
        base_urls["mediaAvatarBaseUrl"],
        "--media-image-base-url",
        base_urls["mediaImageBaseUrl"],
        "--media-video-base-url",
        base_urls["mediaVideoBaseUrl"],
        "--media-upload-base-url",
        base_urls["mediaUploadBaseUrl"],
        "--rtc-media-connection-url",
        base_urls["rtcMediaConnectionUrl"],
    ]
    is_android = str(device.get("targetPlatform") or "").lower().startswith(
        "android"
    )
    if is_android:
        transport_values = {
            "reverseExpectedPorts": command_env.get(
                "QWQ_ANDROID_REVERSE_EXPECTED_PORTS", ""
            ),
            "reverseActualPorts": command_env.get(
                "QWQ_ANDROID_REVERSE_ACTUAL_PORTS", ""
            ),
            "reverseReceiptDigest": command_env.get(
                "QWQ_ANDROID_REVERSE_RECEIPT_DIGEST", ""
            ),
            "consumerLeaseId": command_env.get("QWQ_CONSUMER_LEASE_ID", ""),
        }
        missing_transport = sorted(
            key for key, value in transport_values.items() if not value
        )
        if missing_transport:
            raise ValueError(
                "Android test_live launcher transport is incomplete: "
                + ", ".join(missing_transport)
            )
        command.extend(
            (
                "--transport-required",
                "--reverse-expected-ports",
                transport_values["reverseExpectedPorts"],
                "--reverse-actual-ports",
                transport_values["reverseActualPorts"],
                "--reverse-receipt-digest",
                transport_values["reverseReceiptDigest"],
                "--consumer-lease-id",
                transport_values["consumerLeaseId"],
            )
        )
    try:
        result = subprocess.run(
            command,
            cwd=APP_DIR,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"canonical test_live launcher handoff failed: {exc}") from exc
    if result.returncode != 0:
        raise ValueError(
            result.stderr.strip()
            or result.stdout.strip()
            or "canonical test_live launcher handoff failed"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"canonical test_live launcher handoff is not JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("canonical test_live launcher handoff must be an object")
    _canonical_handoff_projection(payload)
    expected_identity = {
        "environment": runtime_env,
        "target": target_name,
        "launchProvenance": "canonical_launcher",
        "runtimeConfigSupplyMode": RUNTIME_CONFIG_SUPPLY_MODES[0],
        "launchPolicy": "test_live",
    }
    mismatched = sorted(
        field
        for field, value in expected_identity.items()
        if payload.get(field) != value
    )
    if mismatched:
        raise ValueError(
            "canonical test_live launcher handoff identity mismatch: "
            + ", ".join(mismatched)
        )
    expected_runtime_defines = {
        "APP_LEGAL_BASE_URL": base_urls["legalBaseUrl"],
        "MEDIA_AVATAR_CDN_BASE_URL": base_urls["mediaAvatarBaseUrl"],
        "MEDIA_IMAGE_CDN_BASE_URL": base_urls["mediaImageBaseUrl"],
        "MEDIA_VIDEO_CDN_BASE_URL": base_urls["mediaVideoBaseUrl"],
        "MEDIA_UPLOAD_BASE_URL": base_urls["mediaUploadBaseUrl"],
        "RTC_MEDIA_CONNECTION_URL": base_urls["rtcMediaConnectionUrl"],
    }
    defines = _test_host_dart_defines(payload)
    mismatched_runtime_defines = sorted(
        key
        for key, value in expected_runtime_defines.items()
        if defines.get(key) != value
    )
    if mismatched_runtime_defines:
        raise ValueError(
            "canonical test_live launcher handoff topology mismatch: "
            + ", ".join(mismatched_runtime_defines)
        )
    if is_android:
        transport = payload["effectiveLaunchManifest"].get("transport")
        if not isinstance(transport, dict) or transport.get("required") is not True:
            raise ValueError("Android test_live launcher transport is not required")
        for field, env_key in (
            ("reverseExpectedPorts", "QWQ_ANDROID_REVERSE_EXPECTED_PORTS"),
            ("reverseActualPorts", "QWQ_ANDROID_REVERSE_ACTUAL_PORTS"),
            ("reverseReceiptDigest", "QWQ_ANDROID_REVERSE_RECEIPT_DIGEST"),
            ("consumerLeaseId", "QWQ_CONSUMER_LEASE_ID"),
        ):
            if transport.get(field) != command_env.get(env_key, ""):
                raise ValueError(
                    f"Android test_live launcher transport mismatch: {field}"
                )
    if not trust_path.is_file() or trust_path.stat().st_size <= 0:
        raise ValueError(
            "canonical test_live launcher handoff did not materialize the trust envelope"
        )
    build_profile = str(payload.get("buildProfile") or "").strip()
    if not build_profile:
        raise ValueError(
            "canonical test_live launcher handoff is missing buildProfile"
        )
    # 宿主构建期的 trust 供给，与 run.sh 对生产 App 的注入同名同义：Android 走 assets 根，
    # iOS 走 bundle 资源复制。buildProfile 必须一并交出，否则 Gradle 侧无法判定 envelope
    # 是否属于当前构建产物。
    command_env["QWQ_APP_BUILD_PROFILE"] = build_profile
    command_env["QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT"] = str(trust_root)
    command_env["QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH"] = str(trust_path)
    return payload


def _validated_provider_patrol_runtime_identity(
    args: argparse.Namespace,
    command_env: dict[str, str],
) -> dict[str, Any] | None:
    """Freeze the stackctl-selected Provider rail before runtime side effects.

    Generic environment Patrol has no Provider runtime identity and retains its
    existing test_live launcher behavior. Provider Patrol must carry both the
    bounded identity envelope and the same explicit CLI mode.
    """

    explicit_runtime_mode = str(
        getattr(args, "runtime_mode", "") or ""
    ).strip()
    raw_identity = command_env.get(
        PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV,
        "",
    ).strip()
    if not raw_identity:
        if explicit_runtime_mode:
            raise ValueError(
                "Provider Patrol runtime identity handoff is required"
            )
        return None
    try:
        identity = json.loads(raw_identity)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Provider Patrol runtime identity handoff is invalid"
        ) from exc
    if not isinstance(identity, dict):
        raise ValueError("Provider Patrol runtime identity handoff must be an object")
    runtime_mode = str(identity.get("runtimeMode") or "").strip()
    mode_fields = (
        PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_IMMUTABLE_FIELDS
        if runtime_mode == "immutable_candidate"
        else PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_MUTABLE_FIELDS
        if runtime_mode == "test_live"
        else frozenset()
    )
    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    target_name = _local_target_for_environment_alias(args.env_name)
    candidate_field = (
        "candidateDigest"
        if runtime_mode == "immutable_candidate"
        else "mutableComposeDigest"
    )
    selected_candidate = str(identity.get(candidate_field) or "").strip()
    expected_candidate = str(
        getattr(args, "candidate_digest", "") or ""
    ).strip()
    digest_fields = {"providerRuntimeDigest", candidate_field}
    if runtime_mode == "test_live":
        digest_fields.update(
            {
                "mutableConfigurationDigest",
                "mutableStateDigest",
                "mutableWorkspaceStatusDigest",
                "mutableResolverHandoffDigest",
            }
        )
    if (
        not mode_fields
        or explicit_runtime_mode != runtime_mode
        or set(identity)
        != PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_COMMON_FIELDS | mode_fields
        or identity.get("schema")
        != PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_SCHEMA
        or identity.get("environment") != runtime_env
        or identity.get("target") != target_name
        or identity.get("workload") != "full"
        or identity.get("failureFree") is not True
        or identity.get("nonPromotable") is not (runtime_mode == "test_live")
        or not str(identity.get("startupAttemptId") or "").strip()
        or not expected_candidate
        or selected_candidate != expected_candidate
        or any(
            CANONICAL_DIGEST_PATTERN.fullmatch(
                str(identity.get(field) or "")
            )
            is None
            for field in digest_fields
        )
        or (
            runtime_mode == "test_live"
            and re.fullmatch(
                r"[0-9a-f]{40}",
                str(identity.get("mutableSourceRevision") or ""),
            )
            is None
        )
    ):
        raise ValueError(
            "Provider Patrol runtime identity handoff does not match execution"
        )
    return identity


def _provider_patrol_launcher_handoff(
    args: argparse.Namespace,
    device: dict[str, Any],
    command_env: dict[str, str],
    *,
    runtime_identity: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build only the canonical launcher rail frozen before side effects."""

    if runtime_identity is not None:
        # runtimeMode 只影响服务端 runtime 身份证据；launcher handoff 不再携带
        # 内容绑定，因此两种模式共用同一 canonical handoff。
        _ = runtime_identity["runtimeMode"]
    return _canonical_test_live_launcher_handoff(args, device, command_env)


def _apply_launcher_handoff_to_command_env(
    command_env: dict[str, str],
    handoff: dict[str, Any],
) -> None:
    _, projection = _canonical_handoff_projection(handoff)
    # 内容激活是运行时服务端事实；编译期 dart-define 摘要已随 executor cutover
    # 退役。两类遗留注入都必须清除，否则宿主环境会带着无 owner 的旧摘要继续跑。
    for retired_key in (
        "QWQ_CONTENT_RELEASE_ID",
        "QWQ_CONTENT_MANIFEST_DIGEST",
        "QWQ_CONTENT_READINESS_RECEIPT_DIGEST",
        "QWQ_DART_DEFINES_DIGEST",
    ):
        command_env.pop(retired_key, None)
    command_env.update(projection)
