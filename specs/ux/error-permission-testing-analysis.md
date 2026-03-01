# 错误/权限语义测试分析：从「l10n 存在」到「交互异常」

> 问题：当前 `error_permission_l10n_contract_test.dart` 仅断言 l10n key 存在且非空，几乎不会失败，也无法覆盖真实交互中的异常路径。核心应是在**交互过程**中测试异常/权限态的正确展示。

---

## 1. 当前 L1a 测试的问题

| 现有测试 | 断言内容 | 问题 |
|----------|----------|------|
| `l10n_keys_exist_for_error_permission_semantics` | loadFailed、locationLoadFailed 等 key 非空 | 删 key → build 失败或 key 字面量暴露，非本测试能发现 |
| `location keys match integration errors.yaml semantics` | 文案包含「权限」「位置/重试」 | 纯正则，不触及映射与 UI 链路 |

**结论**：这类测试价值有限，无法守护「异常发生时 UI 展示正确」这一核心契约。

---

## 2. 真正要守护的契约

| 场景 | 预期行为 | 当前可测性 |
|------|----------|------------|
| 位置选择页：云端返回 `location_permission_required` | 内联展示 `locationPermissionRequired` 文案 | ✅ 可测（注入 FakeLocationService 抛 CloudException） |
| 位置选择页：云端返回 `upstream_timeout` | 内联展示 `locationUpstreamTimeout` | ✅ 可测 |
| 位置选择页：权限永久拒绝 | 展示 `locationAppPermissionRequired` + 「去设置」按钮 | ⚠️ 需改造（`ensureLocationPermission` 为 static，直接调 Geolocator） |
| 位置选择页：加载态 | 展示 `locationFetchingResult` + `CircularProgressIndicator` | ⚠️ 需权限 mock 先返回 granted |
| 发现流：加载失败 | 内联占位 + 重试 | ✅ 可测（MockRepo 抛异常） |
| 创作提交失败 | SnackBar 展示 submitFailed | ✅ 可测 |
| 真机：点「去设置」 | 打开系统设置 | L4 Patrol |

---

## 3. L1 层落实方案

### 3.1 L1a：保留与改造

**保留**：错误码 → l10n 映射契约（纯 Dart，有意义）

- 被测对象：`PublishLocationSelectorPage._mapCloudCodeToMessage` 的逻辑，或抽成 `CloudCodeToL10nMapper`
- 断言：给定 `CloudException(code: 'INTEGRATION.MIDDLEWARE.upstream_timeout')`，映射结果等于 `l10n.locationUpstreamTimeout`
- 价值：守护 code→文案 映射，避免新增 code 时漏映射或映射错

**删除/降级**：纯 l10n key 存在性断言

- 可作为可选冒烟测试，不作为核心契约

### 3.2 L1b：Widget 测试 — 错误态/权限态 UI

**目标**：在注入异常/权限态的前提下，断言页面展示正确。

| 用例 | 注入方式 | 断言 |
|------|----------|------|
| 云端 `location_permission_required` | `FakeCreateLocationService.nearby()` 抛 `CloudException(code: '...')` | `find.text(l10n.locationPermissionRequired)` |
| 云端 `upstream_timeout` | 同上，code 改为 timeout | `find.text(l10n.locationUpstreamTimeout)` |
| 云端 `location_unavailable` | 同上，code 改为 unavailable | `find.text(l10n.locationLoadFailed)` |
| 错误态时「重试」FAB | 同上 | `find.byType(FloatingActionButton)` 且可点击 |
| 权限永久拒绝 + 「去设置」 | 需注入 `LocationPermissionChecker` | `find.text(l10n.locationAppPermissionRequired)` + `find.widgetWithText(FilledButton, l10n.locationOpenSettings)` |
| 加载态 | 权限 mock 返回 granted，`nearby()` 延迟不返回 | `find.text(l10n.locationFetchingResult)` + `find.byType(CircularProgressIndicator)` |

**依赖注入缺口**：

1. **CreateLocationService**：页面已通过构造参数注入 ✅
2. **LocationPermissionChecker**：`ensureLocationPermission()` 为 static，直接调 `Geolocator`，当前无法注入 ❌

**改造选项**：

| 方案 | 做法 | 侵入性 | 推荐 |
|------|------|--------|------|
| A. 抽取 `LocationPermissionChecker` | 接口 + 默认实现调 Geolocator，测试注入 `FakeChecker` | 中 | ✅ 推荐 |
| B. MethodChannel mock | 伪造 `Geolocator` 平台返回值 | 低侵入，高维护 | 备选 |
| C. 先测 CloudException 路径 | 仅测 `nearby()` 抛异常，不测权限拒绝 | 无侵入 | 可作第一步 |

**建议步骤**：

1. **阶段 1**：抽取 `LocationPermissionChecker`（方案 A）。否则 `ensureLocationPermission()` 在 test 环境下通常返回 denied/异常，永远进不了 `nearby()`，CloudException 路径无法覆盖。
2. **阶段 2**：实现 L1b 的 CloudException 路径（注入 FakeChecker 返回 granted + FakeLocationService 抛异常）。
3. **阶段 3**：实现 L1b 的权限拒绝路径（FakeChecker 返回 permanentlyDenied）。

### 3.3 L1c：Journey 测试 — 创作流中的错误/权限

**目标**：在创作流程中，验证「选位置 → 失败」的端到端表现。

| 用例 | 做法 | 断言 |
|------|------|------|
| 创作 → 选位置 → 云端超时 | Mock `CreateLocationService`，`nearby()` 抛 `CloudException` | 位置选择页展示内联错误，非 SnackBar |
| 创作 → 选位置 → 权限永久拒绝 | 注入 FakePermissionChecker | 展示「去设置」，点击不崩溃（不实际跳转） |

---

## 4. L4 层落实方案（Patrol）

| 用例 | 做法 | 断言 |
|------|------|------|
| 真机权限弹窗 | 进入位置选择 → 系统弹出权限对话框 | 对话框可见 |
| 拒绝权限后 UI | 用户点「不允许」 | 展示权限卡片 + 「去设置」 |
| 「去设置」跳转 | 点击「去设置」 | 系统设置被打开（或相应系统行为） |

**约束**：L4 为 pre-release advisory，不阻塞 PR；需真机或支持权限的模拟器。

---

## 5. 实施优先级

| 优先级 | 内容 | 前置条件 |
|--------|------|----------|
| P0 | L1b：CloudException 路径（location 选择页） | 确认 test 环境下 `Geolocator` 行为，或先用 MethodChannel mock 返回 granted |
| P1 | L1a：错误码→l10n 映射契约（替换纯 l10n 存在性测试） | 抽取 `_mapCloudCodeToMessage` 或建 mapper |
| P2 | L1b：权限拒绝路径 | 抽取 `LocationPermissionChecker` |
| P3 | L1c：创作流错误 journey | 依赖 P0 |
| P4 | L4 Patrol：真机权限 + 去设置 | 有 Patrol 环境即可 |

---

## 6. 文件与路径建议

| 类型 | 路径 | 说明 |
|------|------|------|
| L1a 映射契约 | `test/cloud/integration/location/contract/cloud_code_to_l10n_mapper_contract_test.dart` | 替换原 error_permission_l10n |
| L1b Widget | `test/ui/create/publish/widgets/publish_location_selector_error_state_test.dart` | 错误态/权限态 UI |
| L1c Journey | `test/ui/create/publish/journeys/create_location_error_journey_test.dart` | 创作流中的位置错误 |
| L4 Patrol | `test/patrol/content/location_permission_flow_test.dart` | 真机权限与去设置 |
