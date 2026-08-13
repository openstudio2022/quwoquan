#!/usr/bin/env python3
"""服务声明错误码的测试断言覆盖棘轮。

`contracts/**/errors.yaml` 声明的每个错误码都是对调用方的行为承诺，
必须有真实测试断言其被正确发射与映射，否则异常路径覆盖会失真
（`*_unavailable` / `internal_error` / `storage_failed` 类依赖失败路径
最容易只声明不验证）。

规则：每服务「声明但未在 tests/** 中出现」的错误码数量只减不增；
新增错误码必须携带断言测试（否则缺失数增长即阻断）。确属无法在
测试树内触发的兜底码在 ``EXEMPT_CODES`` 按码登记理由。

规格：specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICES_ROOT = ROOT / "quwoquan_service" / "services"

CODE_RE = re.compile(r"-\s*code:\s*[\"']?([A-Z_]+\.[A-Z_]+\.[a-z_]+)")
GO_CONST_RE = re.compile(r"go_const:\s*[\"']?(\w+)")
DART_CONST_RE = re.compile(r"dart_const:\s*[\"']?(\w+)")

#: 确属测试树内不可触发的兜底码；每条豁免必须写明理由。
EXEMPT_CODES: dict[str, str] = {
    # errors.yaml 声明 surface: player 且无 http_status,发射侧在 App 端
    # (quwoquan_app/lib/service/content_service/media/media_asset/ 的
    # media_playback_failure.dart 与 seek internals),App 测试树已有
    # media_playback_failure__local_contract_test.dart 等真实断言;
    # 服务侧 internal/** 无任何发射路径,不为不存在的路径造假测试。
    "CONTENT.SYSTEM.media_playback_network_unavailable": "App player surface 发射,证据在 quwoquan_app 测试树",
    "CONTENT.SYSTEM.media_playback_service_busy": "App player surface 发射,证据在 quwoquan_app 测试树",
    "CONTENT.SYSTEM.media_playback_temporarily_unavailable": "App player surface 发射,证据在 quwoquan_app 测试树",
    "CONTENT.SYSTEM.media_playback_unsupported": "App player surface 发射,证据在 quwoquan_app 测试树",
    "CONTENT.USER.media_playback_unavailable": "App player surface 发射,证据在 quwoquan_app 测试树",
    "CONTENT.SYSTEM.media_seek_failed": "App player surface 发射,证据在 quwoquan_app 测试树",
    # 唯一发射点是 cmd/api 包私有的 feed inflight admission writer,
    # 已由同包白盒测试 cmd/api/feed_admission_rejection__local_contract_test.go
    # 真实断言 wire code/503/Retry-After;本门只扫 tests/** 故按码登记。
    "CONTENT.SYSTEM.feed_capacity_unavailable": "cmd/api 装配层发射,已有同包白盒断言(门禁不扫 cmd)",
    # timeoutCode() 的 generic default 分支:validateProviderName 限制该
    # provider 只能以 sms_otp.send 构造(超时走 sms_provider_timeout),
    # push 通道另有 push_provider_timeout;测试树内无真实触发路径。
    "INTEGRATION.MIDDLEWARE.provider_timeout": "generic 超时分支在当前 provider 闭集内不可达",
    # 契约声明 GetNearbyLocations 发射,但服务端全链路无权限校验路径
    # (缺坐标用默认坐标 fallback),权限拒绝语义实际在 App 端;
    # 补服务端实现或删码由 gathering/location 域裁决。
    "INTEGRATION.USER.location_permission_required": "服务侧无发射实现,声明-实现漂移待域内裁决",
}

#: 每服务缺失码数棘轮基线；只减不增，补齐批次同步下调。
#: 基线取建门时实扫值；消化方向见 runtime-test-pyramid OPEN-002。
# 全服务零缺口:剩余 9 条按码登记于 EXEMPT_CODES(App 端发射/装配层白盒/不可达分支)。
MISSING_CEILING: dict[str, int] = {
    "api-edge": 0,
    "assistant-service": 0,
    "chat-service": 0,
    "circle-service": 0,
    "content-service": 0,
    "entity-service": 0,
    "integration-service": 0,
    "notification-service": 0,
    "product-ops-service": 0,
    "realtime-gateway": 0,
    "recommendation-service": 0,
    "rtc-service": 0,
    "search-service": 0,
    "tag-service": 0,
    "user-service": 0,
}


def declared_codes(service_dir: Path) -> dict[str, set[str]]:
    """返回 code -> 断言证据 token 集合（码字面量 + go_const/dart_const 别名）。

    测试经 generated 常量（如 ``generated.ErrIdempotencyConflict``）断言时，
    码字符串不会出现在测试文本里；把声明的 const 名纳入证据 token，
    避免把常量断言误判为未覆盖。
    """
    codes: dict[str, set[str]] = {}
    contracts = service_dir / "contracts"
    if not contracts.is_dir():
        return codes
    for errors_yaml in contracts.rglob("errors.yaml"):
        text = errors_yaml.read_text(encoding="utf-8", errors="ignore")
        entries = re.split(r"(?m)^(?=-\s+(?:\{)?code:)", text)
        for entry in entries:
            match = CODE_RE.search(entry)
            if not match:
                continue
            tokens = codes.setdefault(match.group(1), {match.group(1)})
            for const_re in (GO_CONST_RE, DART_CONST_RE):
                const_match = const_re.search(entry)
                if const_match:
                    tokens.add(const_match.group(1))
    return codes


def asserted_text(service_dir: Path) -> str:
    tests_dir = service_dir / "tests"
    if not tests_dir.is_dir():
        return ""
    chunks: list[str] = []
    for test_file in tests_dir.rglob("*_test.*"):
        try:
            chunks.append(test_file.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(chunks)


def main() -> int:
    if not SERVICES_ROOT.is_dir():
        print(f"[verify-error-code-assertion-coverage] FAIL: missing {SERVICES_ROOT}")
        return 1
    failures: list[str] = []
    total_declared = total_missing = 0
    for service_dir in sorted(SERVICES_ROOT.iterdir()):
        if not service_dir.is_dir():
            continue
        declared = declared_codes(service_dir)
        if not declared:
            continue
        text = asserted_text(service_dir)
        missing = sorted(
            code
            for code, tokens in declared.items()
            if code not in EXEMPT_CODES
            and not any(token in text for token in tokens)
        )
        total_declared += len(declared)
        total_missing += len(missing)
        ceiling = MISSING_CEILING.get(service_dir.name)
        if ceiling is None:
            failures.append(
                f"{service_dir.name}: not registered in MISSING_CEILING; register "
                f"the service with its current missing count ({len(missing)})"
            )
            continue
        if len(missing) > ceiling:
            failures.append(
                f"{service_dir.name}: unasserted error codes grew to {len(missing)} "
                f"(> {ceiling}); new error codes must ship with a test asserting "
                f"the emitted code, sample: {missing[:5]}"
            )
    if failures:
        for item in failures:
            print(f"[verify-error-code-assertion-coverage] FAIL: {item}")
        return 1
    print(
        "[verify-error-code-assertion-coverage] OK: declared="
        f"{total_declared} missing={total_missing} "
        f"(per-service ceilings hold, exempt={len(EXEMPT_CODES)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
