"""启动首帧探针的路径、默认目标与阈值常量（唯一定义处）。

注意：本模块位于 ``scripts/device/startup_first_frame/`` 包内，比原
``verify_startup_first_frame.py`` 深一层，因此 ``APP_DIR`` 使用
``parents[3]``（原入口为 ``parents[2]``），指向值保持不变。
"""

from __future__ import annotations

import os
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[3]
ROOT = APP_DIR.parent
DEFAULT_ANDROID_PACKAGE = "com.quwoquan.quwoquan_app"
DEFAULT_ANDROID_ACTIVITY = "com.quwoquan.quwoquan_app/.StartupGateActivity"
DEFAULT_ANDROID_MAIN_ACTIVITY = "com.quwoquan.quwoquan_app/.MainActivity"
DEFAULT_ANDROID_APK_DIR = APP_DIR / "build/app/outputs/flutter-apk"
DEFAULT_ANDROID_APK = DEFAULT_ANDROID_APK_DIR / "app-debug.apk"
DEFAULT_ANDROID_APK_METADATA = APP_DIR / "build/app/outputs/apk/debug/output-metadata.json"
DEFAULT_IOS_BUNDLE = "com.example.quwoquanApp"
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
