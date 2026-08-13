"""启动首帧设备探针实现包。

唯一稳定入口是 ``quwoquan_app/scripts/device/verify_startup_first_frame.py``
（薄壳 re-export）；本包按职责切分：

- ``context``：路径、默认目标与阈值常量。
- ``execution``：子进程执行、sha256 与构建溯源。
- ``screenshot_analysis``：截图分析与异常帧判定。
- ``startup_log``：启动日志解析、watchdog 证据与终态分类。
- ``android_evidence``：Android launcher/任务栈/Gate→Main/APK 证据。
- ``metrics``：多轮样本 p50/p95 汇总。
- ``android_capture``：Android 冷启动采集与判定。
- ``ios_capture``：iOS 冷启动采集与判定。
- ``cli``：argparse 与 main。
"""
from __future__ import annotations

from .android_capture import capture_android  # noqa: F401
from .android_evidence import (  # noqa: F401
    android_device_kind,
    android_fresh_startup_log_evidence,
    android_gate_main_order_evidence,
    android_gate_main_order_observed,
    android_log_after_baseline,
    android_package_anr_evidence,
    native_launch_visual_provenance,
    normalize_android_component,
    parse_android_launcher_resolution,
    parse_android_task_snapshot,
    read_android_device_abi,
    resolve_android_apk,
    resolve_android_launch_resource_profile,
)
from .cli import (  # noqa: F401
    analyze_existing_screenshots,
    build_arg_parser,
    main,
    parse_offsets,
)
from .context import (  # noqa: F401
    ANDROID_ANR_OBSERVATION_WINDOW_MS,
    APP_DIR,
    DEFAULT_ANDROID_ACTIVITY,
    DEFAULT_ANDROID_APK,
    DEFAULT_ANDROID_APK_DIR,
    DEFAULT_ANDROID_APK_METADATA,
    DEFAULT_ANDROID_MAIN_ACTIVITY,
    DEFAULT_ANDROID_PACKAGE,
    DEFAULT_IOS_APP,
    DEFAULT_IOS_BUNDLE,
    DEFAULT_OUTPUT_DIR,
    FORBIDDEN_NATIVE_WELCOME_LOG_PATTERNS,
    ROOT,
)
from .execution import build_provenance, run, sha256_file  # noqa: F401
from .ios_capture import capture_ios  # noqa: F401
from .metrics import (  # noqa: F401
    build_platform_samples,
    percentile,
    summarize_metric_runs,
    summarize_startup_samples,
)
from .screenshot_analysis import (  # noqa: F401
    ScreenshotAnalysis,
    analyze_screenshot,
    detect_native_static_petal_mismatch,
    detect_prolonged_system_blue,
    detect_repeated_splash,
    first_branded_offset_ms,
    resolve_android_first_visible_ms,
    resolve_first_visible_ms,
)
from .startup_log import (  # noqa: F401
    classify_startup_terminal,
    extract_dart_startup_attempts,
    extract_startup_watchdog_evidence,
    parse_qwqstartup_log,
    parse_startup_sequence_log,
)
