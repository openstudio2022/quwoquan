#!/usr/bin/env python3
"""官网网页版下载安装闭环 UAT runner（automationTier A2）。

从官网 `/download/android/latest.json` 拉取发布事实，下载官网签名 APK，
逐项完成 download_verify（URL 来源、SHA-256、签名证书摘要、包名比对），
再经 adb 完成安装（全新安装或同包名覆盖升级）、图标冷启动与首帧观测，
产出机器可读 `CaseResult`（phases[] + firstFailedPhaseId），供
user_acceptance 证据链消费；失败不得被后续成功覆盖。

- 包名期望值按 canonical application_identity（android × prod × release）
  派生，不写字面值；官网 APK 与市场包同源同 candidate。
- 无已连接设备时可 `--download-only`：只执行 download_verify，
  install/launch/first_frame 记为 skipped（不是 passed）。
- `--upgrade` 表示旧版本在设备上保留使用痕迹后的覆盖安装路径。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

APP_DIR = Path(__file__).resolve().parents[2]
ROOT = APP_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.app_identity import application_id_for  # noqa: E402

# Android 类 FQCN 固定在 namespace 下，与 applicationId 环境/模式后缀无关。
ANDROID_CLASS_NAMESPACE = "com.quwoquan.quwoquan_app"
LAUNCH_ACTIVITY = f"{ANDROID_CLASS_NAMESPACE}.MainActivity"
SPEC_REFS = (
    "specs/feature-tree/runtime/runtime-client-foundation/"
    "public-content-web-entry/spec.md",
    "specs/feature-tree/product-ops-growth/product-control-plane-foundation/"
    "app-release-recovery-routing/spec.md",
)
PHASE_IDS = ("download_verify", "install", "launch", "first_frame")
FIRST_FRAME_TIMEOUT_SECONDS = 60

REQUIRED_LATEST_FIELDS = (
    "latestVersion",
    "latestBuild",
    "apkUrl",
    "apkSHA256",
    "apkSigningCertificateSHA256",
    "packageName",
)


class PhaseFailure(Exception):
    def __init__(self, failure_code: str, message: str) -> None:
        super().__init__(message)
        self.failure_code = failure_code


def _fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise PhaseFailure("LATEST_MANIFEST_MALFORMED", f"{url} did not return an object")
    return payload


def _download_file(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url, timeout=300) as response:
        with destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _apksigner_certificate_sha256(apk_path: Path) -> str:
    """用 apksigner 实测 APK 签名证书摘要；工具缺席是失败而不是跳过。"""
    apksigner = shutil.which("apksigner")
    if apksigner is None:
        raise PhaseFailure(
            "APKSIGNER_UNAVAILABLE",
            "apksigner is required to verify the downloaded APK signing "
            "certificate; install the Android build-tools on this runner",
        )
    result = subprocess.run(
        [apksigner, "verify", "--print-certs", str(apk_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PhaseFailure(
            "APK_SIGNATURE_INVALID",
            f"apksigner rejected the downloaded APK: {result.stderr.strip()[:400]}",
        )
    match = re.search(
        r"certificate SHA-256 digest:\s*([0-9a-fA-F]{64})", result.stdout
    )
    if match is None:
        raise PhaseFailure(
            "APK_SIGNATURE_DIGEST_MISSING",
            "apksigner output did not contain a certificate SHA-256 digest",
        )
    return match.group(1).lower()


def run_download_verify(
    download_base_url: str,
    workdir: Path,
    *,
    verify_signature: bool = True,
) -> dict[str, Any]:
    """download_verify：URL 来源、SHA-256、签名、包名比对，全部同源事实。"""
    base = download_base_url.rstrip("/")
    base_parts = urllib.parse.urlsplit(base)
    if base_parts.scheme != "https":
        raise PhaseFailure(
            "DOWNLOAD_URL_NOT_HTTPS",
            f"official download base url must be https: {download_base_url}",
        )
    latest_url = f"{base}/download/android/latest.json"
    latest = _fetch_json(latest_url)
    missing = [
        field
        for field in REQUIRED_LATEST_FIELDS
        if not str(latest.get(field) or "").strip()
    ]
    if missing:
        raise PhaseFailure(
            "LATEST_MANIFEST_INCOMPLETE",
            f"latest.json is missing required fields: {', '.join(missing)}",
        )

    apk_url = str(latest["apkUrl"])
    apk_parts = urllib.parse.urlsplit(apk_url)
    if apk_parts.scheme != "https":
        raise PhaseFailure(
            "APK_URL_NOT_HTTPS", f"apkUrl must be https: {apk_url}"
        )

    expected_package = application_id_for("android", "prod", "release")
    if str(latest["packageName"]) != expected_package:
        raise PhaseFailure(
            "PACKAGE_NAME_MISMATCH",
            f"latest.json packageName={latest['packageName']} does not match "
            f"the canonical android prod release id {expected_package}",
        )

    apk_path = workdir / f"quwoquan-{latest['latestBuild']}.apk"
    _download_file(apk_url, apk_path)
    actual_sha256 = _sha256_of(apk_path)
    expected_sha256 = str(latest["apkSHA256"]).lower()
    if actual_sha256 != expected_sha256:
        raise PhaseFailure(
            "APK_SHA256_MISMATCH",
            f"downloaded APK sha256 {actual_sha256} does not match the "
            f"published fact {expected_sha256}",
        )

    signature_evidence: dict[str, Any] = {"verified": False}
    if verify_signature:
        actual_certificate = _apksigner_certificate_sha256(apk_path)
        expected_certificate = str(latest["apkSigningCertificateSHA256"]).lower()
        if actual_certificate != expected_certificate:
            raise PhaseFailure(
                "APK_SIGNING_CERTIFICATE_MISMATCH",
                f"APK signing certificate {actual_certificate} does not match "
                f"the published fact {expected_certificate}",
            )
        signature_evidence = {
            "verified": True,
            "certificateSha256": actual_certificate,
        }

    return {
        "latestUrl": latest_url,
        "apkUrl": apk_url,
        "apkPath": str(apk_path),
        "apkSha256": actual_sha256,
        "packageName": expected_package,
        "latestVersion": str(latest["latestVersion"]),
        "latestBuild": str(latest["latestBuild"]),
        "signature": signature_evidence,
    }


def _adb() -> str:
    adb = shutil.which("adb")
    if adb is None:
        raise PhaseFailure("ADB_UNAVAILABLE", "adb is required for install/launch")
    return adb


def _run_adb(device_id: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_adb(), "-s", device_id, *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def run_install(
    device_id: str, apk_path: str, package_name: str, *, upgrade: bool
) -> dict[str, Any]:
    path_probe = _run_adb(device_id, "shell", "pm", "path", package_name)
    previously_installed = path_probe.returncode == 0 and (
        path_probe.stdout or ""
    ).strip().startswith("package:")
    if previously_installed and not upgrade:
        removal = _run_adb(device_id, "uninstall", package_name)
        if removal.returncode != 0:
            raise PhaseFailure(
                "PREVIOUS_INSTALL_REMOVAL_FAILED",
                f"failed to remove the previous install: {removal.stderr.strip()[:300]}",
            )
    if upgrade and not previously_installed:
        raise PhaseFailure(
            "UPGRADE_BASELINE_MISSING",
            "--upgrade requires the previous version to be installed with real "
            "usage traces before the in-place install",
        )
    install = _run_adb(device_id, "install", "-r", apk_path)
    output = ((install.stdout or "") + (install.stderr or "")).strip()
    if install.returncode != 0 or "Success" not in output:
        raise PhaseFailure(
            "APK_INSTALL_FAILED", f"adb install failed: {output[:400]}"
        )
    return {
        "installMode": "upgrade_in_place" if upgrade else "fresh_install",
        "previouslyInstalled": previously_installed,
    }


def run_launch(device_id: str, package_name: str) -> dict[str, Any]:
    _run_adb(device_id, "shell", "am", "force-stop", package_name)
    _run_adb(device_id, "logcat", "-c")
    component = f"{package_name}/{LAUNCH_ACTIVITY}"
    start = _run_adb(device_id, "shell", "am", "start", "-W", "-n", component)
    output = ((start.stdout or "") + (start.stderr or "")).strip()
    if start.returncode != 0 or "Error" in output:
        raise PhaseFailure(
            "ICON_COLD_LAUNCH_FAILED", f"am start failed: {output[:400]}"
        )
    return {"component": component, "coldLaunch": True}


def run_first_frame(device_id: str, package_name: str) -> dict[str, Any]:
    deadline = time.monotonic() + FIRST_FRAME_TIMEOUT_SECONDS
    pattern = re.compile(
        rf"Displayed[^\n]*{re.escape(package_name)}|QWQ_APP_STARTUP_SEQUENCE"
    )
    while time.monotonic() < deadline:
        logcat = _run_adb(device_id, "logcat", "-d", "-v", "brief")
        match = pattern.search(logcat.stdout or "")
        if match is not None:
            return {"evidenceLine": match.group(0)[:200]}
        time.sleep(2)
    raise PhaseFailure(
        "FIRST_FRAME_TIMEOUT",
        f"no first frame evidence within {FIRST_FRAME_TIMEOUT_SECONDS}s",
    )


def execute_case(args: argparse.Namespace) -> dict[str, Any]:
    workdir = Path(args.output_dir)
    workdir.mkdir(parents=True, exist_ok=True)

    phases: list[dict[str, Any]] = []
    first_failed: str = ""
    context: dict[str, Any] = {}

    def record(phase_id: str, status: str, **extra: Any) -> None:
        nonlocal first_failed
        row: dict[str, Any] = {"phaseId": phase_id, "status": status}
        row.update(extra)
        phases.append(row)
        if status == "failed" and not first_failed:
            first_failed = phase_id

    try:
        evidence = run_download_verify(
            args.download_base_url,
            workdir,
            verify_signature=not args.skip_signature_verify,
        )
        context = evidence
        record("download_verify", "passed", evidence=evidence)
    except PhaseFailure as failure:
        record(
            "download_verify",
            "failed",
            failureCode=failure.failure_code,
            message=str(failure),
        )

    device_id = str(args.device_id or "").strip()
    device_phases_enabled = bool(device_id) and not first_failed
    if not device_phases_enabled:
        skip_reason = (
            "download_verify failed" if first_failed else "--download-only"
        )
        for phase_id in ("install", "launch", "first_frame"):
            record(phase_id, "skipped", reason=skip_reason)
    else:
        package_name = str(context["packageName"])
        try:
            install_evidence = run_install(
                device_id,
                str(context["apkPath"]),
                package_name,
                upgrade=bool(args.upgrade),
            )
            record("install", "passed", evidence=install_evidence)
            launch_evidence = run_launch(device_id, package_name)
            record("launch", "passed", evidence=launch_evidence)
            frame_evidence = run_first_frame(device_id, package_name)
            record("first_frame", "passed", evidence=frame_evidence)
        except PhaseFailure as failure:
            recorded_ids = {row["phaseId"] for row in phases}
            for phase_id in ("install", "launch", "first_frame"):
                if phase_id in recorded_ids:
                    continue
                if not first_failed:
                    record(
                        phase_id,
                        "failed",
                        failureCode=failure.failure_code,
                        message=str(failure),
                    )
                else:
                    record(phase_id, "skipped", reason=f"{first_failed} failed")

    status = "failed" if first_failed else (
        "passed" if device_phases_enabled else "download_verified_only"
    )
    case_result = {
        "schema": "quwoquan_app.web_download_install_case_result",
        "caseId": (
            "web_download_install_upgrade" if args.upgrade
            else "web_download_install_fresh"
        ),
        "specRefs": list(SPEC_REFS),
        "automationTier": "A2",
        "executionMode": "unattended_runner",
        "channelId": "official_web",
        "deviceId": device_id,
        "status": status,
        "firstFailedPhaseId": first_failed,
        "phases": phases,
    }
    report_path = workdir / "case_result.json"
    report_path.write_text(
        json.dumps(case_result, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    case_result["reportPath"] = str(report_path)
    return case_result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--download-base-url",
        required=True,
        help="official web origin that serves /download/android/latest.json",
    )
    parser.add_argument(
        "--device-id",
        default="",
        help="connected Android device/emulator id; omit for --download-only",
    )
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="in-place upgrade over the previously installed same-package build",
    )
    parser.add_argument(
        "--skip-signature-verify",
        action="store_true",
        help=(
            "skip local apksigner certificate verification (only for runners "
            "without Android build-tools; download_verify then excludes the "
            "signature comparison and must not claim it)"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=str(
            ROOT / ".qwq_output/env/repo/runs/web_download_install_uat"
        ),
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.download_only:
        args.device_id = ""
    if not args.download_only and not str(args.device_id or "").strip():
        print(
            "GATE_BLOCK: --device-id is required unless --download-only",
            file=sys.stderr,
        )
        return 2
    case_result = execute_case(args)
    print(json.dumps(case_result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if case_result["status"] != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
