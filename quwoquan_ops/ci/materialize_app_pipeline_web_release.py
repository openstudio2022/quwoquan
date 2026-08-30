"""Materialize the canonical Prod Web release manifest from one AppArtifact."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.commands.package_app_artifact_helpers import (
    artifact_digest,
    validate_app_artifact_build_receipt,
)
from quwoquan_ops.cli.lib.app_identity import (
    AppIdentityError,
    resolve_build_product,
)
from quwoquan_ops.cli.lib.web_official_release import (
    WebOfficialReleaseError,
    validate_web_official_artifact,
    web_official_content_digest,
)


class WebReleaseMaterializationError(RuntimeError):
    """Typed fail-closed Web release materialization blocker."""


def _read_result(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise WebReleaseMaterializationError(
            "APP.PIPELINE.web_release_result_unavailable"
        ) from error
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise WebReleaseMaterializationError("APP.PIPELINE.web_release_result_unsafe")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WebReleaseMaterializationError(
            "APP.PIPELINE.web_release_result_malformed"
        ) from error
    if not isinstance(payload, dict):
        raise WebReleaseMaterializationError(
            "APP.PIPELINE.web_release_result_malformed"
        )
    return payload


def _validated_web_manifest(result: Mapping[str, Any]) -> tuple[dict[str, Any], Path]:
    if type(result.get("exitCode")) is not int or result.get("exitCode") != 0:
        raise WebReleaseMaterializationError(
            "APP.PIPELINE.web_release_result_not_successful"
        )
    manifest = result.get("manifest")
    if not isinstance(manifest, dict):
        raise WebReleaseMaterializationError(
            "APP.PIPELINE.web_release_manifest_invalid"
        )
    try:
        product = resolve_build_product("web-shared")
    except AppIdentityError as error:
        raise WebReleaseMaterializationError(
            f"APP.PIPELINE.web_release_product_invalid: {error}"
        ) from error
    expected_identity: dict[str, object] = {
        "schema": "app-artifact-manifest",
        "buildProductId": product.build_product_id,
        "buildProfile": product.build_profile,
        "platform": product.platform,
        "buildMode": product.build_mode,
        "artifactFormat": product.artifact_format,
        "distributionClass": product.distribution_class,
        "promotable": True,
    }
    if any(
        manifest.get(field) != expected for field, expected in expected_identity.items()
    ):
        raise WebReleaseMaterializationError(
            "APP.PIPELINE.web_release_manifest_invalid"
        )
    attempt_value = result.get("attemptDir")
    if not isinstance(attempt_value, str) or not attempt_value.strip():
        raise WebReleaseMaterializationError("APP.PIPELINE.web_release_attempt_invalid")
    return manifest, Path(attempt_value)


def _render_release(*, artifact: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    observed_before = artifact_digest(artifact)
    if manifest.get("artifactDigest") != observed_before:
        raise WebReleaseMaterializationError(
            "APP.PIPELINE.web_release_artifact_digest_mismatch"
        )
    content_digest = web_official_content_digest(artifact)
    payload = {
        "schema": "client-app.web.official-release",
        "environment": "prod",
        "publicOrigin": "https://quwoquan.com",
        "releaseId": content_digest[:20],
        "contentSHA256": content_digest,
        "noindex": False,
        "spaFallback": "/index.html",
        "htmlContentType": "text/html; charset=utf-8",
        "assetCacheControl": "no-cache, must-revalidate",
        "serviceWorker": "flutter_service_worker.js",
    }
    if (
        artifact_digest(artifact) != observed_before
        or web_official_content_digest(artifact) != content_digest
    ):
        raise WebReleaseMaterializationError(
            "APP.PIPELINE.web_release_artifact_drifted"
        )
    return payload


def _atomic_write_create_once(path: Path, payload: Mapping[str, Any]) -> None:
    if not path.is_absolute():
        raise WebReleaseMaterializationError(
            "APP.PIPELINE.web_release_output_path_invalid"
        )
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise WebReleaseMaterializationError(
            "APP.PIPELINE.web_release_output_parent_invalid"
        )
    encoded = (
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
    )
    temporary = parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    descriptor = -1
    linked = False
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError as error:
            raise WebReleaseMaterializationError(
                "APP.PIPELINE.web_release_output_exists"
            ) from error
        linked = True
        directory = os.open(
            parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except WebReleaseMaterializationError:
        raise
    except OSError as error:
        if linked:
            path.unlink(missing_ok=True)
        raise WebReleaseMaterializationError(
            f"APP.PIPELINE.web_release_output_write_failed: {error}"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def materialize(*, result_path: Path, output_path: Path) -> dict[str, Any]:
    result = _read_result(result_path)
    manifest, attempt_dir = _validated_web_manifest(result)
    try:
        validated = validate_app_artifact_build_receipt(
            attempt_dir=attempt_dir,
            expected_build_product_id="web-shared",
            expected_manifest=manifest,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise WebReleaseMaterializationError(
            f"APP.PIPELINE.web_release_receipt_invalid: {error}"
        ) from error
    try:
        validate_web_official_artifact(validated.artifact_path)
    except (OSError, TypeError, ValueError, WebOfficialReleaseError) as error:
        raise WebReleaseMaterializationError(
            f"APP.PIPELINE.web_release_artifact_invalid: {error}"
        ) from error
    payload = _render_release(
        artifact=validated.artifact_path,
        manifest=manifest,
    )
    _atomic_write_create_once(output_path, payload)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        payload = materialize(result_path=args.result, output_path=args.output)
    except WebReleaseMaterializationError as error:
        print(f"::error::GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    print(
        "[app-pipeline-web-release] materialized "
        f"releaseId={payload['releaseId']} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
