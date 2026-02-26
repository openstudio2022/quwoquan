# Design: Metadata Domain Restructure

## Problem

The original flat `contracts/metadata/post/` structure did not express domain ownership.

## Solution

Reorganize to `contracts/metadata/content/post/` with domain-centric nesting:

```
contracts/metadata/
└── content/               ← domain container
    ├── openapi.yaml       ← domain-level OpenAPI spec
    └── post/              ← business object aggregate
        ├── aggregate.yaml
        ├── fields.yaml
        ├── service.yaml
        ├── errors.yaml
        ├── behaviors.yaml
        ├── privacy.yaml
        ├── ui_config.yaml
        ├── projections/
        └── tests/
```

## Tooling Adaptation

All codegen tools updated to recursively discover domain subdirectories, maintaining backward compatibility via fallback path resolution.
