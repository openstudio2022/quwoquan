"""执行会话语义：target 谓词、环境别名解析、typed test-data actor 与会话准备。

正文自 run_environment_patrol_smoke.py 逐字搬入。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

from .constants import (
    ACCOUNT_CLOSURE_TARGET,
    ACCOUNT_ENFORCEMENT_TARGETS,
    ALPHA_APP_CONTENT_TYPED_SESSION_TARGETS,
    CONTROLLED_EDGE_FAULT_TARGET,
    CORE_READBACK_TARGET,
    DEFAULT_TARGET,
    FEED_LOAD_TARGET,
    FORBIDDEN_PROD_PLAYBACK_CANARY_TOKENS,
    HOME_VIDEO_PLAYBACK_TARGET,
    LOCAL_ENVIRONMENT_ALIAS_TARGETS,
    LOCAL_TARGETS,
    RUNTIME_ANONYMOUS_SESSION_MODES,
    RUNTIME_RECOVERY_TARGET,
    TYPED_AUTHENTICATED_SESSION_TARGETS,
    TYPED_TEST_DATA_ACTOR_ENV,
    TYPED_TEST_DATA_CONVERSATION_ENV,
    TYPED_TEST_DATA_CONVERSATION_TARGETS,
)


def _runtime_env_for_alias(alias: str) -> str:
    normalized = alias.strip().lower()
    if normalized in {"prod", "prod-sim", "prod-hosted"}:
        return "prod"
    if "gamma" in normalized:
        return "gamma"
    if "beta" in normalized:
        return "beta"
    return "alpha"


def _evidence_class_for_runtime(runtime_env: str) -> str:
    del runtime_env
    return "user_acceptance_remote"


def _requires_native_video_playback_signals(device: dict[str, Any]) -> bool:
    return str(device.get("targetPlatform") or "").lower().startswith("android")


def _is_feed_load_target(args: argparse.Namespace) -> bool:
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    return target.endswith(FEED_LOAD_TARGET)


def _is_controlled_edge_fault_target(args: argparse.Namespace) -> bool:
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    return target.endswith(CONTROLLED_EDGE_FAULT_TARGET)


def _local_target_for_environment_alias(env_name: str) -> str:
    """Resolve a public environment alias to its concrete local deployment target."""
    normalized = env_name.strip().lower()
    return LOCAL_ENVIRONMENT_ALIAS_TARGETS.get(normalized, normalized)


def _uses_public_video_canary_anonymous_session(
    args: argparse.Namespace,
) -> bool:
    """本地 beta/gamma 的公开视频 canary 无凭据时以 guest 执行只读验收。"""

    target_name = _local_target_for_environment_alias(args.env_name)
    if target_name not in {"beta-local", "gamma-local"}:
        return False
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    if not target.endswith(DEFAULT_TARGET):
        return False
    supplied = (
        args.test_auth_token,
        args.test_refresh_token,
        _resolved_owner_id(args),
        _resolved_persona_id(args),
    )
    return not any(str(value).strip() for value in supplied)


def _requires_video_playback_canary(args: argparse.Namespace) -> bool:
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    return any(
        target.endswith(candidate)
        for candidate in (
            DEFAULT_TARGET,
            HOME_VIDEO_PLAYBACK_TARGET,
            CORE_READBACK_TARGET,
        )
    )


def _requires_typed_authenticated_session(args: argparse.Namespace) -> bool:
    """Return whether this local UAT consumes one stackctl-owned Actor scope."""

    target_name = _local_target_for_environment_alias(args.env_name)
    if target_name not in {
        "alpha-local",
        "beta-local",
        "gamma-local",
    }:
        return False
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    shared_protected = any(
        target.endswith(candidate)
        for candidate in TYPED_AUTHENTICATED_SESSION_TARGETS
    )
    alpha_content_protected = target_name == "alpha-local" and any(
        target.endswith(candidate)
        for candidate in ALPHA_APP_CONTENT_TYPED_SESSION_TARGETS
    )
    return shared_protected or alpha_content_protected


def _requires_account_closure(args: argparse.Namespace) -> bool:
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    return target.endswith(ACCOUNT_CLOSURE_TARGET)


def _is_runtime_recovery_target(args: argparse.Namespace) -> bool:
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    return target.endswith(RUNTIME_RECOVERY_TARGET)


def _account_enforcement_phase(args: argparse.Namespace) -> str:
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    return next(
        (
            phase
            for phase, expected_target in ACCOUNT_ENFORCEMENT_TARGETS.items()
            if target.endswith(expected_target)
        ),
        "",
    )


def _is_account_enforcement_target(args: argparse.Namespace) -> bool:
    return bool(_account_enforcement_phase(args))


def _account_enforcement_subject_digest(args: argparse.Namespace) -> str:
    if not _is_account_enforcement_target(args):
        return ""
    owner_id = _resolved_owner_id(args).strip()
    if not owner_id:
        return ""
    return f"sha256:{hashlib.sha256(owner_id.encode('utf-8')).hexdigest()}"


def _uses_persisted_device_session(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "persisted_device_session", False))


def _validate_account_closure_execution(
    args: argparse.Namespace,
    runtime_env: str,
) -> None:
    if not _requires_account_closure(args):
        return
    install_id = str(getattr(args, "patrol_install_id", "") or "").strip()
    if not install_id or "{device}" not in install_id:
        raise ValueError(
            "account closure Patrol requires --patrol-install-id with a "
            "{device} placeholder"
        )
    if runtime_env != "prod":
        return
    if _uses_runtime_anonymous_session(args):
        raise ValueError(
            "prod account closure Patrol requires an injected disposable session"
        )
    if not bool(getattr(args, "account_closure_disposable_ack", False)):
        raise ValueError(
            "prod account closure Patrol requires "
            "--account-closure-disposable-ack"
        )


def _uses_runtime_anonymous_session(args: argparse.Namespace) -> bool:
    return (
        args.env_name.strip().lower() in RUNTIME_ANONYMOUS_SESSION_MODES
        and not bool(getattr(args, "unauthenticated_auth_entry", False))
        and not _uses_public_video_canary_anonymous_session(args)
        and not _uses_persisted_device_session(args)
        and not _is_account_enforcement_target(args)
        and not _requires_typed_authenticated_session(args)
    )


def _runtime_anonymous_session_mode(args: argparse.Namespace) -> str:
    alias = args.env_name.strip().lower()
    try:
        return RUNTIME_ANONYMOUS_SESSION_MODES[alias]
    except KeyError as exc:
        raise ValueError(
            f"{alias or '<empty>'} does not support runtime anonymous login"
        ) from exc


def _public_video_canary_session_mode(args: argparse.Namespace) -> str:
    target_name = _local_target_for_environment_alias(args.env_name)
    if target_name == "beta-local":
        return "anonymous_public_video_session"
    if target_name == "gamma-local":
        return "anonymous_public_video_session"
    raise ValueError(f"{target_name} does not support anonymous public video canary")


def _is_local_target(env_name: str) -> bool:
    return _local_target_for_environment_alias(env_name) in LOCAL_TARGETS


def _resolved_media_base_urls(args: argparse.Namespace) -> dict[str, str]:
    """解析四类显式注入的媒体 authority；禁止单一 media base 回退。"""
    return {
        "mediaAvatarBaseUrl": str(
            getattr(args, "media_avatar_base_url", "") or ""
        ).strip(),
        "mediaImageBaseUrl": str(
            getattr(args, "media_image_base_url", "") or ""
        ).strip(),
        "mediaVideoBaseUrl": str(
            getattr(args, "media_video_base_url", "") or ""
        ).strip(),
        "mediaUploadBaseUrl": str(
            getattr(args, "media_upload_base_url", "") or ""
        ).strip(),
    }


def _resolved_owner_id(args: argparse.Namespace) -> str:
    return str(getattr(args, "current_owner_id", "") or "").strip()


def _resolved_persona_id(args: argparse.Namespace) -> str:
    return str(getattr(args, "current_persona_id", "") or "").strip()


def _validate_video_playback_canary_work_id(
    args: argparse.Namespace,
    runtime_env: str,
) -> str:
    work_id = str(
        getattr(args, "video_playback_canary_work_id", "") or ""
    ).strip()
    if not work_id:
        raise ValueError("video playback canary work id is required")
    if runtime_env == "prod" and any(
        token in work_id.lower()
        for token in FORBIDDEN_PROD_PLAYBACK_CANARY_TOKENS
    ):
        raise ValueError(
            "prod playback canary must reference a published release work, not fixture/mock/seed/test data"
        )
    return work_id


@dataclass(frozen=True)
class TypedTestDataActor:
    access_token: str
    refresh_token: str
    owner_id: str
    persona_id: str

    def secret_values(self) -> tuple[str, ...]:
        return (
            self.access_token,
            self.refresh_token,
            self.owner_id,
            self.persona_id,
        )


@dataclass(frozen=True)
class TypedTestDataConversation:
    conversation_id: str
    message_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.conversation_id.strip():
            raise ValueError("typed test-data conversation id is required")
        if (
            not self.message_ids
            or any(not item.strip() for item in self.message_ids)
            or len(self.message_ids) != len(set(self.message_ids))
        ):
            raise ValueError(
                "typed test-data conversation messages must be non-empty and unique"
            )

    def artifact_values(self) -> tuple[str, ...]:
        return (
            self.conversation_id,
            *self.message_ids,
            json.dumps(
                list(self.message_ids),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )


def _typed_test_data_actor_from_environment() -> TypedTestDataActor | None:
    values = {
        field: os.environ.get(environment_key, "").strip()
        for field, environment_key in TYPED_TEST_DATA_ACTOR_ENV.items()
    }
    populated = [field for field, value in values.items() if value]
    if not populated:
        return None
    missing = sorted(set(values) - set(populated))
    if missing:
        raise ValueError(
            "typed test-data actor handoff is incomplete: " + ", ".join(missing)
        )
    return TypedTestDataActor(**values)


def _typed_test_data_conversation_from_environment(
) -> TypedTestDataConversation | None:
    values = {
        field: os.environ.get(environment_key, "").strip()
        for field, environment_key in TYPED_TEST_DATA_CONVERSATION_ENV.items()
    }
    populated = [field for field, value in values.items() if value]
    if not populated:
        return None
    missing = sorted(set(values) - set(populated))
    if missing:
        raise ValueError(
            "typed test-data conversation handoff is incomplete: "
            + ", ".join(missing)
        )
    try:
        raw_message_ids = json.loads(values["message_ids_json"])
    except json.JSONDecodeError as exc:
        raise ValueError(
            "typed test-data conversation message ids are invalid"
        ) from exc
    if not isinstance(raw_message_ids, list) or any(
        not isinstance(item, str) for item in raw_message_ids
    ):
        raise ValueError("typed test-data conversation message ids are invalid")
    return TypedTestDataConversation(
        conversation_id=values["conversation_id"],
        message_ids=tuple(raw_message_ids),
    )


def _requires_typed_test_data_conversation(args: argparse.Namespace) -> bool:
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    return any(
        target.endswith(candidate)
        for candidate in TYPED_TEST_DATA_CONVERSATION_TARGETS
    )


def _bind_typed_test_data_actor(args: argparse.Namespace) -> TypedTestDataActor:
    supplied = {
        "test_auth_token": args.test_auth_token,
        "test_refresh_token": args.test_refresh_token,
        "current_owner_id": _resolved_owner_id(args),
        "current_persona_id": _resolved_persona_id(args),
    }
    if any(str(value).strip() for value in supplied.values()):
        raise ValueError(
            "typed authenticated Patrol forbids caller-injected credentials"
        )
    actor = _typed_test_data_actor_from_environment()
    if actor is None:
        raise ValueError(
            "typed authenticated Patrol requires a stackctl TestDataSession actor handoff"
        )
    args.test_auth_token = actor.access_token
    args.test_refresh_token = actor.refresh_token
    args.current_owner_id = actor.owner_id
    args.current_persona_id = actor.persona_id
    args._typed_test_data_actor = actor
    return actor


def _prepare_execution_session(args: argparse.Namespace) -> str:
    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    _validate_account_closure_execution(args, runtime_env)
    if _uses_persisted_device_session(args):
        if not _is_runtime_recovery_target(args):
            raise ValueError(
                "--persisted-device-session is only valid for runtime recovery UAT"
            )
        supplied = (
            args.test_auth_token,
            args.test_refresh_token,
            _resolved_owner_id(args),
            _resolved_persona_id(args),
        )
        if any(str(value).strip() for value in supplied):
            raise ValueError(
                "persisted-device-session UAT forbids injected auth tokens or actor identities"
            )
        if runtime_env not in {"beta", "gamma"}:
            raise ValueError(
                "runtime recovery persisted-session UAT only accepts beta or gamma"
            )
        return "persisted_device_session"
    if _is_runtime_recovery_target(args):
        raise ValueError(
            "runtime recovery UAT requires --persisted-device-session"
        )
    if _requires_typed_authenticated_session(args):
        _bind_typed_test_data_actor(args)
        return "test_data_protected_authenticated_session"
    if bool(getattr(args, "unauthenticated_auth_entry", False)):
        supplied = (
            args.test_auth_token,
            args.test_refresh_token,
            _resolved_owner_id(args),
            _resolved_persona_id(args),
        )
        if any(str(value).strip() for value in supplied):
            raise ValueError(
                "unauthenticated auth-entry Patrol cannot preload a session"
            )
        return "unauthenticated_auth_entry"
    if _uses_public_video_canary_anonymous_session(args):
        return _public_video_canary_session_mode(args)
    if _uses_runtime_anonymous_session(args):
        supplied = {
            "test_auth_token": args.test_auth_token,
            "test_refresh_token": args.test_refresh_token,
            "current_owner_id": _resolved_owner_id(args),
            "current_persona_id": _resolved_persona_id(args),
        }
        if any(str(value).strip() for value in supplied.values()):
            raise ValueError(
                "local Remote Patrol must use device-runtime anonymous login; "
                "do not inject auth tokens or actor identities"
            )
        return _runtime_anonymous_session_mode(args)
    return "provided_remote_session"


def _missing_required_args(args: argparse.Namespace) -> list[str]:
    required = [
        ("gateway_base_url", args.gateway_base_url),
        ("product_ops_base_url", args.product_ops_base_url),
        ("media_avatar_base_url", getattr(args, "media_avatar_base_url", "")),
        ("media_image_base_url", getattr(args, "media_image_base_url", "")),
        ("media_video_base_url", getattr(args, "media_video_base_url", "")),
        ("media_upload_base_url", getattr(args, "media_upload_base_url", "")),
        (
            "rtc_media_connection_url",
            getattr(args, "rtc_media_connection_url", ""),
        ),
    ]
    if _requires_video_playback_canary(args):
        required.append(
            (
                "video_playback_canary_work_id",
                getattr(args, "video_playback_canary_work_id", ""),
            )
        )
    if not (
        bool(getattr(args, "unauthenticated_auth_entry", False)) or
        _uses_runtime_anonymous_session(args) or
        _uses_public_video_canary_anonymous_session(args) or
        _uses_persisted_device_session(args)
    ):
        required.extend(
            [
                ("test_auth_token", args.test_auth_token),
                ("test_refresh_token", args.test_refresh_token),
                ("current_owner_id", _resolved_owner_id(args)),
                ("current_persona_id", _resolved_persona_id(args)),
            ]
        )
    return [name for name, value in required if not str(value).strip()]
