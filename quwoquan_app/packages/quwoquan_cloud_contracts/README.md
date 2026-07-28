# quwoquan_cloud_contracts

`CircleRepository` / `ContentRepository` **抽象**与共享常量，供 `quwoquan_app` 内 Mock、Remote 实现。

- **依赖**：`path` → `quwoquan_app`（用于 DTO / metadata 类型）。`quwoquan_app` 再依赖本包，形成 **path 包互依**；`dart pub get` 可解析。
- **测试替身**：对象级最小 typed doubles 只放在 App `test/support`；本包与环境
  App 不依赖任何 Mock package 或 fixture bundle。
