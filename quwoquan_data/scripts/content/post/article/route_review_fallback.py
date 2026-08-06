"""Fallback-stage resolution for route review failures."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _review_fallback_stage(checks: Mapping[str, Mapping[str, Any]]) -> str:
    if not checks.get("generatorProvenance", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("evidenceQuality", {"passed": True})["passed"]:
        return "download"
    if not checks.get("articleMediaClosure", {"passed": True})["passed"]:
        return "download"
    if not checks.get("factTraceability", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("baseDraftFidelity", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("commercialNearCopy", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("provenanceRewrite", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("routeCoverage", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("travelogueDensity", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("crossArticleSimilarity", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("creativeGovernance", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("mixedLayout", {"passed": True})["passed"]:
        return "agent_compose"
    image_gate = checks.get("imageGate", {"passed": True})
    if not image_gate["passed"]:
        return "agent_compose"
    if not checks.get("imageFidelity", {"passed": True})["passed"]:
        return "compose_brief"
    if not checks.get("carrierConsistency", {"passed": True})["passed"]:
        return "agent_compose"
    return "review"
