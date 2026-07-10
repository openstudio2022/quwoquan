#!/usr/bin/env python3
"""
verify_error_recovery_alignment.py

recovery 对齐门禁（云侧）。

对使用 AppError 工厂风格（runtime/errors.NewAppError(...).WithRecovery(...)）生成的
错误码域，断言：errors.yaml 中每个声明了 recovery_action 的错误，其生成的
internal/generated/errors.go 必含同一 code 对应的 .WithRecovery("<action>", <afterSeconds>)。

目的：锁定 recovery_action / recovery_after_seconds 从 errors.yaml -> 生成 Go ->
随 ErrorResponse 下发的链路不被回退（如有人误删 codegen 的 goErrorRecoveryCall、
手改生成产物、或某服务未重新 codegen）。客户端消费 recovery 由
quwoquan_service/contracts/runtime_errors/packages/dart/quwoquan_runtime_errors 的 codec/policy 测试单独锁定。

content 域已纳入强约束；客户端可见域不得再登记 sentinel-only 豁免。

Usage:
  python3 quwoquan_service/scripts/verify/verify_error_recovery_alignment.py
Exit 0 on success, 1 on misalignment.
"""

import os
import re
import sys

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

# AppError 工厂风格域：errors.yaml(可多个) -> 生成的 Go errors.go。
FACTORY_DOMAINS = {
    "content": {
        "yaml": ["quwoquan_service/contracts/metadata/content/post/errors.yaml"],
        "go": "quwoquan_service/services/content-service/internal/generated/errors.go",
    },
    "chat": {
        "yaml": ["quwoquan_service/contracts/metadata/messages/conversation/errors.yaml"],
        "go": "quwoquan_service/services/chat-service/internal/generated/errors.go",
    },
    "integration_location": {
        "yaml": ["quwoquan_service/contracts/metadata/integration/location/errors.yaml"],
        "go": "quwoquan_service/services/integration-service/internal/generated/errors.go",
    },
    "rtc": {
        "yaml": ["quwoquan_service/contracts/metadata/rtc/call_session/errors.yaml"],
        "go": "quwoquan_service/services/rtc-service/internal/generated/errors.go",
    },
    "user": {
        "yaml": [
            "quwoquan_service/contracts/metadata/user/user_profile/errors.yaml",
            "quwoquan_service/contracts/metadata/user/contact_discovery/errors.yaml",
            "quwoquan_service/contracts/metadata/user/greeting_request/errors.yaml",
            "quwoquan_service/contracts/metadata/user/invite_record/errors.yaml",
        ],
        "go": "quwoquan_service/services/user-service/internal/generated/errors.go",
    },
}

# 解析 errors.yaml 的逐条 error：code / recovery_action / recovery_after_seconds。
# errors.yaml 为缩进块，逐 error 项以 "- code:" 起。简单状态机解析。
CODE_RE = re.compile(r"^\s*-?\s*code:\s*(\S+)\s*$")
ACTION_RE = re.compile(r"^\s*recovery_action:\s*(\S+)\s*$")
AFTER_RE = re.compile(r"^\s*recovery_after_seconds:\s*(\d+)\s*$")
# 生成 Go 中的工厂注释 + .WithRecovery("action", secs)，按 code 精确绑定。
FACTORY_BLOCK_RE = re.compile(
    r"//\s+AppErrorFrom[A-Za-z0-9_]+\s+returns\s+\*AppError\s+for\s+"
    r"([A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z0-9_]+)"
    r"[\s\S]{0,420}?\.WithRecovery\(\s*\"([a-z_]+)\"\s*,\s*(\d+)\s*\)",
    re.MULTILINE,
)


def parse_yaml_recoveries(rel_paths: list[str]) -> tuple[dict[str, tuple[str, int]], list[str]]:
    """Return {code: (action, after_seconds)} required by yaml entries, plus missing files."""
    required: dict[str, tuple[str, int]] = {}
    missing: list[str] = []
    for rel in rel_paths:
        path = os.path.join(REPO_ROOT, rel)
        if not os.path.isfile(path):
            missing.append(rel)
            continue
        cur_action = None
        cur_after = 0
        cur_code = None
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                code_match = CODE_RE.match(line)
                if code_match:
                    # flush previous entry
                    if cur_code and cur_action:
                        required[cur_code] = (cur_action, cur_after)
                    cur_code = code_match.group(1)
                    cur_action = None
                    cur_after = 0
                    continue
                m = ACTION_RE.match(line)
                if m:
                    cur_action = m.group(1).strip('"\'')
                    continue
                m = AFTER_RE.match(line)
                if m:
                    cur_after = int(m.group(1))
                    continue
            if cur_code and cur_action:
                required[cur_code] = (cur_action, cur_after)
    return required, missing


def parse_go_recoveries(rel_path: str) -> tuple[dict[str, tuple[str, int]], bool]:
    path = os.path.join(REPO_ROOT, rel_path)
    if not os.path.isfile(path):
        return {}, False
    with open(path, encoding="utf-8") as handle:
        content = handle.read()
    present: dict[str, tuple[str, int]] = {}
    for code, action, secs in FACTORY_BLOCK_RE.findall(content):
        present[code] = (action, int(secs))
    return present, True


def main() -> int:
    failed = False
    for domain, cfg in sorted(FACTORY_DOMAINS.items()):
        required, missing_yaml = parse_yaml_recoveries(cfg["yaml"])
        if missing_yaml:
            print(f"[{domain}] errors.yaml 缺失: {', '.join(missing_yaml)}")
            failed = True
            continue
        present, go_exists = parse_go_recoveries(cfg["go"])
        if not go_exists:
            print(f"[{domain}] 生成 Go errors.go 缺失: {cfg['go']}（请运行 make codegen-app）")
            failed = True
            continue
        for code, expected in sorted(required.items()):
            actual = present.get(code)
            if actual != expected:
                print(f"[{domain}] {code} recovery 对齐失败:")
                print(f"    yaml: .WithRecovery(\"{expected[0]}\", {expected[1]})")
                if actual is None:
                    print("    go:   缺少对应 AppErrorFrom* 或 .WithRecovery")
                else:
                    print(f"    go:   .WithRecovery(\"{actual[0]}\", {actual[1]})")
                failed = True

    if failed:
        print(
            "\nverify_error_recovery_alignment: recovery 对齐不一致已被阻断。\n"
            "  先在 errors.yaml 声明 recovery_action/recovery_after_seconds，再 make codegen-app。",
            file=sys.stderr,
        )
        return 1
    print(
        "verify_error_recovery_alignment: recovery 对齐 OK"
        f"（factory 域 {len(FACTORY_DOMAINS)} 个强约束；无 sentinel 客户端可见域豁免）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
