"""启动环境矩阵门禁的环境/设备矩阵常量与 schema 标识（唯一定义处）。

注意：本模块位于 ``scripts/runtime/platform/startup_environment_matrix/`` 包内，
比原 ``verify_startup_environment_matrix.py`` 深一层；``_SCRIPTS_ROOT`` 通过向上
探测 ``scripts/_common/paths.py`` 定位，不依赖固定 parents 索引，指向值不变。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT  # noqa: E402,F401


APP_DIR = APP_ROOT
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
RUNTIME_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}
RUNTIME_CASES = (
    ("alpha", "alpha-local"),
    ("beta", "beta-local"),
    ("gamma", "gamma-local"),
    ("prod", "prod-hosted"),
)
DEVICE_PROFILES = {
    "alpha-local": (
        ("android", "simulator", "android-simulator"),
        ("android", "true_device", "android-physical"),
        ("ios", "simulator", "ios-simulator"),
    ),
    "beta-local": (
        ("android", "simulator", "android-simulator"),
        ("android", "true_device", "android-physical"),
        ("ios", "simulator", "ios-simulator"),
    ),
    "gamma-local": (
        ("android", "simulator", "android-simulator"),
        ("android", "true_device", "android-physical"),
        ("ios", "simulator", "ios-simulator"),
    ),
    "prod-hosted": (
        ("android", "true_device", "android-physical"),
        ("ios", "physical", "ios-physical"),
    ),
}
REQUIRED_DEFINES = {
    "APP_RUNTIME_ENV",
    "CLOUD_GATEWAY_BASE_URL",
    "APP_LEGAL_BASE_URL",
    "PUBLIC_WEB_BASE_URL",
    "MEDIA_AVATAR_CDN_BASE_URL",
    "MEDIA_IMAGE_CDN_BASE_URL",
    "MEDIA_VIDEO_CDN_BASE_URL",
    "MEDIA_UPLOAD_BASE_URL",
    "RTC_MEDIA_CONNECTION_URL",
}
SPEC_REFS = (
    "specs/feature-tree/spec.md#uat-003",
    (
        "specs/feature-tree/runtime/runtime-data-engineering/"
        "spec.md#sit-001"
    ),
    (
        "specs/feature-tree/runtime/runtime-client-foundation/"
        "cold-start-performance/spec.md#gwt-004"
    ),
    (
        "specs/feature-tree/runtime/runtime-config/"
        "environment-topology-and-packaging/spec.md#gwt-001"
    ),
    (
        "specs/feature-tree/runtime/runtime-config/"
        "environment-topology-and-packaging/spec.md#gwt-002"
    ),
)
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
RUNTIME_EVIDENCE_SCHEMA = "qwq.startup-runtime-evidence"
READBACK_EVIDENCE_SCHEMA = "qwq.app-core-readback-evidence"
OBSERVABILITY_EVIDENCE_SCHEMA = "qwq.startup-observability-readback"
