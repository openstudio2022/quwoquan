"""启动首帧探针的路径、默认目标与阈值常量（唯一定义处）。

注意：本模块位于 ``scripts/device/startup_first_frame/`` 包内，比原
``verify_startup_first_frame.py`` 深一层，因此 ``APP_DIR`` 使用
``parents[3]``（原入口为 ``parents[2]``），指向值保持不变。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[3]
ROOT = APP_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.app_identity import application_id_for  # noqa: E402

# 探针默认针对 alpha Debug 构建；App 身份按环境 × BuildMode 派生，不写字面值。
# Android 类的 FQCN 固定在 namespace 下，与 applicationId 后缀无关。
_ANDROID_CLASS_NAMESPACE = "com.quwoquan.quwoquan_app"
DEFAULT_ANDROID_PACKAGE = application_id_for("android", "alpha", "debug")
DEFAULT_ANDROID_ACTIVITY = (
    f"{DEFAULT_ANDROID_PACKAGE}/{_ANDROID_CLASS_NAMESPACE}.StartupGateActivity"
)
DEFAULT_ANDROID_MAIN_ACTIVITY = (
    f"{DEFAULT_ANDROID_PACKAGE}/{_ANDROID_CLASS_NAMESPACE}.MainActivity"
)
DEFAULT_ANDROID_APK_DIR = APP_DIR / "build/app/outputs/flutter-apk"
DEFAULT_ANDROID_APK = DEFAULT_ANDROID_APK_DIR / "app-debug.apk"
DEFAULT_ANDROID_APK_METADATA = APP_DIR / "build/app/outputs/apk/debug/output-metadata.json"
DEFAULT_IOS_BUNDLE = application_id_for("ios", "alpha", "debug")
DEFAULT_IOS_APP = APP_DIR / "build/ios/iphonesimulator/Runner.app"
DEFAULT_OUTPUT_DIR = (
    Path(os.environ.get("QWQ_OUTPUT_ROOT", ROOT / ".qwq_output"))
    / "env"
    / "alpha"
    / "runs"
    / "startup_first_frame"
    / "probe"
)
FORBIDDEN_NATIVE_WELCOME_LOG_PATTERNS = (
    "android_startup_welcome_first_draw",
    "android_startup_activity_handoff",
    "android_native_welcome_first_draw",
    "android_native_welcome_host_installed",
    "android_flutter_welcome_ready",
    "android_native_welcome_completion_received",
    "android_flutter_welcome_ready_timeout",
)
ANDROID_ANR_OBSERVATION_WINDOW_MS = 7_000
