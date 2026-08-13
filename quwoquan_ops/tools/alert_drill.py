#!/usr/bin/env python3
"""告警链路开火演练（可重复执行的一次性脚本，不建常驻平台）。

验证链路：合成告警 → Alertmanager 接收 → （可选）platform-ops 回流列表。
业界标准做法：直接向 Alertmanager v2 API 注入带演练标记的合成告警，
不影响真实规则求值；演练告警 20 分钟自动过期。

用法：
  ALERTMANAGER_URL=http://127.0.0.1:9093 python3 quwoquan_ops/tools/alert_drill.py
  可选：PLATFORM_OPS_URL + PLATFORM_OPS_BEARER 校验控制面回流。

证据写入 .qwq_output/env/repo/runs/alert-drill/<UTC时间戳>.json。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / ".qwq_output/env/repo/runs/alert-drill"
DRILL_ALERT_NAME = "DrillSyntheticAlert"


def _post_json(url: str, payload: object, headers: dict[str, str]) -> int:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status


def _get_json(url: str, headers: dict[str, str]) -> object:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    alertmanager_url = os.environ.get("ALERTMANAGER_URL", "").strip().rstrip("/")
    if not alertmanager_url:
        print("FAIL: ALERTMANAGER_URL is required (e.g. http://127.0.0.1:9093)")
        return 2
    now = datetime.now(timezone.utc)
    evidence: dict[str, object] = {
        "startedAt": now.isoformat(),
        "alertmanagerUrl": alertmanager_url,
        "alertName": DRILL_ALERT_NAME,
    }

    synthetic_alert = [
        {
            "labels": {
                "alertname": DRILL_ALERT_NAME,
                "severity": "warning",
                "drill": "true",
                "service": "alert-drill",
            },
            "annotations": {
                "summary": "告警链路演练合成告警（自动过期，无需处置）",
                "runbook_url": "quwoquan_ops/runbooks/slo_burn_rate.md",
            },
            "startsAt": now.isoformat(),
            "endsAt": (now + timedelta(minutes=20)).isoformat(),
        }
    ]
    try:
        status = _post_json(f"{alertmanager_url}/api/v2/alerts", synthetic_alert, {})
    except (OSError, urllib.error.URLError) as error:
        print(f"FAIL: cannot reach Alertmanager: {error}")
        return 1
    evidence["injectStatus"] = status
    print(f"injected synthetic alert (http {status}); polling active alerts ...")

    received = False
    for _ in range(10):
        time.sleep(2)
        try:
            active = _get_json(f"{alertmanager_url}/api/v2/alerts?filter=drill%3D%22true%22", {})
        except (OSError, urllib.error.URLError):
            continue
        if isinstance(active, list) and any(
            item.get("labels", {}).get("alertname") == DRILL_ALERT_NAME for item in active
        ):
            received = True
            break
    evidence["alertmanagerReceived"] = received

    platform_url = os.environ.get("PLATFORM_OPS_URL", "").strip().rstrip("/")
    if platform_url:
        bearer = os.environ.get("PLATFORM_OPS_BEARER", "").strip()
        headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
        ingested = False
        for _ in range(15):
            time.sleep(4)
            try:
                payload = _get_json(
                    f"{platform_url}/control-plane/platform/alerts/active", headers
                )
            except (OSError, urllib.error.URLError):
                continue
            body = json.dumps(payload, ensure_ascii=False)
            if DRILL_ALERT_NAME in body:
                ingested = True
                break
        evidence["platformOpsIngested"] = ingested
    else:
        evidence["platformOpsIngested"] = "skipped: PLATFORM_OPS_URL not configured"

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    evidence_path = EVIDENCE_DIR / f"{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        printable_path = evidence_path.relative_to(REPO_ROOT)
    except ValueError:
        printable_path = evidence_path
    print(f"evidence: {printable_path}")

    if not received:
        print("FAIL: Alertmanager did not report the synthetic alert as active")
        return 1
    if platform_url and evidence["platformOpsIngested"] is False:
        print("FAIL: platform-ops active alerts did not ingest the synthetic alert")
        return 1
    print("PASS: alert drill delivered end to end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
