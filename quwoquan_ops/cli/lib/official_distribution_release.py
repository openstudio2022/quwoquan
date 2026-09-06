from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from quwoquan_ops.ci.render_release_application_package import validate_package
from quwoquan_ops.cli.commands.package_app_artifact_helpers import artifact_digest
from quwoquan_ops.cli.lib.android_official_release import _verify_remote_artifact
from quwoquan_ops.cli.lib.web_official_release import (
    WebOfficialReleaseError,
    validate_web_official_artifact,
    web_official_content_digest,
)


class OfficialDistributionReleaseError(RuntimeError):
    pass


_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
# 对外分发只走两个 canonical store/hosted build product；正式路径仅从
# stable admission 绑定的 app factory actual bytes 选择它们。
_KINDS = {
    "web": "web-shared",
    "app-release": "android-prod-apk",
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
    graph_root: Path,
    stable_tag_admission_ref: Mapping[str, str],
    app_factory_root: Path,
    distribution_root: Path,
    expected_current: str = "",
) -> dict[str, Any]:
    component_key = _component_key(kind)
    graph_root = graph_root.expanduser().resolve()
    app_factory_root = app_factory_root.expanduser().resolve()
    distribution_root = distribution_root.expanduser().resolve()
    loaded = _load_official_distribution_material(
        graph_root=graph_root,
        stable_tag_admission_ref=stable_tag_admission_ref,
        app_factory_root=app_factory_root,
        component_key=component_key,
    )
    package_manifest_path = loaded["distributionManifestPath"]
    package_manifest = loaded["distributionManifest"]
    payload_path = loaded["payloadPath"]
    _require_external_distribution_root(distribution_root)
    distribution_root.mkdir(parents=True, exist_ok=True)

    if kind == "web":
        result = _deploy_web(
            package_manifest_path=package_manifest_path,
            manifest=package_manifest,
            payload_path=payload_path,
            distribution_root=distribution_root,
            expected_current=expected_current,
        )
    else:
        result = _deploy_android(
            package_manifest_path=package_manifest_path,
            manifest=package_manifest,
            payload_path=payload_path,
            distribution_root=distribution_root,
            expected_current=expected_current,
        )
    receipt = {
        "schema": "client-app.official-distribution.receipt",
        "artifactKind": kind,
        "channelId": loaded["channelId"],
        "stableTag": loaded["stableTag"],
        "releaseTagAdmissionRef": loaded["releaseTagAdmission"]["ref"],
        "releaseTagAdmissionDigest": loaded["releaseTagAdmission"]["digest"],
        "releaseTagAdmissionId": loaded["releaseTagAdmissionId"],
        "qualificationRef": loaded["qualification"]["ref"],
        "qualificationDigest": loaded["qualification"]["digest"],
        "qualificationId": loaded["qualificationId"],
        "candidateMaterialManifestRef": loaded["candidateMaterialManifest"]["ref"],
        "candidateMaterialManifestDigest": loaded["candidateMaterialManifest"]["digest"],
        "candidateMaterialId": loaded["candidateMaterialId"],
        "appFactoryRef": loaded["appFactoryRef"],
        "appFactoryDigest": loaded["appFactoryDigest"],
        "appFactoryPayloadDigest": loaded["appFactoryPayloadDigest"],
        "appFactoryMaterialDigest": loaded["appFactoryMaterialDigest"],
        "selectedAppArtifactDigest": loaded["selectedAppArtifactDigest"],
        "sourceGitSha": loaded["sourceGitSha"],
        "sourceTreeDigest": loaded["sourceTreeDigest"],
        "artifactBuildNumber": loaded["artifactBuildNumber"],
        **result,
    }
    receipt_bytes = _canonical_bytes(receipt)
    receipt["receiptSHA256"] = "sha256:" + hashlib.sha256(receipt_bytes).hexdigest()
    receipt_path = distribution_root / "receipts" / (
        receipt["receiptSHA256"].removeprefix("sha256:") + ".json"
    )
    _append_only_json(receipt_path, receipt)
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
    payload_path: Path | None = None,
) -> dict[str, Any]:
    if manifest.get("schema") != "client-app.web.official-release":
        raise OfficialDistributionReleaseError("Web release manifest schema mismatch")
    release_id = str(manifest.get("releaseId") or "")
    if not re.fullmatch(r"[0-9a-f]{20}", release_id):
        raise OfficialDistributionReleaseError("Web release id is invalid")
    source_release = package_manifest_path.parent
    _verify_deployed_web(source_release, manifest, public_path=payload_path)
    releases_root = distribution_root / "web" / "releases"
    destination = releases_root / release_id
    if destination.exists():
        _verify_deployed_web(destination, manifest)
    else:
        releases_root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{release_id}-", dir=releases_root))
        try:
            shutil.copytree(payload_path or source_release / "public", temporary / "public")
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
    payload_path: Path | None = None,
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
    source_apk = payload_path or (package_manifest_path.parent / artifact_name)
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
        _validate_security_exception(security_exception)
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


def _validate_security_exception(value: Any) -> None:
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
    raise OfficialDistributionReleaseError(
        "formal graph has no canonical security exception approval authority"
    )


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


def _load_official_distribution_material(
    *,
    graph_root: Path,
    stable_tag_admission_ref: Mapping[str, str],
    app_factory_root: Path,
    component_key: str,
) -> dict[str, Any]:
    stable, stable_exact = _exact_fact(
        graph_root, stable_tag_admission_ref, "releaseTagAdmission"
    )
    stable_tag = str(stable.get("tagName") or "")
    if (
        stable.get("schema") != "quwoquan_ops.release_tag_admission_fact.v1"
        or stable.get("decision") != "admitted"
        or stable.get("tagKind") != "stable"
        or re.fullmatch(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", stable_tag)
        is None
    ):
        raise OfficialDistributionReleaseError(
            "formal distribution requires an admitted stable SemVer tag"
        )
    stable_id = _fact_identity(stable, "admissionId", "releaseTagAdmission")
    qualification, qualification_exact = _exact_fact(
        graph_root, stable.get("qualificationFact"), "qualification"
    )
    material, material_exact = _exact_fact(
        graph_root, qualification.get("candidateMaterialManifest"),
        "candidateMaterialManifest",
    )
    request, request_exact = _exact_fact(
        graph_root, material.get("qualificationRequest"), "qualificationRequest"
    )
    allocation, allocation_exact = _exact_fact(
        graph_root,
        material.get("artifactBuildNumberAllocation"),
        "artifactBuildNumberAllocation",
    )
    qualification_id = _fact_identity(
        qualification, "qualificationId", "qualification"
    )
    material_id = _fact_identity(material, "materialId", "candidateMaterialManifest")
    _fact_identity(request, "requestId", "qualificationRequest")
    _fact_identity(allocation, "allocationId", "artifactBuildNumberAllocation")

    source = str(stable.get("peeledCommit") or "")
    tree = str(stable.get("sourceTree") or "")
    build = material.get("artifactBuildNumber")
    expected_tree_digest = _prefixed_tree_digest(tree)
    stable_artifacts = _formal_artifacts(stable.get("artifacts"), "releaseTagAdmission")
    qualification_artifacts = _formal_artifacts(
        qualification.get("artifacts"), "qualification"
    )
    material_artifacts = _formal_artifacts(material.get("artifacts"), "candidateMaterialManifest")
    if (
        qualification.get("schema") != "quwoquan_ops.qualification_fact.v1"
        or qualification.get("decision") != "qualified"
        or qualification.get("candidateMaterialManifest") != material_exact
        or stable.get("qualificationFact") != qualification_exact
        or stable.get("qualificationId") != qualification_id
        or stable.get("candidateMaterialManifest") != material_exact
        or stable.get("candidateMaterialId") != material_id
        or material.get("schema") != "quwoquan_ops.candidate_material_manifest.v1"
        or material.get("qualificationRequest") != request_exact
        or qualification.get("qualificationRequest") != request_exact
        or material.get("artifactBuildNumberAllocation") != allocation_exact
        or request.get("schema") != "quwoquan_ops.release_qualification_request.v1"
        or allocation.get("schema") != "quwoquan_ops.artifact_build_number_allocation.v1"
        or request.get("sourceGitSha") != source
        or request.get("sourceTree") != tree
        or qualification.get("sourceGitSha") != source
        or qualification.get("sourceTree") != tree
        or material.get("sourceGitSha") != source
        or material.get("sourceTree") != tree
        or stable.get("artifactBuildNumber") != build
        or qualification.get("artifactBuildNumber") != build
        or allocation.get("artifactBuildNumber") != build
        or allocation.get("qualificationRequest") != request_exact
        or stable_artifacts != qualification_artifacts
        or stable_artifacts != material_artifacts
    ):
        raise OfficialDistributionReleaseError(
            "formal distribution source/tree/build or exact graph binding drifted"
        )
    if not isinstance(build, int) or isinstance(build, bool) or build < 1:
        raise OfficialDistributionReleaseError("formal artifact build number is invalid")

    factory_outputs = material.get("factoryOutputs")
    app_output = factory_outputs.get("app") if isinstance(factory_outputs, Mapping) else None
    if not isinstance(app_output, Mapping):
        raise OfficialDistributionReleaseError("candidate material lacks app factory output")
    app_ref = _exact_oci_ref(app_output.get("ociRef"), "app factory ref")
    app_digest = _required_digest(app_output.get("ociDigest"), "app factory digest")
    if (
        not app_ref.endswith("@" + app_digest)
        or any(
            item["ociRef"] != app_ref or item["digest"] != app_digest
            for item in material_artifacts
            if item["platform"] != "service"
        )
        or factory_outputs.get("qualificationRequestOciRef")
        != material.get("qualificationRequestOciRef")
        or factory_outputs.get("artifactBuildNumberAllocationOciRef")
        != material.get("artifactBuildNumberAllocationOciRef")
    ):
        raise OfficialDistributionReleaseError("app factory exact OCI binding drifted")

    app_material_path = app_factory_root / "manifest.json"
    app_material = _canonical_json_object(app_material_path, "app factory material", compact=True)
    app_payload_digest = _sha256_prefixed_file(app_material_path)
    app_material_digest = _self_digest(app_material, "materialDigest", "app factory material")
    app_artifacts = app_material.get("artifacts")
    output_manifests = app_output.get("artifactManifests")
    output_digests = app_output.get("artifactDigests")
    request_oci = _exact_oci_ref(
        material.get("qualificationRequestOciRef"), "qualification request OCI ref"
    )
    allocation_oci = _exact_oci_ref(
        material.get("artifactBuildNumberAllocationOciRef"),
        "artifact build-number allocation OCI ref",
    )
    request_binding = app_material.get("qualificationRequest")
    allocation_binding = app_material.get("artifactBuildNumberAllocation")
    if (
        set(app_material)
        != {
            "schema",
            "sourceGitSha",
            "sourceTreeDigest",
            "qualificationRequest",
            "rcTagAdmissionRef",
            "artifactBuildNumber",
            "artifactBuildNumberAllocation",
            "artifacts",
            "materialDigest",
        }
        or set(app_output)
        != {
            "ociRef",
            "ociDigest",
            "payloadDigest",
            "materialDigest",
            "artifactDigests",
            "artifactManifests",
            "sourceTreeDigest",
        }
        or app_payload_digest != app_output.get("payloadDigest")
        or app_material_digest != app_output.get("materialDigest")
        or app_material.get("schema") != "quwoquan_ops.app_factory_material"
        or app_material.get("sourceGitSha") != source
        or app_material.get("sourceTreeDigest") != expected_tree_digest
        or app_material.get("artifactBuildNumber") != build
        or not isinstance(request_binding, Mapping)
        or request_binding
        != {"ref": request_oci, "digest": request_oci.rsplit("@", 1)[1]}
        or app_material.get("rcTagAdmissionRef")
        != (request.get("rcTagAdmission") or {}).get("ref")
        or not isinstance(allocation_binding, Mapping)
        or allocation_binding
        != {"ref": allocation_oci, "digest": allocation_oci.rsplit("@", 1)[1]}
        or not isinstance(app_artifacts, Mapping)
        or set(app_artifacts) != {"android", "ios", "web"}
        or output_manifests != app_artifacts
        or not isinstance(output_digests, Mapping)
        or set(output_digests) != {"android", "ios", "web"}
        or app_output.get("sourceTreeDigest") != expected_tree_digest
    ):
        raise OfficialDistributionReleaseError(
            "app factory material authority/source/tree/build binding drifted"
        )

    selected_platform = "android" if component_key == "android-prod-apk" else "web"
    selected_manifest = app_artifacts[selected_platform]
    for platform, expected_product in {
        "android": "android-prod-apk",
        "ios": "ios-prod-app",
        "web": "web-shared",
    }.items():
        manifest = app_artifacts[platform]
        if not isinstance(manifest, dict):
            raise OfficialDistributionReleaseError(
                f"app factory {platform} AppArtifactManifest is missing"
            )
        _validate_app_artifact_manifest(
            manifest,
            build_product_id=expected_product,
            source_git_sha=source,
            source_tree_digest=expected_tree_digest,
        )
        if (
            manifest.get("buildNumber") != str(build)
            or manifest.get("qualificationRequestRef") != request_oci
            or manifest.get("qualificationRequestDigest") != request_oci.rsplit("@", 1)[1]
            or manifest.get("rcTagAdmissionRef")
            != (request.get("rcTagAdmission") or {}).get("ref")
            or manifest.get("artifactBuildNumberAllocationRef") != allocation_oci
            or manifest.get("artifactBuildNumberAllocationDigest")
            != allocation_oci.rsplit("@", 1)[1]
            or manifest.get("promotable") is not True
            or output_digests.get(platform) != manifest.get("artifactDigest")
            or (material.get("artifactByteDigests") or {}).get(platform)
            != manifest.get("artifactDigest")
        ):
            raise OfficialDistributionReleaseError(
                f"app factory {platform} AppArtifactManifest authority drifted"
            )

    package_path = app_factory_root / "application-packages" / f"{component_key}.json"
    package = _canonical_json_object(
        package_path, f"factory package descriptor {component_key}", compact=False
    )
    try:
        validate_package(
            package,
            build_product_id=component_key,
            source_git_sha=source,
            source_tree_digest=expected_tree_digest,
        )
    except ValueError as error:
        raise OfficialDistributionReleaseError(
            f"factory package descriptor {component_key} is invalid: {error}"
        ) from error
    if package.get("artifactManifest") != selected_manifest:
        raise OfficialDistributionReleaseError(
            f"factory package descriptor {component_key} AppArtifactManifest drifted"
        )

    payload_root = app_factory_root / "payloads" / component_key
    if _package_tree_digest(payload_root) != package.get("packageDigest"):
        raise OfficialDistributionReleaseError(
            f"factory package descriptor {component_key} packageDigest drifted"
        )
    if component_key == "android-prod-apk":
        payload_path = _regular_factory_file(
            payload_root / "app-release.apk", "Android factory APK payload"
        )
        special_path = app_factory_root / "android-release-manifest.json"
        channel_id = "official_web"
        actual_digest = artifact_digest(payload_path)
    else:
        payload_path = payload_root / "public-web"
        if payload_path.is_symlink() or not payload_path.is_dir():
            raise OfficialDistributionReleaseError("Web factory payload is missing or unsafe")
        special_path = app_factory_root / "public-web-manifest.json"
        channel_id = "hosted_web"
        actual_digest = artifact_digest(payload_path)
    if actual_digest != selected_manifest.get("artifactDigest"):
        raise OfficialDistributionReleaseError(
            f"factory {component_key} actual payload artifact digest drifted"
        )

    special = _canonical_json_object(
        special_path, f"factory distribution manifest {component_key}", compact=False
    )
    _validate_distribution_manifest_fields(
        component_key=component_key, package_manifest=special
    )
    if special.get("artifactManifest") != selected_manifest:
        raise OfficialDistributionReleaseError(
            f"factory distribution manifest {component_key} AppArtifactManifest drifted"
        )
    _validate_official_channel(
        component_key=component_key,
        manifest=special,
        payload_path=payload_path,
    )
    return {
        "stableTag": stable_tag,
        "releaseTagAdmission": stable_exact,
        "releaseTagAdmissionId": stable_id,
        "qualification": qualification_exact,
        "qualificationId": qualification_id,
        "candidateMaterialManifest": material_exact,
        "candidateMaterialId": material_id,
        "appFactoryRef": app_ref,
        "appFactoryDigest": app_digest,
        "appFactoryPayloadDigest": app_payload_digest,
        "appFactoryMaterialDigest": app_material_digest,
        "selectedAppArtifactDigest": selected_manifest["artifactDigest"],
        "sourceGitSha": source,
        "sourceTreeDigest": expected_tree_digest,
        "artifactBuildNumber": build,
        "channelId": channel_id,
        "distributionManifestPath": special_path,
        "distributionManifest": special,
        "payloadPath": payload_path,
    }


def _exact_fact(
    root: Path, value: Any, label: str
) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(value, Mapping) or set(value) != {"ref", "digest"}:
        raise OfficialDistributionReleaseError(f"{label} must contain exact ref/digest")
    ref = str(value.get("ref") or "")
    relative = PurePosixPath(ref)
    if (
        not ref
        or relative.is_absolute()
        or relative.as_posix() != ref
        or "\\" in ref
        or any(part in {"", ".", "..", "latest", "current"} for part in relative.parts)
    ):
        raise OfficialDistributionReleaseError(f"{label} ref is mutable or unsafe")
    expected = _required_digest(value.get("digest"), f"{label} digest")
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise OfficialDistributionReleaseError(f"{label} ref traverses symlink")
    if not path.is_file() or _sha256_prefixed_file(path) != expected:
        raise OfficialDistributionReleaseError(f"{label} exact bytes drifted")
    payload = _canonical_json_object(path, label, compact=True)
    return payload, {"ref": ref, "digest": expected}


def _canonical_json_object(path: Path, label: str, *, compact: bool) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise OfficialDistributionReleaseError(f"{label} is unreadable: {error}") from error
    if not isinstance(payload, dict):
        raise OfficialDistributionReleaseError(f"{label} must be an object")
    expected = (
        _canonical_bytes(payload) + b"\n"
        if compact
        else (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    )
    if raw != expected:
        raise OfficialDistributionReleaseError(f"{label} is not canonical JSON with one newline")
    return payload


def _fact_identity(payload: Mapping[str, Any], field: str, label: str) -> str:
    claimed = _required_digest(payload.get(field), f"{label}.{field}")
    unsigned = {key: value for key, value in payload.items() if key != field}
    if _digest_object(unsigned) != claimed:
        raise OfficialDistributionReleaseError(f"{label} {field} self identity drifted")
    return claimed


def _self_digest(payload: Mapping[str, Any], field: str, label: str) -> str:
    claimed = _required_digest(payload.get(field), f"{label}.{field}")
    unsigned = {key: value for key, value in payload.items() if key != field}
    if _digest_object(unsigned) != claimed:
        raise OfficialDistributionReleaseError(f"{label} material digest drifted")
    return claimed


def _formal_artifacts(value: Any, label: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) != 4:
        raise OfficialDistributionReleaseError(f"{label} artifact set is incomplete")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"platform", "ociRef", "digest"}:
            raise OfficialDistributionReleaseError(f"{label} artifact shape drifted")
        platform = str(item.get("platform") or "")
        locator = _exact_oci_ref(item.get("ociRef"), f"{label}.{platform}.ociRef")
        digest = _required_digest(item.get("digest"), f"{label}.{platform}.digest")
        if platform in seen or not locator.endswith("@" + digest):
            raise OfficialDistributionReleaseError(f"{label} artifact identity drifted")
        seen.add(platform)
        result.append({"platform": platform, "ociRef": locator, "digest": digest})
    if seen != {"android", "ios", "service", "web"}:
        raise OfficialDistributionReleaseError(f"{label} artifact platforms are incomplete")
    return sorted(result, key=lambda item: item["platform"])


def _validate_app_artifact_manifest(
    manifest: dict[str, Any],
    *,
    build_product_id: str,
    source_git_sha: str,
    source_tree_digest: str,
) -> None:
    descriptor = {
        "schema": "release-application-package",
        "buildProductId": build_product_id,
        "buildProfile": manifest.get("buildProfile"),
        "platform": manifest.get("platform"),
        "sourceGitSha": source_git_sha,
        "sourceTreeDigest": source_tree_digest,
        "packageDigest": "sha256:" + "0" * 64,
        "artifactManifest": manifest,
    }
    try:
        validate_package(
            descriptor,
            build_product_id=build_product_id,
            source_git_sha=source_git_sha,
            source_tree_digest=source_tree_digest,
        )
    except ValueError as error:
        raise OfficialDistributionReleaseError(
            f"{build_product_id} AppArtifactManifest is invalid: {error}"
        ) from error


def _validate_distribution_manifest_fields(
    *, component_key: str, package_manifest: dict[str, Any]
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
            f"factory distribution manifest fields are not canonical: {component_key}"
        )


def _validate_official_channel(
    *, component_key: str, manifest: dict[str, Any], payload_path: Path
) -> None:
    source = manifest.get("artifactManifest")
    if (
        manifest.get("sourceGitSha") != source.get("sourceGitSha")
        or manifest.get("sourceTreeDigest") != source.get("sourceTreeDigest")
    ):
        raise OfficialDistributionReleaseError("official channel source identity drifted")
    if component_key == "web-shared":
        if (
            manifest.get("schema") != "client-app.web.official-release"
            or manifest.get("environment") != "prod"
            or source.get("buildProductId") != "web-shared"
            or source.get("distributionClass") != "hosted_web"
            or not _official_https_url(manifest.get("publicOrigin"), allow_cdn=False)
            or manifest.get("contentSHA256") != web_official_content_digest(payload_path)
        ):
            raise OfficialDistributionReleaseError("Web official channel identity drifted")
        return
    allowlist = manifest.get("apkHostAllowlist")
    if (
        manifest.get("schema") != "client-app.android.official-release"
        or manifest.get("platform") != "android"
        or source.get("buildProductId") != "android-prod-apk"
        or source.get("applicationId") != "com.leadwise.quwoquan"
        or manifest.get("packageName") != source.get("applicationId")
        or not isinstance(allowlist, list)
        or not allowlist
        or not all(_official_host(str(host)) for host in allowlist)
        or not _official_https_url(manifest.get("publicOrigin"), allow_cdn=False)
        or not _official_https_url(manifest.get("recoveryUrl"), allow_cdn=False)
        or not _official_https_url(manifest.get("apkUrl"), allow_cdn=True)
        or not _official_https_url(manifest.get("updateUrl"), allow_cdn=True)
        or urlparse(str(manifest.get("apkUrl"))).hostname not in allowlist
        or urlparse(str(manifest.get("updateUrl"))).hostname not in allowlist
        or manifest.get("apkSHA256") != artifact_digest(payload_path).removeprefix("sha256:")
    ):
        raise OfficialDistributionReleaseError("Android official channel identity drifted")


def _official_https_url(value: Any, *, allow_cdn: bool) -> bool:
    parsed = urlparse(str(value or ""))
    return (
        parsed.scheme == "https"
        and parsed.username is None
        and parsed.password is None
        and parsed.hostname is not None
        and _official_host(parsed.hostname)
        and (allow_cdn or parsed.hostname == "quwoquan.com" or parsed.hostname.endswith(".quwoquan.com"))
    )


def _official_host(host: str) -> bool:
    return host == "quwoquan.com" or host.endswith(".quwoquan.com")


def _package_tree_digest(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise OfficialDistributionReleaseError("factory package payload root is missing or unsafe")
    entries = sorted(root.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise OfficialDistributionReleaseError("factory package payload contains symlink")
    files = [path for path in entries if path.is_file()]
    if not files:
        raise OfficialDistributionReleaseError("factory package payload is empty")
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


def _regular_factory_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise OfficialDistributionReleaseError(f"{label} is missing or unsafe")
    return path


def _prefixed_tree_digest(tree: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", tree):
        return "sha1:" + tree
    if re.fullmatch(r"[0-9a-f]{64}", tree):
        return "sha256:" + tree
    raise OfficialDistributionReleaseError("source tree is not an exact Git tree")


def _exact_oci_ref(value: Any, label: str) -> str:
    locator = str(value or "")
    if re.fullmatch(r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}", locator) is None:
        raise OfficialDistributionReleaseError(f"{label} is not an exact OCI ref")
    return locator


def _required_digest(value: Any, label: str) -> str:
    digest = str(value or "")
    if _SHA256.fullmatch(digest) is None:
        raise OfficialDistributionReleaseError(f"{label} is not an exact digest")
    return digest


def _digest_object(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(dict(payload))).hexdigest()


def _sha256_prefixed_file(path: Path) -> str:
    return "sha256:" + _sha256_file(path)


def _verify_deployed_web(
    root: Path,
    manifest: dict[str, Any],
    *,
    public_path: Path | None = None,
) -> None:
    public = public_path or root / "public"
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


def _append_only_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError as error:
        if path.is_symlink() or path.read_bytes() != encoded:
            raise OfficialDistributionReleaseError(
                f"append-only receipt conflicts: {path}"
            ) from error
        return
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


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
