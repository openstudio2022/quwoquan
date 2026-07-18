"""Android SDK discovery shared by device-matrix runners and evidence capture."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_android_debug_bridge(
    *,
    environ: dict[str, str] | None = None,
    home_dir: Path | None = None,
) -> str | None:
    """Resolve adb from PATH, explicit SDK settings, or standard SDK locations."""

    from_path = shutil.which("adb")
    if from_path:
        return from_path
    environment = environ if environ is not None else os.environ
    home = home_dir if home_dir is not None else Path.home()
    executable = "adb.exe" if os.name == "nt" else "adb"
    sdk_roots = [
        environment.get("ANDROID_SDK_ROOT", "").strip(),
        environment.get("ANDROID_HOME", "").strip(),
        str(home / "Library" / "Android" / "sdk"),
        str(home / "Android" / "Sdk"),
    ]
    for sdk_root in sdk_roots:
        if not sdk_root:
            continue
        candidate = Path(sdk_root) / "platform-tools" / executable
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None
