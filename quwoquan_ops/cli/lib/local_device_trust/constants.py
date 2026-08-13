"""local_device_trust 包共享常量（原单文件顶部常量逐字搬移）。"""

from __future__ import annotations

import re
from pathlib import Path

SCHEMA = "stackctl-local-device-system-trust"
PLATFORMS = ("ios-simulator", "android-emulator")
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
# 原单文件为 parents[3]；包形态多一层目录，改为 parents[4]，值保持仓库根不变。
_ROOT = Path(__file__).resolve().parents[4]
_ANDROID_CONSCRYPT_CACERTS = "/apex/com.android.conscrypt/cacerts"
_ANDROID_LEGACY_CACERTS = "/system/etc/security/cacerts"
_ANDROID_TRUST_STAGE_ROOT = "/data/local/tmp/quwoquan-device-trust"
