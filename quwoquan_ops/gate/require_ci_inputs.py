#!/usr/bin/env python3
"""Fail closed when a GitHub workflow is missing declared environment inputs."""

from __future__ import annotations

import argparse
import os
import re


INPUT_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
SCOPE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", required=True)
    parser.add_argument("names", nargs="+")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not SCOPE_RE.fullmatch(args.scope):
        print("::error::GATE_BLOCK: CI input scope is invalid")
        return 2
    invalid_names = [name for name in args.names if not INPUT_NAME_RE.fullmatch(name)]
    if invalid_names:
        print("::error::GATE_BLOCK: CI input name is invalid")
        return 2
    missing = [name for name in args.names if not os.environ.get(name, "").strip()]
    if missing:
        print(
            "::error::GATE_BLOCK: "
            f"{args.scope} required inputs are missing: {','.join(missing)}"
        )
        return 2
    print(f"[require_ci_inputs] OK scope={args.scope} inputs={len(args.names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
