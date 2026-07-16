#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

SERVICE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SERVICE_ROOT.parent
SERVICES_ROOT = SERVICE_ROOT / "services"
PROFILE_PATH = SERVICE_ROOT / "service_asset_profiles.json"
OPS_ENV = REPO_ROOT / "quwoquan_ops/environments"

SOURCE_PROFILES = {
    "go-domain-source",
    "go-control-plane-source",
    "python-domain-source",
}
ALL_PROFILES = SOURCE_PROFILES | {
    "deployment-package",
    "external-workload",
    "static-artifact",
}


def fail(message: str) -> None:
    raise SystemExit(f"[verify] FAIL: {message}")


def rel(path: Path) -> str:
    return path.relative_to(SERVICE_ROOT.parent).as_posix()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"JSON root must be object: {rel(path)}")
    return value


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"YAML root must be object: {rel(path)}")
    return value


def verify_profiles() -> dict[str, dict]:
    if not PROFILE_PATH.is_file():
        fail(f"missing service asset profile registry: {rel(PROFILE_PATH)}")
    registry = load_json(PROFILE_PATH)
    if registry.get("schemaVersion") != 1:
        fail("service_asset_profiles.json schemaVersion must be 1")
    if set(registry.get("profiles", [])) != ALL_PROFILES:
        fail("service asset profile closed set drifted")
    assets = registry.get("assets")
    if not isinstance(assets, list):
        fail("service asset registry assets must be an array")
    by_id: dict[str, dict] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            fail("service asset entry must be object")
        asset_id = str(asset.get("id", "")).strip()
        profile = str(asset.get("profile", "")).strip()
        if not asset_id or asset_id in by_id:
            fail(f"duplicate/empty service asset id: {asset_id!r}")
        if profile not in ALL_PROFILES:
            fail(f"{asset_id}: unknown profile {profile!r}")
        by_id[asset_id] = asset

    disk_ids = {
        path.name for path in SERVICES_ROOT.iterdir() if path.is_dir()
    }
    if set(by_id) != disk_ids:
        fail(
            "service asset registry/disk mismatch: "
            f"missing={sorted(disk_ids - set(by_id))} "
            f"stale={sorted(set(by_id) - disk_ids)}"
        )

    for asset_id, asset in sorted(by_id.items()):
        root = SERVICES_ROOT / asset_id
        profile = asset["profile"]
        if profile in {"go-domain-source", "go-control-plane-source"}:
            verify_go_source(root, asset)
        elif profile == "python-domain-source":
            verify_python_source(root, asset)
        elif profile == "deployment-package":
            verify_deployment_package(root, asset, by_id)
        elif profile == "external-workload":
            verify_external_workload(root, asset)
        elif profile == "static-artifact":
            manifest = root / str(asset.get("sourceManifest", ""))
            if not manifest.is_file():
                fail(f"{asset_id}: static source manifest missing: {rel(manifest)}")
    return by_id


def verify_go_source(root: Path, asset: dict) -> None:
    if (root / "go.mod").exists():
        fail(f"nested Go module is forbidden: {rel(root / 'go.mod')}")
    if asset["profile"] == "go-domain-source" and not (root / "internal").is_dir():
        fail(f"{asset['id']}: Go source missing internal/")
    if (
        asset["profile"] == "go-control-plane-source"
        and not (root / "internal").is_dir()
        and asset.get("prodEligible") is not False
    ):
        fail(
            f"{asset['id']}: non-canonical control-plane source must remain "
            "prod-ineligible until moved under internal/"
        )
    if not (root / "tests").is_dir():
        fail(f"{asset['id']}: Go source missing tests/")
    verify_entrypoints(root, asset)
    verify_env_configs(root, asset["id"])


def verify_python_source(root: Path, asset: dict) -> None:
    verify_entrypoints(root, asset)
    if not (root / "tests/local_contract").is_dir():
        fail(f"{asset['id']}: Python source missing tests/local_contract")
    if not (root / "tests/api_integration").is_dir():
        fail(f"{asset['id']}: Python source missing tests/api_integration")
    if not (root / "requirements.txt").is_file():
        fail(f"{asset['id']}: Python source missing requirements.txt")


def verify_entrypoints(root: Path, asset: dict) -> None:
    entrypoints = asset.get("entrypoints")
    if not isinstance(entrypoints, list) or not entrypoints:
        fail(f"{asset['id']}: source profile must declare entrypoints")
    for entrypoint in entrypoints:
        path = root / str(entrypoint)
        if not path.is_file():
            fail(f"{asset['id']}: entrypoint missing: {rel(path)}")


def verify_env_configs(root: Path, asset_id: str) -> None:
    for env in ("default", "alpha", "beta", "gamma", "prod"):
        path = root / "configs" / env / "config.yaml"
        if not path.is_file():
            fail(f"{asset_id}: missing environment config {rel(path)}")


def verify_deployment_package(
    root: Path,
    asset: dict,
    by_id: dict[str, dict],
) -> None:
    source_assets = asset.get("sourceAssets")
    if not isinstance(source_assets, list):
        fail(f"{asset['id']}: deployment-package sourceAssets must be array")
    for source_id in source_assets:
        source = by_id.get(str(source_id))
        if source is None or source.get("profile") not in SOURCE_PROFILES:
            fail(f"{asset['id']}: unknown/non-source asset {source_id!r}")
    if asset.get("prodEligible") and not source_assets:
        fail(f"{asset['id']}: prod deployment package has no source provenance")
    dockerfile_value = asset.get("dockerfile")
    if dockerfile_value:
        dockerfile = (root / str(dockerfile_value)).resolve()
        if not dockerfile.is_file():
            fail(f"{asset['id']}: Dockerfile missing: {dockerfile}")


def verify_external_workload(root: Path, asset: dict) -> None:
    capabilities = asset.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        fail(f"{asset['id']}: external workload missing capabilities")
    image = str(asset.get("image", ""))
    if not re.fullmatch(r"[^@\s]+@sha256:[a-f0-9]{64}", image):
        fail(f"{asset['id']}: external image must be pinned by sha256 digest")
    deployment = root / str(asset.get("deployment", ""))
    if not deployment.is_file():
        fail(f"{asset['id']}: external deployment missing")
    deployment_text = deployment.read_text(encoding="utf-8")
    if f"image: {image}" not in deployment_text:
        fail(f"{asset['id']}: deployment image differs from profile digest")


def verify_tracked_artifacts() -> None:
    result = subprocess.run(
        ["git", "ls-files", "-z", "quwoquan_service/services"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    binary_magic = (
        b"\x7fELF",
        b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe",
        b"MZ",
    )
    forbidden_names = {".coverage", "coverage.out"}
    violations: list[str] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        path = REPO_ROOT / raw.decode("utf-8")
        if path.name in forbidden_names or path.suffix == ".test":
            violations.append(f"tracked test/coverage artifact: {rel(path)}")
            continue
        try:
            prefix = path.read_bytes()[:4]
        except FileNotFoundError:
            continue
        if any(prefix.startswith(magic) for magic in binary_magic):
            violations.append(f"tracked executable binary: {rel(path)}")

    for asset_dir in SERVICES_ROOT.iterdir():
        if not asset_dir.is_dir():
            continue
        root_api = asset_dir / "api"
        if root_api.is_file():
            violations.append(
                f"service-root build output is forbidden: {rel(root_api)}"
            )
    if violations:
        fail("; ".join(violations))


def verify_source_build_workload_closure(assets: dict[str, dict]) -> None:
    process_mapping = load_yaml(OPS_ENV / "process_domain_mapping.yaml")
    module_mapping = load_yaml(OPS_ENV / "module_package_mapping.yaml")
    inventory = load_yaml(OPS_ENV / "workload_topology_inventory.yaml")
    prod_processes = process_mapping["environments"]["prod"]
    prod_modules = module_mapping["environments"]["prod"]
    workloads = {
        item["name"]: item for item in inventory.get("workloads", [])
    }
    external = {
        item["name"]: item
        for item in inventory.get("external_workloads", [])
    }
    if set(prod_processes) != set(prod_modules) or set(prod_processes) != set(
        workloads
    ):
        fail("prod process/module/workload name closure drifted")
    for name, process in prod_processes.items():
        domains = set(process.get("domains", []))
        if domains != set(prod_modules[name].get("domains", [])):
            fail(f"{name}: process/module domains differ")
        if domains != set(workloads[name].get("domains", [])):
            fail(f"{name}: process/workload domains differ")
        asset = assets.get(name)
        if asset is None:
            fail(f"{name}: workload has no service asset profile")
        if (
            workloads[name].get("wired_to_prod_root")
            and asset.get("prodEligible") is False
        ):
            fail(f"{name}: prod-ineligible asset is wired to prod")

    process_domains = {
        domain
        for process in prod_processes.values()
        for domain in process.get("domains", [])
    }
    for name, workload in external.items():
        if workload.get("domains"):
            fail(f"{name}: external capability must not declare domains")
        if name in prod_processes:
            fail(f"{name}: external capability leaked into process mapping")
        asset = assets.get(name)
        if asset is None or asset.get("profile") != "external-workload":
            fail(f"{name}: external workload profile mismatch")
        if process_domains.intersection(workload.get("capabilities", [])):
            fail(f"{name}: capability collides with business domain")


def verify_seed_box_closure() -> None:
    process_mapping = load_yaml(OPS_ENV / "process_domain_mapping.yaml")
    module_mapping = load_yaml(OPS_ENV / "module_package_mapping.yaml")
    inventory = load_yaml(OPS_ENV / "workload_topology_inventory.yaml")
    expected_domains = set(
        process_mapping["environments"]["prod"]["seed-box"]["domains"]
    )
    module_domains = set(
        module_mapping["environments"]["prod"]["seed-box"]["domains"]
    )
    workload = next(
        item
        for item in inventory["workloads"]
        if item["name"] == "seed-box"
    )
    workload_domains = set(workload["domains"])
    expected_services = {f"{domain}-service" for domain in expected_domains}

    dockerfile = (
        SERVICES_ROOT / "seed-box/deploy/Dockerfile"
    ).read_text(encoding="utf-8")
    built = set(
        re.findall(r"-o /out/bin/([a-z0-9-]+) \./services/", dockerfile)
    )
    config_copies = set(
        re.findall(
            r"COPY quwoquan_service/services/([a-z0-9-]+)/configs/",
            dockerfile,
        )
    )
    entrypoint = (
        SERVICES_ROOT / "seed-box/deploy/seed_box_entrypoint.py"
    ).read_text(encoding="utf-8")
    service_specs = entrypoint.split("SERVICE_SPECS = [", 1)[1].split(
        "\n]\n",
        1,
    )[0]
    launched = set(re.findall(r'name="([a-z0-9-]+)"', service_specs))
    sets = {
        "process domains": expected_domains,
        "module domains": module_domains,
        "workload domains": workload_domains,
        "Docker binaries": {value.removesuffix("-service") for value in built},
        "Docker configs": {
            value.removesuffix("-service") for value in config_copies
        },
        "SERVICE_SPECS": {
            value.removesuffix("-service") for value in launched
        },
    }
    for label, values in sets.items():
        if values != expected_domains:
            fail(
                f"seed-box {label} closure drifted: "
                f"missing={sorted(expected_domains - values)} "
                f"extra={sorted(values - expected_domains)}"
            )
    if built != expected_services:
        fail("seed-box binary names do not match domain service names")


def main() -> None:
    forbidden_root_dirs = {
        "cmd",
        "infrastructure",
        "platform",
        "specs",
        ".cursor",
        ".control-plane-state",
        ".pytest_cache",
    }
    forbidden_root_files = {
        "architecture_review.md",
        "design.md",
        "proposal.md",
        "tasks.md",
        "工程目录设计.md",
        "技术选型.md",
        "端云协同落地方案.md",
        "codegen_app_metadata",
        "codegen_chat_service",
        "codegen_content_service",
        "codegen_rec_model_python",
        "codegen_storage",
        "import",
        "seed",
        "verify_metadata",
        "Dockerfile",
    }
    forbidden_script_dirs = {
        "deploy",
        "gamma",
        "ml",
        "seed",
    }
    forbidden_generated_dirs = {
        ".control-plane-state",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        ".qwq_output",
        ".cursor",
        "state",
    }

    for name in sorted(forbidden_root_dirs):
        path = SERVICE_ROOT / name
        if path.exists():
            fail(f"forbidden service root directory exists: {rel(path)}")

    for name in sorted(forbidden_root_files):
        path = SERVICE_ROOT / name
        if path.exists():
            fail(f"forbidden service root file exists: {rel(path)}")

    for path in sorted(SERVICE_ROOT.glob("docker-compose*.y*ml")):
        fail(f"cross-service compose belongs in quwoquan_ops/environments/compose: {rel(path)}")

    scripts_root = SERVICE_ROOT / "scripts"
    for name in sorted(forbidden_script_dirs):
        path = scripts_root / name
        if path.exists():
            fail(f"script directory must move to domain owner or ops: {rel(path)}")

    for path in SERVICE_ROOT.rglob("*"):
        if not path.is_dir():
            continue
        if path.name in forbidden_generated_dirs:
            fail(f"local state/cache/output directory must not live in service tree: {rel(path)}")

    for service_dir in sorted(p for p in SERVICES_ROOT.iterdir() if p.is_dir()):
        root_dockerfile = service_dir / "Dockerfile"
        if root_dockerfile.exists():
            fail(f"service Dockerfile must live under deploy/: {rel(root_dockerfile)}")
        for compose_file in sorted(service_dir.glob("docker-compose*.y*ml")):
            fail(f"service compose must live under deploy/ if service-owned: {rel(compose_file)}")

    assets = verify_profiles()
    verify_tracked_artifacts()
    verify_source_build_workload_closure(assets)
    verify_seed_box_closure()

    print(
        "[verify] OK: quwoquan_service layout/assets/source-build-workload "
        "closure is normalized"
    )


if __name__ == "__main__":
    main()
