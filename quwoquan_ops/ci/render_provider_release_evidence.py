#!/usr/bin/env python3
"""Bind real Prod Provider conformance to exact candidate material."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    DIGEST_PATTERN,
    validate_manifest,
)
from quwoquan_ops.ci.render_provider_conformance_source import validate_source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component-manifest", required=True, type=Path)
    parser.add_argument("--contract-graph", required=True, type=Path)
    parser.add_argument("--conformance-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _load(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def render(
    *,
    manifest: dict[str, Any],
    contract_graph_digest: str,
    conformance: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    validate_manifest(manifest, allowed_statuses={"component-ready"})
    if manifest.get("candidateId") is not None:
        raise ValueError("Provider qualification must precede candidate sealing")
    if DIGEST_PATTERN.fullmatch(contract_graph_digest) is None:
        raise ValueError("ContractGraph digest is not immutable")
    validate_source(conformance)
    evidence_count = conformance.get("evidenceCount")
    readiness = conformance.get("readiness")
    prod = readiness.get("prod") if isinstance(readiness, dict) else None
    if not isinstance(prod, dict) or not prod:
        raise ValueError("Prod Provider readiness is missing")
    malformed = sorted(
        capability
        for capability, item in prod.items()
        if not isinstance(capability, str)
        or not capability
        or not isinstance(item, dict)
        or not isinstance(item.get("required"), bool)
        or not isinstance(item.get("capability_ready"), bool)
    )
    if malformed:
        raise ValueError("Prod Provider readiness is malformed: " + ", ".join(malformed))
    required = {
        capability: item
        for capability, item in prod.items()
        if item.get("required") is True
    }
    if not required:
        raise ValueError("Prod Provider readiness has no required capability")
    blocked = sorted(
        capability
        for capability, item in required.items()
        if item.get("capability_ready") is not True
    )
    if blocked:
        raise ValueError("Prod Provider capabilities are not ready: " + ", ".join(blocked))

    images = manifest.get("images")
    if not isinstance(images, dict) or not images:
        raise ValueError("component image evidence is missing")
    image_digests = {
        service: descriptor.get("digest")
        for service, descriptor in sorted(images.items())
        if isinstance(descriptor, dict)
    }
    if len(image_digests) != len(images) or any(
        DIGEST_PATTERN.fullmatch(str(digest or "")) is None
        for digest in image_digests.values()
    ):
        raise ValueError("component image evidence is not immutable")
    source = manifest["source"]
    return {
        "schema": "provider-conformance-readiness",
        "status": "passed",
        "generatedAt": generated_at,
        "source": {
            "gitSha": source["gitSha"],
            "treeDigest": source["treeDigest"],
            "repository": source["repository"],
            "workflowRunId": source["workflowRunId"],
        },
        "candidateMaterial": {
            "images": image_digests,
            "contractGraphDigest": contract_graph_digest,
        },
        "sourceEvidence": conformance["sourceEvidence"],
        "evidenceCount": evidence_count,
        "readiness": {"prod": prod},
    }


def main() -> int:
    args = parse_args()
    try:
        payload = render(
            manifest=_load(args.component_manifest, "component manifest"),
            contract_graph_digest=_sha256(args.contract_graph),
            conformance=_load(args.conformance_report, "Provider conformance report"),
            generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"render_provider_release_evidence: FAIL: {error}")
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
