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
import selectors
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
DEFAULT_TEST_TIMEOUT_SECONDS = int(
  os.environ.get("FLUTTER_TEST_GUARD_TIMEOUT_SECONDS", "1200")
)
RUNTIME_DEFINE_SCRIPT = APP_ROOT / "scripts" / "env" / "print_app_env_dart_defines.py"


def _cpu_default_concurrency(*, full_local_contract: bool) -> int:
  env = os.environ.get("FLUTTER_TEST_CONCURRENCY", "").strip()
  if env.isdigit():
    return max(1, min(8, int(env)))
  try:
    cores = os.cpu_count() or 2
  except Exception:
    cores = 2
  if full_local_contract:
    # Manual/CI full suite default; commit impacted path sets FLUTTER_TEST_CONCURRENCY=6.
    return max(2, min(4, cores - 1))
  return max(2, min(6, cores - 1))


def _has_concurrency_flag(args: list[str]) -> bool:
  for index, arg in enumerate(args):
    if arg.startswith("--concurrency="):
      return True
    if arg == "--concurrency":
      return index + 1 < len(args)
  return False


def _is_local_contract_target(args: list[str]) -> bool:
  return any(
    arg.rstrip("/") == "test/local_contract" or arg.startswith("test/local_contract/")
    for arg in args
  )


def _with_concurrency(args: list[str]) -> list[str]:
  if _has_concurrency_flag(args):
    return args
  concurrency = _cpu_default_concurrency(
    full_local_contract=_is_local_contract_target(args)
    and not any(arg.endswith("_test.dart") for arg in args),
  )
  return [f"--concurrency={concurrency}", *args]


def _with_shard_flags(args: list[str]) -> list[str]:
  total = os.environ.get("FLUTTER_TEST_TOTAL_SHARDS", "").strip()
  index = os.environ.get("FLUTTER_TEST_SHARD_INDEX", "").strip()
  result = list(args)
  if total.isdigit() and not any(
    arg.startswith("--total-shards=") or arg == "--total-shards" for arg in result
  ):
    result = [f"--total-shards={total}", *result]
  if index.isdigit() and not any(
    arg.startswith("--shard-index=") or arg == "--shard-index" for arg in result
  ):
    result = [f"--shard-index={index}", *result]
  return result


def _with_serial_tag_policy(args: list[str]) -> list[str]:
  """CI parallel shards exclude serial-tagged suites; serial job sets include."""
  mode = os.environ.get("FLUTTER_TEST_SERIAL_MODE", "").strip().lower()
  has_tags = any(
    arg == "--tags" or arg.startswith("--tags=") or arg == "--exclude-tags"
    or arg.startswith("--exclude-tags=")
    for arg in args
  )
  if has_tags or not mode:
    return args
  if mode == "exclude":
    return ["--exclude-tags", "serial", *args]
  if mode == "only":
    return ["--tags", "serial", *args]
  return args


def _run_checked(cmd: list[str], *, cwd: Path = APP_ROOT) -> int:
  return subprocess.run(cmd, cwd=str(cwd)).returncode


def _terminate_process(proc: subprocess.Popen[bytes]) -> None:
  proc.terminate()
  try:
    proc.wait(timeout=5)
  except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait(timeout=5)


def _stream_command(
  cmd: list[str],
  *,
  cwd: Path,
  timeout_seconds: int,
) -> tuple[int, str, bool]:
  proc = subprocess.Popen(
    cmd,
    cwd=str(cwd),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
  )
  assert proc.stdout is not None
  selector = selectors.DefaultSelector()
  selector.register(proc.stdout, selectors.EVENT_READ)
  output_parts: list[str] = []
  started_at = time.monotonic()
  last_output_at = started_at
  timed_out = False
  try:
    while proc.poll() is None:
      now = time.monotonic()
      if now - started_at >= timeout_seconds:
        timed_out = True
        _terminate_process(proc)
        break
      events = selector.select(timeout=1.0)
      if events:
        chunk = os.read(proc.stdout.fileno(), 4096)
        if chunk:
          text = chunk.decode("utf-8", errors="replace")
          output_parts.append(text)
          print(text, end="", flush=True)
          last_output_at = now
      elif now - last_output_at >= 30:
        print(
          f"[flutter-test-guard] waiting for flutter test output "
          f"({int(now - started_at)}s elapsed)",
          flush=True,
        )
        last_output_at = now
    remaining = proc.stdout.read()
    if remaining:
      text = remaining.decode("utf-8", errors="replace")
      output_parts.append(text)
      print(text, end="", flush=True)
  finally:
    selector.close()
  if timed_out:
    return 124, "".join(output_parts), True
  return proc.returncode or 0, "".join(output_parts), False


def _run_flutter_test_with_retries(
  cmd: list[str],
  *,
  cwd: Path = APP_ROOT,
  max_attempts: int = 3,
  timeout_seconds: int = DEFAULT_TEST_TIMEOUT_SECONDS,
) -> int:
  for attempt in range(1, max_attempts + 1):
    returncode, output, timed_out = _stream_command(
      cmd,
      cwd=cwd,
      timeout_seconds=timeout_seconds,
    )
    if timed_out:
      print(
        f"[flutter-test-guard] FAIL: command timed out after {timeout_seconds}s: "
        + " ".join(cmd),
        file=sys.stderr,
      )
      return 124
    if returncode == 0:
      return 0
    if attempt >= max_attempts:
      return returncode
    matched_markers = [marker for marker in RETRY_MARKERS if marker in output]
    if not matched_markers:
      return returncode
    wait_seconds = attempt * 5
    print(
      f"[flutter-test-guard] transient flutter failure, retry {attempt}/{max_attempts - 1} "
      f"after {wait_seconds}s: {', '.join(matched_markers)}",
    )
    time.sleep(wait_seconds)
  return 1


def _dart_define_values(args: list[str]) -> dict[str, str]:
  values: dict[str, str] = {}
  for arg in args:
    if not arg.startswith("--dart-define="):
      continue
    raw = arg.removeprefix("--dart-define=")
    key, separator, value = raw.partition("=")
    if separator and key:
      values[key] = value
  return values


def _with_runtime_environment_defines(args: list[str]) -> list[str]:
  defined = _dart_define_values(args)
  runtime_env = (
    defined.get("APP_RUNTIME_ENV")
    or os.environ.get("QWQ_APP_RUNTIME_ENV")
    or "alpha"
  ).strip()
  result = subprocess.run(
    [
      sys.executable,
      str(RUNTIME_DEFINE_SCRIPT),
      "--env",
      runtime_env,
      "--format",
      "args",
    ],
    cwd=str(APP_ROOT),
    text=True,
    capture_output=True,
    check=False,
  )
  if result.returncode != 0:
    raise RuntimeError(
      "cannot resolve explicit runtime Dart defines for Flutter tests: "
      + (result.stderr or result.stdout).strip()
    )
  injected: list[str] = []
  for line in result.stdout.splitlines():
    value = line.strip()
    if not value.startswith("--dart-define="):
      continue
    key = value.removeprefix("--dart-define=").partition("=")[0]
    if key and key not in defined:
      injected.append(value)
  return [*injected, *args]


def _ensure_flutter_pub_get() -> None:
  package_config = APP_ROOT / ".dart_tool" / "package_config.json"
  if package_config.exists():
    return
  print("[flutter-test-guard] package_config missing, running flutter pub get --offline")
  rc = _run_checked(["flutter", "pub", "get", "--offline"])
  if rc != 0:
    print(
      "[flutter-test-guard] FAIL: offline Flutter dependency resolution failed. "
      "This repo forbids hidden network fetches during test bootstrap.",
      file=sys.stderr,
    )
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
    flutter_args = _with_runtime_environment_defines(flutter_args)
    flutter_args = _with_serial_tag_policy(flutter_args)
    flutter_args = _with_shard_flags(flutter_args)
    flutter_args = _with_concurrency(flutter_args)
    cmd = ["flutter", "test", "--no-pub", *flutter_args]
    print(f"[flutter-test-guard] {' '.join(cmd)}")
    return _run_flutter_test_with_retries(cmd)


if __name__ == "__main__":
  raise SystemExit(main(sys.argv[1:]))
