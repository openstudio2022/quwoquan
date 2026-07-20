from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod_plane_access_isolation.yaml"
DEFAULT_KEY_DIR = Path.home() / ".ssh/quwoquan-prod"
DEFAULT_HOST = "118.31.239.122"
OCI_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True)
class PlaneSpec:
    plane: str
    account: str
    governed_services: tuple[str, ...]
    support_services: tuple[str, ...]


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _plane_spec(plane_name: str) -> PlaneSpec:
    access = _load_yaml(ACCESS_MANIFEST)
    for plane in access.get("planes") or []:
        if str(plane.get("plane")) != plane_name:
            continue
        return PlaneSpec(
            plane=plane_name,
            account=str(plane.get("account") or ""),
            governed_services=tuple(str(item) for item in (plane.get("rootlessGovernedComposeServices") or [])),
            support_services=tuple(str(item) for item in (plane.get("rootlessSupportComposeServices") or [])),
        )
    raise SystemExit(f"FAIL: unknown plane: {plane_name}")


def _compose_image_refs(
    services: list[str],
    *,
    image_version: str = "",
) -> dict[str, str]:
    if not image_version or image_version == "latest":
        raise SystemExit("FAIL: fixed image version required for production images")
    return {
        service: f"localhost/quwoquan_service_{service}:{image_version}"
        for service in services
    }


def _local_image_architecture(image_ref: str) -> str | None:
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Architecture}}", image_ref],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _local_image_digest(image_ref: str) -> str | None:
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image_ref],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    digest = result.stdout.strip()
    return digest if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) else None


def _canonical_manifest_digest(payload: dict[str, Any]) -> str:
    canonical = dict(payload)
    canonical.pop("manifestDigest", None)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _release_image_sources(
    manifest_path: Path,
    *,
    services: list[str],
    image_version: str,
) -> tuple[str, dict[str, str]]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"FAIL: cannot read release manifest: {error}") from error
    if not isinstance(manifest, dict):
        raise SystemExit("FAIL: release manifest must be an object")
    if (
        manifest.get("schema") != "mainline-release-artifact"
        or manifest.get("status") != "deployable"
    ):
        raise SystemExit("FAIL: release manifest is not deployable")
    manifest_digest = str(manifest.get("manifestDigest") or "")
    if manifest_digest != _canonical_manifest_digest(manifest):
        raise SystemExit("FAIL: release manifest digest mismatch")
    versions = manifest.get("versions")
    if not isinstance(versions, dict) or versions.get("imageVersion") != image_version:
        raise SystemExit("FAIL: release manifest image version mismatch")
    images = manifest.get("images")
    if not isinstance(images, dict):
        raise SystemExit("FAIL: release manifest images must be an object")
    sources: dict[str, str] = {}
    for service in services:
        image = images.get(service)
        if not isinstance(image, dict):
            raise SystemExit(f"FAIL: release manifest missing image for {service}")
        digest = str(image.get("digest") or "")
        repository = str(image.get("repository") or "")
        ref = str(image.get("ref") or "")
        if OCI_DIGEST_PATTERN.fullmatch(digest) is None or ref != f"{repository}@{digest}":
            raise SystemExit(f"FAIL: release manifest has invalid digest ref for {service}")
        attestations = image.get("attestations")
        if not isinstance(attestations, dict) or not all(
            str(attestations.get(kind) or "") == f"oci://{ref}#{kind}"
            for kind in ("spdxSbom", "slsaProvenance")
        ):
            raise SystemExit(f"FAIL: release manifest missing attestations for {service}")
        sources[service] = ref
    return manifest_digest, sources


def _pull_and_tag_release_image(source_ref: str, target_ref: str) -> None:
    pull = subprocess.run(
        ["docker", "pull", source_ref],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if pull.returncode != 0:
        raise SystemExit(f"FAIL: docker pull failed for {source_ref}:\n{pull.stdout}")
    tag = subprocess.run(
        ["docker", "tag", source_ref, target_ref],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if tag.returncode != 0:
        raise SystemExit(f"FAIL: docker tag failed for {source_ref}: {tag.stdout}")


def _target_arch(platform: str) -> str:
    return platform.split("/")[-1].strip()


def _remote_image_digest(
    image_ref: str,
    account: str,
    host: str,
    key_file: Path,
) -> str | None:
    result = subprocess.run(
        [
            "ssh",
            "-i",
            str(key_file),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            f"{account}@{host}",
            "podman",
            "image",
            "inspect",
            "--format",
            "{{.Id}}",
            image_ref,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    digest = result.stdout.strip()
    return digest if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) else None


def _stream_image(image_ref: str, account: str, host: str, key_file: Path) -> str:
    save_proc = subprocess.Popen(
        ["docker", "save", image_ref],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert save_proc.stdout is not None
    load_proc = subprocess.run(
        [
            "ssh",
            "-i",
            str(key_file),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            f"{account}@{host}",
            "podman load",
        ],
        stdin=save_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    save_proc.stdout.close()
    save_stderr = save_proc.stderr.read().decode("utf-8", errors="replace") if save_proc.stderr else ""
    save_rc = save_proc.wait()
    if save_rc != 0:
        raise SystemExit(f"FAIL: docker save failed for {image_ref}: {save_stderr.strip()}")
    if load_proc.returncode != 0:
        raise SystemExit(
            "FAIL: remote podman load failed for "
            f"{image_ref}: {(load_proc.stderr or '').strip()}"
        )
    remote_digest = _remote_image_digest(image_ref, account, host, key_file)
    if remote_digest is None:
        raise SystemExit(
            f"FAIL: remote image content digest unavailable after load: {image_ref}"
        )
    return remote_digest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load local Docker service images into a prod plane rootless Podman store.",
    )
    parser.add_argument("--plane", default="service")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--key-dir", type=Path, default=DEFAULT_KEY_DIR)
    parser.add_argument("--services", default="")
    parser.add_argument("--platform", default="linux/amd64")
    parser.add_argument(
        "--image-version",
        default=os.environ.get("IMAGE_VERSION", ""),
    )
    parser.add_argument(
        "--release-manifest",
        type=Path,
        default=Path(os.environ["RELEASE_MANIFEST"]) if os.environ.get("RELEASE_MANIFEST") else None,
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plane = _plane_spec(args.plane)
    requested = [item.strip() for item in args.services.split(",") if item.strip()]
    governed = list(plane.governed_services)
    if requested:
        governed = [item for item in governed if item in requested]
    if not governed:
        raise SystemExit("FAIL: no governed services selected")
    key_file = args.key_dir / plane.account
    if not key_file.is_file():
        raise SystemExit(f"FAIL: missing key file: {key_file}")
    image_refs = _compose_image_refs(
        governed,
        image_version=args.image_version,
    )
    manifest_digest = ""
    source_refs: dict[str, str] = {}
    if args.release_manifest is not None:
        manifest_digest, source_refs = _release_image_sources(
            args.release_manifest,
            services=governed,
            image_version=args.image_version,
        )
    elif not args.dry_run:
        raise SystemExit("FAIL: --release-manifest is required for production image delivery")
    if not args.dry_run:
        for service, source_ref in source_refs.items():
            target_ref = image_refs.get(service)
            if not target_ref:
                raise SystemExit(f"FAIL: rendered image target missing for {service}")
            _pull_and_tag_release_image(source_ref, target_ref)
    target_arch = _target_arch(args.platform)
    rebuild_services: list[str] = []
    missing: list[str] = []
    arch_mismatch: dict[str, str] = {}
    for service, ref in image_refs.items():
        arch = _local_image_architecture(ref)
        if arch is None:
            missing.append(ref)
            rebuild_services.append(service)
            continue
        if arch != target_arch:
            arch_mismatch[service] = arch
            rebuild_services.append(service)
    local_digests = {
        service: _local_image_digest(ref)
        for service, ref in image_refs.items()
        if service in governed
    }
    report: dict[str, Any] = {
        "plane": plane.plane,
        "account": plane.account,
        "host": args.host,
        "keyFile": str(key_file),
        "services": governed,
        "images": image_refs,
        "sourceImages": source_refs,
        "releaseManifestDigest": manifest_digest,
        "imageContentDigests": local_digests,
        "platform": args.platform,
        "rebuildServices": rebuild_services,
        "missingImages": missing,
        "archMismatch": arch_mismatch,
        "dryRun": bool(args.dry_run),
    }
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False))
        return 0
    if missing:
        raise SystemExit("FAIL: local docker images missing: " + ", ".join(missing))
    if arch_mismatch:
        detail = ", ".join(f"{service}={arch}" for service, arch in sorted(arch_mismatch.items()))
        raise SystemExit(
            f"FAIL: local docker images are not {target_arch}: {detail}; "
            "release images must be rebuilt by Service Pipeline for linux/amd64"
        )
    for service in governed:
        image_ref = image_refs.get(service)
        if not image_ref:
            continue
        local_digest = local_digests.get(service)
        if local_digest is None:
            raise SystemExit(
                f"FAIL: local image content digest unavailable: {image_ref}"
            )
        remote_digest = _stream_image(
            image_ref,
            plane.account,
            args.host,
            key_file,
        )
        if remote_digest != local_digest:
            raise SystemExit(
                "FAIL: remote image digest mismatch for "
                f"{service}: {remote_digest} != {local_digest}"
            )
    report["remoteImageContentDigests"] = {
        service: _remote_image_digest(ref, plane.account, args.host, key_file)
        for service, ref in image_refs.items()
        if service in governed
    }
    report["contentDigestVerified"] = all(
        local_digests.get(service) == report["remoteImageContentDigests"].get(service)
        for service in governed
        if service in image_refs
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
