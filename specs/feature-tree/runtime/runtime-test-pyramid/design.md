# Test Pyramid — 设计决策

## 1. Mock Wall：为什么以 Repository 接口为边界

**决策**：L1a/b/c 全部使用 MockRepository，L2+ 使用真实存储。Repository 接口是唯一边界。

**动因**：
- Repository 接口由 `service.yaml` API 一一映射生成，是端云合约的 Dart 表示
- MockRepository 实现同一接口，保证 mock 测试的"语义契约"与真实实现对齐
- Riverpod Provider 模式（`xxxRepositoryProvider`）使 ProviderScope override 天然成为测试注入点，无需额外 DI 框架

**替代方案（否决）**：
- 直接 mock Provider → 跳过了 Provider 本身的状态管理逻辑，发现不了 Notifier bug
- 在测试中 new MockRepository() 注入 Widget → 绕过 Provider 体系，与生产路径不一致

---

## 2. L1b/c：`flutter_test` 而非 Patrol 做 Journey

**决策**：使用 `flutter_test` 的 `pumpWidget` + `tap`/`enterText` 做 Widget 和 Journey 测试。

**动因**：
- 速度：`flutter_test` journey ~5-30s，Patrol E2E ~60-180s
- 稳定性：Widget 树确定性高，无动画时序、渲染延迟问题
- 覆盖范围：约 80% 的旅程断裂可在 Widget 树层发现，Patrol 只处理剩余 20%

**Patrol vs flutter_test 边界**（经验法则）：

| 需求 | 用 flutter_test | 用 Patrol |
|---|---|---|
| 点击/输入 | `tap` / `enterText` | 同左 |
| 路由跳转 | `pumpAndSettle` | 同左 |
| Provider 状态 | `ProviderScope` override | — |
| 软键盘输入 | 模拟即可 | 真实 IME 测试 |
| iOS 权限弹窗 | ❌ 无法覆盖 | `$.native.grantPermissionWhenInUse()` |
| 相机/相册 picker | ❌ | `$.native.tapAlertButton()` |
| 推送通知点击 | ❌ | `$.native.pressHomeButton()` |
| 跨平台字体渲染 | 不测（golden test） | 真实设备截图 |

---

## 3. L2：testcontainers 而非 embedded-postgres

**决策**：Content Service 使用 MongoDB，测试引擎选 `testcontainers-go/modules/mongodb`，不用 in-memory store。

**动因**：
- MongoDB 的 BSON 序列化、ObjectId 生成、索引计划、aggregation pipeline 在 in-memory 中无法验证
- testcontainers 在 CI 和本地行为一致（均拉 `mongo:7` 镜像）
- `runtime/testinfra` 包已提供 `testcontainers` 集成，只需在 `content-service/tests/testmain_test.go` 调用即可

**关于 embedded-postgres**：当前规则模板用 embedded-postgres 示例，Content Service 没有 PostgreSQL，示例仅供参考——实际存储引擎由 `storage.yaml` 中 `primary_db` 字段决定。

---

## 4. L3：Dart HTTP Client 而非专用 REST 测试工具

**决策**：L3 API Contract 使用 Dart HTTP client（`package:http`）配合 ContentRepository 的 `fromJson` 逻辑验证响应。

**动因**：
- 共享 DTO 解析代码，发现"真实 API 返回字段"与"端侧 fromJson 解析"之间的漂移
- 无需维护单独的测试语言（Postman/Newman、Python requests 等）
- e2e.yaml 中已声明的断言可直接映射为 Dart assert 语句

---

## 5. L4：Patrol 而非 Appium

**决策**：L4 使用 Patrol（https://patrol.leancode.co/）。

**动因**：

| 维度 | Patrol | Appium |
|---|---|---|
| 语言 | Dart（与 app 同） | 通常 Python/Java/JS |
| Widget Key | 直接引用 `lib/core/test_keys.dart` 常量 | 需 accessibility ID 映射 |
| Native 交互 | `$.native` 原生支持 | 需 flutter-driver 插件，维护成本高 |
| 单一代码库 | 一套测试跑 iOS + Android | 常需维护两套 |
| Firebase Test Lab | 官方支持 | 支持但配置复杂 |

**Widget Key 策略**：生产代码中关键交互元素打 `Key(TestKeys.xxx)`，`TestKeys` 常量统一声明在 `lib/core/test_keys.dart`，Patrol 通过 Key 而非文本字符串定位元素（文本随 i18n 变化）。

---

## 6. mock.yaml 驱动 codegen 生成 Dart 测试骨架（演进方向）

**当前**：mock.yaml 的 `dto_scenarios`、`error_scenarios`、`behavior_scenarios` 存在，但对应 Dart 测试文件手写。

**演进路径**：
1. 近期：在 mock.yaml 中新增 `widget_scenarios` 和 `journey_scenarios` 作为「测试意图声明」
2. 中期：codegen_app_metadata 读取这些 section 生成 `_generated_*_test.dart` 骨架（TODO 注释 + fixture 工厂）
3. 长期：gate 检查 mock.yaml 中每个 scenario 都有对应测试函数存在（通过 `dart_func` 字段）

---

## 7. 门禁升级策略（最小破坏性路径）

**问题**：直接加 `flutter test` 和 `go test` 到 gate 会因现有测试不完整而立即红。

**分步方案**：
1. **T0（立即）**：`go test ./services/content-service/...` 加入 gate，当前已有的 handler tests 继续通过（in-memory 暂时保留，标记 TODO）
2. **T1（本迭代）**：修复 testcontainers，删除 in-memory store
3. **T2（本迭代）**：`flutter test` 去掉 QWQ_GATE_TESTS=1 跳过条件（现有 6 个 L1a 测试已全通过）
4. **T3（下一迭代）**：补全 L1b/c Widget + Journey tests，contract.yaml go_func 全部实现
