# Mock / 远端与生产包物理隔离执行规格

> **状态**：**执行中（2026-07-13 已触发）** — 本文件不再表示“以后再做”的
> 历史延期项已经进入执行。App Cloud 商用重构采用唯一物理隔离形态：pure Dart contracts、
> 独立 `quwoquan_cloud_mock` 与 alpha/test runner、production Remote composition。
> 退出必须证明 prod dependency graph、kernel/AOT 可达图与 SBOM 零 Mock/fixture/Noop。

---

## 当前迁移约定

- **禁止新增同仓混写**：现有 `lib/cloud/services/**` 的 Abstract + Mock + Remote
  只作为待删除输入，不再是目标结构。
- **生产 composition**：只依赖 pure contracts + Remote；不得通过
  `appDataSourceModeProvider` 把 Mock implementation 链入 prod。
- **alpha/test composition**：通过独立 `quwoquan_cloud_mock` package 与 runner
  注入，fixture 由 metadata seed manifest 构建期生成。
- **UI / application**：只依赖对象专属 typed `*CommandWriter/*Query` Facet，
  不依赖 Repository、Remote、Mock、fixture 或运行时数据源能力位；与
  [`.cursor/rules/08-mock-data-isolation.mdc`](../../.cursor/rules/08-mock-data-isolation.mdc) 一致。

---

## 专项目标（执行时）

1. **契约包**：`quwoquan_cloud_contracts` 只含 pure Dart typed request/result、descriptor、codec 与 Facet；App 与 Mock 均只依赖契约，禁止 export 旧 DTO/Repository。
2. **Mock 物理归位**：Mock 与 fixture 只能位于
   [`quwoquan_app/packages/quwoquan_cloud_mock`](../../quwoquan_app/packages/quwoquan_cloud_mock/)；
   `test/` 只保存测试，不保存可被 runner 当作运行时实现的第二套源码树。
3. **运行时策略**
   - production runner 仅 Remote。
   - alpha/test runner 依赖 `packages/quwoquan_cloud_mock`；Mock 与 fixture 不进入
     production pub dependency。
4. **组合根收敛**：production 与 alpha/test 使用物理独立 composition root；
   禁止业务层重复 `mode == remote ? … : …`。
5. **发布剥离**：以独立 runner/package dependency 和 artifact reachability 门禁
   证明剥离；仅依赖 tree-shaking 或 `kReleaseMode` 不算通过。

---

## 执行清单（阶段 A–F，与规划对齐）

| 阶段 | 内容 |
|------|------|
| **A** | 契约包生成 typed `*CommandWriter/*Query` Facet；禁止迁入或 export Repository |
| **B** | `Mock*` 与 fixture 迁入 `packages/quwoquan_cloud_mock/{context}/{object}` |
| **B'** | 独立 alpha/test runner 装配 mock package，production pubspec 不得引用 |
| **C** | 组合根单一绑定 |
| **D** | 双 `pubspec` / `main_release` |
| **E** | 测试 import 规范、`lib` 禁止 import `test/` 门禁 |
| **F** | 边角：`analytics` 等默认 Mock 注入、契约测试 import 更新 |

**验证**：clean checkout `dart analyze` / `flutter test`、production/alpha 双构建、
dependency graph、kernel/AOT reachability 与 SBOM 检查。

---

## 工作量提示

2026-07-14 当前扫描为 `quwoquan_app/lib/cloud` 与 mock package 合计 31 个
`Mock*` 顶层类；这是只降不升的迁移输入，不是允许保留的终态。完整清单由
[`mock_migration_checklist.md`](mock_migration_checklist.md) 与静态门禁对代码扫描结果
双向校验。先完成 Integration/Location 小域基础设施试点，再消费上游 Content
Post+Report ABI，最后按对象波次原子迁移。
