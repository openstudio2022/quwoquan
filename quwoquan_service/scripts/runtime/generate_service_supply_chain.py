#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from service_image_build_input import service_image_build_inputs


ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = ROOT / "quwoquan_service" / "services"
MODULE_ROOT = ROOT / "quwoquan_service"


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _source_files(service: str) -> list[Path]:
    service_dir = SERVICE_ROOT / service
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            str(service_dir.relative_to(ROOT)),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"FAIL: cannot enumerate source files for {service}")
    files = [
        ROOT / item
        for item in result.stdout.splitlines()
        if item and (ROOT / item).is_file()
    ]
    files.extend([MODULE_ROOT / "go.mod", MODULE_ROOT / "go.sum"])
    return sorted(set(files), key=lambda path: str(path.relative_to(ROOT)))


def _source_digest(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        relative = str(path.relative_to(ROOT)).encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def _git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    revision = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise SystemExit("FAIL: cannot resolve git revision")
    return revision


def _dirty_paths(service: str) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            str((SERVICE_ROOT / service).relative_to(ROOT)),
            str((MODULE_ROOT / "go.mod").relative_to(ROOT)),
            str((MODULE_ROOT / "go.sum").relative_to(ROOT)),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"FAIL: cannot inspect source status for {service}")
    return [line[3:] for line in result.stdout.splitlines() if len(line) > 3]


def _go_modules() -> list[dict[str, Any]]:
    result = subprocess.run(
        ["go", "list", "-m", "-json", "all"],
        cwd=MODULE_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"FAIL: go module inventory failed: {result.stderr.strip()}")
    decoder = json.JSONDecoder()
    cursor = 0
    modules: list[dict[str, Any]] = []
    while cursor < len(result.stdout):
        while cursor < len(result.stdout) and result.stdout[cursor].isspace():
            cursor += 1
        if cursor >= len(result.stdout):
            break
        item, cursor = decoder.raw_decode(result.stdout, cursor)
        if isinstance(item, dict):
            modules.append(item)
    return modules


def _spdx_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9.-]+", "-", value).strip("-")
    return f"SPDXRef-{normalized or 'package'}"


def _build_sbom(
    *,
    service: str,
    revision: str,
    source_digest: str,
    modules: list[dict[str, Any]],
) -> dict[str, Any]:
    root_id = _spdx_id(service)
    packages: list[dict[str, Any]] = [
        {
            "name": service,
            "SPDXID": root_id,
            "versionInfo": revision,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "NOASSERTION",
            "copyrightText": "NOASSERTION",
            "checksums": [
                {
                    "algorithm": "SHA256",
                    "checksumValue": source_digest.removeprefix("sha256:"),
                }
            ],
        }
    ]
    relationships: list[dict[str, str]] = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": root_id,
        }
    ]
    for index, module in enumerate(modules):
        path = str(module.get("Path") or "").strip()
        if not path or path == "quwoquan_service":
            continue
        version = str(module.get("Version") or "devel")
        package_id = f"{_spdx_id(path)}-{index}"
        packages.append(
            {
                "name": path,
                "SPDXID": package_id,
                "versionInfo": version,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "copyrightText": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": f"pkg:golang/{path}@{version}",
                    }
                ],
            }
        )
        relationships.append(
            {
                "spdxElementId": root_id,
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": package_id,
            }
        )
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{service}-source-sbom",
        "documentNamespace": (
            f"urn:quwoquan:sbom:{service}:{source_digest.removeprefix('sha256:')}"
        ),
        "creationInfo": {
            "created": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "creators": ["Tool: quwoquan-service-supply-chain"],
        },
        "packages": packages,
        "relationships": relationships,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic service source provenance and SPDX SBOM."
    )
    parser.add_argument("--service", required=True)
    parser.add_argument("--env", required=True, choices=["alpha", "beta", "gamma", "prod"])
    parser.add_argument("--package-dir", required=True, type=Path)
    args = parser.parse_args()

    service_dir = SERVICE_ROOT / args.service
    dockerfile = service_dir / "build" / "Dockerfile"
    report_path = args.package_dir / "report.json"
    if not service_dir.is_dir() or not dockerfile.is_file():
        raise SystemExit(
            f"FAIL: source-built service or Dockerfile missing: {args.service}"
        )
    if not report_path.is_file():
        raise SystemExit(f"FAIL: package report missing: {report_path}")

    files = _source_files(args.service)
    source_digest = _source_digest(files)
    revision = _git_revision()
    dirty_paths = _dirty_paths(args.service)
    if args.env == "prod" and dirty_paths:
        raise SystemExit(
            "FAIL: prod source package requires a clean source tree: "
            + ", ".join(dirty_paths)
        )

    sbom_path = args.package_dir / "sbom.spdx.json"
    sbom = _build_sbom(
        service=args.service,
        revision=revision,
        source_digest=source_digest,
        modules=_go_modules(),
    )
    sbom_path.write_text(
        json.dumps(sbom, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    provenance = report.setdefault("provenance", {})
    image_inputs = [
        path.relative_to(ROOT).as_posix()
        for path in service_image_build_inputs(
            ROOT, f"quwoquan_service/services/{args.service}"
        )
    ]
    provenance["source"] = {
        "serviceRoot": str(service_dir.relative_to(ROOT)),
        "buildContext": "quwoquan_service",
        "dockerfile": str(dockerfile.relative_to(ROOT)),
        "dockerfileSha256": _sha256_file(dockerfile),
        "sourceTreeSha256": source_digest,
        "sourceFileCount": len(files),
        "imageBuildInputs": image_inputs,
        "gitDirty": bool(dirty_paths),
        "dirtyPaths": dirty_paths,
    }
    provenance["sbom"] = {
        "format": "SPDX-2.3",
        "path": sbom_path.name,
        "sha256": _sha256_file(sbom_path),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
