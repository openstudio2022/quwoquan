#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[3]
USER_CONFIGS = ROOT / "quwoquan_service" / "services" / "user-service" / "configs"
DEBT_REGISTER = ROOT / "specs" / "technical_debt_register.yaml"
DEBT_ID = "TECHDEBT-SMS-OTP-PASSTHROUGH-001"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def value(text: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}:\s*\"?([^\"\n#]*)\"?\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def main() -> int:
    failures: list[str] = []
    debt_text = read(DEBT_REGISTER)
    if DEBT_ID not in debt_text or "prod_allowed: false" not in debt_text:
        failures.append(f"{DEBT_REGISTER}: missing active non-prod debt registration for {DEBT_ID}")

    prod = read(USER_CONFIGS / "prod" / "config.yaml")
    if value(prod, "pass_through_enabled") != "false":
        failures.append("prod user-service config must set sms_otp.pass_through_enabled: false")
    if DEBT_ID in prod:
        failures.append("prod user-service config must not carry SMS OTP pass-through debt id")

    for env in ("alpha", "beta", "gamma"):
        text = read(USER_CONFIGS / env / "config.yaml")
        enabled = value(text, "pass_through_enabled") == "true"
        if enabled:
            if value(text, "pass_through_debt_id") != DEBT_ID:
                failures.append(f"{env}: missing pass_through_debt_id {DEBT_ID}")
            if not value(text, "pass_through_owner"):
                failures.append(f"{env}: pass_through_owner is required")
            if not value(text, "pass_through_expires_at"):
                failures.append(f"{env}: pass_through_expires_at is required")
        if "https://" not in value(text, "external_interaction_base_url"):
            failures.append(f"{env}: external_interaction_base_url must default to https")

    default = read(USER_CONFIGS / "default" / "config.yaml")
    if value(default, "pass_through_enabled") != "false":
        failures.append("default user-service config must keep sms_otp.pass_through_enabled false")
    if "https://" not in value(default, "external_interaction_base_url"):
        failures.append("default external_interaction_base_url must use https")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("verify_sms_otp_pass_through_gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
