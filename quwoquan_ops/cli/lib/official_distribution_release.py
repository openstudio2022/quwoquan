from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from quwoquan_ops.cli.lib.android_official_release import _verify_remote_artifact
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    validate_manifest,
    validate_manifest_files,
)


class OfficialDistributionReleaseError(RuntimeError):
    pass


_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
_KINDS = {
    "web": "web",
    "app-release": "android",
}


def deploy_official_distribution(
    *,
    kind: str,
    package_manifest_path: Path,
    release_manifest_path: Path,
    distribution_root: Path,
    expected_current: str = "",
) -> dict[str, Any]:
    component_key = _component_key(kind)
    package_manifest_path = package_manifest_path.expanduser().resolve()
    release_manifest_path = release_manifest_path.expanduser().resolve()
    distribution_root = distribution_root.expanduser().resolve()
    release_manifest, release_digest = _release_manifest(release_manifest_path)
    package_manifest = _json_object(package_manifest_path, "distribution package manifest")
    _verify_component_binding(
        release_manifest=release_manifest,
        component_key=component_key,
        package_manifest_path=package_manifest_path,
        package_manifest=package_manifest,
    )
    _require_external_distribution_root(distribution_root)
    distribution_root.mkdir(parents=True, exist_ok=True)

    if kind == "web":
        result = _deploy_web(
            package_manifest_path=package_manifest_path,
            manifest=package_manifest,
            distribution_root=distribution_root,
            expected_current=expected_current,
        )
    else:
        result = _deploy_android(
            package_manifest_path=package_manifest_path,
            manifest=package_manifest,
            distribution_root=distribution_root,
            expected_current=expected_current,
        )
    receipt = {
        "schema": "qwq.official-distribution.receipt",
        "artifactKind": kind,
        "artifactDigest": release_digest,
        "candidateId": release_manifest["candidateId"],
        **result,
    }
    receipt_bytes = _canonical_bytes(receipt)
    receipt["receiptSHA256"] = "sha256:" + hashlib.sha256(receipt_bytes).hexdigest()
    receipt_path = distribution_root / "receipts" / (
        receipt["receiptSHA256"].removeprefix("sha256:") + ".json"
    )
    _atomic_json(receipt_path, receipt)
    return {**receipt, "receiptPath": str(receipt_path)}


def inspect_official_distribution(
    *,
    distribution_root: Path,
    public_origin: str = "",
    download_origin: str = "",
    verify_hosted: bool = False,
) -> dict[str, Any]:
    root = distribution_root.expanduser().resolve()
    _require_external_distribution_root(root)
    issues: list[str] = []
    web: dict[str, Any] = {"status": "missing"}
    android: dict[str, Any] = {"status": "missing"}

    web_current = root / "web" / "current"
    if web_current.is_symlink():
        try:
            resolved = web_current.resolve(strict=True)
            manifest = _json_object(resolved / "manifest.json", "deployed Web manifest")
            _verify_deployed_web(resolved, manifest)
            web = {
                "status": "ready",
                "releaseId": manifest["releaseId"],
                "contentSHA256": manifest["contentSHA256"],
            }
        except (OSError, KeyError, ValueError, OfficialDistributionReleaseError) as error:
            issues.append(f"Web distribution invalid: {error}")
            web = {"status": "invalid"}
    else:
        issues.append("Web distribution current pointer is missing")

    latest_path = root / "download" / "android" / "latest.json"
    if latest_path.is_file():
        try:
            latest = _json_object(latest_path, "Android latest manifest")
            apk_path = root / str(latest["apkPath"])
            if not apk_path.is_file():
                raise OfficialDistributionReleaseError("Android latest APK is missing")
            if _sha256_file(apk_path) != str(latest["apkSHA256"]):
                raise OfficialDistributionReleaseError("Android latest APK digest mismatch")
            if apk_path.stat().st_size != int(latest["apkSizeBytes"]):
                raise OfficialDistributionReleaseError("Android latest APK size mismatch")
            product_ops_path = root / "product-ops" / "app-release" / "current.env"
            if not product_ops_path.is_file():
                raise OfficialDistributionReleaseError(
                    "Product Ops app-release environment is missing"
                )
            product_ops_environment = product_ops_path.read_text(encoding="utf-8")
            if (
                f"PRODUCT_OPS_ANDROID_LATEST_BUILD={latest['buildNumber']}\n"
                not in product_ops_environment
                or f"PRODUCT_OPS_ANDROID_APK_SHA256={latest['apkSHA256']}\n"
                not in product_ops_environment
            ):
                raise OfficialDistributionReleaseError(
                    "Product Ops app-release environment is not bound to latest APK"
                )
            android = {
                "status": "ready",
                "versionName": latest["versionName"],
                "buildNumber": latest["buildNumber"],
                "apkSHA256": latest["apkSHA256"],
            }
            if verify_hosted:
                apk_url = str(latest["apkUrl"])
                _verify_remote_artifact(
                    apk_url=apk_url,
                    expected_sha256=str(latest["apkSHA256"]),
                    expected_size=int(latest["apkSizeBytes"]),
                )
        except (OSError, KeyError, TypeError, ValueError, OfficialDistributionReleaseError) as error:
            issues.append(f"Android distribution invalid: {error}")
            android = {"status": "invalid"}
    else:
        issues.append("Android latest manifest is missing")

    if verify_hosted:
        try:
            _verify_hosted_web(public_origin)
        except OfficialDistributionReleaseError as error:
            issues.append(str(error))
        if download_origin:
            host = urlparse(download_origin).hostname
            if not host or not host.endswith(".quwoquan.com"):
                issues.append("hosted download origin is not an official quwoquan.com host")

    return {
        "schema": "qwq.official-distribution.inspection",
        "status": "ready" if not issues else "GATE_BLOCK",
        "web": web,
        "android": android,
        "issues": issues,
    }


def prevalidate_android_distribution_candidate(
    *,
    package_manifest_path: Path,
    scratch_root: Path,
) -> dict[str, Any]:
    """Prove immutable APK and latest-pointer assembly without publishing it."""

    package_manifest_path = package_manifest_path.expanduser().resolve()
    scratch_root = scratch_root.expanduser().resolve()
    _require_external_distribution_root(scratch_root)
    if scratch_root.exists():
        shutil.rmtree(scratch_root)
    scratch_root.mkdir(parents=True)
    manifest = _json_object(
        package_manifest_path,
        "Android distribution package manifest",
    )
    result = _deploy_android(
        package_manifest_path=package_manifest_path,
        manifest=manifest,
        distribution_root=scratch_root,
        expected_current="",
    )
    latest_path = Path(str(result["latestManifestPath"]))
    latest = _json_object(latest_path, "prevalidated Android latest manifest")
    apk_path = scratch_root / str(latest["apkPath"])
    if (
        not apk_path.is_file()
        or _sha256_file(apk_path) != str(latest["apkSHA256"])
        or apk_path.stat().st_size != int(latest["apkSizeBytes"])
    ):
        raise OfficialDistributionReleaseError(
            "prevalidated Android latest pointer does not bind the immutable APK"
        )
    return {
        "schema": "qwq.android.distribution-prevalidation",
        "status": "component-ready",
        "versionName": latest["versionName"],
        "buildNumber": latest["buildNumber"],
        "apkSHA256": latest["apkSHA256"],
        "apkSigningCertificateSHA256": latest[
            "apkSigningCertificateSHA256"
        ],
        "latestPointerValidated": True,
        "downloadObjectValidated": True,
    }


def _deploy_web(
    *,
    package_manifest_path: Path,
    manifest: dict[str, Any],
    distribution_root: Path,
    expected_current: str,
) -> dict[str, Any]:
    if manifest.get("schema") != "qwq.public-web.release":
        raise OfficialDistributionReleaseError("Web release manifest schema mismatch")
    release_id = str(manifest.get("releaseId") or "")
    if not re.fullmatch(r"[0-9a-f]{20}", release_id):
        raise OfficialDistributionReleaseError("Web release id is invalid")
    source_release = package_manifest_path.parent
    _verify_deployed_web(source_release, manifest)
    releases_root = distribution_root / "web" / "releases"
    destination = releases_root / release_id
    if destination.exists():
        _verify_deployed_web(destination, manifest)
    else:
        releases_root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{release_id}-", dir=releases_root))
        try:
            shutil.copytree(source_release / "public", temporary / "public")
            shutil.copy2(package_manifest_path, temporary / "manifest.json")
            _verify_deployed_web(temporary, manifest)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    current = distribution_root / "web" / "current"
    previous = _current_symlink_name(current)
    _require_expected_current(previous, expected_current, label="Web")
    _atomic_symlink(current, Path("releases") / release_id)
    return {
        "releaseId": release_id,
        "previousReleaseId": previous,
        "currentReleaseId": release_id,
        "contentSHA256": manifest["contentSHA256"],
    }


def _deploy_android(
    *,
    package_manifest_path: Path,
    manifest: dict[str, Any],
    distribution_root: Path,
    expected_current: str,
) -> dict[str, Any]:
    if manifest.get("schema") != "qwq.android.official-release":
        raise OfficialDistributionReleaseError("Android release manifest schema mismatch")
    version = str(manifest.get("versionName") or "")
    build = str(manifest.get("buildNumber") or "")
    artifact_name = str(manifest.get("packagedAPK") or "")
    if not re.fullmatch(r"[1-9][0-9]{0,17}", build):
        raise OfficialDistributionReleaseError("Android build number is invalid")
    if artifact_name != f"quwoquan-{build}.apk":
        raise OfficialDistributionReleaseError("Android APK immutable filename is invalid")
    source_apk = package_manifest_path.parent / artifact_name
    if not source_apk.is_file():
        raise OfficialDistributionReleaseError("packaged Android APK is missing")
    if _sha256_file(source_apk) != str(manifest.get("apkSHA256") or ""):
        raise OfficialDistributionReleaseError("packaged Android APK digest mismatch")
    if source_apk.stat().st_size != int(manifest.get("apkSizeBytes") or 0):
        raise OfficialDistributionReleaseError("packaged Android APK size mismatch")

    relative_apk = Path("download") / "android" / version / build / artifact_name
    destination = distribution_root / relative_apk
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if _sha256_file(destination) != str(manifest["apkSHA256"]):
            raise OfficialDistributionReleaseError("immutable Android APK object conflicts")
    else:
        _atomic_copy(source_apk, destination)

    latest_path = distribution_root / "download" / "android" / "latest.json"
    previous = ""
    if latest_path.is_file():
        current = _json_object(latest_path, "Android latest manifest")
        previous = str(current.get("buildNumber") or "")
    _require_expected_current(previous, expected_current, label="Android")
    latest = {
        "schema": "qwq.android.latest",
        "versionName": version,
        "buildNumber": build,
        "minAndroidVersion": manifest["minAndroidVersion"],
        "packageName": manifest["packageName"],
        "apkUrl": manifest["apkUrl"],
        "apkPath": relative_apk.as_posix(),
        "apkSHA256": manifest["apkSHA256"],
        "apkSizeBytes": manifest["apkSizeBytes"],
        "apkSigningCertificateSHA256": manifest[
            "apkSigningCertificateSHA256"
        ],
    }
    _atomic_json(latest_path, latest)
    product_ops_environment = {
        "PRODUCT_OPS_APP_RELEASE_PUBLIC_ORIGIN": manifest["publicOrigin"],
        "PRODUCT_OPS_APP_RELEASE_RECOVERY_URL": manifest["recoveryUrl"],
        "PRODUCT_OPS_ANDROID_LATEST_VERSION": version,
        "PRODUCT_OPS_ANDROID_LATEST_BUILD": build,
        "PRODUCT_OPS_ANDROID_APK_URL": manifest["apkUrl"],
        "PRODUCT_OPS_ANDROID_APK_HOST_ALLOWLIST": ",".join(
            str(value) for value in manifest.get("apkHostAllowlist") or []
        ),
        "PRODUCT_OPS_ANDROID_APK_PACKAGE_NAME": manifest["packageName"],
        "PRODUCT_OPS_ANDROID_APK_SHA256": manifest["apkSHA256"],
        "PRODUCT_OPS_ANDROID_APK_SIZE_BYTES": str(manifest["apkSizeBytes"]),
        "PRODUCT_OPS_ANDROID_APK_SIGNING_CERTIFICATE_SHA256": manifest[
            "apkSigningCertificateSHA256"
        ],
        "PRODUCT_OPS_ANDROID_MIN_ANDROID_VERSION": manifest["minAndroidVersion"],
    }
    product_ops_path = (
        distribution_root / "product-ops" / "app-release" / "current.env"
    )
    _atomic_text(
        product_ops_path,
        "".join(
            f"{key}={value}\n"
            for key, value in sorted(product_ops_environment.items())
        ),
    )
    return {
        "versionName": version,
        "previousBuildNumber": previous,
        "currentBuildNumber": build,
        "apkSHA256": manifest["apkSHA256"],
        "latestManifestPath": str(latest_path),
        "productOpsEnvironmentPath": str(product_ops_path),
    }


def _release_manifest(path: Path) -> tuple[dict[str, Any], str]:
    manifest = _json_object(path, "release manifest")
    try:
        validate_manifest(manifest, allowed_statuses={"deployable"})
        validate_manifest_files(path.parent, manifest)
    except ValueError as error:
        raise OfficialDistributionReleaseError(
            f"release evidence manifest is not deployable: {error}"
        ) from error
    declared = str(manifest["artifactDigest"])
    return manifest, declared


def _verify_component_binding(
    *,
    release_manifest: dict[str, Any],
    component_key: str,
    package_manifest_path: Path,
    package_manifest: dict[str, Any],
) -> None:
    components = release_manifest.get("applicationPackages")
    prod_components = components.get("prod") if isinstance(components, dict) else None
    component = (
        prod_components.get(component_key)
        if isinstance(prod_components, dict)
        else None
    )
    if not isinstance(component, dict):
        raise OfficialDistributionReleaseError(
            f"release manifest does not bind artifact {component_key}"
        )
    digest = "sha256:" + hashlib.sha256(package_manifest_path.read_bytes()).hexdigest()
    if component.get("digest") != digest:
        raise OfficialDistributionReleaseError(
            f"release manifest distribution digest mismatch: {component_key}"
        )
    expected_schema = {
        "web": "qwq.public-web.release",
        "android": "qwq.android.official-release",
    }[component_key]
    if expected_schema != str(package_manifest.get("schema") or ""):
        raise OfficialDistributionReleaseError(
            f"release manifest distribution schema mismatch: {component_key}"
        )


def _verify_deployed_web(root: Path, manifest: dict[str, Any]) -> None:
    public = root / "public"
    required = ("index.html", "main.dart.js", "manifest.json", "flutter_service_worker.js")
    missing = [name for name in required if not (public / name).is_file()]
    if missing:
        raise OfficialDistributionReleaseError(
            "deployed Web release is incomplete: " + ", ".join(missing)
        )
    if _tree_sha256(public) != str(manifest.get("contentSHA256") or ""):
        raise OfficialDistributionReleaseError("deployed Web content digest mismatch")
    index = (public / "index.html").read_text(encoding="utf-8")
    if '<html lang="zh-CN">' not in index or '<meta charset="utf-8">' not in index:
        raise OfficialDistributionReleaseError("deployed Web index is not UTF-8 zh-CN")


def _verify_hosted_web(public_origin: str) -> None:
    origin = public_origin.strip().rstrip("/")
    parsed = urlparse(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith("-quwoquan.com")
        and parsed.hostname != "quwoquan.com"
    ):
        raise OfficialDistributionReleaseError("hosted Web origin is not official HTTPS")
    request = urllib.request.Request(origin + "/", headers={"Accept": "text/html"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            body = response.read(512 * 1024).decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise OfficialDistributionReleaseError(
            f"hosted Web verification failed: {error}"
        ) from error
    if "text/html" not in content_type or "charset=utf-8" not in content_type:
        raise OfficialDistributionReleaseError("hosted Web response is not UTF-8 HTML")
    if '<html lang="zh-CN">' not in body or '<meta charset="utf-8">' not in body:
        raise OfficialDistributionReleaseError("hosted Web body lacks UTF-8 zh-CN contract")


def _component_key(kind: str) -> str:
    try:
        return _KINDS[kind]
    except KeyError as error:
        raise OfficialDistributionReleaseError(
            f"unsupported distribution artifact kind: {kind}"
        ) from error


def _require_external_distribution_root(root: Path) -> None:
    repository = Path(__file__).resolve().parents[3]
    output = repository / ".qwq_output"
    if _within(root, repository) or _within(root, output) or _within(output, root):
        raise OfficialDistributionReleaseError(
            "distribution root must be outside the repository and .qwq_output"
        )
    if root == Path(root.anchor):
        raise OfficialDistributionReleaseError("distribution root cannot be a filesystem root")


def _require_expected_current(actual: str, expected: str, *, label: str) -> None:
    expected = expected.strip()
    if expected and actual != expected:
        raise OfficialDistributionReleaseError(
            f"{label} distribution CAS conflict: expected {expected!r}, current {actual!r}"
        )


def _current_symlink_name(path: Path) -> str:
    if not path.exists() and not path.is_symlink():
        return ""
    if not path.is_symlink():
        raise OfficialDistributionReleaseError("distribution current pointer must be a symlink")
    return path.resolve(strict=True).name


def _atomic_symlink(path: Path, target: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    temporary.symlink_to(target, target_is_directory=True)
    os.replace(temporary, path)


def _atomic_copy(source: Path, destination: Path) -> None:
    temporary = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OfficialDistributionReleaseError(f"{label} is unreadable: {error}") from error
    if not isinstance(payload, dict):
        raise OfficialDistributionReleaseError(f"{label} must be an object")
    return payload


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
