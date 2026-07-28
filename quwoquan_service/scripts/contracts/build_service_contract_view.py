#!/usr/bin/env python3
"""Build the disposable compiler view for service-owned contracts.

The repository truth lives under services/*/contracts (and control-plane
contracts). Existing compilers consume a domain/context/object tree, so this
script projects the service-owned truth into .qwq_output without creating a
second tracked metadata tree.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

import yaml


ENV_OUTPUT_PARTS = (".qwq_output", "env", "repo", "local")


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_domain(path: Path) -> str:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected mapping")
    domain = str(payload.get("domain") or "").strip()
    if not domain or "/" in domain or domain.startswith("_"):
        raise ValueError(f"{path}: invalid domain {domain!r}")
    if set(payload) != {"domain"}:
        raise ValueError(f"{path}: only the path-derived domain selector is allowed")
    return domain


def safe_output(root: Path, requested: Path) -> Path:
    output = requested.resolve()
    allowed = root.joinpath(*ENV_OUTPUT_PARTS).resolve()
    if output == allowed or allowed not in output.parents:
        raise ValueError(f"output must be below {allowed}")
    relative = output.relative_to(allowed)
    if len(relative.parts) < 3 or relative.parts[1] != "cache":
        raise ValueError(
            "output must use local/<target>/cache/<run>: "
            f"{output}"
        )
    return output


def link_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(source.resolve())


def link_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in sorted(source.iterdir()):
        destination = target / child.name
        if child.is_dir():
            link_tree(child, destination)
        else:
            link_file(child, destination)


def contract_roots(root: Path) -> list[Path]:
    candidates = sorted((root / "quwoquan_service/services").glob("*/contracts"))
    candidates.extend(
        sorted((root / "quwoquan_service/control-plane").glob("*/contracts"))
    )
    return [path for path in candidates if (path / "domain.yaml").is_file()]


def build_config_views(root: Path, output: Path, contracts_roots: list[Path]) -> None:
    """聚合服务自治 schema，供尚未改造完成的编译器读取派生视图。"""
    schema_paths = [contracts.parent / "config/schema.yaml" for contracts in contracts_roots]
    schema_paths.extend(
        [
            root / "quwoquan_service/runtime/config/schema.yaml",
            root / "quwoquan_app/config/schema.yaml",
        ]
    )
    definitions: dict[str, tuple[dict, Path]] = {}
    for schema_path in schema_paths:
        if not schema_path.is_file():
            raise ValueError(f"missing autonomous config schema: {schema_path}")
        payload = yaml.safe_load(schema_path.read_text(encoding="utf-8")) or {}
        entries = payload.get("configs", []) or []
        if not isinstance(entries, list):
            raise ValueError(f"{schema_path}: configs must be a list")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("key"), str):
                raise ValueError(f"{schema_path}: invalid config definition")
            key = entry["key"]
            if key in definitions:
                raise ValueError(
                    f"config key {key} has multiple owners: "
                    f"{definitions[key][1]} and {schema_path}"
                )
            definitions[key] = (entry, schema_path)

    platform = [entry for key, (entry, _) in sorted(definitions.items()) if key.startswith("sys.")]
    product = [entry for key, (entry, _) in sorted(definitions.items()) if key.startswith("ops.")]
    unknown = sorted(key for key in definitions if not key.startswith(("sys.", "ops.")))
    if unknown:
        raise ValueError(f"config keys must start with sys. or ops.: {unknown}")
    for target, description, entries in (
        (
            output / "platform/config.yaml",
            "由服务自治 config/schema.yaml 生成的 sys.* 编译视图；不可编辑。",
            platform,
        ),
        (
            output / "_control_plane/product/config.yaml",
            "由服务自治 config/schema.yaml 生成的 ops.* 编译视图；不可编辑。",
            product,
        ),
    ):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            yaml.safe_dump(
                {"description": description, "configs": entries},
                allow_unicode=True,
                sort_keys=False,
                width=120,
            ),
            encoding="utf-8",
        )


def build(root: Path, output: Path) -> Path:
    output = safe_output(root, output)
    if output.exists() or output.is_symlink():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    foundation = root / "quwoquan_service/contracts/metadata"
    for name in ("_schemas", "_shared", "_control_plane", "_vectors", "platform"):
        source = foundation / name
        if source.is_dir():
            link_tree(source, output / name)
    for source in sorted(foundation.glob("*.yaml")):
        link_file(source, output / source.name)

    roots = contract_roots(root)
    owners: dict[tuple[str, str], Path] = {}
    for contracts in roots:
        domain = load_domain(contracts / "domain.yaml")
        domain_output = output / domain
        domain_output.mkdir(exist_ok=True)
        for child in sorted(contracts.iterdir()):
            if child.name == "domain.yaml":
                continue
            if child.name == "_shared":
                for shared_child in sorted(child.iterdir()):
                    if shared_child.is_dir():
                        # Historical domain-owned support contracts are not
                        # bounded contexts and remain direct compiler inputs.
                        link_tree(shared_child, domain_output / shared_child.name)
                    else:
                        link_file(
                            shared_child,
                            domain_output / "_shared" / shared_child.name,
                        )
                continue
            owner_key = (domain, child.name)
            if owner_key in owners:
                raise ValueError(
                    f"context {domain}.{child.name} has multiple contract owners: "
                    f"{owners[owner_key]} and {contracts}"
                )
            owners[owner_key] = contracts
            link_tree(child, domain_output / child.name)

        generated_openapi = contracts.parent / "generated" / "openapi.yaml"
        if generated_openapi.is_file():
            link_file(generated_openapi, domain_output / "openapi.yaml")

    if not owners:
        raise ValueError("no service-owned contracts found")
    build_config_views(root, output, roots)
    return output


def main() -> int:
    root = repository_root()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=root.joinpath(
            *ENV_OUTPUT_PARTS,
            "service-contract-view",
            "cache",
            "view",
        ),
    )
    args = parser.parse_args()
    try:
        print(build(root, args.output))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"[service-contract-view] FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
