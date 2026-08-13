"""命中摘要与全仓快照 dataclass。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class HitSummary:
    count: int
    digest: str
    samples: tuple[str, ...]


@dataclass(frozen=True)
class Snapshot:
    vertical_terms: frozenset[str]
    service_domains: Mapping[str, str]
    platform_vertical_branches: Mapping[str, HitSummary]
    content_vertical_usage: Mapping[str, HitSummary]
    domain_taxonomy_runtime_consumers: Mapping[str, HitSummary]
    travel_service_dependencies: Mapping[str, Mapping[str, HitSummary]]
