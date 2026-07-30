from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_hls_cmaf_packaging_fallback_has_metric_dashboard_and_alert() -> None:
    metric_source = (
        ROOT
        / "quwoquan_service/services/content-service/internal/content/post/"
        "infrastructure/content/media/processing/metrics.go"
    ).read_text(encoding="utf-8")
    alerts = (
        ROOT
        / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
    ).read_text(encoding="utf-8")
    dashboard = (
        ROOT
        / "quwoquan_ops/observability/monitoring/dashboards/l2_content_objects.json"
    ).read_text(encoding="utf-8")

    metric = "content_media_hls_cmaf_packaging_total"
    assert metric in metric_source
    assert metric in alerts
    assert "ContentMediaHLSCMAFPackagingFallbackRateHigh" in alerts
    assert 'result="fallback_progressive"' in alerts
    assert metric in dashboard
