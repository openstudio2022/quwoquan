from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.prod.registry_transport import run_with_bounded_retry
from quwoquan_ops.cli.lib.prod_management_access import prod_management_ssh_host

ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
DEFAULT_KEY_DIR = Path.home() / ".ssh/quwoquan-prod"
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
    candidate_digest: str,
) -> dict[str, str]:
    if OCI_DIGEST_PATTERN.fullmatch(candidate_digest) is None:
        raise SystemExit("FAIL: exact candidate digest required for production images")
    local_tag = candidate_digest.removeprefix("sha256:")
    return {
        service: f"localhost/quwoquan_service_{service}:{local_tag}"
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


def _service_factory_image_sources(
    manifest_path: Path,
    *,
    services: list[str],
) -> tuple[str, dict[str, str]]:
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"FAIL: cannot read service factory material: {error}") from error
    canonical = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8") + b"\n"
    if not isinstance(manifest, dict) or raw != canonical:
        raise SystemExit("FAIL: service factory material must be canonical JSON bytes")
    if manifest.get("schema") != "quwoquan_ops.service_factory_material":
        raise SystemExit("FAIL: service factory material schema is invalid")
    unsigned = dict(manifest)
    material_digest = str(unsigned.pop("materialDigest", ""))
    actual_digest = "sha256:" + __import__("hashlib").sha256(
        json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    if material_digest != actual_digest:
        raise SystemExit("FAIL: service factory material digest drifted")
    images = manifest.get("images")
    if not isinstance(images, list):
        raise SystemExit("FAIL: service factory material images must be an array")
    selected: dict[str, str] = {}
    for index, image in enumerate(images):
        if not isinstance(image, dict) or set(image) != {
            "trustDomain", "runtimeImageOwner", "ociRef", "digest",
            "signature", "attestations",
        }:
            raise SystemExit(f"FAIL: service factory image[{index}] shape drifted")
        if image.get("trustDomain") != "prod":
            continue
        owner = str(image.get("runtimeImageOwner") or "")
        ref = str(image.get("ociRef") or "")
        digest = str(image.get("digest") or "")
        signature = image.get("signature")
        attestations = image.get("attestations")
        if (
            owner in selected
            or OCI_DIGEST_PATTERN.fullmatch(digest) is None
            or ref.rpartition("@")[2] != digest
            or not isinstance(signature, dict)
            or set(signature) != {"issuer", "signerWorkflow", "verificationDigest"}
            or any(not str(signature.get(field) or "").strip() for field in ("issuer", "signerWorkflow"))
            or OCI_DIGEST_PATTERN.fullmatch(str(signature.get("verificationDigest") or "")) is None
            or not isinstance(attestations, dict)
            or set(attestations) != {"spdxSbom", "slsaProvenance"}
        ):
            raise SystemExit(f"FAIL: service factory image identity is invalid: {owner or index}")
        for name, attestation in attestations.items():
            if (
                not isinstance(attestation, dict)
                or set(attestation) != {"predicateType", "verificationDigest"}
                or not str(attestation.get("predicateType") or "").strip()
                or OCI_DIGEST_PATTERN.fullmatch(str(attestation.get("verificationDigest") or "")) is None
            ):
                raise SystemExit(f"FAIL: service factory image attestation is invalid: {owner}/{name}")
        selected[owner] = ref
    if set(selected) != set(services):
        missing = sorted(set(services) - set(selected))
        extra = sorted(set(selected) - set(services))
        raise SystemExit(
            f"FAIL: service factory Prod image owner closure drifted: missing={missing}, extra={extra}"
        )
    return material_digest, selected


def _pull_and_tag_release_image(
    source_ref: str,
    target_ref: str,
    *,
    platform: str,
) -> None:
    argv = ["docker", "pull", "--platform", platform, source_ref]
    pull = run_with_bounded_retry(
        lambda: subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    )
    if pull.returncode != 0:
        raise SystemExit(
            f"FAIL: docker pull failed after 3 bounded attempts for {source_ref}:\n"
            f"{pull.stdout}"
        )
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
    if re.fullmatch(r"[0-9a-f]{64}", digest):
        digest = f"sha256:{digest}"
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
    parser.add_argument("--host", default=prod_management_ssh_host())
    parser.add_argument("--key-dir", type=Path, default=DEFAULT_KEY_DIR)
    parser.add_argument("--services", default="")
    parser.add_argument(
        "--platform",
        choices=("linux/amd64",),
        default="linux/amd64",
    )
    parser.add_argument(
        "--candidate-digest",
        default=os.environ.get("CANDIDATE_DIGEST", ""),
    )
    parser.add_argument(
        "--service-factory-material",
        type=Path,
        default=(
            Path(os.environ["SERVICE_FACTORY_MATERIAL"])
            if os.environ.get("SERVICE_FACTORY_MATERIAL")
            else None
        ),
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
        candidate_digest=args.candidate_digest,
    )
    candidate_material_digest = ""
    source_refs: dict[str, str] = {}
    if args.service_factory_material is not None:
        candidate_material_digest, source_refs = _service_factory_image_sources(
            args.service_factory_material,
            services=governed,
        )
    elif not args.dry_run:
        raise SystemExit(
            "FAIL: --service-factory-material is required for production image delivery"
        )
    if not args.dry_run:
        for service, source_ref in source_refs.items():
            target_ref = image_refs.get(service)
            if not target_ref:
                raise SystemExit(f"FAIL: rendered image target missing for {service}")
            _pull_and_tag_release_image(
                source_ref,
                target_ref,
                platform=args.platform,
            )
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
        "candidateMaterialDigest": candidate_material_digest,
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
