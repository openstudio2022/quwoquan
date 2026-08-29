"""Public post-command CAS API for one private App dependency projection.

Prepare is the sole object-aware convenience layer. Load and revalidation
need only canonical evidence bytes plus their caller-retained digest, so shell
retry, package subprocesses and a fresh process use the same contract.
"""

from __future__ import annotations

from pathlib import Path

from .dependency_projection_contract import (
    CAS_BLOCKER as DEPENDENCY_PROJECTION_CAS_BLOCKER,
)
from .dependency_projection_contract import (
    EVIDENCE_BLOCKER as DEPENDENCY_PROJECTION_EVIDENCE_BLOCKER,
)
from .dependency_projection_contract import (
    EXPECTATION_SCHEMA as DEPENDENCY_PROJECTION_EXPECTATION_SCHEMA,
)
from .dependency_projection_contract import (
    READBACK_SCHEMA as DEPENDENCY_PROJECTION_READBACK_SCHEMA,
)
from .dependency_projection_contract import (
    DependencyProjectionExpectation,
    DependencyProjectionReadback,
    DependencyProjectionReadbackEvidence,
    load_expectation,
    load_historical_expectation,
    load_readback_evidence,
    write_readback_evidence,
)
from .dependency_projection_prepare import prepare_dependency_projection_cas_evidence
from .dependency_projection_readback import revalidate_dependency_projection_cas

__all__ = [
    "DEPENDENCY_PROJECTION_CAS_BLOCKER",
    "DEPENDENCY_PROJECTION_EVIDENCE_BLOCKER",
    "DEPENDENCY_PROJECTION_EXPECTATION_SCHEMA",
    "DEPENDENCY_PROJECTION_READBACK_SCHEMA",
    "DependencyProjectionExpectation",
    "DependencyProjectionReadback",
    "DependencyProjectionReadbackEvidence",
    "load_dependency_projection_cas_evidence",
    "load_dependency_projection_cas_readback",
    "load_historical_dependency_projection_cas_evidence",
    "prepare_dependency_projection_cas_evidence",
    "revalidate_dependency_projection_cas",
    "write_dependency_projection_cas_readback",
]


def load_dependency_projection_cas_evidence(
    *, projection_root: Path, evidence_path: Path, expected_digest: str
) -> DependencyProjectionExpectation:
    """Read canonical expectation evidence without a live projection object."""

    return load_expectation(
        projection_root_path=projection_root,
        evidence_path=evidence_path,
        expected_digest=expected_digest,
    )


def load_historical_dependency_projection_cas_evidence(
    *, evidence_path: Path, expected_digest: str
) -> DependencyProjectionExpectation:
    """Read expectation evidence after its ephemeral projection was removed."""

    return load_historical_expectation(
        evidence_path=evidence_path,
        expected_digest=expected_digest,
    )


def write_dependency_projection_cas_readback(
    *, readback: DependencyProjectionReadback, evidence_path: Path
) -> DependencyProjectionReadbackEvidence:
    """Persist a successful readback as fresh canonical mode-0600 evidence."""

    return write_readback_evidence(readback=readback, evidence_path=evidence_path)


def load_dependency_projection_cas_readback(
    *,
    evidence_path: Path,
    expected_digest: str,
    expected_expectation_digest: str,
) -> DependencyProjectionReadbackEvidence:
    """Load persisted readback evidence in a fresh process."""

    return load_readback_evidence(
        evidence_path=evidence_path,
        expected_digest=expected_digest,
        expected_expectation_digest=expected_expectation_digest,
    )
