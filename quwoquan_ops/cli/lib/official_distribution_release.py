from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from quwoquan_ops.cli.lib.android_official_release import _verify_remote_artifact
from quwoquan_ops.cli.lib.web_official_release import (
    WebOfficialReleaseError,
    validate_web_official_artifact,
    web_official_content_digest,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    validate_manifest,
    validate_manifest_files,
)


class OfficialDistributionReleaseError(RuntimeError):
    pass


_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
# 对外分发只走两个 store/hosted 产品，键必须与 ReleaseEvidence 的
# applicationPackages 同源；后者已按 canonical build product ID 编址，
# 不再按 environment × surface 分层。
_KINDS = {
    "web": "web-shared",
    "app-release": "android-prod-apk",
}
_COMPONENT_SCHEMAS = {
    "web-shared": "client-app.web.official-release",
    "android-prod-apk": "client-app.android.official-release",
}
_COMPONENT_CONTENT_DIGEST_KEYS = {
    "web-shared": "contentSHA256",
    "android-prod-apk": "apkSHA256",
}
_COMPONENT_RELEASE_EVIDENCE_KEYS = {
    "web-shared": "publicWeb",
    "android-prod-apk": "androidOfficialRelease",
}
_WEB_PACKAGE_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "publicOrigin",
        "releaseId",
        "contentSHA256",
        "noindex",
        "spaFallback",
        "htmlContentType",
        "assetCacheControl",
        "serviceWorker",
        "sourceGitSha",
        "sourceTreeDigest",
        "artifactManifest",
    }
)
_ANDROID_PACKAGE_FIELDS = frozenset(
    {
        "schema",
        "platform",
        "versionName",
        "buildNumber",
        "minAndroidVersion",
        "packageName",
        "apkUrl",
        "apkSHA256",
        "apkSizeBytes",
        "apkSigningCertificateSHA256",
        "apkHostAllowlist",
        "publicOrigin",
        "recoveryUrl",
        "updateUrl",
        "minimumSupportedVersion",
        "minimumSupportedBuild",
        "packagedAPK",
        "remoteVerified",
        "sourceGitSha",
        "sourceTreeDigest",
        "artifactManifest",
    }
)
_ANDROID_OPTIONAL_PACKAGE_FIELDS = frozenset(
    {"minimumSupportedBuildIncreaseEvidence"}
)


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
        release_manifest_path=release_manifest_path,
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
            release_manifest_path=release_manifest_path,
            release_manifest=release_manifest,
        )
    receipt = {
        "schema": "client-app.official-distribution.receipt",
        "artifactKind": kind,
        "artifactDigest": release_digest,
        "releaseCompositionId": release_manifest["releaseCompositionId"],
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
            _validate_android_latest_manifest(latest)
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
                or (
                    "PRODUCT_OPS_ANDROID_MINIMUM_SUPPORTED_VERSION="
                    f"{latest['minimumSupportedVersion']}\n"
                )
                not in product_ops_environment
                or (
                    "PRODUCT_OPS_ANDROID_MINIMUM_SUPPORTED_BUILD="
                    f"{latest['minimumSupportedBuild']}\n"
                )
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
                "minimumSupportedVersion": latest["minimumSupportedVersion"],
                "minimumSupportedBuild": latest["minimumSupportedBuild"],
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
        "schema": "client-app.official-distribution.inspection",
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
    _validate_android_latest_manifest(latest)
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
        "schema": "client-app.android.distribution-prevalidation",
        "status": "component-ready",
        "versionName": latest["versionName"],
        "buildNumber": latest["buildNumber"],
        "minimumSupportedVersion": latest["minimumSupportedVersion"],
        "minimumSupportedBuild": latest["minimumSupportedBuild"],
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
    if manifest.get("schema") != "client-app.web.official-release":
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
    release_manifest_path: Path | None = None,
    release_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if manifest.get("schema") != "client-app.android.official-release":
        raise OfficialDistributionReleaseError("Android release manifest schema mismatch")
    version = str(manifest.get("versionName") or "")
    build = str(manifest.get("buildNumber") or "")
    minimum_supported_version = str(manifest.get("minimumSupportedVersion") or "")
    minimum_supported_build = str(manifest.get("minimumSupportedBuild") or "")
    artifact_name = str(manifest.get("packagedAPK") or "")
    if not re.fullmatch(r"[1-9][0-9]{0,17}", build):
        raise OfficialDistributionReleaseError("Android build number is invalid")
    if (
        not minimum_supported_version
        or not re.fullmatch(r"[1-9][0-9]{0,17}", minimum_supported_build)
        or int(minimum_supported_build) > int(build)
    ):
        raise OfficialDistributionReleaseError(
            "Android minimum supported version/build is invalid"
        )
    if artifact_name != f"quwoquan-{build}.apk":
        raise OfficialDistributionReleaseError("Android APK immutable filename is invalid")
    source_apk = package_manifest_path.parent / artifact_name
    if not source_apk.is_file():
        raise OfficialDistributionReleaseError("packaged Android APK is missing")
    if _sha256_file(source_apk) != str(manifest.get("apkSHA256") or ""):
        raise OfficialDistributionReleaseError("packaged Android APK digest mismatch")
    if source_apk.stat().st_size != int(manifest.get("apkSizeBytes") or 0):
        raise OfficialDistributionReleaseError("packaged Android APK size mismatch")

    latest_path = distribution_root / "download" / "android" / "latest.json"
    previous = ""
    previous_minimum_supported_build = ""
    if latest_path.is_file():
        current = _json_object(latest_path, "Android latest manifest")
        _validate_android_latest_manifest(current)
        previous = str(current["buildNumber"])
        previous_minimum_supported_build = str(current["minimumSupportedBuild"])
    _require_expected_current(previous, expected_current, label="Android")
    if previous_minimum_supported_build and (
        int(minimum_supported_build) > int(previous_minimum_supported_build)
    ):
        _validate_minimum_supported_build_increase(
            manifest=manifest,
            from_minimum_supported_build=previous_minimum_supported_build,
            release_manifest_path=release_manifest_path,
            release_manifest=release_manifest,
        )

    relative_apk = Path("download") / "android" / version / build / artifact_name
    destination = distribution_root / relative_apk
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if _sha256_file(destination) != str(manifest["apkSHA256"]):
            raise OfficialDistributionReleaseError("immutable Android APK object conflicts")
    else:
        _atomic_copy(source_apk, destination)

    latest = {
        "schema": "client-app.android.latest",
        "versionName": version,
        "buildNumber": build,
        "minimumSupportedVersion": minimum_supported_version,
        "minimumSupportedBuild": minimum_supported_build,
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
        "PRODUCT_OPS_ANDROID_LATEST_VERSION": version,
        "PRODUCT_OPS_ANDROID_LATEST_BUILD": build,
        "PRODUCT_OPS_ANDROID_MINIMUM_SUPPORTED_VERSION": minimum_supported_version,
        "PRODUCT_OPS_ANDROID_MINIMUM_SUPPORTED_BUILD": minimum_supported_build,
        "PRODUCT_OPS_ANDROID_UPDATE_URL": manifest["updateUrl"],
        "PRODUCT_OPS_ANDROID_RECOVERY_URL": manifest["recoveryUrl"],
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
        "previousMinimumSupportedBuild": previous_minimum_supported_build,
        "currentMinimumSupportedBuild": minimum_supported_build,
        "minimumSupportedBuildRaised": bool(previous_minimum_supported_build)
        and int(minimum_supported_build) > int(previous_minimum_supported_build),
        "apkSHA256": manifest["apkSHA256"],
        "latestManifestPath": str(latest_path),
        "productOpsEnvironmentPath": str(product_ops_path),
    }


def _validate_minimum_supported_build_increase(
    *,
    manifest: dict[str, Any],
    from_minimum_supported_build: str,
    release_manifest_path: Path | None,
    release_manifest: dict[str, Any] | None,
) -> None:
    evidence = manifest.get("minimumSupportedBuildIncreaseEvidence")
    if not isinstance(evidence, dict):
        raise OfficialDistributionReleaseError(
            "minimum supported build increase requires canonical evidence"
        )
    expected_fields = {
        "schema",
        "platform",
        "fromMinimumSupportedBuild",
        "toMinimumSupportedVersion",
        "toMinimumSupportedBuild",
        "wouldBlock",
        "normalSupport",
        "channels",
        "securityException",
    }
    if set(evidence) != expected_fields:
        raise OfficialDistributionReleaseError(
            "minimum supported build increase evidence shape is invalid"
        )
    if (
        evidence.get("schema")
        != "client-app.minimum-supported-build-increase-evidence"
        or evidence.get("platform") != "android"
        or str(evidence.get("fromMinimumSupportedBuild") or "")
        != from_minimum_supported_build
        or str(evidence.get("toMinimumSupportedVersion") or "")
        != str(manifest["minimumSupportedVersion"])
        or str(evidence.get("toMinimumSupportedBuild") or "")
        != str(manifest["minimumSupportedBuild"])
    ):
        raise OfficialDistributionReleaseError(
            "minimum supported build increase evidence is not bound to this change"
        )

    _validate_update_and_recovery_channels(evidence.get("channels"))
    security_exception = evidence.get("securityException")
    if security_exception is not None:
        _validate_security_exception(
            security_exception,
            release_manifest_path=release_manifest_path,
            release_manifest=release_manifest,
        )
        return
    _validate_would_block_observation(evidence.get("wouldBlock"))
    _validate_normal_support_window(evidence.get("normalSupport"))


def _validate_would_block_observation(value: Any) -> None:
    expected_fields = {
        "observationStartedAt",
        "observationEndedAt",
        "oldVersionActiveInstallShareBasisPoints",
        "receiptDigest",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise OfficialDistributionReleaseError("would_block evidence shape is invalid")
    started = _timestamp(value["observationStartedAt"], "would_block start")
    ended = _timestamp(value["observationEndedAt"], "would_block end")
    if (ended - started).total_seconds() < 30 * 24 * 60 * 60:
        raise OfficialDistributionReleaseError(
            "would_block observation must cover at least 30 days"
        )
    share = value["oldVersionActiveInstallShareBasisPoints"]
    if (
        not isinstance(share, int)
        or isinstance(share, bool)
        or share < 0
        or share >= 10
    ):
        raise OfficialDistributionReleaseError(
            "old-version active install share must be below 0.1 percent"
        )
    _receipt_digest(value["receiptDigest"], "would_block")


def _validate_normal_support_window(value: Any) -> None:
    expected_fields = {"supportedSince", "evaluatedAt", "receiptDigest"}
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise OfficialDistributionReleaseError("normal support evidence shape is invalid")
    supported_since = _timestamp(value["supportedSince"], "normal support start")
    evaluated_at = _timestamp(value["evaluatedAt"], "normal support evaluation")
    try:
        anniversary = supported_since.replace(year=supported_since.year + 1)
    except ValueError:
        anniversary = supported_since.replace(
            year=supported_since.year + 1,
            month=2,
            day=28,
        )
    if evaluated_at < anniversary:
        raise OfficialDistributionReleaseError(
            "normal support window must cover at least 12 months"
        )
    _receipt_digest(value["receiptDigest"], "normal support")


def _validate_update_and_recovery_channels(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"update", "recovery"}:
        raise OfficialDistributionReleaseError(
            "update and recovery channel evidence is required"
        )
    for channel_name in ("update", "recovery"):
        channel = value[channel_name]
        if (
            not isinstance(channel, dict)
            or set(channel) != {"verified", "verifiedAt", "receiptDigest"}
            or channel.get("verified") is not True
        ):
            raise OfficialDistributionReleaseError(
                f"{channel_name} channel is not verified"
            )
        _timestamp(channel["verifiedAt"], f"{channel_name} channel verification")
        _receipt_digest(channel["receiptDigest"], f"{channel_name} channel")


def _validate_security_exception(
    value: Any,
    *,
    release_manifest_path: Path | None,
    release_manifest: dict[str, Any] | None,
) -> None:
    expected_fields = {"risk", "reason", "approvalAuthority"}
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise OfficialDistributionReleaseError(
            "security exception evidence shape is invalid"
        )
    reason = str(value.get("reason") or "").strip()
    if value.get("risk") != "high" or len(reason) < 20:
        raise OfficialDistributionReleaseError(
            "security exception must declare a high-risk audited reason"
        )
    if value.get("approvalAuthority") != "governance-receipt.json":
        raise OfficialDistributionReleaseError(
            "security exception approval authority is not canonical"
        )
    if release_manifest_path is None or release_manifest is None:
        raise OfficialDistributionReleaseError(
            "security exception requires governed release evidence"
        )
    approval_path = release_manifest_path.parent / "governance-receipt.json"
    if not approval_path.is_file():
        raise OfficialDistributionReleaseError(
            "security exception approval receipt is missing"
        )
    approval = _json_object(approval_path, "security exception approval receipt")
    source = release_manifest.get("source")
    expected_approval_fields = {
        "schema",
        "repository",
        "gitSha",
        "artifactDigest",
        "pullRequest",
        "author",
        "mergedBy",
        "approvers",
        "distinctPrincipals",
        "verifiedAt",
    }
    approvers = approval.get("approvers")
    principals = approval.get("distinctPrincipals")
    if (
        set(approval) != expected_approval_fields
        or approval.get("schema") != "prod-release-governance-receipt"
        or not isinstance(source, dict)
        or approval.get("repository") != source.get("repository")
        or approval.get("gitSha") != source.get("gitSha")
        or approval.get("artifactDigest") != release_manifest.get("artifactDigest")
        or not isinstance(approval.get("pullRequest"), int)
        or isinstance(approval.get("pullRequest"), bool)
        or approval["pullRequest"] < 1
        or not isinstance(approvers, list)
        or not approvers
        or not all(isinstance(item, str) and item for item in approvers)
        or not isinstance(principals, list)
        or len(set(principals)) < 2
        or str(approval.get("author") or "") in approvers
    ):
        raise OfficialDistributionReleaseError(
            "security exception approval does not bind the reviewed release"
        )
    _timestamp(approval.get("verifiedAt"), "security exception approval")


def _validate_android_latest_manifest(value: dict[str, Any]) -> None:
    if value.get("schema") != "client-app.android.latest":
        raise OfficialDistributionReleaseError("Android latest manifest schema mismatch")
    if "minimumVersion" in value or "minimumBuild" in value:
        raise OfficialDistributionReleaseError(
            "Android latest manifest contains non-canonical minimum version fields"
        )
    minimum_version = str(value.get("minimumSupportedVersion") or "")
    minimum_build = str(value.get("minimumSupportedBuild") or "")
    build = str(value.get("buildNumber") or "")
    if (
        not minimum_version
        or re.fullmatch(r"[1-9][0-9]{0,17}", minimum_build) is None
        or re.fullmatch(r"[1-9][0-9]{0,17}", build) is None
        or int(minimum_build) > int(build)
    ):
        raise OfficialDistributionReleaseError(
            "Android latest minimum supported version/build is invalid"
        )


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise OfficialDistributionReleaseError(f"{label} timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise OfficialDistributionReleaseError(
            f"{label} timestamp is invalid"
        ) from error
    if parsed.tzinfo != timezone.utc:
        raise OfficialDistributionReleaseError(f"{label} timestamp is invalid")
    return parsed


def _receipt_digest(value: Any, label: str) -> str:
    digest = str(value or "")
    if _SHA256.fullmatch(digest) is None:
        raise OfficialDistributionReleaseError(f"{label} receipt digest is invalid")
    return digest


def _release_manifest(path: Path) -> tuple[dict[str, Any], str]:
    manifest = _json_object(path, "release manifest")
    try:
        validate_manifest(manifest, allowed_statuses={"main-admitted"})
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
    release_manifest_path: Path,
    component_key: str,
    package_manifest_path: Path,
    package_manifest: dict[str, Any],
) -> None:
    components = release_manifest.get("applicationPackages")
    component = components.get(component_key) if isinstance(components, dict) else None
    if not isinstance(component, dict):
        raise OfficialDistributionReleaseError(
            f"release manifest does not bind artifact {component_key}"
        )
    expected_schema = _COMPONENT_SCHEMAS[component_key]
    if expected_schema != str(package_manifest.get("schema") or ""):
        raise OfficialDistributionReleaseError(
            f"release manifest distribution schema mismatch: {component_key}"
        )
    _validate_distribution_manifest_fields(
        component_key=component_key,
        package_manifest=package_manifest,
    )

    release_root = release_manifest_path.parent
    component_evidence_path = _bound_release_file(
        release_root,
        str(component.get("path") or ""),
        f"application package {component_key}",
    )
    application_evidence = _json_object(
        component_evidence_path,
        f"application package {component_key}",
    )
    if component.get("packageDigest") != application_evidence.get("packageDigest"):
        raise OfficialDistributionReleaseError(
            f"release manifest package digest mismatch: {component_key}"
        )

    candidate_artifact_manifest = application_evidence.get("artifactManifest")
    supplied_artifact_manifest = package_manifest.get("artifactManifest")
    if (
        not isinstance(candidate_artifact_manifest, dict)
        or supplied_artifact_manifest != candidate_artifact_manifest
    ):
        raise OfficialDistributionReleaseError(
            f"release manifest distribution artifactManifest mismatch: {component_key}"
        )
    if (
        package_manifest.get("sourceGitSha")
        != candidate_artifact_manifest.get("sourceGitSha")
        or package_manifest.get("sourceTreeDigest")
        != candidate_artifact_manifest.get("sourceTreeDigest")
    ):
        raise OfficialDistributionReleaseError(
            f"release manifest distribution source identity mismatch: {component_key}"
        )
    artifact_digest = str(candidate_artifact_manifest.get("artifactDigest") or "")
    content_digest = _prefixed_digest(
        package_manifest.get(_COMPONENT_CONTENT_DIGEST_KEYS[component_key])
    )
    if artifact_digest != content_digest:
        raise OfficialDistributionReleaseError(
            f"release manifest distribution artifact digest mismatch: {component_key}"
        )

    evidence_key = _COMPONENT_RELEASE_EVIDENCE_KEYS[component_key]
    distribution_descriptor = release_manifest.get(evidence_key)
    if not isinstance(distribution_descriptor, dict):
        raise OfficialDistributionReleaseError(
            f"release manifest does not bind distribution evidence {evidence_key}"
        )
    candidate_manifest_path = _bound_release_file(
        release_root,
        str(distribution_descriptor.get("path") or ""),
        evidence_key,
    )
    candidate_bytes = candidate_manifest_path.read_bytes()
    supplied_bytes = package_manifest_path.read_bytes()
    supplied_digest = "sha256:" + hashlib.sha256(supplied_bytes).hexdigest()
    if (
        distribution_descriptor.get("digest") != supplied_digest
        or candidate_bytes != supplied_bytes
    ):
        raise OfficialDistributionReleaseError(
            f"release manifest distribution evidence mismatch: {evidence_key}"
        )


def _validate_distribution_manifest_fields(
    *,
    component_key: str,
    package_manifest: dict[str, Any],
) -> None:
    actual_fields = set(package_manifest)
    if component_key == "web-shared":
        canonical = actual_fields == _WEB_PACKAGE_FIELDS
    else:
        canonical = (
            _ANDROID_PACKAGE_FIELDS.issubset(actual_fields)
            and actual_fields.issubset(
                _ANDROID_PACKAGE_FIELDS | _ANDROID_OPTIONAL_PACKAGE_FIELDS
            )
        )
    if not canonical:
        raise OfficialDistributionReleaseError(
            f"release manifest distribution fields are not canonical: {component_key}"
        )


def _bound_release_file(root: Path, relative: str, label: str) -> Path:
    relative_path = Path(relative)
    if not relative or relative_path.is_absolute() or ".." in relative_path.parts:
        raise OfficialDistributionReleaseError(f"{label} path is unsafe")
    candidate = root / relative_path
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if (
        resolved_root not in resolved.parents
        or candidate.is_symlink()
        or not candidate.is_file()
    ):
        raise OfficialDistributionReleaseError(
            f"{label} is missing or escapes the release evidence root"
        )
    return candidate


def _prefixed_digest(value: Any) -> str:
    digest = str(value or "")
    return digest if digest.startswith("sha256:") else "sha256:" + digest


def _verify_deployed_web(root: Path, manifest: dict[str, Any]) -> None:
    public = root / "public"
    try:
        validate_web_official_artifact(public)
    except (OSError, TypeError, ValueError, WebOfficialReleaseError) as error:
        raise OfficialDistributionReleaseError(
            f"deployed Web artifact is not official: {error}"
        ) from error
    if _tree_sha256(public) != str(manifest.get("contentSHA256") or ""):
        raise OfficialDistributionReleaseError("deployed Web content digest mismatch")


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
    return web_official_content_digest(root)


def _within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
