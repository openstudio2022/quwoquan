"""CLI facade for digest-bound, reachability-first canonical GC."""

from content.release.canonical.garbage_collection_operations import (
    GC_APPLY_SCHEMA,
    GC_PLAN_SCHEMA,
    apply_canonical_gc,
    plan_canonical_gc,
)
from content.release.canonical.garbage_collection_protection import (
    release_identity_incident_protected_execution_ids,
    release_identity_incident_protected_release_ids,
    reviewed_closure_adoption_protected_refs,
)

__all__ = [
    "GC_APPLY_SCHEMA",
    "GC_PLAN_SCHEMA",
    "apply_canonical_gc",
    "plan_canonical_gc",
    "release_identity_incident_protected_execution_ids",
    "release_identity_incident_protected_release_ids",
    "reviewed_closure_adoption_protected_refs",
]
