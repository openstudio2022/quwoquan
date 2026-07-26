#!/usr/bin/env python3
"""Verify alpha/beta/gamma seed manifests and production seed isolation."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
METADATA = ROOT / "quwoquan_service" / "contracts" / "metadata"
SHARED = METADATA / "_shared" / "test_fixtures"
CONTRACT_GRAPH = ROOT / "quwoquan_service" / "generated" / "contract_graph.json"
MANIFESTS = {
    "alpha": SHARED / "app_alpha_seed_manifest.json",
    "beta": SHARED / "app_beta_seed_manifest.json",
    "gamma": SHARED / "app_gamma_seed_manifest.json",
}
PROD_FORBIDDEN = ("test_fixtures", "seedRefs", "requiresSeedReset", "APP_DATA_SOURCE=mock")
ENTITY_HOMEPAGE_TARGET = "mongodb:quwoquan_entity.homepages"


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing file: {path.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        fail(f"invalid json {path.relative_to(ROOT)}: {exc}")
    raise AssertionError("unreachable")


def fail(message: str) -> None:
    print(f"[verify] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def resolve_fixture_path(raw: str) -> Path:
    fixture_ref = Path(raw)
    if fixture_ref.is_absolute() or ".." in fixture_ref.parts:
        fail(f"fixturePath must be a safe repository or metadata relative path: {raw}")
    base = ROOT if fixture_ref.parts and fixture_ref.parts[0].startswith("quwoquan_") else METADATA
    resolved = (base / fixture_ref).resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        fail(f"fixturePath escapes repository: {raw}")
    return resolved


def matches_path_template(path: str, template: str) -> bool:
    path_parts = path.strip("/").split("/")
    template_parts = template.strip("/").split("/")
    return len(path_parts) == len(template_parts) and all(
        template_part.startswith("{") and template_part.endswith("}")
        or template_part == path_part
        for path_part, template_part in zip(path_parts, template_parts)
    )


def verify_content_endpoints_use_contract_paths(manifest: dict, manifest_path: Path) -> None:
    graph = load_json(CONTRACT_GRAPH)
    content_templates = [
        str(operation.get("pathTemplate") or "").strip()
        for operation in graph.get("operations", [])
        if operation.get("domain") == "content"
    ]
    for item in manifest.get("seedRefs", []):
        if item.get("domain") != "content":
            continue
        for raw_path in item.get("verifiedEndpoints", []):
            endpoint = str(raw_path).split("?", 1)[0].strip()
            if not endpoint or not any(
                matches_path_template(endpoint, template)
                for template in content_templates
            ):
                fail(
                    f"{rel(manifest_path)} content verifiedEndpoint is not a "
                    f"canonical ContractGraph path: {raw_path}"
                )


def verify_manifest(env: str, path: Path) -> None:
    manifest = load_json(path)
    if manifest.get("schema") != "app-seed-manifest":
        fail(f"{rel(path)} schema must be app-seed-manifest")
    if manifest.get("environment") != env:
        fail(f"{rel(path)} environment must be {env}")

    seen_domains: set[str] = set()
    domain_items: dict[str, dict] = {}
    for item in manifest.get("seedRefs", []):
        domain = str(item.get("domain", "")).strip()
        fixture_rel = str(item.get("fixturePath", "")).strip()
        refs = [str(ref) for ref in item.get("refs", [])]
        if not domain or not fixture_rel or not refs:
            fail(f"{rel(path)} has incomplete seedRefs item: {item}")
        if domain in seen_domains:
            fail(f"{rel(path)} duplicates domain seed entry: {domain}")
        seen_domains.add(domain)
        domain_items[domain] = item

        fixture_path = resolve_fixture_path(fixture_rel)
        fixture = load_json(fixture_path)
        seed_sets = fixture.get("seedSets", {})
        scenarios = fixture.get("scenarios", [])
        repo_expectations = fixture.get("repositoryExpectations", {})
        if repo_expectations.get("alpha") != "mock" or repo_expectations.get("beta") != "remote" or repo_expectations.get("gamma") != "remote":
            fail(f"{rel(fixture_path)} repositoryExpectations must be alpha=mock beta/gamma=remote")
        if env == "alpha":
            delivery_channels = item.get("deliveryChannels")
            if not isinstance(delivery_channels, list) or len(delivery_channels) < 2:
                fail(f"{rel(path)} alpha domain {domain} must declare dual deliveryChannels")
        for ref in refs:
            if ref not in seed_sets:
                fail(f"{rel(path)} references missing seedRef {ref} in {rel(fixture_path)}")
        for scenario in scenarios:
            envs = scenario.get("environments", {})
            for required_env, expected_repo in (("alpha", "mock"), ("beta", "remote"), ("gamma", "remote")):
                env_spec = envs.get(required_env, {})
                if env_spec.get("repository") != expected_repo:
                    fail(f"{rel(fixture_path)} scenario {scenario.get('id')} has invalid {required_env} repository")

    verify_content_endpoints_use_contract_paths(manifest, path)

    if env in ("beta", "gamma") and manifest.get("appAssets", {}).get("alphaOnlyFixtureAllowlist"):
        fail(f"{rel(path)} must not carry alphaOnlyFixtureAllowlist for {env}")
    if env in ("beta", "gamma"):
        entity = domain_items.get("entity")
        if entity is None:
            fail(f"{rel(path)} must declare entity seed delivery")
        if entity.get("targetStore") != ENTITY_HOMEPAGE_TARGET:
            fail(
                f"{rel(path)} entity targetStore must be "
                f"{ENTITY_HOMEPAGE_TARGET}"
            )
        seed_channel = str(entity.get("seedChannel", ""))
        if "homepage-import" not in seed_channel:
            fail(
                f"{rel(path)} entity seedChannel must use canonical "
                "homepage-import"
            )
        if "homepage_state" in str(entity.get("resetScope", "")):
            fail(f"{rel(path)} must not reference retired homepage_state")

    print(f"[verify] OK: {rel(path)}")


def verify_prod_isolation() -> None:
    candidate_roots = [
        ROOT / "quwoquan_app" / "configs" / "prod",
        ROOT / "quwoquan_app" / "configs" / "default",
    ]
    candidate_files: list[Path] = []
    for root in candidate_roots:
        if root.exists():
            candidate_files.extend([p for p in root.rglob("*") if p.is_file()])
    for service_cfg in (ROOT / "quwoquan_service" / "services").glob("*/environments/prod/config.yaml"):
        candidate_files.append(service_cfg)
    for path in candidate_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in PROD_FORBIDDEN:
            if token in text:
                fail(f"production config must not contain {token}: {rel(path)}")
    print(f"[verify] OK: production seed isolation checked ({len(candidate_files)} files)")


def main() -> int:
    for env, path in MANIFESTS.items():
        verify_manifest(env, path)
    verify_prod_isolation()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
