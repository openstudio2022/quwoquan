#!/usr/bin/env python3
"""Verify alpha/beta/gamma seed manifests and production seed isolation."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "quwoquan_service" / "contracts" / "metadata"
SHARED = METADATA / "_shared" / "test_fixtures"
MANIFESTS = {
    "alpha": SHARED / "app_alpha_seed_manifest.json",
    "beta": SHARED / "app_beta_seed_manifest.json",
    "gamma": SHARED / "app_gamma_seed_manifest.json",
}
PROD_FORBIDDEN = ("test_fixtures", "seedRefs", "requiresSeedReset", "APP_DATA_SOURCE=mock")


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


def verify_manifest(env: str, path: Path) -> None:
    manifest = load_json(path)
    if manifest.get("schemaVersion") != "app-seed-manifest.v1":
        fail(f"{rel(path)} schemaVersion must be app-seed-manifest.v1")
    if manifest.get("environment") != env:
        fail(f"{rel(path)} environment must be {env}")

    seen_domains: set[str] = set()
    for item in manifest.get("seedRefs", []):
        domain = str(item.get("domain", "")).strip()
        fixture_rel = str(item.get("fixturePath", "")).strip()
        refs = [str(ref) for ref in item.get("refs", [])]
        if not domain or not fixture_rel or not refs:
            fail(f"{rel(path)} has incomplete seedRefs item: {item}")
        if domain in seen_domains:
            fail(f"{rel(path)} duplicates domain seed entry: {domain}")
        seen_domains.add(domain)

        fixture_path = METADATA / fixture_rel
        fixture = load_json(fixture_path)
        seed_sets = fixture.get("seedSets", {})
        scenarios = fixture.get("scenarios", [])
        repo_expectations = fixture.get("repositoryExpectations", {})
        if repo_expectations.get("alpha") != "mock" or repo_expectations.get("beta") != "remote" or repo_expectations.get("gamma") != "remote":
            fail(f"{rel(fixture_path)} repositoryExpectations must be alpha=mock beta/gamma=remote")
        for ref in refs:
            if ref not in seed_sets:
                fail(f"{rel(path)} references missing seedRef {ref} in {rel(fixture_path)}")
        for scenario in scenarios:
            envs = scenario.get("environments", {})
            for required_env, expected_repo in (("alpha", "mock"), ("beta", "remote"), ("gamma", "remote")):
                env_spec = envs.get(required_env, {})
                if env_spec.get("repository") != expected_repo:
                    fail(f"{rel(fixture_path)} scenario {scenario.get('id')} has invalid {required_env} repository")

    if env in ("beta", "gamma") and manifest.get("appAssets", {}).get("alphaOnlyFixtureAllowlist"):
        fail(f"{rel(path)} must not carry alphaOnlyFixtureAllowlist for {env}")

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
    for service_cfg in (ROOT / "quwoquan_service" / "services").glob("*/configs/prod*/config.yaml"):
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
