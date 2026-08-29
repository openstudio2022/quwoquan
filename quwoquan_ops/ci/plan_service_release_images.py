#!/usr/bin/env python3
"""Build the trust-domain Service Pipeline runtime-image plan (DEC-005).

镜像字节环境无关，只按 nonprod/prod 两个信任域分叉（编译期 Provider binding
不同）；alpha/beta/gamma 复用同一 nonprod digest。构建矩阵是 2 × runtime image
owner，不再按四环境展开。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.immutable_image_composition import (
    first_party_service_names,
    runtime_image_owner_names,
)
from quwoquan_ops.cli.lib.service_core_composition import (
    SERVICE_CORE_MODULE_SET,
    SERVICE_CORE_WORKLOAD,
)


ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
TRUST_DOMAINS = ("nonprod", "prod")
NONPROD_ENVIRONMENTS = ("alpha", "beta", "gamma")
LOGICAL_SERVICES = frozenset(first_party_service_names(ROOT))
RUNTIME_IMAGE_OWNERS = runtime_image_owner_names(ROOT)
ALL_SERVICES = frozenset(RUNTIME_IMAGE_OWNERS)


def _build_definition(owner: str) -> dict[str, str]:
    if owner == SERVICE_CORE_WORKLOAD:
        context = "quwoquan_service"
        dockerfile = "quwoquan_service/cmd/service-core/Dockerfile"
    elif owner == "platform-ops-service":
        context = "."
        dockerfile = "quwoquan_service/control-plane/platform-ops/build/Dockerfile"
    else:
        context = "quwoquan_service"
        dockerfile = f"quwoquan_service/services/{owner}/build/Dockerfile"
    if not (ROOT / dockerfile).is_file():
        raise RuntimeError(f"runtime image owner has no canonical Dockerfile: {owner}")
    return {
        "service": owner,
        "runtime_image_owner": owner,
        "context": context,
        "dockerfile": dockerfile,
    }


SERVICE_BUILD_DEFINITIONS: tuple[dict[str, str], ...] = tuple(
    _build_definition(owner) for owner in RUNTIME_IMAGE_OWNERS
)

# Feature ownership maps product domains to logical services. The final image
# owner is always projected through the canonical service-core composition.
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
    "travel-journey": frozenset({"circle-service"}),
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


def _runtime_owner(logical_service: str) -> str:
    return (
        SERVICE_CORE_WORKLOAD
        if logical_service in SERVICE_CORE_MODULE_SET
        else logical_service
    )


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
    for feature, services in FEATURE_OWNERS.items():
        unknown = services - LOGICAL_SERVICES
        if unknown:
            raise ValueError(
                f"feature owner {feature} names unknown logical services: {sorted(unknown)}"
            )
        not_in_graph = services - graph_services - {"product-ops-service"}
        if not_in_graph:
            raise ValueError(
                f"feature owner {feature} is not backed by ContractGraph domains: "
                f"{sorted(not_in_graph)}"
            )


def _runtime_owners(services: set[str] | frozenset[str]) -> set[str]:
    return {_runtime_owner(service) for service in services}


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
        if direct and direct.group(1) in LOGICAL_SERVICES:
            service = direct.group(1)
            first_segment = direct.group(2).split("/", 1)[0]
            if first_segment in SERVICE_WIDE_IMPACT_SEGMENTS:
                return ALL_SERVICES, [f"service-wide-impact:{service}/{first_segment}"]
            owner = _runtime_owner(service)
            affected.add(owner)
            reasons.append(f"runtime-image-owner:{owner}")
            continue
        if path.startswith("quwoquan_service/control-plane/platform-ops/"):
            affected.add("platform-ops-service")
            reasons.append("runtime-image-owner:platform-ops-service")
            continue
        feature = re.match(r"specs/feature-tree/([^/]+)/", path)
        if feature and feature.group(1) in FEATURE_OWNERS:
            affected.update(_runtime_owners(FEATURE_OWNERS[feature.group(1)]))
            reasons.append(f"feature-owner:{feature.group(1)}")
            continue
        if path.startswith("quwoquan_service/"):
            return ALL_SERVICES, [f"unclassified-service-change:{path}"]
        if path.startswith("specs/feature-tree/"):
            return ALL_SERVICES, [f"unclassified-feature-owner:{path}"]
    return frozenset(affected), sorted(set(reasons))


def reusable_refs(path: Path | None) -> dict[tuple[str, str], str]:
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
    if DIGEST_PATTERN.fullmatch(str(payload.get("releaseTrainId") or "")) is None:
        raise ValueError("previous evidence releaseTrainId is not immutable")
    if DIGEST_PATTERN.fullmatch(str(payload.get("candidateId") or "")) is None:
        raise ValueError("previous evidence candidateId is not immutable")
    if DIGEST_PATTERN.fullmatch(str(payload.get("artifactDigest") or "")) is None:
        raise ValueError("previous evidence artifactDigest is not immutable")
    if "images" in payload:
        raise ValueError("previous evidence uses retired flat images")
    artifacts = payload.get("environmentArtifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(ENVIRONMENTS):
        raise ValueError("previous evidence environmentArtifacts are incomplete")
    # DEC-005 信任域裁决：nonprod 三环境同 owner 必须同 digest（复用同一 ref），
    # prod 独立信任域 digest 必须与 nonprod 分叉；违背任一约束的 evidence 不可复用。
    refs: dict[tuple[str, str], str] = {}
    for environment in ENVIRONMENTS:
        artifact = artifacts.get(environment)
        images = artifact.get("images") if isinstance(artifact, dict) else None
        if not isinstance(images, dict) or set(images) != ALL_SERVICES:
            raise ValueError(
                f"previous evidence runtime image owner set is incomplete: {environment}"
            )
        domain = "prod" if environment == "prod" else "nonprod"
        for owner in RUNTIME_IMAGE_OWNERS:
            descriptor = images.get(owner)
            ref = str((descriptor or {}).get("ref") or "")
            digest = str((descriptor or {}).get("digest") or "")
            if IMMUTABLE_GHCR_REF.fullmatch(ref) is None or not ref.endswith("@" + digest):
                raise ValueError(
                    f"previous evidence image is not immutable: {environment}/{owner}"
                )
            existing = refs.setdefault((domain, owner), ref)
            if existing != ref:
                raise ValueError(
                    "previous evidence nonprod environments do not share one "
                    f"image digest: {owner}"
                )
    for owner in RUNTIME_IMAGE_OWNERS:
        if refs[("prod", owner)] == refs[("nonprod", owner)]:
            raise ValueError(
                "previous evidence prod image reuses the nonprod trust-domain "
                f"digest: {owner}"
            )
    return refs


def build_plan(
    paths: list[str], previous_manifest: Path | None
) -> tuple[list[dict[str, str]], list[str]]:
    affected, reasons = affected_services(paths)
    previous = reusable_refs(previous_manifest)
    expected_previous = len(TRUST_DOMAINS) * len(RUNTIME_IMAGE_OWNERS)
    if affected != ALL_SERVICES and len(previous) != expected_previous:
        affected = ALL_SERVICES
        reasons = [*reasons, "previous-canonical-evidence-unavailable"]
    plan: list[dict[str, str]] = []
    for trust_domain in TRUST_DOMAINS:
        for definition in SERVICE_BUILD_DEFINITIONS:
            owner = definition["runtime_image_owner"]
            action = "build" if owner in affected else "reuse"
            plan.append(
                {
                    **definition,
                    "trust_domain": trust_domain,
                    "image_name": f"{owner}-{trust_domain}",
                    "action": action,
                    "source_ref": (
                        previous.get((trust_domain, owner), "")
                        if action == "reuse"
                        else ""
                    ),
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
