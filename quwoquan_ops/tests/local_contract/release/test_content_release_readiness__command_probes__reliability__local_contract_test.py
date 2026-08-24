"""content-readiness 命令按 phase 组合探针并 fail-closed 的契约。

由 1000 行硬顶拆分自
test_content_release_readiness__policy__reliability__local_contract_test.py；
测试逐字搬移，_IMPORT_SCOPE_CHECKS 常量随本场景组走。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from quwoquan_ops.cli import stackctl

_IMPORT_SCOPE_CHECKS = [
    {"name": "api-health", "scope": "edge"},
    {"name": "media-edge-health", "scope": "media"},
    {"name": "entity-service", "scope": "content-import"},
]


def test_content_release_readiness__import_ignores_commercial_doctor__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {"exitCode": 0, "details": [], "reportDir": "health"},
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {"checks": list(_IMPORT_SCOPE_CHECKS)},
    )
    monkeypatch.setattr(
        stackctl,
        "command_doctor",
        lambda _args: (_ for _ in ()).throw(
            AssertionError("import must not call doctor")
        ),
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="import",
            env="beta",
            report_dir=str(tmp_path),
            output_format="json",
        )
    )

    assert result["exitCode"] == 0
    assert result["outcome"] == "PASS"
    assert result["phase"] == "import"
    assert result["schema"] == "quwoquan_ops.ship_readiness_receipt"


def test_content_release_readiness__import_ignores_user_availability_blocker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """import 门只消费声明能力的探针结论（DEC-027 后缀链的 bootstrap 前提）。

    health 附带的 user availability 聚合中 release_active 层描述的是「当前
    serving release 的已验证证据」，首个 release 的导入正是为了创造这份证据；
    把导入后才存在的 readiness receipt 倒置为导入前置会形成 bootstrap 死锁。
    """
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {
            "exitCode": 1,
            "details": [
                "user availability/release failed: content release evidence is "
                "unavailable: active release has no valid research readiness "
                "receipt: no receipt exists"
            ],
            "reportDir": "health",
        },
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {"checks": list(_IMPORT_SCOPE_CHECKS)},
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="import",
            env="gamma",
            report_dir=str(tmp_path),
            output_format="json",
        )
    )

    assert result["exitCode"] == 0
    assert result["outcome"] == "PASS"


def test_content_release_readiness__import_keeps_probe_findings_gate_block(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """import 门对真实能力探针失败仍必须 fail-closed，过滤只豁免 availability。"""
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {
            "exitCode": 1,
            "details": ["media/media-edge-health failed: HTTP 502"],
            "reportDir": "health",
        },
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {"checks": list(_IMPORT_SCOPE_CHECKS)},
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="import",
            env="gamma",
            report_dir=str(tmp_path),
            output_format="json",
        )
    )

    assert result["exitCode"] == 2
    assert result["outcome"] == "GATE_BLOCK"
    assert any("media-edge-health" in item for item in result["details"])


def test_content_release_readiness__missing_declared_probe_is_gate_block__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """健康门绿但缺少能力声明的探针时必须 fail-closed，不得凭空 PASS。"""
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {"exitCode": 0, "details": [], "reportDir": "health"},
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {"checks": [{"name": "api-health", "scope": "edge"}]},
    )
    monkeypatch.setattr(
        stackctl,
        "command_doctor",
        lambda _args: (_ for _ in ()).throw(
            AssertionError("import must not call doctor")
        ),
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="import",
            env="beta",
            report_dir=str(tmp_path),
            output_format="json",
        )
    )

    assert result["exitCode"] == 2
    assert result["outcome"] == "GATE_BLOCK"
    assert any("content_services" in item for item in result["details"])


def test_content_release_readiness__commercial_missing_capability_is_gate_block(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {"exitCode": 0, "details": [], "reportDir": "health"},
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {
            "checks": list(_IMPORT_SCOPE_CHECKS)
            + [{"name": "content-feed", "scope": "content-consumer"}]
        },
    )
    monkeypatch.setattr(
        stackctl,
        "command_doctor",
        lambda _args: {"exitCode": 1, "details": ["Elasticsearch is unavailable"]},
    )
    monkeypatch.setattr(
        stackctl,
        "command_product_telemetry_log_sink",
        lambda _args: {
            "exitCode": 2,
            "details": ["Elasticsearch log sink is unavailable"],
        },
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="commercial",
            env="gamma",
            report_dir=str(tmp_path),
            output_format="json",
        )
    )

    assert result["exitCode"] == 2
    assert result["outcome"] == "GATE_BLOCK"
    assert any("telemetry_log_sink" in item for item in result["details"])


def test_content_release_readiness__gamma_controls_elasticsearch_log_sink(
    monkeypatch,
    tmp_path: Path,
) -> None:
    control_calls: list[argparse.Namespace] = []
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {"exitCode": 0, "details": [], "reportDir": "health"},
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {
            "checks": list(_IMPORT_SCOPE_CHECKS)
            + [{"name": "content-feed", "scope": "content-consumer"}]
        },
    )
    monkeypatch.setattr(
        stackctl,
        "command_product_telemetry_log_sink",
        lambda args: control_calls.append(args) or {"exitCode": 0, "details": []},
    )
    monkeypatch.setattr(
        stackctl,
        "command_doctor",
        lambda _args: {"exitCode": 0, "details": []},
    )
    monkeypatch.setattr(
        stackctl,
        "_load_data_release_readiness",
        lambda **_kwargs: (
            {
                "schema": "quwoquan_data.environment_release_readiness",
                "releaseId": "release-001",
                "manifestDigest": "sha256:" + "1" * 64,
                "passed": True,
            },
            tmp_path / "release-readiness.json",
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "_run_release_feed_readback_probe",
        lambda **_kwargs: (
            {
                "schema": "environment-integration-probe-report",
                "status": "passed",
                "checks": [],
            },
            tmp_path / "feed-readback" / "integration-probe.json",
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "_run_release_video_delivery_probe",
        lambda **_kwargs: (
            {
                "schema": "quwoquan_ops.release_video_delivery_evidence",
                "status": "passed",
                "release": {"releaseId": "release-001"},
            },
            tmp_path / "video-delivery" / "report.json",
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "_load_data_release_lifecycle_exit",
        lambda **_kwargs: (
            {
                "schema": "quwoquan_data.environment_release_lifecycle_exit",
                "passed": True,
            },
            tmp_path / "lifecycle-exit.json",
        ),
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="commercial",
            env="gamma",
            report_dir=str(tmp_path),
            output_format="json",
            lifecycle_exit_ref=(
                "env/gamma/runs/release-lifecycle-exit/"
                "release-001/exit-001/lifecycle-exit.json"
            ),
        )
    )

    assert result["exitCode"] == 0
    assert result["outcome"] == "PASS"
    assert result["probes"][-1] == "product-telemetry-log-sink:all"
    assert "release-bound-feed-readback" in result["probes"]
    assert "release-video-delivery" in result["probes"]
    assert "canonical-data-release-lifecycle-exit" in result["probes"]
    assert result["dataRelease"]["feedReadbackEvidenceRef"]
    assert result["dataRelease"]["videoDeliveryEvidenceRef"]
    assert [(item.target, item.action) for item in control_calls] == [
        ("gamma-local", "all")
    ]


def test_content_release_readiness__consumer_skips_commercial_video_delivery(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {"exitCode": 0, "details": [], "reportDir": "health"},
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {
            "checks": list(_IMPORT_SCOPE_CHECKS)
            + [{"name": "content-feed", "scope": "content-consumer"}]
        },
    )
    monkeypatch.setattr(
        stackctl,
        "_load_data_release_readiness",
        lambda **_kwargs: (
            {
                "schema": "quwoquan_data.environment_release_readiness",
                "releaseId": "release-001",
                "readinessPhase": "consumer",
                "passed": True,
            },
            tmp_path / "release-readiness.json",
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "_run_release_feed_readback_probe",
        lambda **_kwargs: (
            {
                "schema": "environment-integration-probe-report",
                "status": "passed",
                "checks": [],
            },
            tmp_path / "feed-readback" / "integration-probe.json",
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "_run_release_video_delivery_probe",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("consumer must not require commercial video delivery")
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "command_doctor",
        lambda _args: (_ for _ in ()).throw(
            AssertionError("consumer must not call commercial doctor")
        ),
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="consumer",
            env="alpha",
            release_id="release-001",
            verify_run_id="verify-001",
            manifest_digest="sha256:" + "1" * 64,
            report_dir=str(tmp_path),
            output_format="json",
        )
    )

    assert result["exitCode"] == 0
    assert "release-bound-feed-readback" in result["probes"]
    assert "release-video-delivery" not in result["probes"]
    assert result["dataRelease"]["videoDeliveryEvidenceRef"] == ""
    assert result["dataRelease"]["videoDelivery"] is None
