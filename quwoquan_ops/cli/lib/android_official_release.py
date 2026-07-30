from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse


class AndroidOfficialReleaseError(RuntimeError):
    pass


def package_android_official_release(
    *,
    apk_path: Path,
    package_root: Path,
    public_origin: str,
    download_origin: str,
    expected_package: str,
    expected_signing_certificate_sha256: str,
    verify_remote: bool = False,
    apkanalyzer: str = "",
    apksigner: str = "",
) -> dict[str, object]:
    apk_path = apk_path.resolve()
    if not apk_path.is_file() or apk_path.suffix.lower() != ".apk":
        raise AndroidOfficialReleaseError(f"signed APK not found: {apk_path}")
    analyzer = apkanalyzer or _android_build_tool("apkanalyzer")
    signer = apksigner or _android_build_tool("apksigner")
    package_name = _tool_output(
        [analyzer, "manifest", "application-id", str(apk_path)],
        "read APK package name",
    )
    version_name = _tool_output(
        [analyzer, "manifest", "version-name", str(apk_path)],
        "read APK version name",
    )
    build_number = _tool_output(
        [analyzer, "manifest", "version-code", str(apk_path)],
        "read APK build number",
    )
    min_android_version = _tool_output(
        [analyzer, "manifest", "min-sdk", str(apk_path)],
        "read APK minimum Android version",
    )
    if package_name != expected_package:
        raise AndroidOfficialReleaseError(
            f"APK package mismatch: {package_name} != {expected_package}"
        )
    if not re.fullmatch(r"[1-9][0-9]{0,17}", build_number):
        raise AndroidOfficialReleaseError(f"APK build number is invalid: {build_number}")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}(?:[-.][A-Za-z0-9]+)*", version_name):
        raise AndroidOfficialReleaseError(f"APK version name is invalid: {version_name}")

    signer_output = _tool_output(
        [signer, "verify", "--print-certs", str(apk_path)],
        "verify APK signature",
    )
    certificate_match = re.search(
        r"certificate SHA-256 digest:\s*([0-9A-Fa-f:]{64,95})",
        signer_output,
        re.IGNORECASE,
    )
    if certificate_match is None:
        raise AndroidOfficialReleaseError(
            "apksigner did not return a SHA-256 signing certificate digest"
        )
    certificate_sha256 = certificate_match.group(1).replace(":", "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", certificate_sha256):
        raise AndroidOfficialReleaseError("APK signing certificate digest is invalid")
    expected_certificate = (
        expected_signing_certificate_sha256.strip().replace(":", "").lower()
    )
    if not re.fullmatch(r"[0-9a-f]{64}", expected_certificate):
        raise AndroidOfficialReleaseError(
            "expected APK signing certificate SHA-256 is required"
        )
    if certificate_sha256 != expected_certificate:
        raise AndroidOfficialReleaseError(
            "APK signing certificate does not match the trusted production identity"
        )

    public_origin = _trusted_origin(public_origin, "public web origin")
    download_origin = _trusted_origin(download_origin, "APK download origin")
    if not re.fullmatch(r"[1-9][0-9]{0,2}", min_android_version):
        raise AndroidOfficialReleaseError(
            f"APK minimum Android version is invalid: {min_android_version}"
        )
    artifact_name = f"quwoquan-{build_number}.apk"
    apk_url = urljoin(
        download_origin.rstrip("/") + "/",
        f"download/android/{version_name}/{build_number}/{artifact_name}",
    )
    apk_sha256 = _sha256(apk_path)
    apk_size = apk_path.stat().st_size
    if apk_size <= 0:
        raise AndroidOfficialReleaseError("APK is empty")
    if verify_remote:
        _verify_remote_artifact(
            apk_url=apk_url,
            expected_sha256=apk_sha256,
            expected_size=apk_size,
        )

    release_dir = package_root / "official-release" / "android" / build_number
    release_dir.mkdir(parents=True, exist_ok=True)
    packaged_apk = release_dir / artifact_name
    shutil.copy2(apk_path, packaged_apk)
    manifest: dict[str, object] = {
        "schema": "qwq.android.official-release",
        "platform": "android",
        "versionName": version_name,
        "buildNumber": build_number,
        "minAndroidVersion": min_android_version,
        "packageName": package_name,
        "apkUrl": apk_url,
        "apkSHA256": apk_sha256,
        "apkSizeBytes": apk_size,
        "apkSigningCertificateSHA256": certificate_sha256,
        "apkHostAllowlist": [urlparse(download_origin).hostname],
        "publicOrigin": public_origin,
        "recoveryUrl": public_origin.rstrip("/") + "/download",
        "packagedAPK": packaged_apk.name,
        "remoteVerified": verify_remote,
    }
    manifest_path = release_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    environment = {
        "PRODUCT_OPS_APP_RELEASE_PUBLIC_ORIGIN": public_origin,
        "PRODUCT_OPS_APP_RELEASE_RECOVERY_URL": manifest["recoveryUrl"],
        "PRODUCT_OPS_ANDROID_LATEST_VERSION": version_name,
        "PRODUCT_OPS_ANDROID_LATEST_BUILD": build_number,
        "PRODUCT_OPS_ANDROID_APK_URL": apk_url,
        "PRODUCT_OPS_ANDROID_APK_HOST_ALLOWLIST": urlparse(download_origin).hostname,
        "PRODUCT_OPS_ANDROID_APK_PACKAGE_NAME": package_name,
        "PRODUCT_OPS_ANDROID_APK_SHA256": apk_sha256,
        "PRODUCT_OPS_ANDROID_APK_SIZE_BYTES": str(apk_size),
        "PRODUCT_OPS_ANDROID_APK_SIGNING_CERTIFICATE_SHA256": certificate_sha256,
        "PRODUCT_OPS_ANDROID_MIN_ANDROID_VERSION": min_android_version,
    }
    env_path = release_dir / "product-ops.env"
    env_path.write_text(
        "".join(f"{key}={value}\n" for key, value in sorted(environment.items())),
        encoding="utf-8",
    )
    return {
        **manifest,
        "manifestPath": str(manifest_path),
        "environmentPath": str(env_path),
    }


def _android_build_tool(name: str) -> str:
    direct = shutil.which(name)
    if direct:
        return direct
    sdk_root = os.environ.get("ANDROID_SDK_ROOT", "").strip() or os.environ.get(
        "ANDROID_HOME", ""
    ).strip()
    if sdk_root:
        candidates = sorted(
            (Path(sdk_root) / "build-tools").glob(f"*/{name}"),
            reverse=True,
        )
        if candidates:
            return str(candidates[0])
        commandline = Path(sdk_root) / "cmdline-tools" / "latest" / "bin" / name
        if commandline.is_file():
            return str(commandline)
    raise AndroidOfficialReleaseError(
        f"Android SDK tool {name} is required to verify the official APK"
    )


def _tool_output(argv: list[str], label: str) -> str:
    result = subprocess.run(
        argv,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "LC_ALL": "C"},
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise AndroidOfficialReleaseError(f"{label} failed: {detail}")
    return result.stdout.strip()


def _trusted_origin(raw: str, label: str) -> str:
    value = raw.strip().rstrip("/")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise AndroidOfficialReleaseError(f"{label} must be an HTTPS origin")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_remote_artifact(
    *,
    apk_url: str,
    expected_sha256: str,
    expected_size: int,
) -> None:
    digest = hashlib.sha256()
    size = 0
    request = urllib.request.Request(
        apk_url,
        headers={"Accept": "application/vnd.android.package-archive"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status < 200 or response.status >= 300:
                raise AndroidOfficialReleaseError(
                    f"official APK download returned HTTP {response.status}"
                )
            cache_control = response.headers.get("Cache-Control", "").lower()
            if "immutable" not in cache_control:
                raise AndroidOfficialReleaseError(
                    "official APK response must use immutable cache semantics"
                )
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
            if content_type not in {
                "application/vnd.android.package-archive",
                "application/octet-stream",
            }:
                raise AndroidOfficialReleaseError(
                    f"official APK response has unexpected content type: {content_type}"
                )
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                size += len(chunk)
                if size > expected_size:
                    raise AndroidOfficialReleaseError(
                        "official APK download is larger than the packaged artifact"
                    )
                digest.update(chunk)
    except OSError as error:
        raise AndroidOfficialReleaseError(
            f"official APK download verification failed: {error}"
        ) from error
    if size != expected_size or digest.hexdigest() != expected_sha256:
        raise AndroidOfficialReleaseError(
            "official APK download digest/size differs from the signed package"
        )
    range_request = urllib.request.Request(
        apk_url,
        headers={
            "Accept": "application/vnd.android.package-archive",
            "Range": "bytes=0-0",
        },
    )
    try:
        with urllib.request.urlopen(range_request, timeout=15) as response:
            if response.status != 206:
                raise AndroidOfficialReleaseError(
                    "official APK download must support HTTP Range with 206"
                )
            content_range = response.headers.get("Content-Range", "")
            if not content_range.startswith("bytes 0-0/"):
                raise AndroidOfficialReleaseError(
                    "official APK Range response has invalid Content-Range"
                )
    except OSError as error:
        raise AndroidOfficialReleaseError(
            f"official APK Range verification failed: {error}"
        ) from error
