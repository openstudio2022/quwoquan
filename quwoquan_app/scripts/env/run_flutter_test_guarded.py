#!/usr/bin/env python3
"""Run Flutter tests under a shared lock and native-asset warmup.

This helper fixes two recurring environment failures:
- callers running from the repository root instead of `quwoquan_app`
- concurrent Flutter invocations racing on startup lock / native assets

Usage:
  python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py <flutter test args...>
"""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
LOCK_FILE = APP_ROOT / ".dart_tool" / "flutter_test.lock"
RETRY_MARKERS = (
  "Waiting for another flutter command to release the startup lock",
  "Building native assets failed",
  "Connection closed while receiving data",
  "HttpException",
  "release-assets.githubusercontent.com",
  "PathNotFoundException",
)
WARMUP_TEMPLATE = """import 'package:sqlite3/sqlite3.dart';

void main() {
  final db = sqlite3.openInMemory();
  db.execute('select 1;');
  db.dispose();
  print('sqlite3-prewarm-ok ${sqlite3.version}');
}
"""


def _run_checked(cmd: list[str], *, cwd: Path = APP_ROOT) -> int:
  return subprocess.run(cmd, cwd=str(cwd)).returncode


def _run_flutter_test_with_retries(
  cmd: list[str],
  *,
  cwd: Path = APP_ROOT,
  max_attempts: int = 3,
) -> int:
  for attempt in range(1, max_attempts + 1):
    result = subprocess.run(
      cmd,
      cwd=str(cwd),
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      errors="replace",
    )
    output = result.stdout or ""
    if output:
      print(output, end="" if output.endswith("\n") else "\n")
    if result.returncode == 0:
      return 0
    if attempt >= max_attempts:
      return result.returncode
    matched_markers = [marker for marker in RETRY_MARKERS if marker in output]
    if not matched_markers:
      return result.returncode
    wait_seconds = attempt * 5
    print(
      f"[flutter-test-guard] transient flutter failure, retry {attempt}/{max_attempts - 1} "
      f"after {wait_seconds}s: {', '.join(matched_markers)}",
    )
    time.sleep(wait_seconds)
  return 1


def _ensure_flutter_pub_get() -> None:
  package_config = APP_ROOT / ".dart_tool" / "package_config.json"
  if package_config.exists():
    return
  print("[flutter-test-guard] package_config missing, running flutter pub get")
  rc = _run_checked(["flutter", "pub", "get"])
  if rc != 0:
    raise SystemExit(rc)


def _prewarm_sqlite3() -> None:
  warmup_dir = APP_ROOT / ".dart_tool"
  warmup_dir.mkdir(parents=True, exist_ok=True)
  warmup_file = tempfile.NamedTemporaryFile(
    prefix="sqlite3-prewarm.",
    suffix=".dart",
    dir=str(warmup_dir),
    delete=False,
    mode="w",
    encoding="utf-8",
  )
  try:
    warmup_file.write(WARMUP_TEMPLATE)
    warmup_file.close()
    attempts = 0
    while True:
      rc = _run_checked(["dart", "run", warmup_file.name])
      if rc == 0:
        return
      attempts += 1
      if attempts >= 5:
        raise SystemExit(
          f"[flutter-test-guard] FAIL: sqlite3 native asset prewarm failed after {attempts} attempts"
        )
      time.sleep(attempts * 5)
  finally:
    try:
      os.unlink(warmup_file.name)
    except FileNotFoundError:
      pass


def main(argv: list[str]) -> int:
  args = [arg for arg in argv if arg != "--"]
  if not args:
    print(
      "Usage: python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py <flutter test args...>",
      file=sys.stderr,
    )
    return 2

  LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
  with LOCK_FILE.open("a+") as lock_handle:
    fcntl.flock(lock_handle, fcntl.LOCK_EX)
    _ensure_flutter_pub_get()
    _prewarm_sqlite3()
    flutter_args = [arg for arg in args if arg != "--no-pub"]
    cmd = ["flutter", "test", "--no-pub", *flutter_args]
    print(f"[flutter-test-guard] {' '.join(cmd)}")
    return _run_flutter_test_with_retries(cmd)


if __name__ == "__main__":
  raise SystemExit(main(sys.argv[1:]))
