"""ops 事件 schema 完整性门禁的期望闭集（常量真相源）。

从 verify_ops_event_schema_completeness.py 迁出的纯常量段：公共字段、
必需体验事件、允许的聚合/来源轨/门户级别与命名模式。入口 re-export
全部符号，判定逻辑仍在入口模块。
"""
from __future__ import annotations

EXPECTED_COMMON_FIELDS = [
    "logType",
    "eventType",
    "sessionId",
    "pageName",
    "occurredAt",
    "deviceManufacturer",
    "deviceModel",
    "appVersion",
    "networkClass",
]
EXPECTED_CONTEXT_EXTENSIONS = ["devicePlatform"]
FORBIDDEN_LEGACY_FIELDS = {
    "eventVersion",
    "eventId",
    "eventName",
    "priority",
    "producer",
    "payload",
    "metrics",
    "userIdHash",
}
EVENT_STORAGE_LOGSTORE_ROLES = (
    "raw",
    "startup_diagnostic",
    "runtime_diagnostic",
    "aggregate",
)
REQUIRED_EXPERIENCE_EVENTS = {
    "app_anr_outcome": {
        "required_extensions": {"detectionSource", "result"},
        "optional_extensions": {"durationMs"},
    },
    "app_frame_jank_outcome": {
        "required_extensions": {
            "sampledFrames",
            "jankyFrames",
            "worstFrameMs",
            "worstBuildFrameMs",
            "worstRasterFrameMs",
            "jankThresholdMs",
            "result",
        },
        "optional_extensions": {"surfaceId", "channelId"},
    },
    "page_first_usable": {
        "required_extensions": {"durationMs", "terminalState"},
        "optional_extensions": {"surfaceId", "failReasonCode"},
    },
    "page_error_outcome": {
        "required_extensions": {
            "surfaceId",
            "errorCode",
            "recoveryAction",
            "result",
        },
        "optional_extensions": {"action", "durationMs"},
    },
}
REQUIRED_APP_EXPERIENCE_METRIC_IDS = {
    "app_anr_rate",
    "app_jank_frame_rate",
    "page_first_usable_p95_ms",
    "page_error_recovery_rate",
}
ALLOWED_GOLDEN_AGGREGATIONS = {
    "event_ratio",
    "unique_session_ratio",
    "percentile_p50",
    "percentile_p95",
    "percentile_p99",
    "sum",
    "sum_ratio",
    "count",
}
ALLOWED_SERIES_AGGREGATIONS = {"series_rate_ratio"}
ALLOWED_READFACE_AGGREGATIONS = {"readface_ratio"}
READFACE_FIELD_PATTERN = r"[a-z][a-zA-Z0-9]*"
ALLOWED_SOURCE_TRACKS = {
    "product_telemetry",
    "behavior_attribution",
    "domain_fact_readface",
}
ALLOWED_PORTAL_LEVELS = {"L1", "L2"}
ALLOWED_TARGET_OPERATORS = {
    "less_than",
    "less_than_or_equal",
    "greater_than",
    "greater_than_or_equal",
}
SERIES_NAME_PATTERN = r"[a-z][a-z0-9_]*"
