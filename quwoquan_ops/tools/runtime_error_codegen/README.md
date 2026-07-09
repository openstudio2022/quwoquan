# Runtime Error Codegen

Generates language-specific runtime error models from `quwoquan_service/contracts/runtime_errors/errors`.

The first milestone validates the contract source and provides generator entrypoints for Dart and Go, with TypeScript and Python reserved for management and offline jobs.

```bash
dart run quwoquan_ops/tools/runtime_error_codegen/bin/generate_runtime_errors.dart --check
```
