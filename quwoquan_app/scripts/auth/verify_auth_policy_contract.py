#!/usr/bin/env python3
"""校验 API 鉴权契约（security.auth_mode）的元数据真相源与端侧产物一致性。

门禁内容：
1. 每个 service.yaml operation 解析出的 auth_mode 必须是 public/optional/required。
2. 认证类 operation（登录/刷新/匿名）必须是 public/optional，绝不能是 required。
3. 一批明确需要登录的核心 operation 必须解析为 required（防止漏标回退）。
4. 生成的端侧快照 auth_policy.g.dart 必须与 service.yaml 重新解析结果一致（防漂移）。

解析逻辑与 tools/codegen_app_metadata/main.go 的 routeDef.resolveAuthMode() 等价。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
METADATA_DIR = REPO_ROOT / "quwoquan_service" / "contracts" / "metadata"
POLICY_DART = (
    REPO_ROOT
    / "quwoquan_app"
    / "lib"
    / "cloud"
    / "runtime"
    / "generated"
    / "auth"
    / "auth_policy.g.dart"
)

VALID_MODES = {"public", "optional", "required"}

# 认证类入口：绝不能 required（否则没人能登录）。
AUTH_PUBLIC_OPERATIONS = {
    "LoginWithPhone",
    "LoginWithWechat",
    "LoginWithApple",
    "LoginWithPasskey",
    "LoginOneTap",
    "ResolveOneTapLoginHint",
    "LoginAnonymous",
    "RefreshToken",
    "SendOtp",
}

# 明确需要账号身份的核心入口：必须 required，防止漏标回退为 public。
# 注意：点赞/分享已按「游客设备态可写」策略下放到 MUST_BE_DEVICE_WRITABLE；
# 内容互动只有 赞/评/转；足迹（GetMyFootprint）属个人资产，必须登录。
MUST_BE_REQUIRED = {
    "ActivatePersona",
    "ApplyPersonaProfileSync",
    "BindCredential",
    "ClearRecentSearches",
    "CreatePost",
    "UpdatePost",
    "DeletePost",
    "CreateComment",
    "CreatePersona",
    "GetMyFootprint",
    "SendMessage",
    "ListConversations",
    "GetConversation",
    "FollowUser",
    "CreateReport",
    "GetActivePersonaContext",
    "GetAppearanceSettings",
    "GetCallSettings",
    "GetMeProfile",
    "GetNotificationSettings",
    "GetPersonaLifecycleGuard",
    "GetPersonaManagementSummary",
    "GetPrivacySettings",
    "ListPersonas",
    "ListCredentials",
    "Logout",
    "RetirePersona",
    "UnbindCredential",
    "UpdateAppearanceSettings",
    "UpdateCallSettings",
    "UpdateNotificationSettings",
    "UpdatePersona",
    "UpdatePrivacySettings",
}

# 游客设备态可写入口（like/share）：必须是 optional（auth_mode=optional +
# anonymous_policy=allow），既不能回退为 required（会重新拦截游客设备态写入），
# 也不能放成 public（仍需登录用户走账号维度）。维度分层由云侧 deviceActorId 计数实现。
MUST_BE_DEVICE_WRITABLE = {
    "LikePost",
    "UnlikePost",
    "SharePost",
    "UnsharePost",
}


def resolve_auth_mode(route: dict) -> str:
    security = route.get("security") or {}
    mode = str(security.get("auth_mode", "")).strip().lower()
    if mode in VALID_MODES:
        return mode
    fallback_auth = str(route.get("auth", "")).strip().lower()
    if fallback_auth == "required":
        return "required"
    if fallback_auth == "optional":
        return "optional"
    auth_required = route.get("auth_required")
    if isinstance(auth_required, bool):
        return "required" if auth_required else "public"
    return "public"


def collect_operations() -> dict[str, str]:
    op_to_mode: dict[str, str] = {}
    for service_file in sorted(METADATA_DIR.rglob("service.yaml")):
        try:
            data = yaml.safe_load(service_file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - 配置错误直接暴露
            print(f"FAIL: 无法解析 {service_file}: {exc}")
            sys.exit(1)
        for route in data.get("api_routes", []) or []:
            op = str(route.get("operation", "")).strip()
            if not op:
                continue
            mode = resolve_auth_mode(route)
            # 跨域可能存在同名 operation（如 messages 与 notification 的 MarkAsRead）。
            # 与 codegen 聚合一致：按文件路径排序后首见优先，后续同名忽略。
            if op not in op_to_mode:
                op_to_mode[op] = mode
    return op_to_mode


def parse_generated_policy() -> dict[str, str]:
    if not POLICY_DART.exists():
        print(f"FAIL: 未找到生成的鉴权快照 {POLICY_DART}，请先运行 make codegen-app")
        sys.exit(1)
    text = POLICY_DART.read_text(encoding="utf-8")
    pairs = re.findall(r"'([A-Za-z0-9_]+)':\s*'(public|optional|required)'", text)
    return {op: mode for op, mode in pairs}


def main() -> int:
    errors: list[str] = []
    op_to_mode = collect_operations()

    for op, mode in op_to_mode.items():
        if mode not in VALID_MODES:
            errors.append(f"operation {op} 的 auth_mode 非法: {mode}")

    for op in AUTH_PUBLIC_OPERATIONS:
        mode = op_to_mode.get(op)
        if mode is None:
            errors.append(f"认证入口 {op} 缺失（service.yaml 未定义）")
        elif mode == "required":
            errors.append(f"认证入口 {op} 不能是 required（会导致无法登录）")

    for op in MUST_BE_REQUIRED:
        mode = op_to_mode.get(op)
        if mode is None:
            errors.append(f"核心受限入口 {op} 缺失（service.yaml 未定义）")
        elif mode != "required":
            errors.append(f"核心受限入口 {op} 必须是 required，当前为 {mode}")

    for op in MUST_BE_DEVICE_WRITABLE:
        mode = op_to_mode.get(op)
        if mode is None:
            errors.append(f"游客设备态可写入口 {op} 缺失（service.yaml 未定义）")
        elif mode != "optional":
            errors.append(
                f"游客设备态可写入口 {op} 必须是 optional（anonymous_policy=allow），当前为 {mode}"
            )

    generated = parse_generated_policy()
    for op, mode in op_to_mode.items():
        gen_mode = generated.get(op)
        if gen_mode is None:
            errors.append(f"生成快照缺少 operation {op}，请重跑 make codegen-app")
        elif gen_mode != mode:
            errors.append(
                f"生成快照 {op}={gen_mode} 与 service.yaml 解析 {mode} 漂移，请重跑 make codegen-app"
            )

    if errors:
        print("FAIL: API 鉴权契约校验未通过：")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(
        f"OK: 鉴权契约一致（operations={len(op_to_mode)}, "
        f"required={sum(1 for m in op_to_mode.values() if m == 'required')}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
