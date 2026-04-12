# Mock / 远端与生产包分离 — 后续整改 Backlog

> **状态**：**部分落地** — 契约包（Circle/Content）、组合根 `cloudRepositoryImplForMode`、门禁 `verify_lib_no_import_test_tree`、路线图见 [`mock_test_separation_roadmap.md`](mock_test_separation_roadmap.md)。  
> **完整 Mock→`test/` 物理迁移** 仍待触发条件：全 App 具备上线要求后专项执行。

---

## 当前约定（保持至专项启动前）

- **`lib/cloud/services/**`** 继续采用 **Abstract + Mock + Remote** 同仓并存；[`app_providers.dart`](../../quwoquan_app/lib/core/providers/app_providers.dart) 经 **`appDataSourceModeProvider`** 在 Mock ↔ Remote 间选型。
- **不**在本阶段启动：`Mock*` 整体迁入 `test/`、拆 **`quwoquan_cloud_contracts`**、发布专用 **双 pubspec** / **`main_release`** 等大规模改动。
- **UI / 业务逻辑**：只依赖 **Repository 抽象** 与既有能力位（如 `usesEmbeddedContentCatalog`），**不**新增 `if (mock)` 分支；与 [`mock_data_cloud_integration_policy.md`](mock_data_cloud_integration_policy.md)、[`.cursor/rules/08-mock-data-isolation.mdc`](../../.cursor/rules/08-mock-data-isolation.mdc) 一致。

---

## 专项目标（执行时）

1. **契约包**：`quwoquan_cloud_contracts`（名称可议），抽象接口 + 必要 DTO export；**`quwoquan_app`** 与 Mock 实现侧 **均只依赖契约**，避免循环依赖。
2. **Mock 迁入 `test/` 镜像**：[`quwoquan_app/test/cloud/services/`](../../quwoquan_app/test/cloud/services/) 对齐 `lib/cloud/services/` 相对路径；**注意**：`lib` **不可** import `test/`，应用内若仍要 **可切换内嵌数据**，须配合 **R1** 或 **R2**（见下）。
3. **运行时策略（必选其一）**
   - **R1**：运行进程内 **仅 Remote**；`Mock*` **只**给 `flutter test`；**取消**或弱化应用内 `AppDataSourceMode.mock`。
   - **R2**：保留应用内切换时，**额外**使用 **`packages/quwoquan_cloud_mock`**（dev 依赖、发布去掉），与「权威在 test/」时需 **export/codegen** 防双份漂移。
4. **组合根收敛**：单一 `RepositoryBinding` 或 dev/release 绑定文件，**禁止**业务层重复 `mode == remote ? … : …`。
5. **发布剥离**：双 `pubspec` 和/或 **`main_release`** + `rg` 门禁：`lib/**` 不 import mock 包 / `test/`。

---

## 执行清单（阶段 A–F，与规划对齐）

| 阶段 | 内容 |
|------|------|
| **A** | 契约包骨架；抽象 `*Repository` 迁入或 export |
| **B** | `Mock*` 与 mock 数据迁入 `test/cloud/services/...` 镜像树 |
| **B'** | 可选：`packages/quwoquan_cloud_mock`（仅 R2） |
| **C** | 组合根单一绑定 |
| **D** | 双 `pubspec` / `main_release` |
| **E** | 测试 import 规范、`lib` 禁止 import `test/` 门禁 |
| **F** | 边角：`analytics` 等默认 Mock 注入、契约测试 import 更新 |

**验证**：`flutter test` / `dart analyze`；发布构建下 `rg` 无 mock 依赖与非法 import。

---

## 工作量提示

涉及 **20+** `Mock*` 类、巨型 repository 文件拆分、全仓 import；建议先 **Circle + Content** 竖切 PoC，再批量迁移。
