#!/usr/bin/env python3
"""Ratchet gate for cold-start TTID baseline JSON artifacts.

Validates committed baseline structure and blocks regressions where the latest
baseline P50 firstVisibleMs exceeds the ratchet by more than 10%.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_DIR = ROOT / "quwoquan_app"
DEFAULT_RATCHET = ROOT / "specs/gates/startup_ttid_ratchet_baseline.json"
DEFAULT_BASELINE = DEFAULT_RATCHET
REQUIRED_ACCEPTANCE = (
    ROOT
    / "specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/acceptance.yaml"
)
REQUIRED_TESTS = (
    APP_DIR / "test/local_contract/app/startup_ttid__local_contract_test.dart",
    APP_DIR / "test/local_contract/app/startup_deferred_router__local_contract_test.dart",
    APP_DIR / "test/local_contract/app/app_startup_welcome__local_contract_test.dart",
    APP_DIR / "test/local_contract/app/startup_native_launch_screen__local_contract_test.dart",
    APP_DIR / "test/local_contract/ui/welcome/welcome_screen__local_contract_test.dart",
    APP_DIR / "test/local_contract/ui/welcome/welcome_motion_golden__local_contract_test.dart",
    APP_DIR / "test/local_contract/app/startup_probe_parser__local_contract_test.py",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_baseline_shape(raw: dict) -> list[str]:
    errors: list[str] = []
    for key in ("schemaVersion", "metric", "p50"):
        if key not in raw:
            errors.append(f"missing key: {key}")
    p50 = raw.get("p50")
    if not isinstance(p50, dict) or "firstVisibleMs" not in p50:
        errors.append("p50.firstVisibleMs missing")
    sla = raw.get("slaTargetRelease")
    if isinstance(sla, dict):
        for key in ("ttidP50Ms", "ttidP95Ms"):
            if key not in sla:
                errors.append(f"slaTargetRelease.{key} missing")
    return errors


def validate_commercial_uat(raw: dict) -> list[str]:
    errors: list[str] = []
    samples = raw.get("samples")
    if not isinstance(samples, list) or len(samples) < 20:
        errors.append("commercial UAT requires at least 20 samples")
        return errors
    if raw.get("deviceKind") != "true_device":
        errors.append("commercial mobile UAT requires deviceKind=true_device")

    p95 = raw.get("p95") if isinstance(raw.get("p95"), dict) else {}
    if not isinstance(p95.get("firstVisibleMs"), int) or p95["firstVisibleMs"] > 2000:
        errors.append("p95.firstVisibleMs must be <= 2000")
    if (
        not isinstance(p95.get("shellFirstPaintMs"), int)
        or p95["shellFirstPaintMs"] > 3000
    ):
        errors.append("p95.shellFirstPaintMs must be <= 3000")

    valid_exit_reasons = {
        "ready_primary",
        "ready_replay",
        "degraded",
        "deadline",
        "reduced_motion",
    }
    for index, sample in enumerate(samples, start=1):
        welcome_exit = sample.get("welcomeExitMs")
        if not isinstance(welcome_exit, int) or welcome_exit > 6000:
            errors.append(f"sample {index} welcomeExitMs must be <= 6000")
        if sample.get("exitReason") not in valid_exit_reasons:
            errors.append(f"sample {index} exitReason missing or invalid")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--ratchet", default=str(DEFAULT_RATCHET))
    parser.add_argument(
        "--regression-ratio",
        type=float,
        default=1.10,
        help="Fail when current P50 exceeds ratchet P50 times this ratio.",
    )
    parser.add_argument("--write-ratchet", action="store_true")
    parser.add_argument(
        "--commercial-uat",
        action="store_true",
        help="Require true-device 20-run TTID, 3s shell P95, and 6s hard exit evidence.",
    )
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    ratchet_path = Path(args.ratchet)

    missing_tests = [str(path) for path in REQUIRED_TESTS if not path.is_file()]
    if missing_tests:
        print("FAIL: missing required startup tests:", file=sys.stderr)
        for item in missing_tests:
            print(f"  - {item}", file=sys.stderr)
        return 1

    if not REQUIRED_ACCEPTANCE.is_file():
        print(f"FAIL: missing acceptance: {REQUIRED_ACCEPTANCE}", file=sys.stderr)
        return 1

    if not baseline_path.is_file():
        print(f"FAIL: missing baseline: {baseline_path}", file=sys.stderr)
        return 1

    baseline = load_json(baseline_path)
    shape_errors = validate_baseline_shape(baseline)
    if shape_errors:
        print(f"FAIL: invalid baseline shape: {baseline_path}", file=sys.stderr)
        for item in shape_errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    if args.commercial_uat:
        commercial_errors = validate_commercial_uat(baseline)
        if commercial_errors:
            print("FAIL: commercial startup UAT evidence incomplete:", file=sys.stderr)
            for item in commercial_errors:
                print(f"  - {item}", file=sys.stderr)
            return 1

    current_p50 = baseline.get("p50", {}).get("firstVisibleMs")
    if current_p50 is None:
        print("FAIL: baseline p50.firstVisibleMs is null", file=sys.stderr)
        return 1

    if args.write_ratchet:
        ratchet_path.parent.mkdir(parents=True, exist_ok=True)
        ratchet_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "metric": "brandWelcomeFirstVisibleMs",
                    "p50": {"firstVisibleMs": current_p50},
                    "sourceBaseline": str(baseline_path.relative_to(ROOT)),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Wrote ratchet baseline: {ratchet_path}")
        return 0

    if not ratchet_path.is_file():
        print(f"FAIL: missing ratchet baseline: {ratchet_path}", file=sys.stderr)
        print("Run with --write-ratchet after capturing a trusted baseline.", file=sys.stderr)
        return 1

    ratchet = load_json(ratchet_path)
    ratchet_p50 = ratchet.get("p50", {}).get("firstVisibleMs")
    if ratchet_p50 is None:
        print("FAIL: ratchet p50.firstVisibleMs missing", file=sys.stderr)
        return 1

    allowed = int(ratchet_p50 * args.regression_ratio)
    if int(current_p50) > allowed:
        print(
            "FAIL: TTID P50 regression "
            f"{current_p50}ms > allowed {allowed}ms "
            f"(ratchet {ratchet_p50}ms * {args.regression_ratio})",
            file=sys.stderr,
        )
        return 1

    sla_p50 = baseline.get("slaTargetRelease", {}).get("ttidP50Ms")
    if isinstance(sla_p50, int) and int(current_p50) > sla_p50:
        print(
            f"WARN: TTID SLA not met (P50 {current_p50}ms > target {sla_p50}ms); "
            "ratchet gate still green.",
            file=sys.stderr,
        )

    print(
        json.dumps(
            {
                "passed": True,
                "baseline": str(baseline_path),
                "ratchet": str(ratchet_path),
                "currentP50FirstVisibleMs": current_p50,
                "ratchetP50FirstVisibleMs": ratchet_p50,
                "allowedP50FirstVisibleMs": allowed,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
