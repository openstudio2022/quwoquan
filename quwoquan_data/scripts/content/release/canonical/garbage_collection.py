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
from content.release.canonical.garbage_collection_tombstone_backfill import (
    backfill_absent_execution_tombstones,
    unresolved_execution_references,
)

__all__ = [
    "GC_APPLY_SCHEMA",
    "GC_PLAN_SCHEMA",
    "apply_canonical_gc",
    "backfill_absent_execution_tombstones",
    "plan_canonical_gc",
    "unresolved_execution_references",
    "release_identity_incident_protected_execution_ids",
    "release_identity_incident_protected_release_ids",
    "reviewed_closure_adoption_protected_refs",
]
