# Design: Three-Layer Test Contract

## Test Pyramid

```
mock.yaml       → Dart contract tests (no cloud dependency)
contract.yaml   → Go server-side contract tests (real DB)
e2e.yaml        → Full-stack integration tests
```

## Key Test Files

| File | Coverage |
|------|----------|
| `error_code_contract_test.dart` | All 13 error codes × fromCode × recoveryAction |
| `behavior_tracker_contract_test.dart` | Queue semantics, batch route, event shapes |
| `ui_config_contract_test.dart` | Tab count, layouts, feature flag completeness |

## Gate Integration (G4-G10)

All metadata cross-cutting checks run as part of `make gate`:
- G4: error codes → mock.yaml coverage
- G5: behaviors batch_route → service.yaml consistency
- G6: ui_config contentTypes → shared/types.yaml enum validity
- G7: contract.yaml scenarios → service.yaml route coverage
- G8: PII/SENSITIVE fields → privacy.yaml declared
- G9: behavior event types → BehaviorEventType enum validity
- G10: feature_flags key uniqueness
