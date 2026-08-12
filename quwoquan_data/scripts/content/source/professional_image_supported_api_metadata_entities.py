"""Resolve governed discovery entities from the version-controlled master list."""
from __future__ import annotations

import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from core.paths import REPO_ROOT
from core.schema import assert_valid

from content.execution.workspace import entity_catalog_digest


class ProfessionalImageMetadataEntityError(ValueError):
    """The requested entity is absent or ambiguous in the frozen catalog."""


def _normalized(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _catalog_ref(path: Path) -> tuple[Path, str]:
    resolved = path.expanduser().resolve()
    repo_root = REPO_ROOT.resolve()
    try:
        relative = resolved.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ProfessionalImageMetadataEntityError(
            "entity catalog must be version controlled inside the repository"
        ) from exc
    if not resolved.exists() or resolved.is_symlink():
        raise ProfessionalImageMetadataEntityError(
            f"entity catalog is missing or unsafe: {resolved}"
        )
    return resolved, relative


def _catalog_files(root: Path) -> tuple[Path, ...]:
    files = (root,) if root.is_file() else tuple(sorted(root.rglob("*.yaml")))
    if not files or any(path.is_symlink() or not path.is_file() for path in files):
        raise ProfessionalImageMetadataEntityError(
            f"entity catalog has no safe YAML source files: {root}"
        )
    return files


def _leaf_bindings(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ProfessionalImageMetadataEntityError(
            f"entity catalog document must be an object: {path}"
        )
    assert_valid(payload, "governance", "master_list", label=f"entity catalog:{path}")
    bindings: list[dict[str, Any]] = []
    for group in payload.get("districts") or []:
        if not isinstance(group, dict):
            continue
        for leaf in group.get("leaves") or []:
            if not isinstance(leaf, dict):
                continue
            canonical = _normalized(leaf.get("canonicalName") or leaf.get("name"))
            names = {
                _normalized(leaf.get("name")),
                canonical,
                *(_normalized(value) for value in leaf.get("aliases") or []),
            }
            aliases = sorted(value for value in names if value)
            if not canonical or not aliases:
                raise ProfessionalImageMetadataEntityError(
                    f"entity catalog leaf lacks canonical identity: {path}"
                )
            bindings.append(
                {
                    "entityId": canonical,
                    "entityType": _normalized(leaf.get("entityType")),
                    "entityAliases": aliases,
                    "sourceRef": path.relative_to(REPO_ROOT.resolve()).as_posix(),
                }
            )
    return bindings


def load_entity_bindings(
    path: Path,
) -> tuple[str, str, dict[str, dict[str, Any]]]:
    """Return ref, digest and a unique alias-to-canonical binding index."""
    root, ref = _catalog_ref(path)
    bindings = [row for file in _catalog_files(root) for row in _leaf_bindings(file)]
    if not bindings:
        raise ProfessionalImageMetadataEntityError("entity catalog has no entity leaves")
    by_alias: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for binding in bindings:
        for alias in binding["entityAliases"]:
            by_alias[_normalized(alias)].append(binding)
    index: dict[str, dict[str, Any]] = {}
    for alias, matches in by_alias.items():
        identities = {
            (str(row["entityType"]), str(row["entityId"]))
            for row in matches
        }
        if len(identities) == 1:
            index[alias] = matches[0]
    return ref, entity_catalog_digest(ref), index


def resolve_entity(
    observed: object,
    *,
    index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    key = _normalized(observed)
    binding = index.get(key)
    if binding is None:
        raise ProfessionalImageMetadataEntityError(
            f"discovery entity is absent or ambiguous in entity catalog: {key}"
        )
    return {
        "entityId": str(binding["entityId"]),
        "observedEntityId": key,
        "entityAliases": list(binding["entityAliases"]),
    }


def resolve_entity_ref(
    observed: object,
    *,
    index: dict[str, dict[str, Any]],
) -> str:
    """Return the canonical ``/entity/{domain}/{type}/{name}`` identity."""
    key = _normalized(observed)
    binding = index.get(key)
    if binding is None:
        raise ProfessionalImageMetadataEntityError(
            f"discovery entity is absent or ambiguous in entity catalog: {key}"
        )
    entity_type = _normalized(binding.get("entityType")).strip("/")
    canonical = _normalized(binding.get("entityId"))
    if len(entity_type.split("/")) != 2 or not canonical or "/" in canonical:
        raise ProfessionalImageMetadataEntityError(
            f"entity catalog binding lacks canonical ref identity: {key}"
        )
    return f"/entity/{entity_type}/{canonical}"


__all__ = [
    "ProfessionalImageMetadataEntityError",
    "load_entity_bindings",
    "resolve_entity",
    "resolve_entity_ref",
]
