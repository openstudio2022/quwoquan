#!/usr/bin/env python3
"""
verify_error_code_endcloud_parity.py

端云错误码全集一致门禁（strict parity）。

对每个「客户端可见」业务域，断言：
  云侧 contracts/metadata/**/errors.yaml 的 code 集合
  == 客户端生成的 *ErrorCode 枚举 code 集合（忽略 unknown 兜底项）。

目的：当云侧 errors.yaml 新增/删除错误码时，若客户端 codegen 未同步生成对应
typed 枚举项，立即阻断，避免端侧 typed 覆盖悄悄落后于云侧（用户核心诉求：
端云错误码扩展必须可被发现，不能出现端侧无 typed 覆盖的静默缺口）。

注意：前向兼容（未知码仍回退 userMessage/recovery）由运行时保证，由
verify forward-compat 契约测试单独锁定；本门禁只保证「典型客户端域」的
typed 全集一致，不强制 server-internal 错误码也生成客户端枚举。

server-internal 域（integration 的 provider/中间件错误码，不直接回给客户端）
显式登记在 SERVER_INTERNAL_DOMAINS，便于审计且不掩盖客户端可见域的缺口。

Usage:
  python3 quwoquan_app/scripts/runtime/verify_error_code_endcloud_parity.py
Exit 0 on success, 1 on mismatch.
"""

import os
import re
import sys

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

# 每个客户端可见域：cloud errors.yaml（一个或多个）-> 生成的客户端枚举文件。
CLIENT_DOMAINS = {
    "content": {
        "cloud": ["quwoquan_service/contracts/metadata/content/post/errors.yaml"],
        "dart": "quwoquan_app/lib/cloud/content/generated/content_errors.g.dart",
    },
    "chat": {
        "cloud": ["quwoquan_service/contracts/metadata/messages/conversation/errors.yaml"],
        "dart": "quwoquan_app/lib/cloud/chat/generated/chat_errors.g.dart",
    },
    "user": {
        "cloud": [
            "quwoquan_service/contracts/metadata/user/user_profile/errors.yaml",
            "quwoquan_service/contracts/metadata/user/contact_discovery/errors.yaml",
            "quwoquan_service/contracts/metadata/user/greeting_request/errors.yaml",
            "quwoquan_service/contracts/metadata/user/invite_record/errors.yaml",
        ],
        "dart": "quwoquan_app/lib/cloud/runtime/generated/user/user_errors.g.dart",
    },
    "integration_location": {
        "cloud": ["quwoquan_service/contracts/metadata/integration/location/errors.yaml"],
        "dart": "quwoquan_app/lib/cloud/runtime/generated/integration/integration_location_errors.g.dart",
    },
    "rtc": {
        "cloud": ["quwoquan_service/contracts/metadata/rtc/call_session/errors.yaml"],
        "dart": "quwoquan_app/lib/cloud/rtc/generated/rtc_errors.g.dart",
    },
    "assistant": {
        "cloud": ["quwoquan_service/contracts/metadata/assistant/assistant_run/errors.yaml"],
        "dart": "quwoquan_app/lib/cloud/assistant/generated/assistant_errors.g.dart",
    },
    "circle": {
        "cloud": ["quwoquan_service/contracts/metadata/social/circle/errors.yaml"],
        "dart": "quwoquan_app/lib/cloud/circle/generated/circle_errors.g.dart",
    },
    "entity": {
        "cloud": ["quwoquan_service/contracts/metadata/entity/homepage/errors.yaml"],
        "dart": "quwoquan_app/lib/cloud/entity/generated/entity_errors.g.dart",
    },
}

# 不直接回给客户端的 server-internal 错误码域（integration provider/中间件链路）。
# 仅作审计登记：这些域不要求生成客户端枚举。新增 server-internal 域在此声明。
SERVER_INTERNAL_DOMAINS = {
    "integration/external_interaction": "外部交互 provider 中间件错误，服务间使用，不直接回客户端",
    "integration/push_delivery": "推送投递 provider 错误，服务内编排，不直接回客户端",
    "integration/sms_otp": "短信 OTP provider 错误，在 user-service 边界映射为 USER.AUTH 后才回客户端",
}

CLOUD_CODE_RE = re.compile(r"^\s*-?\s*code:\s*([A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z0-9_]+)\s*$")
# 生成的客户端枚举有两种风格：构造参数式 name('CODE', ...) 与裸枚举 + fromCode/code
# switch 中的 'CODE' case。两者都把 code 以字符串字面量形式出现，故直接收集文件内
# 全部形如 'MODULE.KIND.reason' 的字面量即可（生成文件仅含本域 code）。
DART_CODE_RE = re.compile(r"'([A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z0-9_]+)'")


def read_cloud_codes(rel_paths: list[str]) -> tuple[set[str], list[str]]:
    codes: set[str] = set()
    missing: list[str] = []
    for rel in rel_paths:
        path = os.path.join(REPO_ROOT, rel)
        if not os.path.isfile(path):
            missing.append(rel)
            continue
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                m = CLOUD_CODE_RE.match(line)
                if m:
                    codes.add(m.group(1))
    return codes, missing


def read_dart_codes(rel_path: str) -> tuple[set[str], bool]:
    path = os.path.join(REPO_ROOT, rel_path)
    if not os.path.isfile(path):
        return set(), False
    with open(path, encoding="utf-8") as handle:
        content = handle.read()
    codes = set(DART_CODE_RE.findall(content))
    return codes, True


def main() -> int:
    failed = False
    for domain, cfg in sorted(CLIENT_DOMAINS.items()):
        cloud_codes, missing_cloud = read_cloud_codes(cfg["cloud"])
        if missing_cloud:
            print(f"[{domain}] 云侧 errors.yaml 缺失: {', '.join(missing_cloud)}")
            failed = True
            continue
        dart_codes, dart_exists = read_dart_codes(cfg["dart"])
        if not dart_exists:
            print(f"[{domain}] 客户端枚举缺失: {cfg['dart']}（请运行 make codegen-app）")
            failed = True
            continue

        cloud_only = cloud_codes - dart_codes
        dart_only = dart_codes - cloud_codes
        if cloud_only:
            print(f"[{domain}] 云侧有、客户端枚举缺失的错误码（需 codegen 同步）:")
            for code in sorted(cloud_only):
                print(f"    + {code}")
            failed = True
        if dart_only:
            print(f"[{domain}] 客户端枚举有、云侧 errors.yaml 已无的错误码（需清理枚举）:")
            for code in sorted(dart_only):
                print(f"    - {code}")
            failed = True

    if failed:
        print(
            "\nverify_error_code_endcloud_parity: 端云错误码全集不一致已被阻断。\n"
            "  先改 errors.yaml（唯一真相源），再 make codegen-app 同步客户端枚举。",
            file=sys.stderr,
        )
        return 1
    print("verify_error_code_endcloud_parity: 端云错误码全集一致 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
