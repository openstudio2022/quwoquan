"""Typed provider-policy boundary for reusable content families."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from core.paths import REPO_DATA_ROOT


@dataclass(frozen=True, slots=True)
class ProviderPolicy:
    vertical: str
    provider_ids: frozenset[str]

    def require_declared(self, provider_ids: tuple[str, ...]) -> None:
        unknown = sorted(set(provider_ids).difference(self.provider_ids))
        if unknown:
            raise ValueError(
                f"{self.vertical} provider policy does not declare: {', '.join(unknown)}"
            )


def load_provider_policy(vertical: str) -> ProviderPolicy:
    path = REPO_DATA_ROOT / "verticals" / vertical / "providers.yaml"
    if not path.is_file():
        raise ValueError(f"missing provider policy: {path}")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"provider policy must be an object: {path}")
    if str(document.get("vertical") or "").strip() != vertical:
        raise ValueError(f"provider policy vertical mismatch: {path}")
    sites = document.get("sites")
    if not isinstance(sites, list):
        raise ValueError(f"provider policy sites must be an array: {path}")
    provider_ids = frozenset(
        str(site.get("siteId") or "").strip()
        for site in sites
        if isinstance(site, dict) and str(site.get("siteId") or "").strip()
    )
    return ProviderPolicy(vertical=vertical, provider_ids=provider_ids)


__all__ = ["ProviderPolicy", "load_provider_policy"]
