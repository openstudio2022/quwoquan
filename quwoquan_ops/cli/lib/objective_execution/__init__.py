"""Canonical Objective/Increment execution-state implementation."""
from .admission import inspect_admission
from .authority import AuthorityReadback, UnavailableAuthorityProvider, verify_authority
from .contract import ContractError, ObjectiveExecutionError, load_contract, require_transition, transition_allowed, transition_graph, validate_contract
from .executor import ExecutorDependencies, execute_authorized_effect
from .journal import CASConflict, JournalError, WriterLeaseConflict, append_event, read_events, readback, recover_materialization, writer_lease
from .reducer import reduce_events

__all__ = [
    "AuthorityReadback", "CASConflict", "ContractError", "ExecutorDependencies",
    "JournalError", "ObjectiveExecutionError", "UnavailableAuthorityProvider",
    "WriterLeaseConflict", "append_event", "execute_authorized_effect",
    "inspect_admission", "load_contract", "read_events", "readback", "recover_materialization",
    "reduce_events", "require_transition", "transition_allowed", "transition_graph",
    "validate_contract", "verify_authority", "writer_lease",
]
