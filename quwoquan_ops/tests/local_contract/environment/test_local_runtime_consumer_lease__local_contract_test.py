# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[4]
APP_DIR = ROOT / "quwoquan_app"
for import_root in (
    ROOT,
    APP_DIR / "scripts/device",
    APP_DIR / "test/support/runtime/launcher",
):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import build_launcher_handoff as launcher
from launcher_package_fixture import build_test_handoff_fixture
from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    validate_handoff_against_metadata,
)
from quwoquan_ops.cli.lib.dev_up import local_target_ports
from quwoquan_ops.cli.lib.local_runtime_consumer_lease import (
    acquire_consumer_lease,
    active_consumer_leases,
    list_consumer_leases,
)


STACKCTL = ROOT / "quwoquan_ops/cli/stackctl.py"
APP_RUN = APP_DIR / "run.sh"
APP_EXECUTOR = APP_DIR / "scripts/device/run_app_instance.py"
APP_SUPERVISOR = APP_DIR / "scripts/device/supervise_app_launch.py"
HANDOFF_BUILDER = APP_DIR / "scripts/device/build_launcher_handoff.py"
LAUNCH_CONTRACT = ROOT / "quwoquan_ops/cli/lib/app_launch_manifest_contract.py"


@dataclass(frozen=True)
class _LauncherExecution:
    result: subprocess.CompletedProcess[str]
    flutter_log: str
    stackctl_log: str
    executor_log: str
    handoff_json: str
    adb_log: str
    expected_ports: tuple[int, ...]
    preexisting_ports: tuple[int, ...]


class LocalRuntimeConsumerLeaseTest(unittest.TestCase):
    def _run_launcher_with_preflight_policy(
        self,
        *,
        gate_block: bool,
        connected_device: bool = True,
        transport_ready: bool = False,
    ) -> _LauncherExecution:
        with tempfile.TemporaryDirectory() as temporary_dir:
            temp_root = Path(temporary_dir)
            flutter_log = temp_root / "flutter.log"
            stackctl_log = temp_root / "stackctl.log"
            executor_log = temp_root / "executor.log"
            handoff_json = temp_root / "handoff.json"
            adb_log = temp_root / "adb.log"
            target = "alpha-local"
            expected_ports = tuple(local_target_ports(target))
            preexisting_ports = expected_ports[:1] if transport_ready else ()
            device_payload = (
                '[{"id":"policy-android","name":"Policy Android",'
                '"targetPlatform":"android-arm64","emulator":true,'
                '"ephemeral":false,"isSupported":true}]'
                if connected_device
                else "[]"
            )
            fake_flutter = temp_root / "flutter"
            fake_flutter.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f"printf '%s\\n' \"$*\" >> {shlex.quote(str(flutter_log))}\n"
                "if [[ \"${1:-}\" == \"pub\" && \"${2:-}\" == \"get\" ]]; then exit 0; fi\n"
                "if [[ \"$*\" == \"devices --machine\" ]]; then\n"
                f"  printf '%s\\n' {shlex.quote(device_payload)}\n"
                "  exit 0\n"
                "fi\n"
                "exit 97\n",
                encoding="utf-8",
            )
            fake_flutter.chmod(0o755)

            reverse_lines = "\\n".join(
                f"policy-android tcp:{port} tcp:{port}" for port in expected_ports
            )
            initial_reverse_lines = "\\n".join(
                f"policy-android tcp:{port} tcp:{port}" for port in preexisting_ports
            )
            fake_adb = temp_root / "adb"
            fake_adb.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f"printf '%s\\n' \"$*\" >> {shlex.quote(str(adb_log))}\n"
                "if [[ \"$*\" == *\" reverse --list\" ]]; then\n"
                "  if [[ ! -e \"${TEST_ADB_REVERSE_READY_FILE}\" ]]; then\n"
                f"    printf '%b\\n' {shlex.quote(initial_reverse_lines)}\n"
                "    : > \"${TEST_ADB_REVERSE_READY_FILE}\"\n"
                "  else\n"
                f"    printf '%b\\n' {shlex.quote(reverse_lines)}\n"
                "  fi\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"$*\" == *\" reverse tcp:\"* ]]; then exit 0; fi\n"
                "if [[ \"$*\" == *\" reverse --remove tcp:\"* ]]; then exit 0; fi\n"
                "exit 97\n",
                encoding="utf-8",
            )
            fake_adb.chmod(0o755)

            fake_python = temp_root / "python3"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == */quwoquan_ops/cli/stackctl.py ]]; then\n"
                f"  printf '%s\\n' \"$*\" >> {shlex.quote(str(stackctl_log))}\n"
                "  if [[ \" $* \" == *\" app-debug-preflight \"* ]]; then\n"
                "    if [[ \"${TEST_PREFLIGHT_GATE_BLOCK:-0}\" == \"1\" ]]; then\n"
                "      echo '{\"exitCode\":2,\"status\":\"gate_block\","
                "\"details\":[\"alpha api endpoint escapes the selected namespace\"],"
                "\"warnings\":[]}'\n"
                "      exit 2\n"
                "    fi\n"
                "    echo '{\"exitCode\":0,\"status\":\"warning\","
                "\"purpose\":\"runtime\",\"nonPromotable\":true,"
                "\"details\":[],\"warnings\":[\"target startup status is not running: stopped\"],"
                "\"runtimeChecks\":[],\"contentBindingState\":\"unbound\","
                "\"contentAvailability\":{\"state\":\"unbound\","
                "\"emptyReason\":\"no_active_release\"}}'\n"
                "    exit 0\n"
                "  fi\n"
                "  if [[ \" $* \" == *\" device-trust \"* ]]; then exit 2; fi\n"
                "  if [[ \" $* \" == *\" consumer-lease acquire \"* ]]; then\n"
                "    if [[ \"${TEST_TRANSPORT_READY:-0}\" != \"1\" ]]; then exit 2; fi\n"
                "    if [[ \" $* \" == *\" --handoff-digest \"* ]]; then exit 0; fi\n"
                "    echo '{\"exitCode\":0,\"lease\":{\"leaseId\":\"sha256:"
                + "7" * 64
                + "\"}}'\n"
                "    exit 0\n"
                "  fi\n"
                "  if [[ \" $* \" == *\" consumer-lease release \"* ]]; then exit 0; fi\n"
                "fi\n"
                "if [[ \"${1:-}\" == */quwoquan_app/scripts/device/"
                "build_launcher_handoff.py ]]; then\n"
                f"  {shlex.quote(sys.executable)} \"$@\" | tee {shlex.quote(str(handoff_json))}\n"
                "  exit \"${PIPESTATUS[0]}\"\n"
                "fi\n"
                "if [[ \"${1:-}\" == */quwoquan_app/scripts/device/"
                "supervise_app_launch.py ]]; then\n"
                "  for ((index=1; index <= $#; index++)); do\n"
                "    if [[ \"${!index}\" == \"--\" ]]; then\n"
                "      next=$((index + 1))\n"
                f"      printf '%s\\n' \"${{@:$next}}\" >> {shlex.quote(str(executor_log))}\n"
                "      prefix=(\"${@:1:$((index - 1))}\")\n"
                f"      exec {shlex.quote(sys.executable)} \"${{prefix[@]}}\" -- "
                "/bin/bash -c 'printf \"%s\\n\" "
                "\"QWQ_APP_LAUNCH_PHASE status=compiled\" "
                "\"QWQ_APP_LAUNCH_PHASE status=installing\" "
                "\"QWQ_APP_LAUNCH_PHASE status=installed\" "
                "\"QWQ_APP_LAUNCH_PHASE status=configuring\" "
                "\"QWQ_APP_LAUNCH_PHASE status=configured\" "
                "\"QWQ_APP_LAUNCH_PHASE status=launching\" "
                "\"QWQ_APP_LAUNCH_PHASE status=launched\"'\n"
                "    fi\n"
                "  done\n"
                "  exit 96\n"
                "fi\n"
                f"exec {shlex.quote(sys.executable)} \"$@\"\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = (
                f"{temporary_dir}{os.pathsep}{environment['PATH']}"
            )
            environment["QWQ_IOS_STACKCTL_PYTHON"] = str(fake_python)
            environment["QWQ_OUTPUT_ROOT"] = str(temp_root / "output")
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONPYCACHEPREFIX"] = str(temp_root / "pycache")
            environment["TEST_PREFLIGHT_GATE_BLOCK"] = "1" if gate_block else "0"
            environment["TEST_TRANSPORT_READY"] = "1" if transport_ready else "0"
            environment["TEST_ADB_REVERSE_READY_FILE"] = str(
                temp_root / "adb-reverse-ready"
            )
            result = subprocess.run(
                [
                    "bash",
                    str(APP_RUN),
                    "--env",
                    "alpha",
                    "--mode",
                    "ui-only",
                    "-d",
                    "policy-android",
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            return _LauncherExecution(
                result=result,
                flutter_log=(
                    flutter_log.read_text(encoding="utf-8")
                    if flutter_log.exists()
                    else ""
                ),
                stackctl_log=(
                    stackctl_log.read_text(encoding="utf-8")
                    if stackctl_log.exists()
                    else ""
                ),
                executor_log=(
                    executor_log.read_text(encoding="utf-8")
                    if executor_log.exists()
                    else ""
                ),
                handoff_json=(
                    handoff_json.read_text(encoding="utf-8")
                    if handoff_json.exists()
                    else ""
                ),
                adb_log=(
                    adb_log.read_text(encoding="utf-8") if adb_log.exists() else ""
                ),
                expected_ports=expected_ports,
                preexisting_ports=preexisting_ports,
            )

    def test_launcher_warning_policy_reaches_canonical_executor_without_runtime_lease(
        self,
    ) -> None:
        execution = self._run_launcher_with_preflight_policy(gate_block=False)
        result = execution.result

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "WARN: target startup status is not running: stopped",
            result.stderr,
        )
        self.assertIn(
            "WARN: runtime consumer lease is unavailable",
            result.stderr,
        )
        self.assertIn("pub get --offline --enforce-lockfile", execution.flutter_log)
        self.assertNotIn("run --no-pub", execution.flutter_log)
        executor_arguments = execution.executor_log.splitlines()
        self.assertIn(str(APP_EXECUTOR), executor_arguments)
        self.assertEqual(
            executor_arguments[executor_arguments.index("--device-kind") + 1],
            "android_emulator",
        )
        self.assertIn(
            "app-debug-preflight --purpose runtime "
            "--target alpha-local --runtime-mode test_live",
            execution.stackctl_log,
        )

    def test_launcher_hard_safety_blocker_stops_before_canonical_executor(self) -> None:
        execution = self._run_launcher_with_preflight_policy(gate_block=True)
        result = execution.result

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "alpha api endpoint escapes the selected namespace", result.stderr
        )
        self.assertEqual(execution.executor_log, "")
        self.assertIn(
            "app-debug-preflight --purpose runtime "
            "--target alpha-local --runtime-mode test_live",
            execution.stackctl_log,
        )

    def test_launcher_binds_transport_receipt_before_executor_and_cleans_only_owned_reverse(
        self,
    ) -> None:
        execution = self._run_launcher_with_preflight_policy(
            gate_block=False,
            transport_ready=True,
        )
        result = execution.result

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        handoff = json.loads(execution.handoff_json)
        self.assertRegex(
            handoff["transport"]["reverseReceiptDigest"],
            r"^sha256:[0-9a-f]{64}$",
        )
        self.assertIn("--handoff-digest", execution.stackctl_log)
        self.assertIn(str(APP_EXECUTOR), execution.executor_log)
        for port in execution.expected_ports:
            self.assertIn(f"reverse tcp:{port} tcp:{port}", execution.adb_log)
        for port in execution.preexisting_ports:
            self.assertNotIn(f"reverse --remove tcp:{port}", execution.adb_log)
        for port in execution.expected_ports[len(execution.preexisting_ports) :]:
            self.assertIn(f"reverse --remove tcp:{port}", execution.adb_log)
        self.assertNotIn("forward --remove tcp:8888", execution.adb_log)

    def test_android_launcher_owns_and_releases_lease(self) -> None:
        script = APP_RUN.read_text(encoding="utf-8")
        self.assertIn("trap cleanup_run EXIT", script)
        self.assertIn("cleanup_run()", script)
        self.assertIn("release_consumer_lease", script)
        self.assertIn("consumer-lease acquire", script)
        self.assertIn("consumer-lease release", script)
        self.assertIn('if [[ -z "$DEVICE_ID" ]]', script)
        self.assertIn("pass -d/--device-id", script)
        self.assertIn('--package-name "$QWQ_DEBUG_APP_ID"', script)
        self.assertIn("--ports \"$QWQ_ANDROID_LOCAL_PORTS\"", script)
        self.assertIn('export QWQ_ENVIRONMENT="${REQUESTED_ENVIRONMENT:-alpha}"', script)
        self.assertIn('export QWQ_APP_RUNTIME_ENV="$QWQ_ENVIRONMENT"', script)
        self.assertIn(
            'export QWQ_LAUNCH_TARGET="${REQUESTED_TARGET:-${QWQ_APP_RUNTIME_ENV}-local}"',
            script,
        )
        self.assertIn(
            'app-debug-preflight --purpose "$PREFLIGHT_PURPOSE"',
            script,
        )
        self.assertIn(
            '--target "$QWQ_LAUNCH_TARGET" --runtime-mode test_live',
            script,
        )
        self.assertIn("--platform ios-simulator", script)
        self.assertIn("--platform ios-physical", script)
        self.assertIn('--bundle-id "$QWQ_DEBUG_APP_ID"', script)
        self.assertIn('--ports ""', script)
        self.assertIn("QWQ_CONSUMER_LEASE_ID", script)
        self.assertIn("QWQ_ANDROID_REVERSE_RECEIPT_DIGEST", script)
        self.assertIn("QWQ_ANDROID_REVERSE_OWNED_PORTS", script)
        self.assertIn('reverse --remove "tcp:$port"', script)
        self.assertNotIn("QWQ_ANDROID_VM_FORWARD_PREEXISTING", script)
        self.assertNotIn("forward --remove tcp:8888", script)
        self.assertIn('"compileStatus": compile_status', script)
        self.assertIn('"installStatus": install_status', script)
        self.assertIn('"launchStatus": launch_status', script)
        self.assertIn('"runtimeStatus": runtime_status', script)
        self.assertIn('receipt.get("transitions")', script)
        self.assertNotIn('"compileStatus": "passed" if exit_code == 0', script)
        self.assertIn('"contentAvailability": preflight.get', script)
        self.assertIn('"providerAvailability": provider_availability', script)
        self.assertIn('DEVICE_TRUST_PLATFORM="android-emulator"', script)
        self.assertIn(r'r"tcp:(\d+)\s+tcp:\d+"', script)
        self.assertNotIn("exec flutter run", script)
        acquire_index = script.index("consumer-lease acquire")
        bind_index = script.index('--handoff-digest "$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"')
        executor_index = script.index(
            'python3 "$APP_DIR/scripts/device/run_app_instance.py"'
        )
        self.assertLess(acquire_index, script.index("HANDOFF_JSON="))
        self.assertLess(bind_index, executor_index)

    def test_launcher_rejects_unknown_or_nonmobile_device_after_runtime_preflight(
        self,
    ) -> None:
        script = APP_RUN.read_text(encoding="utf-8")
        device_guard = "a connected iOS/Android device is required after runtime preflight"
        self.assertIn("Flutter device {device_id!r} is not currently connected", script)
        self.assertIn("unsupported platform {platform!r}", script)
        self.assertIn(device_guard, script)
        self.assertLess(
            script.index(
                'app-debug-preflight --purpose "$PREFLIGHT_PURPOSE"'
            ),
            script.index(device_guard),
        )
        self.assertLess(
            script.index(device_guard),
            script.index('python3 "$APP_DIR/scripts/device/run_app_instance.py"'),
        )

    def test_launcher_blocks_unknown_device_after_runtime_preflight_before_executor(
        self,
    ) -> None:
        execution = self._run_launcher_with_preflight_policy(
            gate_block=False,
            connected_device=False,
        )
        result = execution.result

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "a connected iOS/Android device is required after runtime preflight",
            result.stderr,
        )
        self.assertIn("app-debug-preflight --purpose runtime", execution.stackctl_log)
        self.assertIn("pub get --offline", execution.flutter_log)
        self.assertIn("devices --machine", execution.flutter_log)
        self.assertEqual(execution.executor_log, "")

    def test_handoff_contract_is_transport_receipt_authority(self) -> None:
        launcher = APP_RUN.read_text(encoding="utf-8")
        handoff_builder = HANDOFF_BUILDER.read_text(encoding="utf-8")
        contract = LAUNCH_CONTRACT.read_text(encoding="utf-8")
        gradle = (APP_DIR / "android/app/build.gradle.kts").read_text(encoding="utf-8")

        for key in (
            "QWQ_CONSUMER_LEASE_ID",
            "QWQ_RUN_DEVICE_ID",
            "QWQ_ANDROID_REVERSE_EXPECTED_PORTS",
            "QWQ_ANDROID_REVERSE_ACTUAL_PORTS",
            "QWQ_ANDROID_REVERSE_RECEIPT_DIGEST",
        ):
            self.assertIn(key, launcher)
            self.assertNotIn(key, gradle)
        self.assertIn("--consumer-lease-id", launcher)
        self.assertIn("--reverse-receipt-digest", launcher)
        self.assertIn("build_handoff", handoff_builder)
        self.assertIn("is_digest_identity", handoff_builder)
        self.assertIn("canonical_ports", handoff_builder)
        self.assertIn("validate_handoff_against_metadata", handoff_builder)
        self.assertIn("validate_handoff_against_metadata", contract)
        self.assertIn("reverseReceiptDigest", contract)

    def test_build_grace_blocks_without_adb_probe(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                target="alpha-local",
                device="device-1",
                consumer="flutter-run",
                package_name="com.quwoquan.quwoquan_app",
                ports=(17000, 17010, 17100),
                build_grace_seconds=1200,
            )
            started_at = datetime.fromisoformat(
                str(lease["startedAt"]).replace("Z", "+00:00")
            )
            self.assertRegex(str(lease["leaseId"]), r"^sha256:[0-9a-f]{64}$")
            active = active_consumer_leases(
                "alpha-local",
                now=started_at + timedelta(seconds=30),
                runner=lambda _: self.fail("adb must not run during build grace"),
            )
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["state"], "build_grace")

    def test_ios_simulator_lease_records_release_bound_handoff_without_ports(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                target="beta-local",
                device="SIMULATOR-UDID",
                consumer="direct-flutter-run",
                package_name="com.example.quwoquanApp",
                ports=(),
                platform="ios-simulator",
                handoff_digest="sha256:" + "1" * 64,
                release_id="release-001",
                manifest_digest="sha256:" + "2" * 64,
                readiness_receipt_digest="sha256:" + "3" * 64,
                build_grace_seconds=1,
            )
            self.assertEqual(lease["platform"], "ios-simulator")
            self.assertEqual(lease["bundleId"], "com.example.quwoquanApp")
            self.assertEqual(lease["ports"], [])
            self.assertEqual(lease["releaseId"], "release-001")

    def test_ios_physical_lease_records_bundle_without_transport_ports(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                target="gamma-local",
                device="REGISTERED-IPHONE-UDID",
                consumer="canonical-launcher",
                package_name="com.example.quwoquanApp.nonprod.debug",
                ports=(),
                platform="ios-physical",
                handoff_digest="sha256:" + "4" * 64,
                build_grace_seconds=1,
            )
            self.assertEqual(lease["platform"], "ios-physical")
            self.assertEqual(
                lease["bundleId"], "com.example.quwoquanApp.nonprod.debug"
            )
            self.assertEqual(lease["ports"], [])
            self.assertEqual(lease["handoffDigest"], "sha256:" + "4" * 64)

    def test_ios_physical_running_app_keeps_lease_after_grace(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            bundle_id = "com.example.quwoquanApp.nonprod.debug"
            app_url = "/private/var/containers/Bundle/Application/ID/Runner.app"
            lease = acquire_consumer_lease(
                target="alpha-local",
                device="REGISTERED-IPHONE-UDID",
                consumer="canonical-launcher",
                package_name=bundle_id,
                ports=(),
                platform="ios-physical",
                build_grace_seconds=1,
            )
            started_at = datetime.fromisoformat(
                str(lease["startedAt"]).replace("Z", "+00:00")
            )
            commands: list[list[str]] = []

            def running(argv: list[str]) -> subprocess.CompletedProcess[str]:
                command = list(argv)
                commands.append(command)
                output_path = Path(command[command.index("--json-output") + 1])
                if "apps" in command:
                    result = {
                        "apps": [
                            {
                                "bundleIdentifier": bundle_id,
                                "name": "Runner",
                                "url": app_url,
                            }
                        ]
                    }
                else:
                    result = {
                        "runningProcesses": [
                            {
                                "executable": f"{app_url}/Runner",
                                "processIdentifier": 4201,
                            }
                        ]
                    }
                output_path.write_text(
                    json.dumps({"result": result}), encoding="utf-8"
                )
                return subprocess.CompletedProcess(command, 0, "", "")

            active = active_consumer_leases(
                "alpha-local",
                now=started_at + timedelta(seconds=5),
                runner=running,
                xcrun_path="xcrun",
            )
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["state"], "active")
            self.assertEqual(
                [command[2:5] for command in commands],
                [
                    ["device", "info", "apps"],
                    ["device", "info", "processes"],
                ],
            )

    def test_ios_simulator_running_app_keeps_lease_after_grace(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                target="alpha-local",
                device="SIMULATOR-UDID",
                consumer="flutter-run",
                package_name="com.example.quwoquanApp",
                ports=(),
                platform="ios-simulator",
                build_grace_seconds=1,
            )
            started_at = datetime.fromisoformat(
                str(lease["startedAt"]).replace("Z", "+00:00")
            )

            def running(argv: list[str]) -> subprocess.CompletedProcess[str]:
                if argv[-1] == "--json":
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        json.dumps(
                            {
                                "devices": {
                                    "runtime": [
                                        {
                                            "udid": "SIMULATOR-UDID",
                                            "state": "Booted",
                                        }
                                    ]
                                }
                            }
                        ),
                        "",
                    )
                if argv[-2:] == ["id", "-u"]:
                    return subprocess.CompletedProcess(argv, 0, "501\n", "")
                if "get_app_container" in argv:
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        "/tmp/Runner.app\n",
                        "",
                    )
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    (
                        "UIKitApplication:com.example.quwoquanApp[active]\n"
                        "path = /tmp/Runner.app/Runner"
                    ),
                    "",
                )

            active = active_consumer_leases(
                "alpha-local",
                now=started_at + timedelta(seconds=5),
                runner=running,
                xcrun_path="xcrun",
            )
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["state"], "active")

    def test_ios_simulator_verified_app_does_not_expire_after_twelve_hours(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                target="alpha-local",
                device="SIMULATOR-UDID",
                consumer="flutter-run",
                package_name="com.example.quwoquanApp",
                ports=(),
                platform="ios-simulator",
                build_grace_seconds=1,
            )
            started_at = datetime.fromisoformat(
                str(lease["startedAt"]).replace("Z", "+00:00")
            )

            def running(argv: list[str]) -> subprocess.CompletedProcess[str]:
                if argv[-1] == "--json":
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        json.dumps(
                            {
                                "devices": {
                                    "runtime": [
                                        {
                                            "udid": "SIMULATOR-UDID",
                                            "state": "Booted",
                                        }
                                    ]
                                }
                            }
                        ),
                        "",
                    )
                if argv[-2:] == ["id", "-u"]:
                    return subprocess.CompletedProcess(argv, 0, "501\n", "")
                if "get_app_container" in argv:
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        "/tmp/Runner.app\n",
                        "",
                    )
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    (
                        "UIKitApplication:com.example.quwoquanApp[suspended]\n"
                        "path = /tmp/Runner.app/Runner"
                    ),
                    "",
                )

            active = active_consumer_leases(
                "alpha-local",
                now=started_at + timedelta(hours=24),
                runner=running,
                xcrun_path="xcrun",
            )
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["state"], "active")

    def test_ios_simulator_stopped_app_prunes_lease_after_grace(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                target="gamma-local",
                device="SIMULATOR-UDID",
                consumer="flutter-run",
                package_name="com.example.quwoquanApp",
                ports=(),
                platform="ios-simulator",
                build_grace_seconds=1,
            )
            started_at = datetime.fromisoformat(
                str(lease["startedAt"]).replace("Z", "+00:00")
            )

            def stopped(argv: list[str]) -> subprocess.CompletedProcess[str]:
                if argv[-1] == "--json":
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        json.dumps(
                            {
                                "devices": {
                                    "runtime": [
                                        {
                                            "udid": "SIMULATOR-UDID",
                                            "state": "Booted",
                                        }
                                    ]
                                }
                            }
                        ),
                        "",
                    )
                if argv[-2:] == ["id", "-u"]:
                    return subprocess.CompletedProcess(argv, 0, "501\n", "")
                if "get_app_container" in argv:
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        "/tmp/Runner.app\n",
                        "",
                    )
                return subprocess.CompletedProcess(argv, 0, "other services", "")

            active = active_consumer_leases(
                "gamma-local",
                now=started_at + timedelta(seconds=5),
                runner=stopped,
                xcrun_path="xcrun",
            )
            self.assertEqual(active, [])
            self.assertEqual(
                len(list_consumer_leases("gamma-local")),
                1,
                "status/liveness inspection must be strictly read-only",
            )

    def test_disconnected_device_prunes_expired_build_lease(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                target="alpha-local",
                device="device-1",
                consumer="flutter-run",
                package_name="com.quwoquan.quwoquan_app",
                ports=(17000,),
                build_grace_seconds=1,
            )
            started_at = datetime.fromisoformat(
                str(lease["startedAt"]).replace("Z", "+00:00")
            )

            def disconnected(_: list[str]) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess([], 1, "", "device missing")

            active = active_consumer_leases(
                "alpha-local",
                now=started_at + timedelta(seconds=5),
                runner=disconnected,
                adb_path="adb",
            )
            self.assertEqual(active, [])
            self.assertEqual(
                len(list_consumer_leases("alpha-local")),
                1,
                "stale cleanup requires an explicit release or GC operation",
            )

    def test_stackctl_down_is_gate_blocked_by_flutter_consumer(self) -> None:
        with tempfile.TemporaryDirectory() as output_root:
            environment = {
                **os.environ,
                "QWQ_OUTPUT_ROOT": output_root,
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            acquire = subprocess.run(
                [
                    sys.executable,
                    str(STACKCTL),
                    "--output-format",
                    "json",
                    "consumer-lease",
                    "acquire",
                    "--target",
                    "alpha-local",
                    "--device",
                    "device-1",
                ],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(acquire.returncode, 0, acquire.stderr)
            down = subprocess.run(
                [
                    sys.executable,
                    str(STACKCTL),
                    "--output-format",
                    "json",
                    "down",
                    "--target",
                    "alpha-local",
                ],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(down.returncode, 2, down.stderr)
            payload = json.loads(down.stdout)
            self.assertEqual(payload["exitCode"], 2)
            self.assertIn("consumer lease", " ".join(payload["details"]))

    def test_stackctl_accepts_ios_leases_without_transport_ports(self) -> None:
        for platform, device in (
            ("ios-simulator", "SIMULATOR-UDID"),
            ("ios-physical", "REGISTERED-IPHONE-UDID"),
        ):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as output_root:
                environment = {
                    **os.environ,
                    "QWQ_OUTPUT_ROOT": output_root,
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
                acquire = subprocess.run(
                    [
                        sys.executable,
                        str(STACKCTL),
                        "--output-format",
                        "json",
                        "consumer-lease",
                        "acquire",
                        "--target",
                        "beta-local",
                        "--platform",
                        platform,
                        "--device",
                        device,
                        "--bundle-id",
                        "com.example.quwoquanApp",
                        "--ports",
                        "",
                    ],
                    cwd=ROOT,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(acquire.returncode, 0, acquire.stderr)
                payload = json.loads(acquire.stdout)
                self.assertEqual(payload["lease"]["platform"], platform)
                self.assertEqual(payload["lease"]["ports"], [])
                self.assertEqual(
                    payload["lease"]["bundleId"],
                    "com.example.quwoquanApp",
                )


if __name__ == "__main__":
    unittest.main()
