# Design: Full-Stack Error & Behavior Contract

## Error Handling (End-to-End)

```
errors.yaml → codegen → ContentErrorCode (Dart) + ErrXxx vars (Go)
CloudErrorMapper.fromErrorResponse() → ContentErrorCode
CloudException.errorCode → typed error in UI
```

All 13 error codes are defined once in YAML, then generated into:
- Dart: `ContentErrorCode` enum with `recoveryAction` getter, localized messages
- Go: Sentinel `var Err... = errors.New("CONTENT.domain.code")` constants

## Behavior Tracking

```
behaviors.yaml → codegen → ContentBehaviorTracker (Dart) + ContentFeatures (Python)
```

- `ContentBehaviorTracker` provides type-safe static methods; batch route matches `service.yaml`
- `ContentFeatures` and `ContentTrainingSample` Pydantic models generated for ML training pipeline
