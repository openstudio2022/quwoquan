"""Canonical App launcher managed dispatcher entry contracts.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = APP_DIR.parent
LAUNCHER = APP_DIR / "run.sh"
PREFLIGHT_HANDOFF = (
    REPO_ROOT / "quwoquan_ops/cli/lib/app_debug_preflight_handoff.py"
)

_MANIFEST_DIGEST = "sha256:" + "1" * 64
_LEASE_DIGEST = "sha256:" + "3" * 64
_CONSUMER_ID = "flutter-run-managed-test"


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _passed_content_live_payload(
    *,
    readiness_ref: str = "/tmp/release-readiness.json",
    readiness_digest: str = "sha256:" + "2" * 64,
) -> dict[str, object]:
    return {
        "schema": "quwoquan_ops.app_debug_preflight",
        "purpose": "content_live",
        "status": "passed",
        "contentLive": "passed",
        "nonPromotable": True,
        "contentBindingState": "bound",
        "target": "alpha-local",
        "firstBlocker": "",
        "warnings": [],
        "releaseId": "research-alpha",
        "manifestDigest": _MANIFEST_DIGEST,
        "readinessReceiptRef": readiness_ref,
        "readinessReceiptDigest": readiness_digest,
        "contentBinding": {
            "releaseId": "research-alpha",
            "verifyRunId": "verify-alpha",
            "manifestDigest": _MANIFEST_DIGEST,
            "readinessPhase": "research",
            "readinessReceiptRef": readiness_ref,
            "readinessReceiptDigest": readiness_digest,
        },
    }


def _passed_content_preflight_payload(
    *,
    readiness_ref: str,
    readiness_digest: str,
) -> dict[str, object]:
    return {
        "schema": "quwoquan_ops.app_content_preflight",
        "target": "alpha-local",
        "status": "passed",
        "exitCode": 0,
        "details": [],
        "releaseId": "research-alpha",
        "manifestDigest": _MANIFEST_DIGEST,
        "readinessReceiptRef": readiness_ref,
        "readinessReceiptDigest": readiness_digest,
        "releaseProbe": {
            "exitCode": 0,
            "executedSampleCount": 100,
            "mediaChecks": {"automatic": True},
        },
    }


class CanonicalLauncherManagedEntryContractTest(unittest.TestCase):
    def _workspace(
        self,
        *,
        managed: dict[str, object] | None = None,
        managed_exit: int = 0,
        preflight: dict[str, object] | None = None,
    ) -> tuple[tempfile.TemporaryDirectory[str], Path, dict[str, str]]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        app = root / "quwoquan_app"
        app.mkdir()
        (app / "run.sh").write_text(
            LAUNCHER.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (app / "run.sh").chmod(0o755)
        executor_dir = app / "scripts/device"
        (executor_dir / "canonical_app_instance").mkdir(parents=True)
        for relative in (
            "canonical_app_instance/__init__.py",
            "canonical_app_instance/arguments.py",
        ):
            (executor_dir / relative).write_text(
                (APP_DIR / "scripts/device" / relative).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        (app / "ios/Pods").mkdir(parents=True)
        (app / "ios/Podfile.lock").write_text("locked\n", encoding="utf-8")
        (app / "ios/Pods/Manifest.lock").write_text("locked\n", encoding="utf-8")

        stackctl = root / "quwoquan_ops/cli/stackctl.py"
        stackctl.parent.mkdir(parents=True)
        managed_log = root / "managed_calls.log"
        stackctl_log = root / "stackctl_calls.log"
        preflight_log = root / "preflight_calls.log"
        stackctl.write_text(
            "#!/usr/bin/env python3\n"
            "import hashlib\n"
            "import json\n"
            "import sys\n"
            "from pathlib import Path\n"
            f"managed = {managed!r}\n"
            f"preflight = {preflight!r}\n"
            f"managed_exit = {managed_exit!r}\n"
            f"consumer_id = {_CONSUMER_ID!r}\n"
            f"lease_id = {_LEASE_DIGEST!r}\n"
            f"lease_state_path = Path({str(root / 'managed_lease_state.json')!r})\n"
            f"stackctl_log = Path({str(root / 'stackctl_calls.log')!r})\n"
            "with stackctl_log.open('a', encoding='utf-8') as handle:\n"
            "    handle.write(' '.join(sys.argv[1:]) + '\\n')\n"
            "if lease_state_path.is_file():\n"
            "    lease_state = json.loads(lease_state_path.read_text(encoding='utf-8'))\n"
            "    consumer_id = str(lease_state['consumer'])\n"
            "    lease_id = str(lease_state['leaseId'])\n"
            "if '--consumer-id' in sys.argv:\n"
            "    consumer_id = sys.argv[sys.argv.index('--consumer-id') + 1]\n"
            "    lease_id = 'sha256:' + hashlib.sha256(('ios-simulator\\0alpha-local\\0device-1\\0' + consumer_id).encode('utf-8')).hexdigest()\n"
            "if 'app-managed-prepare' in sys.argv:\n"
            f"    with Path({str(managed_log)!r}).open("
            "'a', encoding='utf-8') as handle:\n"
            "        handle.write(' '.join(sys.argv[1:]) + '\\n')\n"
            "    value = dict(managed or {})\n"
            "    receipt_path = Path(str(value.get('receiptPath') or ''))\n"
            "    if receipt_path.is_file():\n"
            "        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))\n"
            "        receipt['consumerId'] = consumer_id\n"
            "        lease_id = 'sha256:' + hashlib.sha256(('ios-simulator\\0alpha-local\\0device-1\\0' + consumer_id).encode('utf-8')).hexdigest()\n"
            "        receipt['consumerLeaseId'] = lease_id\n"
            "        lease_state_path.write_text(json.dumps({'consumer': consumer_id, 'leaseId': lease_id}), encoding='utf-8')\n"
            "        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + '\\n', encoding='utf-8')\n"
            "        if str(value.get('receiptDigest') or '') != 'sha256:' + 'f' * 64:\n"
            "            value['receiptDigest'] = 'sha256:' + hashlib.sha256(receipt_path.read_bytes()).hexdigest()\n"
            "    value.setdefault('exitCode', 0 if managed_exit == 0 else 2)\n"
            "    value.setdefault('summary', 'managed preparation test')\n"
            "    value.setdefault('details', [])\n"
            "    value.setdefault('warnings', [])\n"
            "    value.setdefault('reportDir', 'test-report')\n"
            "    value.setdefault('startedAt', '2026-09-01T00:00:00Z')\n"
            "    value.setdefault('endedAt', '2026-09-01T00:00:01Z')\n"
            "    value.setdefault('durationMs', 1000)\n"
            "    print(json.dumps(value))\n"
            "    raise SystemExit(managed_exit)\n"
            "if 'consumer-lease' in sys.argv and 'status' in sys.argv:\n"
            "    print(json.dumps({'exitCode': 0, 'occupyingLeases': [{\n"
            "        'target': 'alpha-local', 'device': 'device-1',\n"
            "        'consumer': consumer_id, 'leaseId': lease_id,\n"
            "    }]}))\n"
            "    raise SystemExit(0)\n"
            "if 'consumer-lease' in sys.argv and 'bind' in sys.argv:\n"
            "    print('{}')\n"
            "    raise SystemExit(0)\n"
            "if 'consumer-lease' in sys.argv and 'release' in sys.argv:\n"
            "    print('{}')\n"
            "    raise SystemExit(0)\n"
            "if 'app-debug-preflight' in sys.argv:\n"
            f"    with Path({str(preflight_log)!r}).open("
            "'a', encoding='utf-8') as handle:\n"
            "        handle.write(' '.join(sys.argv[1:]) + '\\n')\n"
            "    print(json.dumps(preflight or {}))\n"
            "    raise SystemExit(0)\n"
            "if 'verify' in sys.argv and 'content-delivery' in sys.argv:\n"
            "    print('{}')\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit(93)\n",
            encoding="utf-8",
        )

        dev_up = root / "quwoquan_ops/cli/lib/dev_up.py"
        dev_up.parent.mkdir(parents=True)
        (dev_up.parent / PREFLIGHT_HANDOFF.name).write_text(
            PREFLIGHT_HANDOFF.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        find_device_log = root / "find_device.log"
        dev_up.write_text(
            "from pathlib import Path\n"
            f"FIND_DEVICE_LOG = Path({str(find_device_log)!r})\n"
            "def find_device(*_args, **_kwargs):\n"
            "    FIND_DEVICE_LOG.write_text('called\\n', encoding='utf-8')\n"
            "    return None\n",
            encoding="utf-8",
        )
        bin_dir = root / "bin"
        bin_dir.mkdir()
        flutter_log = root / "flutter.log"
        flutter = bin_dir / "flutter"
        flutter.write_text(
            "#!/usr/bin/env bash\n"
            f"printf '%s\\n' \"$*\" >> {flutter_log!s}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        flutter.chmod(0o755)
        environment = dict(os.environ)
        environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"
        environment.pop("QWQ_ENVIRONMENT", None)
        environment.pop("PYTHONPATH", None)
        environment.pop("QWQ_MANAGED_FLUTTER_ENTRY", None)
        environment.pop("QWQ_APP_DEBUG_PREFLIGHT_RECEIPT", None)
        return temporary, app, environment

    def _write_managed_receipt(
        self,
        root: Path,
        *,
        device_id: str = "device-1",
        target: str = "alpha-local",
    ) -> tuple[Path, str]:
        """落一份与生产 schema 同构的 prepared receipt + 两份 strict receipt。"""
        managed_dir = root / "managed-preparation"
        managed_dir.mkdir(parents=True, exist_ok=True)
        readiness_ref = managed_dir / "release-readiness.json"
        readiness_ref.write_text(
            json.dumps(
                {
                    "schema": "quwoquan_data.release_readiness.v1",
                    "releaseId": "research-alpha",
                    "verifyRunId": "verify-alpha",
                    "manifestDigest": _MANIFEST_DIGEST,
                    "readinessPhase": "research",
                    "passed": True,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        readiness_digest = _sha256_file(readiness_ref)
        strict_ref = managed_dir / "app-debug-preflight.json"
        strict_ref.write_text(
            json.dumps(
                {
                    "schema": "quwoquan_ops.app_debug_preflight",
                    "purpose": "content_live",
                    "target": "alpha-local",
                    "payload": _passed_content_live_payload(
                        readiness_ref=str(readiness_ref),
                        readiness_digest=readiness_digest,
                    ),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        content_payload = _passed_content_preflight_payload(
            readiness_ref=str(readiness_ref),
            readiness_digest=readiness_digest,
        )
        strict_content_ref = managed_dir / "app-content-preflight.exact.json"
        strict_content_ref.write_text(
            json.dumps(
                {
                    "schema": "quwoquan_ops.app_content_preflight_exact.v1",
                    "target": "alpha-local",
                    "status": "passed",
                    "releaseId": "research-alpha",
                    "manifestDigest": _MANIFEST_DIGEST,
                    "readinessReceiptRef": str(readiness_ref),
                    "readinessReceiptDigest": readiness_digest,
                    "releaseProbe": content_payload["releaseProbe"],
                    "payload": content_payload,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        receipt_path = managed_dir / "managed-preparation.json"
        receipt_path.write_text(
            json.dumps(
                {
                    "schema": "quwoquan_ops.app_managed_preparation.v1",
                    "target": target,
                    "environment": "alpha",
                    "platform": "ios",
                    "deviceId": device_id,
                    "runtimeIdentity": {
                        "startupAttemptId": "alpha-attempt-1",
                        "composeProject": "quwoquan_alpha_test_live",
                        "composeDigest": "sha256:" + "4" * 64,
                        "configurationDigest": "sha256:" + "5" * 64,
                        "providerRuntimeDigest": "sha256:" + "6" * 64,
                        "reused": True,
                        "replaced": False,
                    },
                    "consumerId": _CONSUMER_ID,
                    "consumerLeaseId": _LEASE_DIGEST,
                    "androidReversePorts": "",
                    "androidReverseOwnedPorts": "",
                    "deviceTrustReceiptRef": "",
                    "deviceTrustReceiptDigest": "",
                    "contentBinding": {
                        "releaseId": "research-alpha",
                        "verifyRunId": "verify-alpha",
                        "manifestDigest": _MANIFEST_DIGEST,
                        "readinessPhase": "research",
                        "readinessReceiptRef": str(readiness_ref),
                        "readinessReceiptDigest": readiness_digest,
                    },
                    "strictPreflightReceiptRef": str(strict_ref),
                    "strictPreflightReceiptDigest": _sha256_file(strict_ref),
                    "strictContentPreflightReceiptRef": str(strict_content_ref),
                    "strictContentPreflightReceiptDigest": _sha256_file(
                        strict_content_ref
                    ),
                    "createdAt": "2026-09-01T00:00:00Z",
                    "status": "prepared",
                    "firstBlocker": "",
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return receipt_path, _sha256_file(receipt_path)

    def test_managed_entry_calls_prepare_once_and_reuses_its_preflight(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        with temporary:
            root = Path(temporary.name)
            receipt_path, receipt_digest = self._write_managed_receipt(root)
            temporary2, app, environment = self._workspace(
                managed={
                    "status": "prepared",
                    "firstBlocker": "",
                    "receiptPath": str(receipt_path),
                    "receiptDigest": receipt_digest,
                },
            )
            with temporary2:
                environment["QWQ_MANAGED_FLUTTER_ENTRY"] = "1"
                result = subprocess.run(
                    [
                        "bash",
                        "run.sh",
                        "--mode",
                        "content-live",
                        "--device",
                        "device-1",
                    ],
                    cwd=app,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                sandbox = app.parent
                managed_calls = (
                    (sandbox / "managed_calls.log").read_text(encoding="utf-8")
                )
                self.assertEqual(
                    len(managed_calls.strip().splitlines()), 1, managed_calls
                )
                self.assertIn("--target alpha-local", managed_calls)
                self.assertIn("--device device-1", managed_calls)
                consumer_args = managed_calls.strip().split()
                consumer_id = consumer_args[consumer_args.index("--consumer-id") + 1]
                self.assertRegex(consumer_id, r"^flutter-run-[0-9]+$")
                stackctl_calls = (sandbox / "stackctl_calls.log").read_text(
                    encoding="utf-8"
                )
                self.assertNotIn("consumer-lease acquire", stackctl_calls)
                self.assertIn("consumer-lease status", stackctl_calls)
                self.assertIn(
                    "managed preparation receipt verified", result.stdout
                )
                # managed receipt 的 strict preflight 直接进入单一 owner 复用轨，
                # launcher 不再执行第二次宽松 preflight。
                self.assertIn(
                    "reusing upstream content_live preflight", result.stdout
                )
                self.assertFalse(
                    (sandbox / "preflight_calls.log").exists(),
                    "managed entry must not rerun app-debug-preflight",
                )
                # 内容绑定取自 receipt exact binding，继续走既有 build/install 链，
                # 在沙箱内推进到设备准备门（证明未提前退出）。
                self.assertTrue((sandbox / "find_device.log").exists())
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertFalse((sandbox / "flutter.log").exists())

    def test_managed_receipt_identity_mismatch_is_typed_receipt_invalid(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        with temporary:
            root = Path(temporary.name)
            receipt_path, receipt_digest = self._write_managed_receipt(
                root, device_id="another-device"
            )
            temporary2, app, environment = self._workspace(
                managed={
                    "status": "prepared",
                    "firstBlocker": "",
                    "receiptPath": str(receipt_path),
                    "receiptDigest": receipt_digest,
                },
            )
            with temporary2:
                environment["QWQ_MANAGED_FLUTTER_ENTRY"] = "1"
                result = subprocess.run(
                    [
                        "bash",
                        "run.sh",
                        "--mode",
                        "content-live",
                        "--device",
                        "device-1",
                    ],
                    cwd=app,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                sandbox = app.parent
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("APP.PREPARATION.receipt_invalid", result.stderr)
                self.assertIn("deviceId mismatch", result.stderr)
                self.assertFalse((sandbox / "preflight_calls.log").exists())
                self.assertFalse((sandbox / "find_device.log").exists())
                self.assertFalse((sandbox / "flutter.log").exists())

    def test_managed_receipt_digest_mismatch_is_typed_receipt_invalid(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        with temporary:
            root = Path(temporary.name)
            receipt_path, _receipt_digest = self._write_managed_receipt(root)
            temporary2, app, environment = self._workspace(
                managed={
                    "status": "prepared",
                    "firstBlocker": "",
                    "receiptPath": str(receipt_path),
                    "receiptDigest": "sha256:" + "f" * 64,
                },
            )
            with temporary2:
                environment["QWQ_MANAGED_FLUTTER_ENTRY"] = "1"
                result = subprocess.run(
                    [
                        "bash",
                        "run.sh",
                        "--mode",
                        "content-live",
                        "--device",
                        "device-1",
                    ],
                    cwd=app,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("APP.PREPARATION.receipt_invalid", result.stderr)
                self.assertIn("digest mismatch", result.stderr)
                self.assertFalse(
                    (app.parent / "find_device.log").exists()
                )

    def _assert_prebuild_receipt_invalid(
        self,
        *,
        mutate,
        expected_detail: str,
    ) -> None:
        temporary = tempfile.TemporaryDirectory()
        with temporary:
            root = Path(temporary.name)
            receipt_path, _ = self._write_managed_receipt(root)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            mutate(receipt)
            receipt_path.write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            temporary2, app, environment = self._workspace(
                managed={
                    "status": "prepared",
                    "firstBlocker": "",
                    "receiptPath": str(receipt_path),
                    "receiptDigest": _sha256_file(receipt_path),
                },
            )
            with temporary2:
                environment["QWQ_MANAGED_FLUTTER_ENTRY"] = "1"
                result = subprocess.run(
                    [
                        "bash",
                        "run.sh",
                        "--mode",
                        "content-live",
                        "--device",
                        "device-1",
                    ],
                    cwd=app,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("APP.PREPARATION.receipt_invalid", result.stderr)
                self.assertIn(expected_detail, result.stderr)
                self.assertFalse((app.parent / "find_device.log").exists())
                self.assertFalse((app.parent / "flutter.log").exists())

    def test_content_payload_identity_drift_is_receipt_invalid_before_build(self) -> None:
        def mutate(receipt: dict[str, object]) -> None:
            ref = Path(str(receipt["strictContentPreflightReceiptRef"]))
            envelope = json.loads(ref.read_text(encoding="utf-8"))
            envelope["payload"]["releaseId"] = "drifted-release"
            ref.write_text(
                json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            receipt["strictContentPreflightReceiptDigest"] = _sha256_file(ref)

        self._assert_prebuild_receipt_invalid(
            mutate=mutate,
            expected_detail="strict content preflight payload drifted",
        )

    def test_readiness_byte_digest_drift_is_receipt_invalid_before_build(self) -> None:
        def mutate(receipt: dict[str, object]) -> None:
            binding = receipt["contentBinding"]
            assert isinstance(binding, dict)
            ref = Path(str(binding["readinessReceiptRef"]))
            ref.write_text(ref.read_text(encoding="utf-8") + " ", encoding="utf-8")

        self._assert_prebuild_receipt_invalid(
            mutate=mutate,
            expected_detail="content readiness byte digest mismatch",
        )

    def test_strict_content_digest_drift_is_receipt_invalid_before_build(self) -> None:
        def mutate(receipt: dict[str, object]) -> None:
            receipt["strictContentPreflightReceiptDigest"] = "sha256:" + "f" * 64

        self._assert_prebuild_receipt_invalid(
            mutate=mutate,
            expected_detail="strict content preflight digest mismatch",
        )

    def test_managed_prepare_block_propagates_the_typed_first_blocker(self) -> None:
        temporary, app, environment = self._workspace(
            managed={
                "status": "blocked",
                "firstBlocker": "APP.PREPARATION.runtime_unavailable",
                "details": ["running runtime identity drifted"],
                "receiptPath": "",
                "receiptDigest": "",
            },
            managed_exit=2,
        )
        with temporary:
            environment["QWQ_MANAGED_FLUTTER_ENTRY"] = "1"
            result = subprocess.run(
                [
                    "bash",
                    "run.sh",
                    "--mode",
                    "content-live",
                    "--device",
                    "device-1",
                ],
                cwd=app,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            sandbox = app.parent
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("APP.PREPARATION.runtime_unavailable", result.stderr)
            self.assertIn("running runtime identity drifted", result.stderr)
            self.assertFalse((sandbox / "preflight_calls.log").exists())
            self.assertFalse((sandbox / "find_device.log").exists())

    def test_unset_managed_entry_never_calls_app_managed_prepare(self) -> None:
        temporary, app, environment = self._workspace(
            preflight=_passed_content_live_payload(),
        )
        with temporary:
            result = subprocess.run(
                ["bash", "run.sh", "--mode", "content-live", "-d", "device-1"],
                cwd=app,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            sandbox = app.parent
            self.assertFalse(
                (sandbox / "managed_calls.log").exists(),
                "direct run.sh must keep zero managed preparation calls",
            )
            # 未设变量时保持既有 test_live 语义：launcher 自己拥有 preflight。
            preflight_calls = (
                (sandbox / "preflight_calls.log").read_text(encoding="utf-8")
            )
            self.assertEqual(len(preflight_calls.strip().splitlines()), 1)
            self.assertTrue((sandbox / "find_device.log").exists())
            self.assertEqual(result.returncode, 2, result.stdout)

    def test_managed_block_precedes_the_single_preflight_owner(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")

        managed = source.index("app-managed-prepare")
        preflight_owner = source.index(
            'app-debug-preflight --purpose "$PREFLIGHT_PURPOSE"'
        )
        self.assertLess(managed, preflight_owner)
        self.assertIn('QWQ_MANAGED_FLUTTER_ENTRY:-', source)
        # trust 漂移修正：安装身份必须是真实 consumer lease，不允许 fabricated id。
        self.assertIn('--lease-id "$QWQ_CONSUMER_LEASE_ID"', source)
        self.assertNotIn('--lease-id "canonical-launcher:', source)
        # managed 模式复用 preparation 持有的同一 consumer lease/trust。
        self.assertIn('reusing managed preparation consumer lease', source)
        self.assertIn('reusing managed preparation device trust', source)
        self.assertIn('QWQ_RUN_CONSUMER_ID="flutter-run-$$"', source)
        self.assertNotIn('QWQ_RUN_CONSUMER_ID="${QWQ_RUN_CONSUMER_ID:-', source)
        self.assertIn('--consumer-id "$QWQ_RUN_CONSUMER_ID"', source)
        self.assertIn('consumer-lease bind', source)
        self.assertIn('--lease-id "$QWQ_CONSUMER_LEASE_ID"', source)
        # dispatcher 契约：--device 是 -d/--device-id 的别名。
        self.assertIn("-d|--device-id|--device)", source)
        self.assertIn("--device-id=*|--device=*)", source)

    def test_direct_trust_install_arms_symmetric_cleanup_only_on_success(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")
        direct_start = source.index('DEVICE_TRUST_PLATFORM="$QWQ_RUN_DEVICE_KIND"')
        direct_end = source.index("RUNTIME_CONFIG_MATERIAL_ROOT=", direct_start)
        direct = source[direct_start:direct_end]

        success = direct.index(
            'if PYTHONDONTWRITEBYTECODE=1 "${DEVICE_TRUST_COMMAND[@]}" >/dev/null; then'
        )
        failure = direct.index("else", success)
        armed_platform = direct.index(
            'QWQ_MANAGED_DEVICE_TRUST_PLATFORM="$DEVICE_TRUST_PLATFORM"', success
        )
        armed_cleanup = direct.index("QWQ_MANAGED_TRUST_CLEANUP_REQUIRED=1", success)
        self.assertLess(success, armed_platform)
        self.assertLess(armed_platform, failure)
        self.assertLess(armed_cleanup, failure)
        self.assertNotIn("QWQ_MANAGED_TRUST_CLEANUP_REQUIRED=1", direct[failure:])

        cleanup_start = source.index("cleanup_managed_handoff_resources()")
        cleanup_end = source.index("managed_prelaunch_cleanup()", cleanup_start)
        cleanup = source[cleanup_start:cleanup_end]
        trust_release = cleanup.index("device-trust")
        lease_release = cleanup.index("consumer-lease release")
        self.assertLess(trust_release, lease_release)
        self.assertIn('--platform "$QWQ_MANAGED_DEVICE_TRUST_PLATFORM"', cleanup)
        self.assertIn('--lease-id "$QWQ_CONSUMER_LEASE_ID"', cleanup)


if __name__ == "__main__":
    unittest.main()
