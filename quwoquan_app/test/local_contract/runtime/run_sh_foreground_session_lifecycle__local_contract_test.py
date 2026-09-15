# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""source projection 外层与前台 child 的信号、等待和清理契约。"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
DEV_LAUNCH = APP_DIR / "scripts/device/dev_launch.sh"
ATTACH_SESSION = APP_DIR / "scripts/device/canonical_app_instance/attach_session.py"


class ForegroundSessionLifecycleContractTest(unittest.TestCase):
    def test_projection_parent_tracks_child_waits_then_cleans(self) -> None:
        source = DEV_LAUNCH.read_text(encoding="utf-8")
        projection = source[source.index('if [[ -e "$ROOT_DIR/.git" ]]'):]
        self.assertIn('SOURCE_PROJECTION_CHILD_PID=$!', projection)
        self.assertIn("trap 'forward_source_projection_signal INT' INT", projection)
        self.assertIn("trap 'forward_source_projection_signal TERM' TERM", projection)
        self.assertIn("trap 'forward_source_projection_signal HUP' HUP", projection)
        self.assertIn('while true; do\n    if wait "$SOURCE_PROJECTION_CHILD_PID"', projection)
        self.assertIn('trap cleanup_source_projection EXIT', projection)
        self.assertLess(
            projection.index('wait "$SOURCE_PROJECTION_CHILD_PID"'),
            projection.index('exit "$SOURCE_PROJECTION_STATUS"'),
        )

    def test_projection_reports_fresh_snapshot_hot_reload_limit(self) -> None:
        source = DEV_LAUNCH.read_text(encoding="utf-8")
        self.assertIn("APP.LAUNCH.source_projection_live_sync_unavailable", source)
        self.assertIn("hot reload reads projection bytes only", source)
        self.assertIn("rerun run.sh to capture live workspace changes", source)

    def test_supervisor_forwards_each_signal_and_waits_for_child(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-session-lifecycle-") as raw:
            temporary = Path(raw)
            child = temporary / "child.py"
            child.write_text(
                "import os, signal, sys, time\n"
                "marker = sys.argv[1]\n"
                "def stop(signum, frame):\n"
                "    with open(marker, 'a', encoding='utf-8') as stream:\n"
                "        stream.write(f'{signum}\\n')\n"
                "    time.sleep(0.15)\n"
                "    raise SystemExit(0)\n"
                "for item in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):\n"
                "    signal.signal(item, stop)\n"
                "print('ready', flush=True)\n"
                "while True: time.sleep(1)\n",
                encoding="utf-8",
            )
            for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                with self.subTest(signum=signum):
                    marker = temporary / f"signal-{signum}.txt"
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "canonical_app_instance.attach_session",
                            "--supervise-command",
                            sys.executable,
                            str(child),
                            str(marker),
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        env={
                            **os.environ,
                            "PYTHONDONTWRITEBYTECODE": "1",
                            "PYTHONPATH": str(APP_DIR / "scripts/device"),
                        },
                    )
                    self.assertEqual(process.stdout.readline().strip(), "ready")
                    started = time.monotonic()
                    process.send_signal(signum)
                    stdout, stderr = process.communicate(timeout=5)
                    self.assertEqual(stdout, "")
                    self.assertEqual(stderr, "")
                    self.assertEqual(process.returncode, 128 + signum)
                    self.assertGreaterEqual(time.monotonic() - started, 0.1)
                    self.assertEqual(marker.read_text(encoding="utf-8"), f"{signum}\n")


if __name__ == "__main__":
    unittest.main()
