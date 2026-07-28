#!/usr/bin/env python3
"""Collect the six immutable whole-app release artifacts without fabricating evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any


ARTIFACT_SCHEMAS = {
    "publicWeb": "qwq.public-web.release.v1",
    "androidOfficialRelease": "qwq.android.official-release.v1",
    "opsPortal": "qwq.ops_portal_package.v1",
    "contractGraph": "qwq.contract-graph.v1",
    "providerBindings": "compiled-external-provider-bindings",
    "testEvidence": "qwq.three-layer-case-results.v1",
}

DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--descriptors-dir", required=True, type=Path)
    parser.add_argument("--public-web-manifest", required=True, type=Path)
    parser.add_argument("--android-release-manifest", required=True, type=Path)
    parser.add_argument("--ops-portal-provenance", required=True, type=Path)
    parser.add_argument("--contract-graph", required=True, type=Path)
    parser.add_argument("--provider-bindings", required=True, type=Path)
    parser.add_argument("--test-evidence", required=True, type=Path)
    return parser.parse_args()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not readable UTF-8 JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _validate_source(artifact_id: str, payload: dict[str, Any]) -> None:
    expected_schema = ARTIFACT_SCHEMAS[artifact_id]
    if artifact_id == "contractGraph":
        required = {"sources", "documents", "objects", "operations", "projections"}
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"contractGraph missing canonical collections: {missing}")
        return
    if payload.get("schema") != expected_schema:
        raise ValueError(
            f"{artifact_id} schema mismatch: {payload.get('schema')!r} != "
            f"{expected_schema!r}"
        )
    if artifact_id == "testEvidence":
        if payload.get("status") != "passed":
            raise ValueError("testEvidence status must be passed")
        layers = payload.get("layers")
        required_layers = {"local_contract", "api_integration", "user_acceptance"}
        if not isinstance(layers, dict) or set(layers) != required_layers:
            raise ValueError("testEvidence must contain exactly the three canonical layers")
        for layer in sorted(required_layers):
            item = layers.get(layer)
            if (
                not isinstance(item, dict)
                or item.get("status") != "passed"
                or DIGEST_PATTERN.fullmatch(str(item.get("artifactDigest") or "")) is None
            ):
                raise ValueError(f"testEvidence layer is not passed and immutable: {layer}")


def collect(
    *,
    artifact_dir: Path,
    descriptors_dir: Path,
    sources: dict[str, Path],
) -> dict[str, dict[str, str]]:
    artifact_dir = artifact_dir.expanduser().resolve()
    descriptors_dir = descriptors_dir.expanduser().resolve()
    if set(sources) != set(ARTIFACT_SCHEMAS):
        missing = sorted(set(ARTIFACT_SCHEMAS) - set(sources))
        extra = sorted(set(sources) - set(ARTIFACT_SCHEMAS))
        raise ValueError(f"release artifact source set mismatch: missing={missing}, extra={extra}")
    manifest = _load_json(artifact_dir / "manifest.json", "service component manifest")
    if (
        manifest.get("schema") != "mainline-release-artifact"
        or manifest.get("status") != "component-ready"
    ):
        raise ValueError("service component manifest must be component-ready")

    content_dir = artifact_dir / "artifacts"
    content_dir.mkdir(parents=True, exist_ok=True)
    descriptors_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, dict[str, str]] = {}
    for artifact_id in ARTIFACT_SCHEMAS:
        source = sources[artifact_id].expanduser().resolve()
        payload = _load_json(source, artifact_id)
        _validate_source(artifact_id, payload)
        destination = content_dir / f"{artifact_id}.json"
        if destination.exists():
            if destination.read_bytes() != source.read_bytes():
                raise ValueError(f"immutable release artifact already differs: {artifact_id}")
        else:
            shutil.copyfile(source, destination)
        relative = destination.relative_to(artifact_dir).as_posix()
        descriptor = {
            "artifactId": artifact_id,
            "schema": ARTIFACT_SCHEMAS[artifact_id],
            "path": relative,
            "sha256": _sha256(destination),
        }
        descriptor_path = descriptors_dir / f"{artifact_id}.json"
        encoded = (
            json.dumps(descriptor, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if descriptor_path.exists() and descriptor_path.read_bytes() != encoded:
            raise ValueError(f"immutable release descriptor already differs: {artifact_id}")
        descriptor_path.write_bytes(encoded)
        result[artifact_id] = descriptor
    return result


def main() -> int:
    args = parse_args()
    try:
        result = collect(
            artifact_dir=args.artifact_dir,
            descriptors_dir=args.descriptors_dir,
            sources={
                "publicWeb": args.public_web_manifest,
                "androidOfficialRelease": args.android_release_manifest,
                "opsPortal": args.ops_portal_provenance,
                "contractGraph": args.contract_graph,
                "providerBindings": args.provider_bindings,
                "testEvidence": args.test_evidence,
            },
        )
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}")
        return 2
    print(json.dumps({"artifacts": result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
