#!/usr/bin/env python3
"""Verify remote test entrypoints have the required environment wiring."""

from __future__ import annotations

import argparse
import os
import shutil
import sys


class Failures:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        self.items.append(message)

    def exit_code(self) -> int:
        if not self.items:
            print("[verify] OK: remote test environment wiring checked")
            return 0
        for item in self.items:
            print(f"[verify] FAIL: {item}", file=sys.stderr)
        return 1


def env_prefix(env_name: str) -> str:
    return env_name.upper().replace("-", "_")


def require_var(name: str, failures: Failures) -> None:
    if not os.getenv(name):
        failures.add(f"missing required environment variable: {name}")


def require_token(prefix: str, failures: Failures) -> None:
    scoped_name = f"{prefix}_TEST_AUTH_TOKEN"
    if os.getenv(scoped_name) or os.getenv("TEST_AUTH_TOKEN"):
        return
    failures.add(f"missing auth token: set {scoped_name} or TEST_AUTH_TOKEN")


def verify_api_integration(env_name: str, failures: Failures) -> None:
    prefix = env_prefix(env_name)
    require_var(f"{prefix}_BASE_URL", failures)
    require_var(f"{prefix}_PRODUCT_OPS_BASE_URL", failures)
    require_token(prefix, failures)


def verify_user_acceptance(target: str, failures: Failures) -> None:
    if target != "prod-hosted":
        return
    require_var("PROD_BASE_URL", failures)
    require_var("PROD_PRODUCT_OPS_BASE_URL", failures)
    require_token("PROD", failures)
    if os.getenv("USER_ACCEPTANCE_DRY_RUN") == "1":
        return
    if shutil.which("patrol") is None:
        failures.add("patrol CLI not found; install patrol or set USER_ACCEPTANCE_DRY_RUN=1")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("api_integration", "user_acceptance"), required=True)
    parser.add_argument("--env", default="gamma")
    parser.add_argument("--target", default="gamma-local")
    args = parser.parse_args()

    failures = Failures()
    if args.suite == "api_integration":
        verify_api_integration(args.env, failures)
    else:
        verify_user_acceptance(args.target, failures)
    return failures.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
