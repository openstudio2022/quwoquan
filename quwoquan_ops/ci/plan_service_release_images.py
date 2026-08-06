#!/usr/bin/env python3
"""Build the canonical Service Pipeline image plan from repository evidence.

The selector is deliberately conservative.  A service-local change rebuilds the
owning image, feature-tree changes rebuild the services owned by that L1, and a
shared build/contract/topology change expands to every image.  An unchanged
image is reusable only when a previously sealed canonical manifest supplies an
immutable GHCR digest for that exact service.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

SERVICE_BUILD_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "service": "api-edge",
        "image_name": "api-edge",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/api-edge/build/Dockerfile",
    },
    {
        "service": "recommendation-service",
        "image_name": "recommendation-service",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/recommendation-service/build/Dockerfile",
    },
    {
        "service": "content-service",
        "image_name": "content-service",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/content-service/build/Dockerfile",
    },
    {
        "service": "chat-service",
        "image_name": "chat-service",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/chat-service/build/Dockerfile",
    },
    {
        "service": "user-service",
        "image_name": "user-service",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/user-service/build/Dockerfile",
    },
    {
        "service": "assistant-service",
        "image_name": "assistant-service",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/assistant-service/build/Dockerfile",
    },
    {
        "service": "product-ops-service",
        "image_name": "product-ops-service",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/product-ops-service/build/Dockerfile",
    },
    {
        "service": "platform-ops-service",
        "image_name": "platform-ops-service",
        "context": ".",
        "dockerfile": "quwoquan_service/control-plane/platform-ops/build/Dockerfile",
    },
    {
        "service": "tag-service",
        "image_name": "tag-service",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/tag-service/build/Dockerfile",
    },
    {
        "service": "entity-service",
        "image_name": "entity-service",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/entity-service/build/Dockerfile",
    },
    {
        "service": "integration-service",
        "image_name": "integration-service",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/integration-service/build/Dockerfile",
    },
    {
        "service": "notification-service",
        "image_name": "notification-service",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/notification-service/build/Dockerfile",
    },
    {
        "service": "travel-service",
        "image_name": "travel-service",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/travel-service/build/Dockerfile",
    },
    {
        "service": "circle-service",
        "image_name": "circle-service",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/circle-service/build/Dockerfile",
    },
    {
        "service": "search-service",
        "image_name": "search-service",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/search-service/build/Dockerfile",
    },
    {
        "service": "realtime-gateway",
        "image_name": "realtime-gateway",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/realtime-gateway/build/Dockerfile",
    },
    {
        "service": "rtc-service",
        "image_name": "rtc-service",
        "context": "quwoquan_service",
        "dockerfile": "quwoquan_service/services/rtc-service/build/Dockerfile",
    },
)

ALL_SERVICES = frozenset(item["service"] for item in SERVICE_BUILD_DEFINITIONS)

# Feature-tree ownership is explicit and intentionally expands cross-domain L1s.
# ContractGraph domains are checked below so this map cannot silently name a
# retired service boundary.
FEATURE_OWNERS: dict[str, frozenset[str]] = {
    "assistant-run-learning": frozenset({"assistant-service", "user-service"}),
    "chat-conversation": frozenset(
        {"chat-service", "notification-service", "realtime-gateway", "rtc-service"}
    ),
    "circle-community": frozenset({"circle-service", "recommendation-service"}),
    "discovery-content": frozenset({"content-service", "recommendation-service"}),
    "gateway-orchestrator-foundation": frozenset(
        {"integration-service", "realtime-gateway"}
    ),
    "global-search-experience": frozenset({"search-service"}),
    "object-homepage-network": frozenset(
        {"circle-service", "content-service", "entity-service", "user-service"}
    ),
    "platform-ops-governance": frozenset({"platform-ops-service"}),
    "product-ops-growth": frozenset({"product-ops-service"}),
    "recommendation-platform": frozenset({"recommendation-service"}),
    "travel-journey": frozenset({"travel-service"}),
    "runtime": frozenset({"integration-service", "platform-ops-service"}),
    "shared-homepage-network": frozenset(
        {"circle-service", "content-service", "entity-service", "user-service"}
    ),
    "user-identity-profile-relationship": frozenset({"user-service"}),
}

SHARED_PREFIXES = (
    ".github/workflows/",
    "quwoquan_ops/",
    "quwoquan_service/contracts/metadata/",
    "quwoquan_service/generated/",
    "quwoquan_service/internal/",
    "quwoquan_service/scripts/",
    "quwoquan_service/tools/",
)
SHARED_FILES = {
    "Makefile",
    "quwoquan_service/go.mod",
    "quwoquan_service/go.sum",
    "quwoquan_service/Dockerfile",
}
SERVICE_WIDE_IMPACT_SEGMENTS = frozenset({"contracts", "environments"})
IMMUTABLE_GHCR_REF = re.compile(r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}")
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--head-sha", default="HEAD")
    parser.add_argument("--previous-manifest", type=Path)
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--github-output", default="")
    return parser.parse_args()


def git_changed_files(base_sha: str, head_sha: str) -> list[str]:
    if not base_sha.strip():
        return []
    result = subprocess.run(
        ["git", "diff", "--name-only", base_sha, head_sha],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _contract_graph_domains() -> frozenset[str]:
    path = ROOT / "quwoquan_service/generated/contract_graph.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    domains = {
        str(item.get("domain") or "").strip()
        for item in payload.get("operations", [])
        if isinstance(item, dict)
    }
    domains.discard("")
    if not domains:
        raise ValueError("ContractGraph contains no operation domains")
    return frozenset(domains)


def _validate_feature_owners() -> None:
    domains = _contract_graph_domains()
    graph_services = {
        "realtime-gateway" if domain == "realtime" else f"{domain}-service"
        for domain in domains
    }
    graph_services.discard("ops-service")
    graph_services.add("platform-ops-service")
    for owner, services in FEATURE_OWNERS.items():
        unknown = services - ALL_SERVICES
        if unknown:
            raise ValueError(f"feature owner {owner} names unknown services: {sorted(unknown)}")
        # product-ops is an orchestration service and is not a ContractGraph domain.
        not_in_graph = services - graph_services - {"product-ops-service"}
        if not_in_graph:
            raise ValueError(
                f"feature owner {owner} is not backed by ContractGraph domains: "
                f"{sorted(not_in_graph)}"
            )


def affected_services(paths: list[str]) -> tuple[frozenset[str], list[str]]:
    _validate_feature_owners()
    if not paths:
        return ALL_SERVICES, ["missing-diff-range"]
    affected: set[str] = set()
    reasons: list[str] = []
    for raw_path in paths:
        path = raw_path.removeprefix("./")
        if path in SHARED_FILES or path.startswith(SHARED_PREFIXES):
            return ALL_SERVICES, [f"shared-change:{path}"]
        direct = re.match(r"quwoquan_service/services/([^/]+)/(.*)", path)
        if direct and direct.group(1) in ALL_SERVICES:
            service = direct.group(1)
            first_segment = direct.group(2).split("/", 1)[0]
            # Contract and environment assembly changes can affect generated
            # clients, gateways and other service images. Until ContractGraph
            # exposes a complete executable consumer edge set, rebuilding all
            # images is the only fail-closed dependency closure.
            if first_segment in SERVICE_WIDE_IMPACT_SEGMENTS:
                return ALL_SERVICES, [f"service-wide-impact:{service}/{first_segment}"]
            affected.add(service)
            reasons.append(f"service-owner:{service}")
            continue
        platform = path.startswith("quwoquan_service/control-plane/platform-ops/")
        if platform:
            affected.add("platform-ops-service")
            reasons.append("service-owner:platform-ops-service")
            continue
        feature = re.match(r"specs/feature-tree/([^/]+)/", path)
        if feature and feature.group(1) in FEATURE_OWNERS:
            affected.update(FEATURE_OWNERS[feature.group(1)])
            reasons.append(f"feature-owner:{feature.group(1)}")
            continue
        if path.startswith("quwoquan_service/"):
            # A new shared/runtime/codegen location must not silently become a
            # no-build change. Narrow this only after its dependency closure is
            # represented by canonical graph evidence.
            return ALL_SERVICES, [f"unclassified-service-change:{path}"]
        if path.startswith("specs/feature-tree/"):
            return ALL_SERVICES, [f"unclassified-feature-owner:{path}"]
    return frozenset(affected), sorted(set(reasons))


def reusable_refs(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "release-evidence-manifest":
        raise ValueError("previous evidence is not canonical ReleaseEvidenceManifest")
    if payload.get("status") not in {
        "candidate-ready",
        "deployable",
        "released",
        "rolled-back",
    }:
        raise ValueError("previous evidence is not a sealed reusable candidate")
    if DIGEST_PATTERN.fullmatch(str(payload.get("candidateId") or "")) is None:
        raise ValueError("previous evidence candidateId is not an immutable digest")
    if DIGEST_PATTERN.fullmatch(str(payload.get("artifactDigest") or "")) is None:
        raise ValueError("previous evidence artifactDigest is not an immutable digest")
    images = payload.get("images")
    if not isinstance(images, dict):
        raise ValueError("previous evidence images are missing")
    refs: dict[str, str] = {}
    for service in ALL_SERVICES:
        descriptor = images.get(service)
        ref = str((descriptor or {}).get("ref") or "")
        digest = str((descriptor or {}).get("digest") or "")
        if IMMUTABLE_GHCR_REF.fullmatch(ref) is None or not ref.endswith("@" + digest):
            raise ValueError(f"previous evidence image is not immutable: {service}")
        refs[service] = ref
    return refs


def build_plan(
    paths: list[str], previous_manifest: Path | None
) -> tuple[list[dict[str, str]], list[str]]:
    affected, reasons = affected_services(paths)
    previous = reusable_refs(previous_manifest)
    # No changed service is still a valid no-build change (for example App-only),
    # but every service must have immutable prior evidence before it can be reused.
    if affected != ALL_SERVICES and len(previous) != len(ALL_SERVICES):
        affected = ALL_SERVICES
        reasons = [*reasons, "previous-canonical-evidence-unavailable"]
    plan: list[dict[str, str]] = []
    for definition in SERVICE_BUILD_DEFINITIONS:
        service = definition["service"]
        action = "build" if service in affected else "reuse"
        plan.append(
            {
                **definition,
                "action": action,
                "source_ref": previous.get(service, "") if action == "reuse" else "",
            }
        )
    return plan, sorted(set(reasons))


def _write_outputs(path: str, plan: list[dict[str, str]], reasons: list[str]) -> None:
    output = Path(path)
    build_count = sum(item["action"] == "build" for item in plan)
    lines = [
        "image_matrix=" + json.dumps({"include": plan}, separators=(",", ":")),
        f"build_count={build_count}",
        f"reuse_count={len(plan) - build_count}",
        "selection_reasons=" + json.dumps(reasons, separators=(",", ":")),
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        changed = [item for item in args.changed_file if item.strip()]
        if not changed:
            changed = git_changed_files(args.base_sha, args.head_sha)
        plan, reasons = build_plan(changed, args.previous_manifest)
        if args.github_output:
            _write_outputs(args.github_output, plan, reasons)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"plan_service_release_images: FAIL: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "matrix": {"include": plan},
                "buildCount": sum(item["action"] == "build" for item in plan),
                "reuseCount": sum(item["action"] == "reuse" for item in plan),
                "reasons": reasons,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
