"""CLI 参数与发布包/配置输入校验（从 render_prod_plane_stack.py 逐字搬移）。"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import subprocess
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.output_paths import deployment_target_path
from quwoquan_ops.cli.lib.output_paths import resolve_deployment_target_path

from .constants import (
    ACCESS_MANIFEST,
    PREVALIDATION_AUTH_SECRET_KEYS,
    ROOT,
)

try:
    import yaml
except ImportError:  # pragma: no cover
    raise SystemExit("FAIL: PyYAML required")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render prod plane rootless stack from truth sources.",
    )
    parser.add_argument("--plane", default="service", choices=["service", "edge"])
    parser.add_argument(
        "--instance",
        default="prod",
        choices=["gray", "prod", "prevalidate"],
    )
    parser.add_argument(
        "--replica-id",
        default="r0",
        help="Safe replica identity from the prod-hosted deployment plan.",
    )
    parser.add_argument(
        "--host-id",
        default="",
        help="Logical host identity from access-isolation.yaml.",
    )
    parser.add_argument(
        "--rollout-stage",
        default="100",
        choices=["canary", "5", "20", "50", "100"],
    )
    parser.add_argument("--candidate-digest", required=True)
    parser.add_argument(
        "--image-transport-tag",
        default=os.environ.get("IMAGE_TRANSPORT_TAG", ""),
    )
    parser.add_argument(
        "--release-evidence-digest",
        default=os.environ.get("RELEASE_EVIDENCE_DIGEST", ""),
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help=(
            "resolver-derived target-scoped render directory; defaults to "
            "QWQ_DEPLOY_WORK_ROOT/prod-hosted/rendered/<plane>-<instance>"
        ),
    )
    parser.add_argument("--host", default="")
    parser.add_argument(
        "--web-runtime-config-trust",
        default=os.environ.get("QWQ_WEB_RUNTIME_CONFIG_TRUST_PATH", ""),
    )
    parser.add_argument(
        "--web-runtime-config-package",
        default=os.environ.get("QWQ_WEB_RUNTIME_CONFIG_PACKAGE_PATH", ""),
    )
    parser.add_argument(
        "--data-mode",
        default="external",
        choices=["isolated", "external"],
    )
    parser.add_argument(
        "--prevalidate-scope",
        default="",
        choices=["", "first-party"],
    )
    return parser.parse_args()


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"FAIL: {path} must parse as object")
    return data


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _prevalidation_secret_environment() -> dict[str, str]:
    """Return target-local, non-release auth material shared by service/edge.

    The file lives in the external deployment workspace, is never included in
    provenance, and is intentionally separate from the formal prod credentials
    directory.  Both planes must share the JWT/device-ticket keys so an edge
    request can be authenticated by the first-party service plane.
    """

    secret_path = deployment_target_path(
        "prod-hosted", "secrets", "prevalidation-auth.env"
    )
    values: dict[str, str] = {}
    if secret_path.is_file():
        if secret_path.stat().st_mode & 0o077:
            raise SystemExit(
                f"FAIL: prevalidation auth material must be mode 0600: {secret_path}"
            )
        for line in secret_path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key in PREVALIDATION_AUTH_SECRET_KEYS and value:
                values[key] = value
    if set(values) != set(PREVALIDATION_AUTH_SECRET_KEYS):
        values = {
            "AUTH_JWT_SECRET": secrets.token_urlsafe(48),
            "AUTH_DEVICE_TICKET_SECRET": secrets.token_urlsafe(48),
            "OTP_CODE_REF_KEY": base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
            "QWQ_PUSH_TOKEN_ENCRYPTION_KEY": base64.b64encode(
                secrets.token_bytes(32)
            ).decode("ascii"),
            "CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET": secrets.token_urlsafe(48),
            "QWQ_COMPOSE_OBJECT_STORAGE_CDN_SIGN_KEY": secrets.token_urlsafe(48),
        }
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_text(
            "\n".join(f"{key}={values[key]}" for key in PREVALIDATION_AUTH_SECRET_KEYS)
            + "\n",
            encoding="utf-8",
        )
        secret_path.chmod(0o600)
    return values


def _canonical_config_bytes(payload: dict[str, Any]) -> bytes:
    return yaml.safe_dump(
        payload,
        allow_unicode=True,
        sort_keys=True,
        width=120,
    ).encode("utf-8")


def _project_isolated_prevalidation_config(
    path: Path,
) -> dict[str, Any]:
    """Project prod config onto a single-node, empty Redis data plane.

    This is a new immutable config snapshot with its own digest. It never
    changes the package or claims to prove the formal prod data topology.
    """

    payload = _load_yaml(path)
    changes: list[str] = []
    redis = payload.get("redis")
    if isinstance(redis, dict):
        for role, role_config in redis.items():
            if not isinstance(role_config, dict):
                continue
            if role_config.get("mode") != "standalone":
                role_config["mode"] = "standalone"
                changes.append(f"redis.{role}.mode=standalone")
            if role_config.get("tls") is not False:
                role_config["tls"] = False
                changes.append(f"redis.{role}.tls=false")
            if role_config.get("addr") != "redis:6379":
                role_config["addr"] = "redis:6379"
                changes.append(f"redis.{role}.addr=redis:6379")
            if "addrs" in role_config:
                role_config.pop("addrs")
                changes.append(f"redis.{role}.addrs=removed")
    config = payload.setdefault("config", {})
    if not isinstance(config, dict):
        raise SystemExit(f"FAIL: config section is not an object: {path}")
    config.pop("version", None)
    projected_version = "sha256:" + hashlib.sha256(
        _canonical_config_bytes(payload)
    ).hexdigest()
    config["version"] = projected_version
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    return {
        "projectedConfigurationDigest": projected_version,
        "projectedConfigDigest": _sha256(path),
        "changes": changes,
    }


def _resolve_render_output_dir(
    configured_output: str | Path | None,
    *,
    plane: str,
    instance: str,
    replica_id: str = "r0",
) -> Path:
    render_name = f"{plane}-{instance}-{replica_id}"
    try:
        return resolve_deployment_target_path(
            configured_output,
            target="prod-hosted",
            segments=("rendered", render_name),
        )
    except ValueError as exc:
        raise SystemExit(
            "FAIL: prod deployment rendering must use the QWQ_DEPLOY_WORK_ROOT "
            "resolver-derived prod-hosted target directory"
        ) from exc


def _require_external_deployment_root(output_root: Path) -> None:
    """Compatibility guard retained for direct local-contract probes."""
    _resolve_render_output_dir(
        output_root,
        plane="service",
        instance="prod",
    )


def _verified_package_config(
    package_dir: Path,
    *,
    release_id: str,
) -> Path:
    report_path = package_dir / "provenance.json"
    config_path = package_dir / "config" / "config.yaml"
    if not report_path.is_file() or not config_path.is_file():
        raise SystemExit(f"FAIL: incomplete autonomous service package: {package_dir}")
    try:
        provenance = json.loads(report_path.read_text(encoding="utf-8"))
        file_digest = provenance["digests"]["config"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL: invalid package provenance: {report_path}") from exc
    if file_digest != _sha256(config_path):
        raise SystemExit(f"FAIL: package config digest mismatch: {config_path}")
    config_payload = _load_yaml(config_path)
    config_section = config_payload.get("config") if isinstance(config_payload, dict) else None
    embedded_version = (
        str(config_section.get("version") or "")
        if isinstance(config_section, dict)
        else ""
    )
    if provenance.get("configVersion") != embedded_version:
        raise SystemExit(f"FAIL: package CONFIG_VERSION differs from effective config: {report_path}")
    release_evidence = provenance.get("releaseEvidence")
    if not isinstance(release_evidence, dict):
        raise SystemExit(f"FAIL: package release evidence provenance missing: {report_path}")
    if release_evidence.get("candidateId") != release_id:
        raise SystemExit(f"FAIL: package candidate ID mismatch: {report_path}")
    if release_evidence.get("verifiedConfigDigest") != file_digest:
        raise SystemExit(f"FAIL: package release config evidence mismatch: {report_path}")
    manifest_rel = str(release_evidence.get("manifest") or "")
    manifest_path = Path(manifest_rel)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    if (
        not manifest_rel
        or not manifest_path.is_file()
        or release_evidence.get("evidenceFileDigest") != _sha256(manifest_path)
    ):
        raise SystemExit(f"FAIL: package release artifact manifest mismatch: {report_path}")
    return config_path


def _git_revision() -> str:
    revision = os.environ.get("GITHUB_SHA", "").strip()
    if revision:
        return revision
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _plane_spec(plane_name: str) -> dict[str, Any]:
    access = _load_yaml(ACCESS_MANIFEST)
    for plane in access.get("planes") or []:
        if str(plane.get("plane")) == plane_name:
            return plane
    raise SystemExit(f"FAIL: plane missing from access manifest: {plane_name}")


def _prevalidation_spec() -> dict[str, Any]:
    access = _load_yaml(ACCESS_MANIFEST)
    spec = access.get("prevalidation")
    if not isinstance(spec, dict) or spec.get("promotable") is not False:
        raise SystemExit("FAIL: non-promotable prod prevalidation projection is missing")
    return spec
