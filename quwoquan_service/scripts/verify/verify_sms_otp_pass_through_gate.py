#!/usr/bin/env python3
"""登录受控放通门禁。

约束：
  - 全局放通（pass_through_enabled / debug_reveal_enabled）只允许 alpha/beta，且必须登记技术债。
  - gamma 禁止全局放通；只允许"受控放通"sandbox_allowlist（sms_otp/social/one_tap），
    开启时必须登记 SANDBOX_DEBT_ID + owner + expires_at + 非空名单。
  - prod 必须严格：无全局放通、无任何 sandbox_allowlist、无 debugCode。
"""
from __future__ import annotations

from pathlib import Path
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML 应已随仓库工具安装
    print("FAIL: PyYAML is required for verify_sms_otp_pass_through_gate", file=sys.stderr)
    raise SystemExit(2)


ROOT = Path(__file__).resolve().parents[3]
USER_CONFIGS = ROOT / "quwoquan_service" / "services" / "user-service" / "configs"
DEBT_REGISTER = ROOT / "specs" / "technical_debt_register.yaml"
DEBT_ID = "TECHDEBT-SMS-OTP-PASSTHROUGH-001"
SANDBOX_DEBT_ID = "TECHDEBT-LOGIN-SANDBOX-ALLOWLIST-GAMMA-001"


def load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def integration(cfg: dict) -> dict:
    return cfg.get("integration") or {}


def sms_otp(cfg: dict) -> dict:
    return integration(cfg).get("sms_otp") or {}


def sandbox_blocks(cfg: dict) -> list[tuple[str, dict]]:
    ig = integration(cfg)
    blocks: list[tuple[str, dict]] = []
    for name, section in (("sms_otp", sms_otp(cfg)), ("social", ig.get("social") or {}), ("one_tap", ig.get("one_tap") or {})):
        allow = section.get("sandbox_allowlist")
        if isinstance(allow, dict):
            blocks.append((name, allow))
    return blocks


def check_sandbox_enabled_well_formed(env: str, name: str, allow: dict, failures: list[str]) -> None:
    if not allow.get("enabled"):
        return
    phones = allow.get("phones") or []
    tokens = allow.get("tokens") or []
    if not phones and not tokens:
        failures.append(f"{env}.{name}: sandbox_allowlist enabled but phones/tokens empty")
    if allow.get("debt_id") != SANDBOX_DEBT_ID:
        failures.append(f"{env}.{name}: sandbox_allowlist must register debt_id {SANDBOX_DEBT_ID}")
    if not str(allow.get("owner") or "").strip():
        failures.append(f"{env}.{name}: sandbox_allowlist owner is required")
    if not str(allow.get("expires_at") or "").strip():
        failures.append(f"{env}.{name}: sandbox_allowlist expires_at is required")


def main() -> int:
    failures: list[str] = []
    debt_text = DEBT_REGISTER.read_text(encoding="utf-8")
    for debt in (DEBT_ID, SANDBOX_DEBT_ID):
        if debt not in debt_text:
            failures.append(f"{DEBT_REGISTER}: missing debt registration for {debt}")
    if "prod_allowed: false" not in debt_text:
        failures.append(f"{DEBT_REGISTER}: pass-through/sandbox debts must declare prod_allowed: false")

    # prod：严格
    prod = load(USER_CONFIGS / "prod" / "config.yaml")
    if sms_otp(prod).get("pass_through_enabled") is True:
        failures.append("prod user-service config must set sms_otp.pass_through_enabled: false")
    if sms_otp(prod).get("debug_reveal_enabled") is True:
        failures.append("prod user-service config must set sms_otp.debug_reveal_enabled: false")
    for name, allow in sandbox_blocks(prod):
        if allow.get("enabled"):
            failures.append(f"prod.{name}: sandbox_allowlist must be disabled in production")
    if DEBT_ID in (USER_CONFIGS / "prod" / "config.yaml").read_text(encoding="utf-8"):
        failures.append("prod user-service config must not carry SMS OTP pass-through debt id")

    # alpha/beta：允许全局放通，但必须登记技术债
    for env in ("alpha", "beta"):
        cfg = load(USER_CONFIGS / env / "config.yaml")
        otp = sms_otp(cfg)
        if otp.get("pass_through_enabled") is True:
            if otp.get("pass_through_debt_id") != DEBT_ID:
                failures.append(f"{env}: missing pass_through_debt_id {DEBT_ID}")
            if not str(otp.get("pass_through_owner") or "").strip():
                failures.append(f"{env}: pass_through_owner is required")
            if not str(otp.get("pass_through_expires_at") or "").strip():
                failures.append(f"{env}: pass_through_expires_at is required")
        if "https://" not in str(integration(cfg).get("external_interaction_base_url") or ""):
            failures.append(f"{env}: external_interaction_base_url must default to https")

    # gamma：禁止全局放通，只允许受控放通
    gamma = load(USER_CONFIGS / "gamma" / "config.yaml")
    if sms_otp(gamma).get("pass_through_enabled") is True:
        failures.append("gamma user-service config must set sms_otp.pass_through_enabled: false (use sandbox_allowlist)")
    if sms_otp(gamma).get("debug_reveal_enabled") is True:
        failures.append("gamma user-service config must set sms_otp.debug_reveal_enabled: false (use sandbox_allowlist)")
    if DEBT_ID in (USER_CONFIGS / "gamma" / "config.yaml").read_text(encoding="utf-8"):
        failures.append("gamma user-service config must not carry SMS OTP global pass-through debt id")
    for name, allow in sandbox_blocks(gamma):
        check_sandbox_enabled_well_formed("gamma", name, allow, failures)
    if "https://" not in str(integration(gamma).get("external_interaction_base_url") or ""):
        failures.append("gamma: external_interaction_base_url must default to https")

    # default：保持严格
    default = load(USER_CONFIGS / "default" / "config.yaml")
    if sms_otp(default).get("pass_through_enabled") is True:
        failures.append("default user-service config must keep sms_otp.pass_through_enabled false")
    for name, allow in sandbox_blocks(default):
        if allow.get("enabled"):
            failures.append(f"default.{name}: sandbox_allowlist must be disabled by default")
    if "https://" not in str(integration(default).get("external_interaction_base_url") or ""):
        failures.append("default external_interaction_base_url must use https")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("verify_sms_otp_pass_through_gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
