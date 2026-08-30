"""Governance pipeline observe-only admission query surface."""
from .contract import (
    CONTRACT_PATH,
    ContractError,
    GovernancePipelineAdmissionError,
    contract_failure,
    load_contract,
)
from .evaluator import inspect, invalid_inspection
from .evidence import (
    assemble_evidence_bundle, current_repository_input, load_evidence_bundle,
    subject_fingerprint, subject_fingerprint_receipt,
)

__all__ = [
    "CONTRACT_PATH",
    "ContractError",
    "GovernancePipelineAdmissionError",
    "contract_failure",
    "inspect",
    "invalid_inspection",
    "load_contract",
    "assemble_evidence_bundle",
    "current_repository_input",
    "load_evidence_bundle",
    "subject_fingerprint",
    "subject_fingerprint_receipt",
]
