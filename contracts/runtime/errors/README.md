# Runtime Failure Contracts

This directory is the source of truth for cross-client-cloud runtime failures.

## Contract Rules

- Error facts are represented by `RuntimeFailure`.
- Stable codes use `MODULE.KIND.REASON`.
- Context attributes are string-only key-value pairs.
- `context.attributes` is for logs, diagnostics, and alert triage only.
- Recovery decisions are made by runtime policy, not encoded on the failure fact.
- Language packages must be generated from these files or kept byte-for-byte compatible with them.

## Files

- `runtime_failure.schema.yaml`: shared runtime failure model.
- `runtime_failure_codes.yaml`: stable code registry and default classification.
- `runtime_recovery_policy.schema.yaml`: shared recovery decision vocabulary.
