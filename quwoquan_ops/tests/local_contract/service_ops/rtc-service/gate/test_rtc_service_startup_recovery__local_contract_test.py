#!/usr/bin/env python3
# spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
"""rtc-service 的 Compose 启动恢复只承接瞬态 provider 竞态。"""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[6]
RTC_COMPOSE = ROOT / "quwoquan_service/services/rtc-service/deploy/compose.yaml"


def _rtc_service() -> dict[str, object]:
    compose = yaml.safe_load(RTC_COMPOSE.read_text(encoding="utf-8"))
    return compose["services"]["rtc-service"]


def test_rtc_startup_waits_for_provider_health_and_writable_primary() -> None:
    service = _rtc_service()

    assert service["depends_on"] == {
        "mongodb": {"condition": "service_healthy"},
        "mongo-init": {"condition": "service_completed_successfully"},
        "redis": {"condition": "service_healthy"},
    }


def test_rtc_startup_retries_only_failed_processes_with_a_finite_budget() -> None:
    service = _rtc_service()

    assert service["restart"] == "on-failure:5"
    assert service["healthcheck"]["test"] == [
        "CMD-SHELL",
        "wget -qO- http://127.0.0.1:18083/healthz >/dev/null 2>&1",
    ]
