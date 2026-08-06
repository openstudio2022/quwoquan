#!/usr/bin/env python3
"""阻断已退役登记文件、ContractGraph 版本信封和交接 hash 漂移。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


SERVICE = Path(__file__).resolve().parents[2]
ROOT = SERVICE.parent
METADATA = SERVICE / "contracts/metadata"
SCHEMAS = METADATA / "_schemas"
FORBIDDEN_FIELDS = {"version", "schema", "registryRevision"}
TOP_LEVEL_VERSION = re.compile(r"^(version|schemaVersion|registryRevision):", re.MULTILINE)
VERSIONED_SCHEMA_PATH = re.compile(r'["\']_schemas["\']\s*,\s*["\']v\d+["\']')
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_CONTRACT_VIEW = (
    ROOT / ".qwq_output/env/repo/local/service-contract-view/cache/view"
)


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{relative(path)} root must be an object")
    return value


def contract_graph_source_failures(
    graph: dict[str, object],
    metadata_dir: Path,
    repository_root: Path = ROOT,
) -> list[str]:
    """Bind every embedded source digest to the current compiler view.

    The graph/lock/manifest hashes can all agree with one another while all of
    them describe an older source tree.  The disposable service contract view
    is the canonical projection of service-owned contracts, so each graph
    source must still resolve there with the exact embedded digest.
    """
    failures: list[str] = []
    if not metadata_dir.is_dir():
        return [f"metadata compiler view is missing: {metadata_dir}"]
    sources = graph.get("sources")
    if not isinstance(sources, list) or not sources:
        return ["ContractGraph.sources must be a non-empty list"]

    repository = repository_root.resolve()
    seen: set[str] = set()
    for index, source in enumerate(sources):
        location = f"ContractGraph.sources[{index}]"
        if not isinstance(source, dict) or set(source) != {"path", "sha256"}:
            failures.append(f"{location} must contain exactly path/sha256")
            continue
        path_text = source.get("path")
        expected = source.get("sha256")
        if not isinstance(path_text, str) or not path_text.strip():
            failures.append(f"{location}.path must be a non-empty relative path")
            continue
        relative_path = Path(path_text)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            failures.append(f"{location}.path escapes the metadata view: {path_text!r}")
            continue
        if path_text in seen:
            failures.append(f"ContractGraph.sources contains duplicate path: {path_text}")
            continue
        seen.add(path_text)
        if not isinstance(expected, str) or not SHA256_HEX.fullmatch(expected):
            failures.append(f"{location}.sha256 is not canonical: {expected!r}")
            continue

        candidate = metadata_dir / relative_path
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(repository)
        except FileNotFoundError:
            failures.append(f"ContractGraph source is missing from current view: {path_text}")
            continue
        except (OSError, RuntimeError, ValueError) as error:
            failures.append(
                f"ContractGraph source cannot be resolved safely: {path_text}: {error}"
            )
            continue
        if not resolved.is_file():
            failures.append(f"ContractGraph source is not a file: {path_text}")
            continue
        actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
        if actual != expected:
            failures.append(
                "ContractGraph source digest drift: "
                f"{path_text}: graph={expected} current={actual}"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        default=DEFAULT_CONTRACT_VIEW,
        help="current disposable service contract compiler view",
    )
    arguments = parser.parse_args()
    failures: list[str] = []

    for path in sorted(SCHEMAS.iterdir()):
        if path.is_dir():
            failures.append(f"versioned schema directory is forbidden: {relative(path)}")

    retired_inputs = sorted(
        path
        for name in (
            "business_object_map.yaml",
            "entity_catalog.yaml",
            "event_catalog.yaml",
            "readiness.yaml",
        )
        for path in METADATA.rglob(name)
        if path != METADATA / "ops/product_ops/event_record/event_catalog.yaml"
    )
    for path in retired_inputs:
        failures.append(f"retired registration file is forbidden: {relative(path)}")
        match = TOP_LEVEL_VERSION.search(path.read_text(encoding="utf-8"))
        if match:
            failures.append(
                f"retired top-level field {match.group(1)!r}: {relative(path)}"
            )

    graph_path = SERVICE / "generated/contract_graph.json"
    lock_path = ROOT / "quwoquan_app/tool/cloud_codegen/contract_graph.lock.json"
    report_path = ROOT / "quwoquan_app/tool/cloud_codegen/contract_graph.breaking.json"
    manifest_path = ROOT / "quwoquan_app/tool/cloud_codegen/generated_manifest.json"
    artifacts = (graph_path, lock_path, report_path, manifest_path)
    loaded: dict[Path, dict[str, object]] = {}
    for path in artifacts:
        if not path.is_file():
            failures.append(f"missing single-track artifact: {relative(path)}")
            continue
        try:
            value = read_object(path)
        except (ValueError, json.JSONDecodeError) as exc:
            failures.append(str(exc))
            continue
        loaded[path] = value
        retired = sorted(FORBIDDEN_FIELDS.intersection(value))
        if retired:
            failures.append(f"{relative(path)} contains retired fields: {retired}")

    graph = loaded.get(graph_path)
    if graph is not None:
        failures.extend(
            contract_graph_source_failures(
                graph,
                arguments.metadata_dir.resolve(),
            )
        )
        maps = graph.get("businessObjectMaps")
        if not isinstance(maps, list):
            failures.append("ContractGraph.businessObjectMaps must be a list")
        else:
            for index, item in enumerate(maps):
                if not isinstance(item, dict):
                    failures.append(f"ContractGraph.businessObjectMaps[{index}] is not an object")
                    continue
                retired = sorted(FORBIDDEN_FIELDS.intersection(item))
                if retired:
                    failures.append(
                        f"ContractGraph.businessObjectMaps[{index}] contains {retired}"
                    )

    graph_sha = (
        hashlib.sha256(graph_path.read_bytes()).hexdigest()
        if graph_path.is_file()
        else ""
    )
    lock = loaded.get(lock_path)
    if lock is not None:
        contract_graph = lock.get("contractGraph")
        if not isinstance(contract_graph, dict) or contract_graph.get("sha256") != graph_sha:
            failures.append("App handoff lock is not bound to the unique ContractGraph hash")
        if lock.get("generator") != "app-cloud-handoff":
            failures.append("App handoff lock generator is not the unique current generator")
    report = loaded.get(report_path)
    if report is not None:
        if report.get("graphSha256") != graph_sha:
            failures.append("breaking report is not bound to the unique ContractGraph hash")
        if report.get("generator") != "app-cloud-handoff":
            failures.append("breaking report generator is not the unique current generator")
    manifest = loaded.get(manifest_path)
    if manifest is not None:
        if manifest.get("contractGraphSha256") != graph_sha:
            failures.append("generated manifest is not bound to the unique ContractGraph hash")
        if manifest.get("generator") != "app-only-emitter":
            failures.append("generated manifest generator is not the unique current emitter")

    code_expectations = {
        SERVICE / "internal/metadata/graph/graph.go": (
            'json:"schema"',
            'json:"registryRevision"',
            "const RegistryRevision",
            "const Schema",
        ),
        SERVICE / "internal/metadata/validate/schema.go": (
            '"_schemas", "v',
        ),
    }
    for path, patterns in code_expectations.items():
        source = path.read_text(encoding="utf-8")
        for pattern in patterns:
            if pattern in source:
                failures.append(f"retired version switch {pattern!r}: {relative(path)}")

    for base in (SERVICE / "internal", SERVICE / "tools"):
        for path in sorted(base.rglob("*.go")):
            source = path.read_text(encoding="utf-8")
            if VERSIONED_SCHEMA_PATH.search(source):
                failures.append(
                    f"versioned metadata schema path is forbidden: {relative(path)}"
                )

    if failures:
        for failure in failures:
            print(f"[contract-graph-single-track] FAIL: {failure}")
        return 1
    print(
        "[contract-graph-single-track] OK: "
        f"retiredInputs={len(retired_inputs)}, "
        f"graph={graph_sha}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
