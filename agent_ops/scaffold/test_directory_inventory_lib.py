#!/usr/bin/env python3
"""Shared helpers for test directory migration inventory."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "specs" / "gates" / "test_directory_inventory.yaml"

LAYERS = {"local_contract", "api_integration", "user_acceptance"}
APP_ROOT = ROOT / "quwoquan_app" / "test"
SERVICE_ROOT = ROOT / "quwoquan_service" / "services"
DATA_ROOT = ROOT / "quwoquan_data" / "tests"
AGENT_OPS_ROOT = ROOT / "agent_ops" / "tests"


def _strip_test_suffix(stem: str) -> str:
    stem = re.sub(r"__(local_contract|api_integration|user_acceptance)$", "", stem)
    if stem.endswith("_test"):
        return stem[: -len("_test")]
    return stem


def canonical_filename(path: Path, layer: str) -> str:
    return f"{_strip_test_suffix(path.stem)}__{layer}_test{path.suffix}"


def _relative(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def is_app_canonical(rel: str) -> bool:
    return rel.startswith(("local_contract/", "api_integration/", "user_acceptance/"))


def is_service_canonical(rel: str) -> bool:
    return "/tests/local_contract/" in rel or "/tests/api_integration/" in rel


def is_data_canonical(rel: str) -> bool:
    return rel.startswith(("local_contract/", "api_integration/", "user_acceptance/"))


def is_agent_ops_canonical(rel: str) -> bool:
    return rel.startswith(("local_contract/", "api_integration/", "user_acceptance/"))


def app_layer(rel_path: Path) -> str:
    parts = rel_path.parts
    first = parts[0] if parts else ""
    stem = rel_path.stem.lower()
    dir_tokens = {token.lower() for token in parts[:-1]}
    if first in {"patrol"} or "journey" in stem or "journeys" in dir_tokens:
        return "user_acceptance"
    if first in {"beta", "gamma"}:
        return "api_integration"
    return "local_contract"


def app_target_path(rel_path: Path, layer: str) -> str:
    target = Path("quwoquan_app/test") / layer / Path(*rel_path.parts[:-1]) / canonical_filename(rel_path, layer)
    return target.as_posix()


def service_layer(rel_path: Path) -> str:
    parts = rel_path.parts
    if len(parts) >= 3 and parts[2] == "tests":
        return "api_integration"
    return "local_contract"


def service_target_path(rel_path: Path, layer: str) -> str:
    service_name = rel_path.parts[1]
    if layer == "api_integration" and len(rel_path.parts) >= 3 and rel_path.parts[2] == "tests":
        tail = rel_path.parts[3:-1]
    else:
        tail = rel_path.parts[2:-1]
    target = (
        Path("quwoquan_service/services")
        / service_name
        / "tests"
        / layer
        / Path(*tail)
        / canonical_filename(rel_path, layer)
    )
    return target.as_posix()


def data_layer(rel_path: Path) -> str:
    parts = rel_path.parts
    if parts and parts[0] == "integration":
        return "api_integration"
    if "e2e" in rel_path.stem.lower() or "journey" in rel_path.stem.lower():
        return "user_acceptance"
    return "local_contract"


def data_target_path(rel_path: Path, layer: str) -> str:
    target = Path("quwoquan_data/tests") / layer / Path(*rel_path.parts[:-1]) / canonical_filename(rel_path, layer)
    return target.as_posix()


def agent_ops_layer(rel_path: Path) -> str:
    stem = rel_path.stem.lower()
    if any(token in stem for token in ("stackctl", "runtime", "deploy", "up_runtime")):
        return "api_integration"
    return "local_contract"


def agent_ops_target_path(rel_path: Path, layer: str) -> str:
    target = Path("agent_ops/tests") / layer / Path(*rel_path.parts[:-1]) / canonical_filename(rel_path, layer)
    return target.as_posix()


def _scan_entries(
    *,
    area: str,
    base_dir: Path,
    file_glob: str,
    is_canonical: Callable[[str], bool],
    layer_resolver: Callable[[Path], str],
    target_resolver: Callable[[Path, str], str],
    inventory_base: Path,
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for path in sorted(base_dir.rglob(file_glob)):
        rel = path.relative_to(inventory_base)
        rel_text = rel.as_posix()
        if is_canonical(_relative(path, base_dir)):
            continue
        layer = layer_resolver(rel.relative_to(inventory_base / rel.parts[0]) if area != "service" else rel)
        entries.append(
            {
                "current_path": rel_text,
                "layer": layer,
                "target_path": target_resolver(rel.relative_to(inventory_base / rel.parts[0]) if area != "service" else rel, layer),
            }
        )
    return entries


def build_inventory() -> dict:
    app_entries = []
    for path in sorted(APP_ROOT.rglob("*_test.dart")):
        rel = path.relative_to(ROOT)
        test_rel = path.relative_to(APP_ROOT)
        if is_app_canonical(test_rel.as_posix()):
            continue
        layer = app_layer(test_rel)
        app_entries.append(
            {
                "current_path": rel.as_posix(),
                "layer": layer,
                "target_path": app_target_path(test_rel, layer),
            }
        )

    service_entries = []
    for path in sorted(SERVICE_ROOT.rglob("*_test.go")):
        rel = path.relative_to(ROOT)
        if is_service_canonical(rel.as_posix()):
            continue
        layer = service_layer(rel)
        service_entries.append(
            {
                "current_path": rel.as_posix(),
                "layer": layer,
                "target_path": service_target_path(rel, layer),
            }
        )

    data_entries = []
    for path in sorted(DATA_ROOT.rglob("test_*.py")):
        rel = path.relative_to(ROOT)
        test_rel = path.relative_to(DATA_ROOT)
        if is_data_canonical(test_rel.as_posix()):
            continue
        layer = data_layer(test_rel)
        data_entries.append(
            {
                "current_path": rel.as_posix(),
                "layer": layer,
                "target_path": data_target_path(test_rel, layer),
            }
        )

    agent_ops_entries = []
    for path in sorted(AGENT_OPS_ROOT.rglob("test_*.py")):
        rel = path.relative_to(ROOT)
        test_rel = path.relative_to(AGENT_OPS_ROOT)
        if is_agent_ops_canonical(test_rel.as_posix()):
            continue
        layer = agent_ops_layer(test_rel)
        agent_ops_entries.append(
            {
                "current_path": rel.as_posix(),
                "layer": layer,
                "target_path": agent_ops_target_path(test_rel, layer),
            }
        )

    return {
        "version": 1,
        "generated_by": "python3 agent_ops/scaffold/generate_test_directory_inventory.py",
        "areas": {
            "app": {"legacy_count": len(app_entries), "entries": app_entries},
            "service": {"legacy_count": len(service_entries), "entries": service_entries},
            "data": {"legacy_count": len(data_entries), "entries": data_entries},
            "agent_ops": {"legacy_count": len(agent_ops_entries), "entries": agent_ops_entries},
        },
    }


def iter_canonical_files() -> list[tuple[str, Path, str]]:
    files: list[tuple[str, Path, str]] = []
    for layer in LAYERS:
        for path in sorted((APP_ROOT / layer).rglob("*_test.dart")):
            files.append(("app", path, layer))
        for path in sorted((DATA_ROOT / layer).rglob("test_*.py")):
            files.append(("data", path, layer))
        for path in sorted((AGENT_OPS_ROOT / layer).rglob("test_*.py")):
            files.append(("agent_ops", path, layer))
    for service_tests_dir in SERVICE_ROOT.glob("*/tests"):
        for layer in ("local_contract", "api_integration"):
            layer_dir = service_tests_dir / layer
            if not layer_dir.exists():
                continue
            for path in sorted(layer_dir.rglob("*_test.go")):
                files.append(("service", path, layer))
    return files

