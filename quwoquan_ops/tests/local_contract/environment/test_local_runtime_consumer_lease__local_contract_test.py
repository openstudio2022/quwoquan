# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[4]
APP_DIR = ROOT / "quwoquan_app"
for import_root in (
    ROOT,
    APP_DIR / "scripts/device",
    APP_DIR / "test/support/runtime/launcher",
):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from quwoquan_ops.cli.lib.dev_up import local_target_ports
from quwoquan_ops.cli.lib.local_runtime_consumer_lease import (
    MAX_LEASE_AGE_SECONDS,
    acquire_consumer_lease,
    active_consumer_leases,
    bind_consumer_lease,
    inspect_consumer_leases,
    list_consumer_leases,
    release_consumer_lease,
)


STACKCTL = ROOT / "quwoquan_ops/cli/stackctl.py"
APP_RUN = APP_DIR / "run.sh"
APP_EXECUTOR = APP_DIR / "scripts/device/run_app_instance.py"
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


class PublicAndroidPortsContractTest(unittest.TestCase):
    # spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
    def test_public_android_ports_accepts_canonical_https_and_wss(self) -> None:
        from canonical_app_instance.runtime_lease import public_android_ports
        from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology

        topology = load_environment_topology()
        for target in ("beta-local", "gamma-local"):
            with self.subTest(target=target):
                bases = get_target(topology, target)["publicBases"]
                parsed = [urlparse(base) for base in bases.values()]
                self.assertEqual({base.scheme for base in parsed}, {"https", "wss"})
                expected = sorted({base.port for base in parsed})
                self.assertEqual(public_android_ports(target), expected)

    def test_public_android_ports_rejects_unsafe_unknown_and_incomplete_urls(self) -> None:
        from canonical_app_instance.runtime_lease import CanonicalExecutorError, public_android_ports
        from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology

        target = get_target(load_environment_topology(), "beta-local")
        secure = urlparse(target["publicBases"]["api"])
        malformed = [secure._replace(scheme=scheme).geturl()
                     for scheme in ("http", "ws", "ftp", "unknown")]
        malformed.extend([
            secure._replace(netloc=f":{secure.port}").geturl(),
            secure._replace(netloc=secure.hostname).geturl(),
        ])
        for base in malformed:
            with self.subTest(base=base), patch(
                "quwoquan_ops.cli.lib.environment_topology.get_target",
                return_value={**target, "publicBases": {"api": base}},
            ), self.assertRaisesRegex(CanonicalExecutorError,
                                      "APP.LAUNCH.transport_unavailable: public base is invalid"):
                public_android_ports("beta-local")


class LocalRuntimeConsumerLeaseTest(unittest.TestCase):
    def _run_launcher_with_preflight_policy(
        self,
        *,
        gate_block: bool,
        connected_device: bool = True,
        lease_available: bool = True,
    ) -> _LauncherExecution:
        with tempfile.TemporaryDirectory() as temporary_dir:
            temp_root = Path(temporary_dir).resolve()
            temporary_dir = str(temp_root)
            flutter_log = temp_root / "flutter.log"
            stackctl_log = temp_root / "stackctl.log"
            executor_log = temp_root / "executor.log"
            handoff_json = temp_root / "handoff.json"
            adb_log = temp_root / "adb.log"
            target = "beta-local"
            # 只复制 direct 执行所需源码；pub stamp 等写入全部留在临时树。
            sandbox = temp_root / "workspace"
            sandbox_app = sandbox / "quwoquan_app"
            (sandbox / ".git").mkdir(parents=True)
            (sandbox_app / "scripts/device").mkdir(parents=True)
            for relative in ("run.sh", "scripts/device/dev_launch.sh", "pubspec.yaml", "pubspec.lock", ".flutter-version"):
                shutil.copy2(APP_DIR / relative, sandbox_app / relative)
            (sandbox_app / "scripts/tools").mkdir(parents=True)
            shutil.copytree(APP_DIR / "scripts/tools/flutter_facade",
                            sandbox_app / "scripts/tools/flutter_facade")
            expected_ports = tuple(local_target_ports(target))
            preexisting_ports = expected_ports[:1]
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
                "if [[ \"$*\" == \"--version --machine\" ]]; then\n"
                "  printf '%s\\n' '{\"frameworkVersion\":\"3.47.0\","
                "\"frameworkRevision\":\"fixture-revision\","
                "\"engineRevision\":\"fixture-engine\","
                "\"dartSdkVersion\":\"3.10.0\",\"channel\":\"stable\"}'\n"
                "  exit 0\n"
                "fi\n"
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

            # 子进程桥只替换外部 I/O；source、设备选择、签名 handoff 与 lease
            # acquire/bind/release 编排仍执行生产实现。不接触宿主 runtime authority。
            bridge = temp_root / "python_bridge.py"
            bridge.write_text(
                "import contextlib, json, os, runpy, sys\n"
                "from pathlib import Path\n"
                "from unittest.mock import patch\n"
                f"sys.path[:0] = {[str(ROOT), str(APP_DIR / 'scripts/device'), str(APP_DIR / 'test/support/runtime/launcher')]!r}\n"
                "from canonical_app_instance import runtime_lease as leases\n"
                "import run_app_instance as executor\n"
                "import build_launcher_handoff as builder\n"
                "from launcher_package_fixture import temporary_launcher_package\n"
                f"log = Path({str(stackctl_log)!r})\n"
                "def record(value):\n"
                "    with log.open('a') as stream: stream.write(json.dumps(value) + '\\n')\n"
                "def consumer(action, **values):\n"
                "    record(dict(action=action, **values))\n"
                "    if action == 'acquire':\n"
                "        if os.environ['TEST_LEASE_AVAILABLE'] != '1':\n"
                "            raise leases.CanonicalExecutorError('OPS.LEASE.action_blocked: fixture lease unavailable')\n"
                "        return {'exitCode': 0, 'lease': {\n"
                "            'leaseId': 'sha256:' + '7' * 64, 'target': values['target'],\n"
                "            'device': values['device'], 'consumer': values['consumer'],\n"
                "            'instanceGeneration': values['instance_generation'],\n"
                "            'packageName': values['package_name']}}\n"
                "    return {'exitCode': 0}\n"
                "def execute():\n"
                "    record({'action': 'executor'})\n"
                f"    Path({str(executor_log)!r}).write_text('\\n'.join([{str(APP_EXECUTOR)!r}, *sys.argv[1:]]))\n"
                "    return 0\n"
                "arguments = sys.argv[1:]\n"
                "with contextlib.ExitStack() as patches:\n"
                "    patches.enter_context(patch.object(leases, 'running_generation', return_value='runtime-fixture-1'))\n"
                "    patches.enter_context(patch.object(leases, 'selected_device_lock', return_value=contextlib.nullcontext()))\n"
                "    patches.enter_context(patch.object(leases, 'consumer_action', side_effect=consumer))\n"
                "    patches.enter_context(patch.object(executor, 'main', side_effect=execute))\n"
                "    if arguments[0].endswith('/build_launcher_handoff.py'):\n"
                "        args = builder._parser(builder.load_launch_manifest_contract()).parse_args(arguments[1:])\n"
                "        with temporary_launcher_package(args.env, args.target) as package:\n"
                "            patches.enter_context(patch.object(builder, '_runtime_config_trust_envelope', return_value=package.runtime_config_trust_envelope))\n"
                "            handoff = builder.build_handoff(args, runtime_config_package_loader=package.load_runtime_config_package)\n"
                "            issues = package.validate_handoff(builder.validate_handoff_against_metadata, handoff)\n"
                "            if issues: raise ValueError(issues)\n"
                "            payload = json.dumps(handoff)\n"
                f"            Path({str(handoff_json)!r}).write_text(payload)\n"
                "            print(payload)\n"
                "    elif arguments[0] in ('-', '-c'):\n"
                "        code = sys.stdin.read() if arguments[0] == '-' else arguments[1]\n"
                "        sys.argv = ['-' if arguments[0] == '-' else '-c', *arguments[1 if arguments[0] == '-' else 2:]]\n"
                "        exec(compile(code, '<launcher-test>', 'exec'), {'__name__': '__main__'})\n"
                "    else:\n"
                "        sys.argv = arguments\n"
                "        runpy.run_path(arguments[0], run_name='__main__')\n",
                encoding="utf-8",
            )
            fake_python = temp_root / "python3"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == */quwoquan_ops/cli/stackctl.py ]]; then\n"
                f"  printf '%s\\n' \"$*\" >> {shlex.quote(str(stackctl_log))}\n"
                "  if [[ \" $* \" == *\" app-debug-preflight \"* ]]; then\n"
                "    if [[ \"${TEST_PREFLIGHT_GATE_BLOCK:-0}\" == \"1\" ]]; then\n"
                "      echo '{\"schema\":\"quwoquan_ops.app_debug_preflight\","
                "\"exitCode\":2,\"status\":\"gate_block\","
                "\"target\":\"beta-local\",\"environment\":\"beta\","
                "\"firstBlocker\":\"APP.LAUNCH.runtime_config_activation_failed\","
                "\"details\":[\"namespace validation failed closed\"],"
                "\"warnings\":[]}'\n"
                "      exit 2\n"
                "    fi\n"
                "    echo '{\"exitCode\":0,\"status\":\"warning\","
                "\"target\":\"beta-local\",\"environment\":\"beta\","
                "\"firstBlocker\":\"\","
                "\"purpose\":\"runtime\",\"nonPromotable\":true,"
                "\"details\":[],\"warnings\":[\"target startup status is not running: stopped\"],"
                "\"runtimeChecks\":[],\"contentBindingState\":\"unbound\","
                "\"contentAvailability\":{\"state\":\"unbound\","
                "\"emptyReason\":\"no_active_release\"}}'\n"
                "    exit 0\n"
                "  fi\n"
                "  exit 96\n"
                "fi\n"
                f"exec {shlex.quote(sys.executable)} -B {shlex.quote(str(bridge))} \"$@\"\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            environment = {
                key: value for key, value in os.environ.items()
                if not key.startswith("QWQ_")
            }
            environment["PYTHONPATH"] = str(ROOT)
            environment["PATH"] = (
                f"{temporary_dir}{os.pathsep}{environment['PATH']}"
            )
            environment["QWQ_IOS_STACKCTL_PYTHON"] = str(fake_python)
            environment["QWQ_OUTPUT_ROOT"] = str((temp_root / "output").resolve())
            environment["QWQ_REAL_FLUTTER"] = str(fake_flutter.resolve())
            environment.pop("FLUTTER_ROOT", None)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONPYCACHEPREFIX"] = str(temp_root / "pycache")
            environment["TEST_PREFLIGHT_GATE_BLOCK"] = "1" if gate_block else "0"
            environment["TEST_LEASE_AVAILABLE"] = "1" if lease_available else "0"
            # direct 只读取外层既有 reverse，绝不创建或签发 receipt。
            (temp_root / "adb-reverse-ready").touch()
            environment["TEST_ADB_REVERSE_READY_FILE"] = str(
                temp_root / "adb-reverse-ready"
            )
            result = subprocess.run(
                [
                    "bash",
                    str(sandbox_app / "run.sh"),
                    "--env",
                    "beta",
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

    def test_launcher_warning_policy_reaches_canonical_executor_with_exact_runtime_lease(
        self,
    ) -> None:
        execution = self._run_launcher_with_preflight_policy(gate_block=False)
        result = execution.result

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "WARN: target startup status is not running: stopped",
            result.stderr,
        )
        calls = [json.loads(line) for line in execution.stackctl_log.splitlines()
                 if line.startswith("{")]
        self.assertEqual([call["action"] for call in calls],
                         ["acquire", "bind", "executor", "release"])
        acquire, bound, _, released = calls
        for key in ("target", "device", "consumer", "instance_generation"):
            self.assertEqual(bound[key], acquire[key])
            self.assertEqual(released[key], acquire[key])
        self.assertEqual(bound["lease_id"], "sha256:" + "7" * 64)
        self.assertEqual(released["lease_id"], bound["lease_id"])
        self.assertEqual(bound["handoff_digest"],
                         json.loads(execution.handoff_json)["effectiveLaunchManifestDigest"])
        self.assertIn("--version --machine", execution.flutter_log)
        self.assertIn("devices --machine", execution.flutter_log)
        self.assertNotIn(" run", execution.flutter_log)
        self.assertIn("pub get", execution.flutter_log)
        executor_arguments = execution.executor_log.splitlines()
        self.assertIn(str(APP_EXECUTOR), executor_arguments)
        self.assertEqual(
            executor_arguments[executor_arguments.index("--device-kind") + 1],
            "android_emulator",
        )
        self.assertIn(
            "app-debug-preflight --purpose runtime "
            "--target beta-local --runtime-mode test_live",
            execution.stackctl_log,
        )

    def test_launcher_missing_safety_lease_blocks_before_canonical_executor(self) -> None:
        execution = self._run_launcher_with_preflight_policy(
            gate_block=False, lease_available=False,
        )
        self.assertEqual(execution.result.returncode, 2, execution.result.stderr)
        self.assertIn("OPS.LEASE.action_blocked", execution.result.stderr)
        self.assertEqual(execution.executor_log, "")
        calls = [json.loads(line) for line in execution.stackctl_log.splitlines()
                 if line.startswith("{")]
        self.assertEqual([call["action"] for call in calls], ["acquire"])

    def test_launcher_hard_safety_blocker_stops_before_canonical_executor(self) -> None:
        execution = self._run_launcher_with_preflight_policy(gate_block=True)
        result = execution.result

        self.assertEqual(result.returncode, 2)
        terminal_lines = [
            line for line in result.stderr.splitlines() if line.startswith("{")
        ]
        self.assertEqual(len(terminal_lines), 1, result.stdout + result.stderr)
        terminal = json.loads(terminal_lines[0])
        self.assertEqual(terminal["schema"], "quwoquan_ops.app_debug_preflight")
        self.assertEqual(terminal["exitCode"], 2)
        self.assertEqual(terminal["status"], "gate_block")
        self.assertEqual(terminal["target"], "beta-local")
        self.assertEqual(terminal["environment"], "beta")
        self.assertEqual(
            terminal["firstBlocker"],
            "APP.LAUNCH.runtime_config_activation_failed",
        )
        self.assertTrue(terminal["details"])
        self.assertFalse(terminal["warnings"])
        self.assertEqual(execution.executor_log, "")
        self.assertEqual(execution.flutter_log, "")
        self.assertIn(
            "app-debug-preflight --purpose runtime "
            "--target beta-local --runtime-mode test_live",
            execution.stackctl_log,
        )

    def test_direct_launcher_omits_unowned_receipt_and_canonical_path_cleans_owned_reverse(
        self,
    ) -> None:
        execution = self._run_launcher_with_preflight_policy(gate_block=False)
        result = execution.result

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        handoff = json.loads(execution.handoff_json)
        self.assertFalse(handoff["transport"]["required"])
        self.assertEqual(handoff["transport"]["reverseReceiptDigest"], "")
        self.assertEqual(handoff["contentSource"], "remote")
        self.assertEqual(handoff["environment"], "beta")
        self.assertIn(str(APP_EXECUTOR), execution.executor_log)
        self.assertEqual(execution.adb_log.splitlines(),
                         ["-s policy-android reverse --list"])

        script = APP_RUN.read_text(encoding="utf-8")
        receipt_export_index = script.index(
            'print("export QWQ_ANDROID_REVERSE_RECEIPT_DIGEST="'
        )
        handoff_digest_index = script.index(
            '--reverse-receipt-digest "$QWQ_ANDROID_REVERSE_RECEIPT_DIGEST"'
        )
        bind_index = script.index(
            '--handoff-digest "$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"'
        )
        executor_index = script.index(
            'python3 "$APP_DIR/scripts/device/run_app_instance.py"'
        )
        self.assertLess(receipt_export_index, handoff_digest_index)
        self.assertLess(handoff_digest_index, bind_index)
        self.assertLess(bind_index, executor_index)
        cleanup_start = script.index("cleanup_managed_handoff_resources()")
        cleanup_end = script.index("# preparation", cleanup_start)
        cleanup_script = script[cleanup_start:cleanup_end]
        self.assertIn("QWQ_ANDROID_REVERSE_OWNED_PORTS", cleanup_script)
        self.assertNotIn("QWQ_ANDROID_REVERSE_EXPECTED_PORTS", cleanup_script)
        self.assertIn('reverse --remove "tcp:$port"', cleanup_script)
        self.assertNotIn("forward --remove tcp:8888", cleanup_script)
        # 执行现役 cleanup 函数，而非复制实现；双次调用不得重复释放或删预存映射。
        with tempfile.TemporaryDirectory() as temporary:
            cleanup_log = Path(temporary) / "cleanup.log"
            owned = execution.expected_ports[len(execution.preexisting_ports):]
            cleanup_environment = {
                **os.environ,
                "QWQ_MANAGED_TRUST_CLEANUP_REQUIRED": "0",
                "QWQ_MANAGED_PREPARATION_ACTIVE": "0",
                "QWQ_MANAGED_LEASE_CLEANUP_REQUIRED": "1",
                "QWQ_CONSUMER_LEASE_ACQUIRED": "0",
                "QWQ_ANDROID_REVERSE_OWNED_PORTS": ",".join(map(str, owned)),
                "QWQ_CONSUMER_LEASE_ID": "sha256:" + "7" * 64,
                "QWQ_RUNTIME_INSTANCE_GENERATION": "runtime-fixture-1",
                "QWQ_LAUNCH_TARGET": "beta-local",
                "QWQ_RUN_CONSUMER_ID": "fixture-managed-consumer",
                "DEVICE_ID": "policy-android",
                "ROOT_DIR": str(ROOT),
                "TEST_CLEANUP_LOG": str(cleanup_log),
            }
            cleanup = subprocess.run(
                ["bash", "-c", "set -euo pipefail\n"
                 'adb() { printf "adb %s\\n" "$*" >> "$TEST_CLEANUP_LOG"; }\n'
                 'python3() { printf "python3 %s\\n" "$*" >> "$TEST_CLEANUP_LOG"; }\n'
                 'record_teardown_warning() { printf "%s\\n" "$*" >&2; return 1; }\n'
                 + cleanup_script
                 + "\ncleanup_managed_handoff_resources\ncleanup_managed_handoff_resources\n"],
                env=cleanup_environment, capture_output=True, text=True, check=False,
            )
            self.assertEqual(cleanup.returncode, 0, cleanup.stderr)
            cleanup_calls = cleanup_log.read_text().splitlines()
        self.assertTrue(owned)
        self.assertEqual(cleanup_calls[:-1],
                         [f"adb -s policy-android reverse --remove tcp:{port}" for port in owned])
        self.assertEqual(cleanup_calls[-1],
                         f"python3 {STACKCTL} consumer-lease release --target beta-local "
                         "--device policy-android --consumer fixture-managed-consumer "
                         f"--lease-id sha256:{'7' * 64} --instance-generation runtime-fixture-1")

    def test_android_launcher_owns_and_releases_lease(self) -> None:
        script = APP_RUN.read_text(encoding="utf-8")
        self.assertIn("trap managed_prelaunch_cleanup EXIT", script)
        self.assertIn("trap 'run_exit_code=$?; cleanup_run", script)
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
        self.assertIn(
            '"runtimeStatus": receipt.get("runtimeHealthStatus")', script
        )
        self.assertIn("else runtime_status", script)
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
            "Flutter mobile device 'policy-android' is not visible",
            result.stderr,
        )
        self.assertIn(
            "choose a connected iOS/Android device",
            result.stderr,
        )
        self.assertIn("app-debug-preflight --purpose runtime", execution.stackctl_log)
        self.assertIn("devices --machine", execution.flutter_log)
        self.assertNotIn("pub get", execution.flutter_log)
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

    def test_bind_exact_active_lease_preserves_acquire_identity(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            acquired = acquire_consumer_lease(
                instance_generation="runtime-1",
                target="alpha-local",
                device="device-1",
                consumer="flutter-run-123",
                package_name="com.quwoquan.alpha.debug",
                ports=(17000, 17010),
                platform="android",
                build_grace_seconds=321,
            )
            bound = bind_consumer_lease(
                instance_generation="runtime-1",
                target="alpha-local",
                device="device-1",
                consumer="flutter-run-123",
                lease_id=str(acquired["leaseId"]),
                handoff_digest="sha256:" + "e" * 64,
                release_id="release-1",
                manifest_digest="sha256:" + "f" * 64,
                readiness_receipt_digest="sha256:" + "d" * 64,
            )

            self.assertEqual(bound["leaseId"], acquired["leaseId"])
            self.assertEqual(bound["startedAt"], acquired["startedAt"])
            self.assertEqual(bound["ports"], acquired["ports"])
            self.assertEqual(bound["buildGraceSeconds"], 321)
            self.assertEqual(bound["handoffDigest"], "sha256:" + "e" * 64)
            self.assertNotIn("releasedAt", bound)

    def test_bind_rejects_wrong_or_released_lease_without_reacquire(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            acquired = acquire_consumer_lease(
                instance_generation="runtime-1",
                target="gamma-local",
                device="SIM-1",
                consumer="flutter-run-456",
                package_name="com.quwoquan.gamma.debug",
                ports=(),
                platform="ios-simulator",
            )
            with self.assertRaisesRegex(ValueError, "leaseId mismatch"):
                bind_consumer_lease(
                    instance_generation="runtime-1",
                    target="gamma-local",
                    device="SIM-1",
                    consumer="flutter-run-456",
                    lease_id="sha256:" + "0" * 64,
                    handoff_digest="sha256:" + "1" * 64,
                )
            release_consumer_lease(
                lease_id=acquired["leaseId"], instance_generation="runtime-1",
                target="gamma-local",
                device="SIM-1",
                consumer="flutter-run-456",
            )
            with self.assertRaisesRegex(ValueError, "already released"):
                bind_consumer_lease(
                    instance_generation="runtime-1",
                    target="gamma-local",
                    device="SIM-1",
                    consumer="flutter-run-456",
                    lease_id=str(acquired["leaseId"]),
                    handoff_digest="sha256:" + "1" * 64,
                )

    def test_build_grace_blocks_without_adb_probe(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                instance_generation="runtime-1",
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

    def test_release_retains_generation_evidence_and_frees_occupancy(self) -> None:
        """交回 lease 必须同时成立两件事：证据留下，占用让出。

        删文件会让 device_bound 拿不到本代际证据；只改状态却仍计入占用，会让
        下一个消费方永远抢不到本地运行时。
        """
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                instance_generation="runtime-1",
                target="gamma-local",
                device="SIMULATOR-UDID",
                consumer="patrol",
                package_name="com.quwoquan.testhost.patrol",
                ports=(),
                platform="ios-simulator",
                release_id="release-1",
                manifest_digest="sha256:" + "c" * 64,
                readiness_receipt_digest="sha256:" + "d" * 64,
                build_grace_seconds=0,
            )
            started_at = datetime.fromisoformat(
                str(lease["startedAt"]).replace("Z", "+00:00")
            )
            self.assertTrue(
                release_consumer_lease(
                    lease_id=lease["leaseId"], instance_generation="runtime-1",
                    target="gamma-local",
                    device="SIMULATOR-UDID",
                    consumer="patrol",
                )
            )

            retained = list_consumer_leases("gamma-local")
            self.assertEqual(len(retained), 1)
            self.assertEqual(retained[0]["releaseId"], "release-1")
            self.assertEqual(retained[0]["manifestDigest"], "sha256:" + "c" * 64)
            self.assertEqual(
                retained[0]["readinessReceiptDigest"],
                "sha256:" + "d" * 64,
            )

            inspected = inspect_consumer_leases(
                "gamma-local",
                now=started_at + timedelta(seconds=30),
                runner=lambda _: self.fail(
                    "released leases must not be probed for liveness"
                ),
            )
            self.assertEqual([item["state"] for item in inspected], ["released"])

            self.assertEqual(
                active_consumer_leases(
                    "gamma-local",
                    now=started_at + timedelta(seconds=30),
                    runner=lambda _: self.fail(
                        "released leases must not be probed for liveness"
                    ),
                ),
                [],
                "released leases must not block another consumer",
            )

    def test_released_lease_becomes_stale_after_maximum_age(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                instance_generation="runtime-1",
                target="gamma-local",
                device="device-1",
                consumer="patrol",
                package_name="com.quwoquan.testhost.patrol",
                ports=(17000,),
                build_grace_seconds=0,
            )
            started_at = datetime.fromisoformat(
                str(lease["startedAt"]).replace("Z", "+00:00")
            )
            release_consumer_lease(
                lease_id=lease["leaseId"], instance_generation="runtime-1",
                target="gamma-local",
                device="device-1",
                consumer="patrol",
            )

            inspected = inspect_consumer_leases(
                "gamma-local",
                now=started_at + timedelta(seconds=MAX_LEASE_AGE_SECONDS + 1),
                runner=lambda _: self.fail("aged leases must not be probed"),
            )
            self.assertEqual([item["state"] for item in inspected], ["stale"])

    def test_disconnected_device_prunes_expired_build_lease(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                instance_generation="runtime-1",
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
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["state"], "active_unverified")
            self.assertEqual(
                len(list_consumer_leases("alpha-local")),
                1,
                "stale cleanup requires an explicit release or GC operation",
            )

    def test_stackctl_down_is_gate_blocked_by_flutter_consumer(self) -> None:
        from quwoquan_ops.cli import stackctl
        acquire_consumer_lease(target="alpha-local", device="device-1", consumer="flutter", package_name="app", ports=(17000,), instance_generation="runtime-1")
        args = stackctl.build_parser().parse_args(["down", "--target", "alpha-local"])
        with patch.object(stackctl, "_command_down_unlocked", side_effect=AssertionError("leased runtime must not stop")):
            payload = stackctl.command_down(args)
        self.assertEqual(payload["exitCode"], 2)
        self.assertIn("consumer lease", " ".join(payload["details"]))



if __name__ == "__main__":
    unittest.main()
