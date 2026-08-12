#!/usr/bin/env python3
"""Collect authoritative post-100 Prod soak SLO, alert, and health observations."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.render_release_lifecycle_receipts import (
    _validate_receipt_readback,
    _window_seconds,
)
from quwoquan_ops.cli import stackctl


def _load_object(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    return payload


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _wait_for_authoritative_window(
    terminal_readback: dict[str, Any],
    *,
    service: str,
    required_seconds: int,
) -> None:
    receipt = _validate_receipt_readback(terminal_readback, service=service)
    if (
        receipt.get("triggerStage") != "100"
        or receipt.get("stage") != "100"
        or receipt.get("decision") != "continue"
        or receipt.get("rollbackOutcome") != "not_triggered"
    ):
        raise ValueError("100 hosted receipt is not a successful rollout")
    started_at = dt.datetime.fromisoformat(
        str(receipt["verifiedAt"]).replace("Z", "+00:00")
    )
    remaining = (
        started_at + dt.timedelta(seconds=required_seconds) - _utc_now()
    ).total_seconds()
    if remaining > required_seconds + 300:
        raise ValueError("100 hosted receipt is future-dated")
    if remaining > 0:
        time.sleep(remaining)


def _read_alertmanager(base_url: str) -> dict[str, Any]:
    url = (
        base_url.rstrip("/")
        + "/api/v2/alerts?"
        + urllib.parse.urlencode(
            {"active": "true", "silenced": "false", "inhibited": "false"}
        )
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Alertmanager soak readback failed: {error}") from error
    if not isinstance(payload, list):
        raise RuntimeError("Alertmanager soak readback did not return an alert list")
    active = [
        item
        for item in payload
        if isinstance(item, dict)
        and isinstance(item.get("status"), dict)
        and item["status"].get("state") == "active"
    ]
    if active:
        raise RuntimeError(
            f"Alertmanager soak readback has {len(active)} active firing alerts"
        )
    return {
        "schema": "prod-alertmanager-soak-observation",
        "source": "alertmanager",
        "queriedAt": _utc_now().isoformat().replace("+00:00", "Z"),
        "status": "passed",
        "activeFiring": 0,
    }


def collect(
    *,
    full_readback_path: Path,
    service: str,
    prometheus_service: str,
    prometheus_url: str,
    alertmanager_url: str,
    soak_policy_path: Path,
    health_report_dir: Path,
    slo_output: Path,
    alerts_output: Path,
) -> None:
    policy = yaml.safe_load(soak_policy_path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or not isinstance(policy.get("readback"), dict):
        raise ValueError("soak policy is invalid")
    soak_window = str(
        policy["readback"].get("post_100_soak_window") or ""
    ).strip()
    required_seconds = _window_seconds(soak_window)
    _wait_for_authoritative_window(
        _load_object(full_readback_path, "full hosted readback"),
        service=service,
        required_seconds=required_seconds,
    )

    health_report_dir.mkdir(parents=True, exist_ok=True)
    health = subprocess.run(
        [
            sys.executable,
            str(ROOT / "quwoquan_ops/cli/stackctl.py"),
            "health",
            "--target",
            "prod-hosted",
            "--scope",
            "full",
            "--report-dir",
            str(health_report_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if health.returncode != 0:
        raise RuntimeError(
            health.stderr.strip()
            or health.stdout.strip()
            or "full prod-hosted health failed"
        )
    deadline_epoch = int(time.time()) + 120
    slo = stackctl._read_prometheus_slo(
        prometheus_url,
        prometheus_service,
        deadline_epoch=deadline_epoch,
        window_override=soak_window,
    )
    alerts = _read_alertmanager(alertmanager_url)
    _write_json(slo_output, slo)
    _write_json(alerts_output, alerts)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-readback", required=True, type=Path)
    parser.add_argument("--service", default="release")
    parser.add_argument("--prometheus-service", default="")
    parser.add_argument("--prometheus-url", required=True)
    parser.add_argument("--alertmanager-url", required=True)
    parser.add_argument("--soak-policy", required=True, type=Path)
    parser.add_argument("--health-report-dir", required=True, type=Path)
    parser.add_argument("--slo-output", required=True, type=Path)
    parser.add_argument("--alerts-output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        collect(
            full_readback_path=args.full_readback,
            service=args.service,
            prometheus_service=args.prometheus_service,
            prometheus_url=args.prometheus_url,
            alertmanager_url=args.alertmanager_url,
            soak_policy_path=args.soak_policy,
            health_report_dir=args.health_report_dir,
            slo_output=args.slo_output,
            alerts_output=args.alerts_output,
        )
    except (OSError, RuntimeError, ValueError, yaml.YAMLError) as error:
        print(f"collect_prod_soak_observations: GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
