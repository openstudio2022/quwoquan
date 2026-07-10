# quwoquan_cloud_contracts

`CircleRepository` / `ContentRepository` **抽象**与共享常量，供 `quwoquan_app` 内 Mock、Remote 实现。

- **依赖**：`path` → `quwoquan_app`（用于 DTO / metadata 类型）。`quwoquan_app` 再依赖本包，形成 **path 包互依**；`dart pub get` 可解析。
- **后续**：将其余 `*Repository` 抽象迁入本包；Mock 物理迁入 `test/` 或 `packages/quwoquan_cloud_mock` 时仅改实现侧 import。
