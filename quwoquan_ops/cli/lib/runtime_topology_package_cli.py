#!/usr/bin/env python3
"""CLI presentation for runtime topology package validation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
import shlex
from typing import Any


def main(
    load_package: Callable[..., dict[str, Any]],
    package_error: type[Exception],
) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--format", choices=("json", "shell"), default="json")
    args = parser.parse_args()
    try:
        payload = load_package(
            Path(args.candidate_root),
            environment=args.environment,
            target=args.target,
            workload=args.workload,
        )
    except (OSError, package_error) as exc:
        parser.exit(2, f"GATE_BLOCK: {exc}\n")
    serializable = {
        **payload,
        "composeFiles": [str(path) for path in payload["composeFiles"]],
        "policyFile": str(payload["policyFile"]),
    }
    if args.format == "json":
        print(json.dumps(serializable, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "QWQ_RUNTIME_TOPOLOGY_COMPOSE_FILES="
            + shlex.quote("\n".join(serializable["composeFiles"]))
        )
        print(
            "QWQ_RUNTIME_TOPOLOGY_POLICY_FILE="
            + shlex.quote(serializable["policyFile"])
        )
        print(
            "QWQ_RUNTIME_TOPOLOGY_DIGEST="
            + shlex.quote(str(serializable["topologyDigest"]))
        )
    return 0
