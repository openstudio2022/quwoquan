"""Materialize versioned Pinterest-first professional-image discovery plans."""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from core.paths import CONTROL_PLANE_SHARED_ROOT, REPO_ROOT, SOURCE_ACQUISITION_ROOT
from core.schema import assert_valid


CATALOG_PATH = CONTROL_PLANE_SHARED_ROOT / "catalogs" / "professional_image_discovery.yaml"
DISCOVERY_ROOT = SOURCE_ACQUISITION_ROOT / "discovery-plans"


class ProfessionalImageDiscoveryError(ValueError):
    """The discovery catalog or requested dimensions are not auditable."""


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalized_text(value: object, *, label: str) -> str:
    rendered = " ".join(str(value or "").split())
    if not rendered:
        raise ProfessionalImageDiscoveryError(f"{label} is required")
    return rendered


def _load_catalog(path: Path = CATALOG_PATH) -> tuple[dict[str, Any], str, str]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ProfessionalImageDiscoveryError(f"discovery catalog is missing: {resolved}")
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ProfessionalImageDiscoveryError("discovery catalog must be an object")
    assert_valid(
        payload,
        "source",
        "professional_image_discovery_catalog",
        label="professional image discovery catalog",
    )
    provider_order = [str(value) for value in payload["providerOrder"]]
    providers = [str(row["provider"]) for row in payload["providers"]]
    if len(provider_order) != len(set(provider_order)) or set(provider_order) != set(providers):
        raise ProfessionalImageDiscoveryError(
            "providerOrder must name every provider exactly once"
        )
    if provider_order[0] != "pinterest" or "tuchong" not in provider_order[1:]:
        raise ProfessionalImageDiscoveryError(
            "professional image catalog must keep Pinterest first and Tuchong supplemental"
        )
    priorities = [int(row["priority"]) for row in payload["providers"]]
    if len(priorities) != len(set(priorities)):
        raise ProfessionalImageDiscoveryError("provider priorities must be unique")
    try:
        catalog_ref = resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ProfessionalImageDiscoveryError(
            "discovery catalog must be version controlled inside the repository"
        ) from exc
    return payload, catalog_ref, _canonical_digest(payload)


def _render_query(template: str, dimensions: Mapping[str, str], *, entity: str) -> str:
    try:
        rendered = template.format(entity=entity, **dimensions)
    except KeyError as exc:
        raise ProfessionalImageDiscoveryError(
            f"discovery query template has unknown axis: {exc}"
        ) from exc
    return _normalized_text(rendered, label="rendered discovery query")


def _candidate_id(provider: str, stable: Mapping[str, object]) -> str:
    raw = _canonical_digest(stable).removeprefix("sha256:")[:16]
    normalized_provider = re.sub(r"[^a-z0-9_-]+", "-", provider.lower()).strip("-")
    return f"{normalized_provider}:{raw}"


def _write_create_once(path: Path, payload: Mapping[str, object]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict) or existing.get("planDigest") != payload.get(
            "planDigest"
        ):
            raise ProfessionalImageDiscoveryError(
                f"professional image discovery plan collision: {path}"
            )
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def create_professional_image_discovery_plan(
    *,
    entities: Iterable[str],
    category: str,
    season: str,
    style: str,
    viewpoint: str,
    popularity: str,
    catalog_path: Path = CATALOG_PATH,
    output_root: Path = DISCOVERY_ROOT,
) -> tuple[dict[str, object], Path]:
    normalized_entities = tuple(
        sorted({_normalized_text(entity, label="entity") for entity in entities})
    )
    if not normalized_entities:
        raise ProfessionalImageDiscoveryError("at least one entity is required")
    dimensions = {
        "category": _normalized_text(category, label="category"),
        "season": _normalized_text(season, label="season"),
        "style": _normalized_text(style, label="style"),
        "viewpoint": _normalized_text(viewpoint, label="viewpoint"),
        "popularity": _normalized_text(popularity, label="popularity"),
    }
    catalog, catalog_ref, catalog_digest = _load_catalog(catalog_path)
    provider_order = {
        provider: index for index, provider in enumerate(catalog["providerOrder"])
    }
    candidates: list[dict[str, object]] = []
    for provider in sorted(
        catalog["providers"],
        key=lambda row: (provider_order[str(row["provider"])], int(row["priority"])),
    ):
        provider_id = str(provider["provider"])
        search_template = str(provider["searchUrlTemplate"])
        public_urls = [str(value) for value in provider["publicDiscoveryUrls"]]
        manual = provider["discoveryMode"] == "public_explore_manual_query"
        for entity in normalized_entities:
            for query_template in provider["queryTemplates"]:
                query = _render_query(str(query_template), dimensions, entity=entity)
                discovery_url = (
                    search_template.format(query=urllib.parse.quote_plus(query))
                    if search_template
                    else public_urls[0]
                )
                stable: dict[str, object] = {
                    "provider": provider_id,
                    "entity": entity,
                    "queryText": query,
                    "discoveryUrl": discovery_url,
                }
                candidates.append(
                    {
                        "candidateId": _candidate_id(provider_id, stable),
                        "provider": provider_id,
                        "displayName": str(provider["displayName"]),
                        "priority": int(provider["priority"]),
                        "entity": entity,
                        "queryText": query,
                        "discoveryUrl": discovery_url,
                        "manualSearchRequired": bool(manual),
                        "acquisitionPaths": list(provider["acquisitionPaths"]),
                        "termsUrl": str(provider["termsUrl"]),
                    }
                )
    if len({str(row["candidateId"]) for row in candidates}) != len(candidates):
        raise ProfessionalImageDiscoveryError("discovery candidates are not unique")
    counts = Counter(str(row["provider"]) for row in candidates)
    labels = {
        str(row["provider"]): str(row["displayName"])
        for row in catalog["providers"]
    }
    provider_counts = [
        {
            "provider": provider,
            "displayName": labels[provider],
            "plannedAssetCount": counts[provider],
        }
        for provider in catalog["providerOrder"]
    ]
    stable_plan: dict[str, object] = {
        "catalogRef": catalog_ref,
        "catalogDigest": catalog_digest,
        "dimensions": {"entities": list(normalized_entities), **dimensions},
        "candidateCount": len(candidates),
        "providerCandidateCounts": provider_counts,
        "candidates": candidates,
    }
    plan_digest = _canonical_digest(stable_plan)
    plan_id = f"professional-image-discovery-{plan_digest.removeprefix('sha256:')[:16]}"
    payload: dict[str, object] = {
        "schema": "quwoquan_data.professional_image_discovery_plan",
        "planId": plan_id,
        "planDigest": plan_digest,
        **stable_plan,
        "generatedAt": _now(),
    }
    assert_valid(
        payload,
        "source",
        "professional_image_discovery_plan",
        label="professional image discovery plan",
    )
    destination = output_root.expanduser().resolve() / f"{plan_id}.json"
    if destination.exists():
        existing = json.loads(destination.read_text(encoding="utf-8"))
        if not isinstance(existing, dict) or existing.get("planDigest") != plan_digest:
            raise ProfessionalImageDiscoveryError(
                f"professional image discovery plan collision: {destination}"
            )
        return existing, destination
    _write_create_once(destination, payload)
    return payload, destination


__all__ = [
    "CATALOG_PATH",
    "DISCOVERY_ROOT",
    "ProfessionalImageDiscoveryError",
    "create_professional_image_discovery_plan",
]
