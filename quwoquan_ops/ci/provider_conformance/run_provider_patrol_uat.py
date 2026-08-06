"""Run one fixed Provider user journey against its selected environment."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.deployment_candidate_manifest import (  # noqa: E402
    load_candidate_manifest,
)
from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.local_sms_provider_debug import (  # noqa: E402
    read_latest_debug_otp,
)
from quwoquan_ops.cli.lib.output_paths import (  # noqa: E402
    active_deployment_candidate,
)
from quwoquan_ops.cli.lib.startup_attempt_receipt import (  # noqa: E402
    load_startup_attempt,
)
from quwoquan_ops.ci.provider_conformance.protected_otp_broker import (  # noqa: E402
    ProtectedOTPBroker,
    ProtectedOTPBrokerBinding,
)


_TARGET_NAMES = {
    "alpha": ("alpha-local", "alpha-local"),
    "beta": ("beta-local", "local-beta"),
    "gamma": ("gamma-local", "local-gamma"),
    "prod": ("prod-hosted", "prod-hosted"),
}
_NONPROD_ENVIRONMENTS = frozenset({"alpha", "beta", "gamma"})
_DIGEST_PREFIX = "sha256:"
_UNKNOWN_IDENTITIES = frozenset({"", "unknown", "none", "null", "n/a"})


@dataclass(frozen=True)
class ProviderPatrolRuntimeIdentity:
    environment: str
    target: str
    public_bases: dict[str, Any]
    baseline_id: str
    source_revision: str
    package_digest: str
    image_digest: str
    runtime_config_digest: str
    environment_runtime_digest: str
    provider_runtime_digest: str
    elasticsearch_binding_digest: str
    elasticsearch_image_digest: str
    elasticsearch_compose_digest: str
    elasticsearch_cluster_ref: str
    release_id: str
    release_digest: str
    attempt_id: str
    local_capture_sms_enabled: bool


def _sha256_bytes(value: bytes) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(value).hexdigest()


def _require_digest(value: object, *, label: str) -> str:
    normalized = str(value or "").strip()
    if (
        not normalized.startswith(_DIGEST_PREFIX)
        or len(normalized) != 71
        or any(character not in "0123456789abcdef" for character in normalized[7:])
    ):
        raise ValueError(f"{label} must be a sha256 digest")
    return normalized


def _load_nonprod_runtime_identity(
    environment: str,
    target_name: str,
) -> ProviderPatrolRuntimeIdentity:
    if environment not in _NONPROD_ENVIRONMENTS:
        raise ValueError("package-bound Provider Patrol runtime is nonprod-only")
    if target_name != f"{environment}-local":
        raise ValueError("Provider Patrol runtime target/environment mismatch")
    active = active_deployment_candidate(target_name)
    if not isinstance(active, dict):
        raise ValueError(f"{target_name} has no active immutable candidate")
    baseline_id = _require_digest(
        active.get("baselineId"),
        label="active candidate baselineId",
    )
    candidate_root = Path(str(active.get("candidateDir") or "")).resolve()
    manifest = load_candidate_manifest(
        environment,
        target_name,
        baseline_id,
        require_full=True,
    )
    if manifest.get("baselineId") != baseline_id:
        raise ValueError("active candidate manifest baseline identity mismatch")

    runtime_path = candidate_root / "packages/app/environment_runtime.yaml"
    if not runtime_path.is_file() or runtime_path.is_symlink():
        raise ValueError("packaged environment runtime is unavailable")
    try:
        runtime_raw = runtime_path.read_bytes()
        packaged_runtime = json.loads(runtime_raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("packaged environment runtime is unreadable") from exc
    environment_runtime_digest = _sha256_bytes(runtime_raw)
    public_bases = (
        packaged_runtime.get("publicBases")
        if isinstance(packaged_runtime, dict)
        else None
    )
    if (
        not isinstance(packaged_runtime, dict)
        or packaged_runtime.get("schema") != "environment-runtime-package"
        or packaged_runtime.get("environment") != environment
        or packaged_runtime.get("target") != target_name
        or not isinstance(public_bases, dict)
        or manifest.get("environmentRuntimeDigest") != environment_runtime_digest
    ):
        raise ValueError("packaged environment runtime identity mismatch")

    provider_package = manifest.get("providerRuntime")
    composition = (
        provider_package.get("composition")
        if isinstance(provider_package, dict)
        else None
    )
    bindings = composition.get("bindings") if isinstance(composition, dict) else None
    provider_runtime_digest = _require_digest(
        composition.get("runtimeCompositionDigest")
        if isinstance(composition, dict)
        else "",
        label="Provider runtime composition",
    )
    if not isinstance(bindings, list) or not bindings:
        raise ValueError("packaged Provider runtime bindings are unavailable")
    sms_binding = next(
        (
            item
            for item in bindings
            if isinstance(item, dict)
            and item.get("capabilityId") == "identity.sms.otp"
        ),
        None,
    )
    local_capture_sms_enabled = bool(
        isinstance(sms_binding, dict)
        and sms_binding.get("state") == "enabled"
        and sms_binding.get("adapterId") == "ext.sms.local_capture"
        and sms_binding.get("endpointRef")
        == "local_topology:sms-provider-substitute"
    )

    log_sink = manifest.get("observabilityLogSink")
    if (
        not isinstance(log_sink, dict)
        or log_sink.get("adapterId") != "ext.obs.elasticsearch"
        or log_sink.get("deploymentMode") != "package-bound-local"
    ):
        raise ValueError("package-bound Elasticsearch log sink is unavailable")
    elasticsearch_compose_digest = _require_digest(
        log_sink.get("composeDigest"),
        label="Elasticsearch Compose",
    )

    startup = load_startup_attempt(target_name)
    attempt_id = str((startup or {}).get("attemptId") or "").strip()
    if (
        not isinstance(startup, dict)
        or startup.get("status") != "running"
        or startup.get("workload") != "full"
        or startup.get("env") != environment
        or startup.get("target") != target_name
        or startup.get("candidateDigest") != baseline_id
        or startup.get("configurationDigest") != manifest.get("runtimeConfigDigest")
        or startup.get("providerRuntimeDigest") != provider_runtime_digest
        or startup.get("observabilityLogSinkDigest")
        != elasticsearch_compose_digest
        or not str(startup.get("composeProject") or "").strip()
        or attempt_id.lower() in _UNKNOWN_IDENTITIES
        or startup.get("failure") not in {None, ""}
        or startup.get("cleanupFailure") not in {None, ""}
    ):
        raise ValueError(
            "running full startup receipt is not bound to the active candidate, "
            "Provider composition, and Elasticsearch deployment"
        )

    release = manifest.get("release")
    candidate_release = release.get("candidate") if isinstance(release, dict) else None
    if not isinstance(candidate_release, dict):
        raise ValueError("active candidate release binding is unavailable")
    return ProviderPatrolRuntimeIdentity(
        environment=environment,
        target=target_name,
        public_bases=dict(public_bases),
        baseline_id=baseline_id,
        source_revision=str(manifest.get("sourceRevision") or "").strip(),
        package_digest=_require_digest(
            manifest.get("packageDigest"), label="candidate package"
        ),
        image_digest=_require_digest(
            manifest.get("imageDigest"), label="candidate image"
        ),
        runtime_config_digest=_require_digest(
            manifest.get("runtimeConfigDigest"), label="runtime configuration"
        ),
        environment_runtime_digest=environment_runtime_digest,
        provider_runtime_digest=provider_runtime_digest,
        elasticsearch_binding_digest=_require_digest(
            log_sink.get("bindingDigest"), label="Elasticsearch Binding"
        ),
        elasticsearch_image_digest=_require_digest(
            log_sink.get("imageDigest"), label="Elasticsearch image"
        ),
        elasticsearch_compose_digest=elasticsearch_compose_digest,
        elasticsearch_cluster_ref=str(log_sink.get("clusterRef") or "").strip(),
        release_id=str(candidate_release.get("releaseId") or "").strip(),
        release_digest=_require_digest(
            candidate_release.get("releaseDigest"), label="candidate release"
        ),
        attempt_id=attempt_id,
        local_capture_sms_enabled=local_capture_sms_enabled,
    )


def _validated_broker_port(binding: ProtectedOTPBrokerBinding) -> int:
    parsed = urlparse(binding.url)
    try:
        port = int(parsed.port or 0)
    except ValueError as exc:
        raise ValueError("protected OTP broker URL has an invalid port") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/v1/otp"
        or parsed.params
        or parsed.query
        or parsed.fragment
        or port <= 0
    ):
        raise ValueError("protected OTP broker must use the exact HTTPS loopback URL")
    _require_digest(binding.ca_digest, label="protected OTP broker CA")
    _require_digest(
        binding.certificate_digest,
        label="protected OTP broker certificate",
    )
    return port


def _runtime_evidence(
    identity: ProviderPatrolRuntimeIdentity,
    binding: ProtectedOTPBrokerBinding | None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "environment": identity.environment,
        "target": identity.target,
        "baselineId": identity.baseline_id,
        "sourceRevision": identity.source_revision,
        "packageDigest": identity.package_digest,
        "imageDigest": identity.image_digest,
        "runtimeConfigDigest": identity.runtime_config_digest,
        "environmentRuntimeDigest": identity.environment_runtime_digest,
        "providerRuntimeDigest": identity.provider_runtime_digest,
        "elasticsearch": {
            "adapterId": "ext.obs.elasticsearch",
            "bindingDigest": identity.elasticsearch_binding_digest,
            "imageDigest": identity.elasticsearch_image_digest,
            "composeDigest": identity.elasticsearch_compose_digest,
            "clusterRef": identity.elasticsearch_cluster_ref,
        },
        "release": {
            "releaseId": identity.release_id,
            "releaseDigest": identity.release_digest,
        },
        "startup": {"workload": "full", "attemptId": identity.attempt_id},
    }
    if binding is not None:
        evidence["protectedOtpBrokerTls"] = {
            "scheme": "https",
            "minimumTlsVersion": "TLSv1.3",
            "caDigest": binding.ca_digest,
            "certificateDigest": binding.certificate_digest,
        }
    return evidence


def _bind_runtime_evidence_to_patrol_report(
    report_path: Path,
    *,
    identity: ProviderPatrolRuntimeIdentity,
    binding: ProtectedOTPBrokerBinding | None,
) -> None:
    if not report_path.is_file() or report_path.is_symlink():
        raise ValueError("Provider Patrol did not produce a safe report")
    try:
        report_raw = report_path.read_bytes()
        report = json.loads(report_raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Provider Patrol report is unreadable") from exc
    if not isinstance(report, dict):
        raise ValueError("Provider Patrol report root must be an object")
    if (
        report.get("suiteId") != "environment_page_smoke"
        or report.get("runtimeEnv") != identity.environment
        or report.get("apiContractEnv") != identity.environment
        or report.get("candidateDigest") != identity.baseline_id
        or "runtimeIdentityEvidence" in report
    ):
        raise ValueError("Provider Patrol report runtime identity mismatch")
    if binding is not None and binding.token.encode("utf-8") in report_raw:
        raise ValueError("Provider Patrol report exposed the protected broker token")
    report["runtimeIdentityEvidence"] = _runtime_evidence(identity, binding)
    rendered = (
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    if binding is not None and binding.token.encode("utf-8") in rendered:
        raise ValueError("Provider Patrol TLS evidence exposed the broker token")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{report_path.name}.",
        suffix=".tmp",
        dir=report_path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, report_path.stat().st_mode & 0o777)
        temporary.replace(report_path)
    finally:
        temporary.unlink(missing_ok=True)


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _required_url(public_bases: dict[str, Any], name: str) -> str:
    value = str(public_bases.get(name) or "").strip()
    if not value:
        raise ValueError(f"environment topology publicBases.{name} is required")
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--platform", choices=("android", "ios"), default="android")
    parser.add_argument("--unauthenticated", action="store_true")
    parser.add_argument("--define-key", action="append", default=[])
    parser.add_argument("--local-capture-otp-broker", action="store_true")
    return parser.parse_args()


def _configure_android_broker_reverse(
    *,
    action: str,
    device_id: str,
    port: int,
) -> None:
    if not device_id:
        raise ValueError(
            "local-capture Android OTP UAT requires "
            "QWQ_PROVIDER_CONFORMANCE_DEVICE_ID"
        )
    endpoint = f"tcp:{port}"
    command = ["adb", "-s", device_id, "reverse"]
    if action == "add":
        command.extend((endpoint, endpoint))
    elif action == "remove":
        command.extend(("--remove", endpoint))
    else:
        raise ValueError("unsupported Android broker reverse action")
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 and action == "add":
        raise RuntimeError("failed to install protected OTP broker port reverse")


def main() -> int:
    args = _parse_args()
    environment = _required_environment(
        "QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT"
    )
    try:
        target_name, environment_alias = _TARGET_NAMES[environment]
    except KeyError as exc:
        raise ValueError(
            f"unsupported Provider Patrol environment: {environment}"
        ) from exc
    runtime_identity: ProviderPatrolRuntimeIdentity | None = None
    if environment in _NONPROD_ENVIRONMENTS:
        runtime_identity = _load_nonprod_runtime_identity(
            environment,
            target_name,
        )
        public_bases = runtime_identity.public_bases
    else:
        target = get_target(load_environment_topology(), target_name)
        public_bases = target.get("publicBases")
    if not isinstance(public_bases, dict):
        raise ValueError(f"{target_name} publicBases are required")

    result_path = Path(
        _required_environment("QWQ_PROVIDER_CONFORMANCE_RESULT_PATH")
    )
    report_path = result_path.with_name(f"{result_path.stem}.patrol-report.json")
    command = [
        sys.executable,
        "quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py",
        "--env-name",
        environment_alias,
        "--runtime-env",
        environment,
        "--api-contract-env",
        environment,
        "--gateway-base-url",
        _required_url(public_bases, "api"),
        "--product-ops-base-url",
        _required_url(public_bases, "productOps"),
        "--media-avatar-base-url",
        _required_url(public_bases, "mediaAvatar"),
        "--media-image-base-url",
        _required_url(public_bases, "mediaImage"),
        "--media-video-base-url",
        _required_url(public_bases, "mediaVideo"),
        "--media-upload-base-url",
        _required_url(public_bases, "mediaUpload"),
        "--rtc-media-connection-url",
        _required_url(public_bases, "rtc"),
        "--target",
        args.target,
        "--platform",
        args.platform,
        "--report",
        str(report_path),
    ]
    if runtime_identity is not None:
        command.extend(("--candidate-digest", runtime_identity.baseline_id))
    device_id = os.environ.get(
        "QWQ_PROVIDER_CONFORMANCE_DEVICE_ID", ""
    ).strip()
    if device_id:
        command.extend(("--device-id", device_id))
    command_environment = dict(os.environ)
    define_keys = tuple(
        str(key).strip() for key in args.define_key if str(key).strip()
    )
    if args.local_capture_otp_broker:
        define_keys += (
            "QWQ_PROVIDER_UAT_OTP_BROKER_URL",
            "QWQ_PROVIDER_UAT_OTP_BROKER_TOKEN",
        )
    invalid_define_keys = [
        key
        for key in define_keys
        if not key.startswith("QWQ_PROVIDER_UAT_")
    ]
    if invalid_define_keys:
        raise ValueError("Provider Patrol define keys must use QWQ_PROVIDER_UAT_*")
    generated_define_keys = {
        "QWQ_PROVIDER_UAT_OTP_BROKER_URL",
        "QWQ_PROVIDER_UAT_OTP_BROKER_TOKEN",
    } if args.local_capture_otp_broker else set()
    missing_define_keys = [
        key
        for key in define_keys
        if key not in generated_define_keys
        and not command_environment.get(key, "").strip()
    ]
    if missing_define_keys:
        raise ValueError(
            "Provider Patrol define values are required: "
            + ", ".join(missing_define_keys)
        )
    if define_keys:
        command_environment["QWQ_PROVIDER_UAT_DART_DEFINE_KEYS"] = ",".join(
            define_keys
        )
    if args.unauthenticated:
        command.append("--unauthenticated-auth-entry")
        for key in (
            "TEST_AUTH_TOKEN",
            "TEST_REFRESH_TOKEN",
            "APP_CURRENT_OWNER_ID",
            "APP_CURRENT_PERSONA_ID",
        ):
            command_environment.pop(key, None)
    broker: ProtectedOTPBroker | None = None
    broker_binding: ProtectedOTPBrokerBinding | None = None
    broker_port = 0
    broker_reverse_added = False
    try:
        if args.local_capture_otp_broker:
            if environment not in {"alpha", "beta", "gamma"}:
                raise ValueError(
                    "local-capture OTP broker is forbidden for Prod evidence"
                )
            if command_environment.get("QWQ_PROVIDER_UAT_SMS_OTP", "").strip():
                raise ValueError(
                    "local-capture OTP UAT must not preload an OTP"
                )
            if (
                runtime_identity is None
                or not runtime_identity.local_capture_sms_enabled
            ):
                raise ValueError(
                    "active candidate does not select the SMS local-capture "
                    "Provider composition"
                )
            broker = ProtectedOTPBroker(
                environment=environment,
                target_name=target_name,
                recipient=_required_environment("QWQ_PROVIDER_UAT_SMS_PHONE"),
                reader=read_latest_debug_otp,
            )
            broker_binding = broker.start()
            command_environment[
                "QWQ_PROVIDER_UAT_OTP_BROKER_URL"
            ] = broker_binding.url
            command_environment[
                "QWQ_PROVIDER_UAT_OTP_BROKER_TOKEN"
            ] = broker_binding.token
            broker_port = _validated_broker_port(broker_binding)
            if args.platform == "android":
                _configure_android_broker_reverse(
                    action="add",
                    device_id=device_id,
                    port=broker_port,
                )
                broker_reverse_added = True
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=command_environment,
            check=False,
        )
        if runtime_identity is not None:
            try:
                _bind_runtime_evidence_to_patrol_report(
                    report_path,
                    identity=runtime_identity,
                    binding=broker_binding,
                )
            except (OSError, ValueError) as exc:
                print(f"GATE_BLOCK: {exc}", file=sys.stderr)
                return 2
        return completed.returncode
    finally:
        if broker_reverse_added:
            _configure_android_broker_reverse(
                action="remove",
                device_id=device_id,
                port=broker_port,
            )
        if broker is not None:
            broker.close()


if __name__ == "__main__":
    raise SystemExit(main())
