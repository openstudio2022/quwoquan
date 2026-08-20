"""Patrol target wrapper 与命令组装：secret define 文件、bundler target、凭据产物清理与 patrol_command。

正文自 run_environment_patrol_smoke.py 逐字搬入。
"""
from __future__ import annotations

import argparse
import atexit
import base64
import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from quwoquan_ops.ci.device_matrix.evidence import sanitize_device_id

from .constants import (
    APP_DIR,
    APP_CONTENT_VIDEO_PAGE_COUNT_ENV,
    CORE_READBACK_TARGET,
    HOME_VIDEO_PLAYBACK_TARGET,
    PATROL_ANDROID_PACKAGE,
    PATROL_HOST_DIR,
    PATROL_IOS_BUNDLE_ID,
    PATROL_TEST_DIRECTORY,
    PROFILE_JOURNEY_TARGET,
    RELEASE_APP_UAT_DEFINES,
)
from .devices import patrol_ios_runtime_argument
from .handoff import (
    _canonical_handoff_projection,
    _effective_base_urls_for_device,
)
from .session import (
    TypedTestDataActor,
    TypedTestDataConversation,
    _is_account_enforcement_target,
    _local_target_for_environment_alias,
    _public_video_canary_session_mode,
    _requires_account_closure,
    _requires_native_video_playback_signals,
    _resolved_owner_id,
    _resolved_persona_id,
    _runtime_anonymous_session_mode,
    _runtime_env_for_alias,
    _uses_persisted_device_session,
    _uses_public_video_canary_anonymous_session,
    _uses_runtime_anonymous_session,
    _validate_account_closure_execution,
)


def _create_patrol_secret_define_file(
    args: argparse.Namespace,
) -> Path:
    fd, raw_path = tempfile.mkstemp(prefix="qwq-patrol-secrets-", suffix=".json")
    path = Path(raw_path)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            definitions = {
                "TEST_AUTH_TOKEN": args.test_auth_token.strip(),
                "TEST_REFRESH_TOKEN": args.test_refresh_token.strip(),
                "APP_CURRENT_OWNER_ID": _resolved_owner_id(args),
                "APP_CURRENT_PERSONA_ID": _resolved_persona_id(args),
                "APP_CURRENT_USER_ID": _resolved_persona_id(args),
            }
            provider_define_keys = tuple(
                key.strip()
                for key in os.environ.get(
                    "QWQ_PROVIDER_UAT_DART_DEFINE_KEYS", ""
                ).split(",")
                if key.strip()
            )
            invalid_provider_keys = [
                key
                for key in provider_define_keys
                if not re.fullmatch(r"QWQ_PROVIDER_UAT_[A-Z0-9_]+", key)
            ]
            if invalid_provider_keys:
                raise ValueError(
                    "Provider UAT Dart define keys must use the "
                    "QWQ_PROVIDER_UAT_* namespace"
                )
            missing_provider_keys = [
                key
                for key in provider_define_keys
                if not os.environ.get(key, "").strip()
            ]
            if missing_provider_keys:
                raise ValueError(
                    "Provider UAT Dart define values are required: "
                    + ", ".join(missing_provider_keys)
                )
            definitions.update(
                {key: os.environ[key].strip() for key in provider_define_keys}
            )
            json.dump(definitions, handle, ensure_ascii=False)
            handle.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _provider_uat_secret_values() -> tuple[str, ...]:
    keys = tuple(
        key.strip()
        for key in os.environ.get(
            "QWQ_PROVIDER_UAT_DART_DEFINE_KEYS", ""
        ).split(",")
        if key.strip()
    )
    values = tuple(
        (key, os.environ.get(key, "").strip())
        for key in keys
        if os.environ.get(key, "").strip()
    )
    return tuple(
        item
        for key, value in values
        for item in (value, f"{key}={value}")
    )


def _patrol_bundler_target(target: str) -> str:
    """Return a valid wrapper-shaped target after validating the real source."""

    normalized = target.strip().replace("\\", "/")
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:/", normalized)
    ):
        raise ValueError("Patrol target must be a repository-relative path")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Patrol target must not contain path traversal")
    root_parts = ("test", "user_acceptance")
    if tuple(parts[: len(root_parts)]) != root_parts:
        raise ValueError("Patrol target must be under test/user_acceptance")
    if not normalized.endswith("_test.dart"):
        raise ValueError("Patrol target must name one canonical Dart test")
    if not (APP_DIR / normalized).is_file():
        raise ValueError("Patrol target does not exist in the App source tree")
    target_digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return (
        f"{PATROL_TEST_DIRECTORY}/"
        f"qwq_environment_smoke_{target_digest}_test.dart"
    )


def _canonical_patrol_uat_targets() -> tuple[tuple[str, str], ...]:
    """Enumerate every canonical UAT and its collision-free host wrapper target."""

    canonical_root = APP_DIR / "test/user_acceptance"
    targets = tuple(
        path.relative_to(APP_DIR).as_posix()
        for path in sorted(canonical_root.rglob("*_test.dart"))
        if path.is_file()
    )
    if not targets:
        raise RuntimeError("No canonical App UAT is available for the Patrol host")
    enumerated = tuple((target, _patrol_bundler_target(target)) for target in targets)
    wrapper_targets = tuple(wrapper_target for _, wrapper_target in enumerated)
    if len(set(wrapper_targets)) != len(wrapper_targets):
        raise RuntimeError("Canonical App UAT wrapper target collision")
    return enumerated


def _create_patrol_target_wrapper(
    target: str,
    *,
    typed_actor: TypedTestDataActor | None = None,
    typed_conversation: TypedTestDataConversation | None = None,
) -> tuple[Path, str, Callable[[], None]]:
    """Securely create one temporary Patrol-shell wrapper for an external UAT."""

    _patrol_bundler_target(target)
    normalized = target.strip().replace("\\", "/")
    wrapper_directory = PATROL_HOST_DIR / PATROL_TEST_DIRECTORY
    if wrapper_directory.is_symlink() or not wrapper_directory.is_dir():
        raise RuntimeError("Patrol test directory is missing or unsafe")
    bundle_path = wrapper_directory / "test_bundle.dart"
    if bundle_path.is_symlink():
        raise RuntimeError("Patrol test bundle path is unsafe")
    bundle_preimage = bundle_path.read_bytes() if bundle_path.is_file() else None
    bundle_mode = (
        bundle_path.stat().st_mode & 0o777
        if bundle_preimage is not None
        else None
    )
    relative_import = os.path.relpath(
        APP_DIR / normalized,
        wrapper_directory,
    ).replace(os.sep, "/")
    if not relative_import.startswith("../"):
        raise RuntimeError("Patrol wrapper target must remain outside its shell directory")
    imports = [f"import '{relative_import}' as canonical_target;"]
    relative_support_import = os.path.relpath(
        APP_DIR / "test/support/runtime/patrol/patrol_test_support.dart",
        wrapper_directory,
    ).replace(os.sep, "/")
    actor_module_path: Path | None = None
    conversation_module_path: Path | None = None
    actor_install = ""
    conversation_install = ""
    if typed_actor is not None or typed_conversation is not None:
        imports = [
            "import 'dart:convert';",
            *imports,
            f"import '{relative_support_import}' "
            "as patrol_support;",
        ]
    if typed_actor is not None:
        actor_descriptor, raw_actor_path = tempfile.mkstemp(
            prefix="qwq_typed_test_data_actor_",
            suffix=".dart",
            dir=wrapper_directory,
            text=True,
        )
        actor_module_path = Path(raw_actor_path)
        actor_constants = {
            "accessToken": typed_actor.access_token,
            "refreshToken": typed_actor.refresh_token,
            "ownerId": typed_actor.owner_id,
            "personaId": typed_actor.persona_id,
        }
        try:
            os.fchmod(actor_descriptor, 0o600)
            with os.fdopen(
                actor_descriptor,
                "w",
                encoding="utf-8",
                closefd=True,
            ) as actor_handle:
                actor_handle.write(
                    "// Ephemeral encoded typed actor; never commit this file.\n"
                )
                for name, value in actor_constants.items():
                    encoded_value = base64.b64encode(value.encode("utf-8")).decode(
                        "ascii"
                    )
                    actor_handle.write(
                        f"const String {name} = '{encoded_value}';\n"
                    )
                actor_handle.flush()
                os.fsync(actor_handle.fileno())
        except BaseException:
            try:
                os.close(actor_descriptor)
            except OSError:
                pass
            actor_module_path.unlink(missing_ok=True)
            raise
        imports.insert(-1, f"import '{actor_module_path.name}' as typed_actor;")
        actor_install = (
            "  patrol_support.installPatrolAcceptanceSessionForRunner(\n"
            "    accessToken: decode(typed_actor.accessToken),\n"
            "    refreshToken: decode(typed_actor.refreshToken),\n"
            "    ownerId: decode(typed_actor.ownerId),\n"
            "    personaId: decode(typed_actor.personaId),\n"
            "  );\n"
        )
    if typed_conversation is not None:
        conversation_descriptor, raw_conversation_path = tempfile.mkstemp(
            prefix="qwq_typed_test_data_conversation_",
            suffix=".dart",
            dir=wrapper_directory,
            text=True,
        )
        conversation_module_path = Path(raw_conversation_path)
        conversation_constants = {
            "conversationId": typed_conversation.conversation_id,
            "messageIdsJson": json.dumps(
                list(typed_conversation.message_ids),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
        try:
            os.fchmod(conversation_descriptor, 0o600)
            with os.fdopen(
                conversation_descriptor,
                "w",
                encoding="utf-8",
                closefd=True,
            ) as conversation_handle:
                conversation_handle.write(
                    "// Ephemeral encoded typed conversation; never commit this file.\n"
                )
                for name, value in conversation_constants.items():
                    encoded_value = base64.b64encode(value.encode("utf-8")).decode(
                        "ascii"
                    )
                    conversation_handle.write(
                        f"const String {name} = '{encoded_value}';\n"
                    )
                conversation_handle.flush()
                os.fsync(conversation_handle.fileno())
        except BaseException:
            try:
                os.close(conversation_descriptor)
            except OSError:
                pass
            conversation_module_path.unlink(missing_ok=True)
            if actor_module_path is not None:
                actor_module_path.unlink(missing_ok=True)
            raise
        imports.insert(
            -1,
            f"import '{conversation_module_path.name}' as typed_conversation;",
        )
        conversation_install = (
            "  patrol_support.installPatrolTestDataConversationForRunner(\n"
            "    conversationId: decode(typed_conversation.conversationId),\n"
            "    initialMessageIds: (jsonDecode(\n"
            "      decode(typed_conversation.messageIdsJson),\n"
            "    ) as List<dynamic>).cast<String>(),\n"
            "  );\n"
        )
    descriptor, raw_path = tempfile.mkstemp(
        prefix="qwq_environment_smoke_",
        suffix="_test.dart",
        dir=wrapper_directory,
        text=True,
    )
    wrapper_path = Path(raw_path)
    wrapper_target = wrapper_path.relative_to(PATROL_HOST_DIR).as_posix()
    if re.fullmatch(
        r"qwq_environment_smoke_[A-Za-z0-9_]+_test\.dart",
        wrapper_path.name,
    ) is None:
        os.close(descriptor)
        wrapper_path.unlink(missing_ok=True)
        raise RuntimeError("Patrol wrapper filename cannot form a Dart identifier")
    encoded = (
        "// Ephemeral runner-owned Patrol wrapper; never commit this file.\n"
        + "\n".join(imports)
        + "\n\nvoid main() {\n"
        + (
            "  String decode(String value) => "
            "utf8.decode(base64.decode(value));\n"
            if typed_actor is not None or typed_conversation is not None
            else ""
        )
        + actor_install
        + conversation_install
        + "  canonical_target.main();\n}\n"
    ).encode("utf-8")
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        wrapper_path.unlink(missing_ok=True)
        if actor_module_path is not None:
            actor_module_path.unlink(missing_ok=True)
        if conversation_module_path is not None:
            conversation_module_path.unlink(missing_ok=True)
        raise

    def cleanup() -> None:
        wrapper_path.unlink(missing_ok=True)
        if actor_module_path is not None:
            actor_module_path.unlink(missing_ok=True)
        if conversation_module_path is not None:
            conversation_module_path.unlink(missing_ok=True)
        if bundle_path.is_symlink():
            bundle_path.unlink()
        if bundle_preimage is None:
            bundle_path.unlink(missing_ok=True)
            return
        descriptor, raw_restore_path = tempfile.mkstemp(
            prefix=".qwq_patrol_bundle_restore_",
            suffix=".dart",
            dir=wrapper_directory,
        )
        restore_path = Path(raw_restore_path)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(bundle_preimage)
                handle.flush()
                os.fsync(handle.fileno())
            if bundle_mode is not None:
                restore_path.chmod(bundle_mode)
            os.replace(restore_path, bundle_path)
        finally:
            restore_path.unlink(missing_ok=True)

    atexit.register(cleanup)
    return wrapper_path, wrapper_target, cleanup


def _cleanup_patrol_target_wrapper(cleanup: Callable[[], None] | None) -> None:
    if cleanup is None:
        return
    try:
        cleanup()
    finally:
        atexit.unregister(cleanup)


def _stream_contains_any(
    handle: Any,
    needles: tuple[bytes, ...],
) -> bool:
    overlap = max(len(value) for value in needles) - 1
    tail = b""
    while True:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            return False
        data = tail + chunk
        if any(value in data for value in needles):
            return True
        tail = data[-overlap:] if overlap else b""


def _generated_artifact_contains_any(
    path: Path,
    needles: tuple[bytes, ...],
) -> bool:
    try:
        with path.open("rb") as handle:
            if _stream_contains_any(handle, needles):
                return True
        if path.suffix.lower() in {".aab", ".apk", ".ipa", ".zip"}:
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    with archive.open(info) as handle:
                        if _stream_contains_any(handle, needles):
                            return True
    except FileNotFoundError:
        return False
    except (EOFError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise RuntimeError(
            "cannot verify a generated Patrol artifact for credential residue"
        ) from exc
    return False


def _generated_patrol_artifact_candidates(root: Path) -> tuple[Path, ...]:
    """Return bounded compiler/package outputs that can retain a test target."""

    candidates: set[Path] = set()
    build_root = root / "build"
    if build_root.is_dir() and not build_root.is_symlink():
        for path in build_root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            relative_parts = path.relative_to(build_root).parts
            if any(part in {"incremental", "zip-cache"} for part in relative_parts):
                continue
            if path.name == "kernel_blob.bin" or path.suffix.lower() in {
                ".aab",
                ".apk",
                ".dill",
                ".ipa",
                ".snapshot",
                ".zip",
            }:
                candidates.add(path)
    flutter_build_root = root / ".dart_tool" / "flutter_build"
    if flutter_build_root.is_dir() and not flutter_build_root.is_symlink():
        for path in flutter_build_root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            if path.name in {"app.dill", "kernel_blob.bin"} or path.suffix.lower() in {
                ".dill",
                ".snapshot",
            }:
                candidates.add(path)
    return tuple(sorted(candidates))


def _purge_typed_actor_credential_artifacts(
    secret_values: tuple[str, ...],
    *,
    app_dir: Path | None = None,
) -> int:
    """Remove only generated files that contain the ephemeral actor session."""

    canonical_values = tuple(
        dict.fromkeys(value.strip() for value in secret_values if value.strip())
    )
    if not canonical_values:
        return 0
    needles = tuple(value.encode("utf-8") for value in canonical_values)
    root = app_dir or PATROL_HOST_DIR
    removed = 0
    for path in _generated_patrol_artifact_candidates(root):
        if _generated_artifact_contains_any(path, needles):
            path.unlink()
            removed += 1
    for path in _generated_patrol_artifact_candidates(root):
        if _generated_artifact_contains_any(path, needles):
            raise RuntimeError(
                "generated Patrol credential artifact cleanup did not converge"
            )
    return removed


def patrol_command(
    device: dict[str, Any],
    args: argparse.Namespace,
    patrol_executable: str,
    *,
    dart_define_file: Path | None,
    launcher_handoff: dict[str, Any] | None = None,
    patrol_target: str | None = None,
    typed_test_data_session_handoff: bool = False,
) -> list[str]:
    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    api_contract_env = args.api_contract_env.strip() or runtime_env
    base_urls = _effective_base_urls_for_device(args, device)
    gateway_base_url = base_urls["gatewayBaseUrl"]
    product_ops_base_url = base_urls["productOpsBaseUrl"]
    media_avatar_base_url = base_urls["mediaAvatarBaseUrl"]
    media_image_base_url = base_urls["mediaImageBaseUrl"]
    media_video_base_url = base_urls["mediaVideoBaseUrl"]
    media_upload_base_url = base_urls["mediaUploadBaseUrl"]
    rtc_media_connection_url = base_urls["rtcMediaConnectionUrl"]
    legal_base_url = base_urls["legalBaseUrl"]
    canonical_runtime_defines: dict[str, str] | None = None
    if launcher_handoff is not None:
        canonical_runtime_defines, _ = _canonical_handoff_projection(
            launcher_handoff
        )
        expected_target = _local_target_for_environment_alias(args.env_name)
        if launcher_handoff.get("environment") != runtime_env:
            raise ValueError("launcher handoff environment does not match Patrol")
        if launcher_handoff.get("target") != expected_target:
            raise ValueError("launcher handoff target does not match Patrol")
    video_playback_canary_work_id = str(
        getattr(args, "video_playback_canary_work_id", "") or ""
    ).strip()
    patrol_install_id = str(getattr(args, "patrol_install_id", "") or "").strip()
    profile_p0_only = os.environ.get(
        "QWQ_APP_CONTENT_PROFILE_P0_ONLY",
        "",
    ).strip()
    if profile_p0_only and profile_p0_only != "true":
        raise ValueError("QWQ_APP_CONTENT_PROFILE_P0_ONLY must equal true")
    if profile_p0_only and str(args.target).strip() != PROFILE_JOURNEY_TARGET:
        raise ValueError(
            "QWQ_APP_CONTENT_PROFILE_P0_ONLY is only valid for the profile journey"
        )
    _validate_account_closure_execution(args, runtime_env)
    if patrol_install_id:
        patrol_install_id = patrol_install_id.replace(
            "{device}",
            sanitize_device_id(str(device["id"])),
        )
    command = [
        patrol_executable,
        "test",
        "--verbose",
        "-t",
        patrol_target or _patrol_bundler_target(args.target),
        "-d",
        str(device["id"]),
        "--dart-define=RUN_PATROL_ACCEPTANCE=true",
        "--dart-define=REQUIRE_NATIVE_VIDEO_PLAYBACK_SIGNALS="
        + (
            "true"
            if _requires_native_video_playback_signals(device)
            else "false"
        ),
        f"--dart-define=API_CONTRACT_ENV={api_contract_env}",
        f"--dart-define=API_CONTRACT_BASE_URL={gateway_base_url}",
        f"--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL={product_ops_base_url}",
        f"--dart-define=VIDEO_PLAYBACK_CANARY_WORK_ID={video_playback_canary_work_id}",
    ]
    # Patrol instrumentation 只能安装物理隔离 test host；环境身份仅由
    # production Remote runtime defines 传入，test host 永不成为可晋级制品。
    if str(device.get("targetPlatform") or "").lower().startswith("android"):
        command.append(f"--package-name={PATROL_ANDROID_PACKAGE}")
    else:
        command.append(f"--bundle-id={PATROL_IOS_BUNDLE_ID}")
    if canonical_runtime_defines is None:
        command.extend(
            (
                f"--dart-define=APP_RUNTIME_ENV={runtime_env}",
                f"--dart-define=CLOUD_GATEWAY_BASE_URL={gateway_base_url}",
                f"--dart-define=APP_LEGAL_BASE_URL={legal_base_url}",
                "--dart-define=RTC_MEDIA_CONNECTION_URL="
                f"{rtc_media_connection_url}",
            )
        )
    else:
        command.extend(
            f"--dart-define={key}={value}"
            for key, value in sorted(canonical_runtime_defines.items())
        )
    if profile_p0_only:
        command.append("--dart-define=APP_CONTENT_PROFILE_P0_ONLY=true")
    ios_runtime_argument = patrol_ios_runtime_argument(device)
    if ios_runtime_argument:
        command.append(ios_runtime_argument)
    if patrol_install_id:
        command.append(f"--dart-define=QWQ_PATROL_INSTALL_ID={patrol_install_id}")
    if _requires_account_closure(args) and runtime_env == "prod":
        command.append(
            "--dart-define=QWQ_ACCOUNT_CLOSURE_DISPOSABLE_ACK=true"
        )
    if _is_account_enforcement_target(args):
        command.append(
            "--dart-define=QWQ_ACCEPTANCE_CANDIDATE_DIGEST="
            + str(getattr(args, "candidate_digest", "") or "").strip()
        )
    if _uses_public_video_canary_anonymous_session(args):
        command.append(
            "--dart-define=QWQ_PATROL_SESSION_MODE="
            f"{_public_video_canary_session_mode(args)}"
        )
    elif _uses_runtime_anonymous_session(args):
        command.append(
            "--dart-define=QWQ_PATROL_SESSION_MODE="
            f"{_runtime_anonymous_session_mode(args)}"
        )
    elif bool(getattr(args, "unauthenticated_auth_entry", False)):
        command.append(
            "--dart-define=QWQ_PATROL_SESSION_MODE=unauthenticated_auth_entry"
        )
        if dart_define_file is None:
            raise ValueError(
                "unauthenticated auth-entry Patrol requires a private Provider define file"
            )
        command.append(f"--dart-define-from-file={dart_define_file}")
    elif _uses_persisted_device_session(args):
        pass
    elif typed_test_data_session_handoff:
        command.append(
            "--dart-define=QWQ_PATROL_SESSION_MODE="
            "test_data_protected_authenticated_session"
        )
    else:
        if dart_define_file is None:
            raise ValueError("remote Patrol session requires a private Dart define file")
        command.extend(
            [
                f"--dart-define-from-file={dart_define_file}",
            ]
        )
    # Patrol 4.4 uses Xcode's SDK when `--ios` is omitted.  That is not the
    # booted simulator runtime, so always pass the runtime parsed from device
    # discovery and let Xcode resolve the destination against that device.
    if canonical_runtime_defines is None and (
        media_avatar_base_url
        or media_image_base_url
        or media_video_base_url
        or media_upload_base_url
    ):
        command.extend(
            [
                f"--dart-define=MEDIA_AVATAR_CDN_BASE_URL={media_avatar_base_url}",
                f"--dart-define=MEDIA_IMAGE_CDN_BASE_URL={media_image_base_url}",
                f"--dart-define=MEDIA_VIDEO_CDN_BASE_URL={media_video_base_url}",
                f"--dart-define=MEDIA_UPLOAD_BASE_URL={media_upload_base_url}",
            ]
        )
    release_uat_cases_b64 = str(getattr(args, "release_uat_cases_b64", "") or "")
    if release_uat_cases_b64:
        command.append(f"--dart-define=QWQ_RELEASE_HOMEPAGE_UAT_CASES_B64={release_uat_cases_b64}")
    target_name = Path(args.target).name
    if target_name == Path(CORE_READBACK_TARGET).name:
        release_defines = {
            define_name: str(getattr(args, destination, "") or "").strip()
            for destination, define_name in RELEASE_APP_UAT_DEFINES
        }
        missing = sorted(
            name for name, value in release_defines.items() if not value
        )
        if missing:
            raise ValueError(
                "app core readback requires one immutable release envelope: "
                + ", ".join(missing)
            )
        command.extend(
            f"--dart-define={name}={value}"
            for name, value in release_defines.items()
        )
        video_page_count = os.environ.get(
            APP_CONTENT_VIDEO_PAGE_COUNT_ENV,
            "",
        ).strip()
        if re.fullmatch(r"[1-9][0-9]*", video_page_count) is None:
            raise ValueError(
                "app core readback requires a positive release video page count"
            )
        command.append(
            f"--dart-define=DATA_RELEASE_VIDEO_PAGE_COUNT={video_page_count}"
        )
    elif target_name == Path(HOME_VIDEO_PLAYBACK_TARGET).name:
        release_id = str(getattr(args, "data_release_id", "") or "").strip()
        if not release_id:
            raise ValueError(
                "home video playback requires one immutable release identity"
            )
        command.append(f"--dart-define=DATA_RELEASE_ID={release_id}")
    return command
