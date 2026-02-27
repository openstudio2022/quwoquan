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
- testcontainers 在 CI 和本地（有 Docker）行为一致（均拉 `mongo:7` 镜像）
- `runtime/testinfra` 包已提供 `testcontainers` 集成，只需在 `content-service/tests/testmain_test.go` 调用即可

**实施阶段调整（本地 Docker 不可用策略）**：
`testmain_test.go` 使用 `defer/recover` 捕获 testcontainers 内部 panic（Docker daemon 不可用时触发）。
- 本地无 Docker：输出 `[L2] SKIP: Docker unavailable`，`os.Exit(0)` 跳过测试（不阻塞本地开发）
- CI 环境（`CI=true` 或 `GITHUB_ACTIONS=true`）：仍 panic，强制 gate 失败
- 原则：测试在 CI 的行为是强约束，本地开发体验是弱约束

**关于 embedded-postgres**：当前规则模板用 embedded-postgres 示例，Content Service 没有 PostgreSQL，示例仅供参考——实际存储引擎由 `storage.yaml` 中 `primary_db` 字段决定。

---

## 4. L3：Dart HTTP Client 而非专用 REST 测试工具

**决策**：L3 API Contract 使用 Dart HTTP client（`package:http`）配合 ContentRepository 的 `fromJson` 逻辑验证响应。

**动因**：
- 共享 DTO 解析代码，发现"真实 API 返回字段"与"端侧 fromJson 解析"之间的漂移
- 无需维护单独的测试语言（Postman/Newman、Python requests 等）
- e2e.yaml 中已声明的断言可直接映射为 Dart assert 语句

---

## 4a. L3 最佳实践决策（增强）

### 4a.1 契约覆盖维度（三层递进）

L3 不止检查 status code，需覆盖三个维度：

| 维度 | 内容 | 工具 |
|------|------|------|
| **协议层** | HTTP 状态码、Content-Type、分页 header | http.Response |
| **结构层** | 响应 JSON 字段完整性、字段类型正确 | fromMap + assert |
| **语义层** | computed 字段（aspectRatio、格式化时间）、错误码映射 | DTO getter + ContentErrorCode |

**最佳实践参照**：Consumer-Driven Contract Testing（Pact 思路）——端侧声明它依赖的字段/语义，服务端必须满足；但本项目用 e2e.yaml 统一声明，比 Pact 更适合单仓。

### 4a.2 测试数据策略：API seeding 而非静态 fixture

**决策**：L3 在 `setUpAll` 中通过 staging API 创建测试数据，`tearDownAll` 删除；不依赖 staging 的固定数据集。

**动因**：
- 静态 fixture 会因 staging 数据轮换而失效（"测试通过但数据是旧的"假阳性）
- API seeding 与真实写路径一致，同时验证写接口
- tearDown 保持 staging 环境干净，测试互不影响

**示例**：
```dart
late String _seededPostId;
setUpAll(() async {
  _seededPostId = await _seedPhotoPost(client);  // POST /v1/content/posts
});
tearDownAll(() async {
  await _deletePost(client, _seededPostId);       // DELETE /v1/content/posts/{id}
});
```

### 4a.3 错误契约测试：staging error injection

**决策**：通过请求头 `X-Test-Error-Inject: CONTENT.USER.post_not_found` 触发服务端返回指定错误码，不依赖真实数据不存在的偶然性。

**动因**：
- 避免 staging 数据变化导致错误测试失效
- 与 runtime/errors 的错误码枚举直接对齐
- 服务端只在 staging profile 开启 error inject header

### 4a.4 响应时间 SLO 断言

**决策**：L3 在关键接口上增加响应时间上限断言（不在 L1/L2 做，因为它们不经过真实网络）。

```dart
final sw = Stopwatch()..start();
final resp = await http.get(feedUrl, headers: headers);
sw.stop();
expect(sw.elapsedMilliseconds, lessThan(800),
    reason: 'feed API p99 SLO: <800ms on staging');
```

### 4a.5 staging 不可用时的 skip 策略

**决策**：`setUpAll` 中先 HEAD 请求探测 staging；不可用时调用 `markTestSkipped` 或抛出 `TestFailure` 带特殊 exit code，gate 识别后以 warn 处理而非 fail。

```dart
setUpAll(() async {
  try {
    final probe = await http.head(Uri.parse(stagingBaseUrl)).timeout(Duration(seconds: 5));
    if (probe.statusCode >= 500) throw Exception('staging unavailable');
  } catch (_) {
    markTestSkipped('L3: staging unreachable, skipping api_contract tests');
  }
});
```

### 4a.6 认证策略

**决策**：L3 测试使用专用 staging test user（`TEST_AUTH_TOKEN` 环境变量注入），不使用 CI 机器人账号，不硬编码 token。

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

## 5a. L4 最佳实践决策（增强）

### 5a.1 只测 flutter_test 无法替代的行为

**决策**：L4 场景选取遵守"Patrol 专属"原则——flutter_test 能跑的旅程放 L1c，Patrol 只覆盖以下类型：

| 行为类型 | flutter_test | Patrol |
|----------|-------------|--------|
| 点击/滑动/输入 | ✅ 用 tap/drag/enterText | 可以但没必要重复 |
| GoRouter 路由跳转 | ✅ | 可以但没必要 |
| 软键盘真实 IME | ❌ 模拟键盘 | ✅ 真实 IME 键盘 |
| iOS 权限弹窗（相机/通知） | ❌ | ✅ `$.native.grantPermissionWhenInUse()` |
| Android 系统弹窗 | ❌ | ✅ `$.native.tapAlertButton()` |
| 推送通知点击 | ❌ | ✅ `$.native.pressHomeButton()` |
| Deep link 跳转 | ❌ | ✅ |
| 横竖屏切换 | ❌ | ✅ `$.native.rotate()` |
| 应用切后台再回来 | ❌ | ✅ `$.native.pressHomeButton()` + reopen |

**场景数量上限 10**：超出就意味着 L1c 覆盖不够，需先补 L1c。

### 5a.2 测试隔离与状态清理

**决策**：每个 Patrol 测试在 `setUp` 中调用 staging API 重置用户互动状态（unlike、uncomment 等），`tearDown` 清理测试数据。依赖 staging 专用 `X-Test-Reset: true` header 或独立测试接口。

```dart
setUp(() async {
  // 清空 staging 测试用户的点赞/评论记录
  await _resetTestUserInteractions();
});
```

### 5a.3 等待策略：禁止固定 sleep

**决策**：禁止 `await Future.delayed(Duration(seconds: 3))`，使用 Patrol 的响应式等待：

```dart
// ❌ 禁止
await Future.delayed(Duration(seconds: 3));

// ✅ 响应式等待
await $.pumpAndSettle();
await $(Key(TestKeys.likeCountText)).waitUntilVisible(timeout: Duration(seconds: 5));
```

### 5a.4 失败截图与 CI 报告

**决策**：在 `patrolTest` 的 `onFailed` 回调中调用 `$.takeScreenshot()`，截图上传至 FTL artifact 或 CI artifact。Firebase Test Lab 自动保存所有截图/视频。

### 5a.5 Flaky 测试标注与隔离

**决策**：已知不稳定的场景用 `group('flaky', ...)` 隔离，CI 允许这些 group 重试 2 次（patrol.yaml 配置 `retry: 2`），最终仍失败才 fail。不允许用 skip 代替 fix。

### 5a.6 Firebase Test Lab 设备矩阵

**决策**：只测业务覆盖率最高的设备组合：

| 平台 | 设备 | OS 版本 |
|------|------|---------|
| iOS | iPhone 15 | iOS 17 |
| iOS | iPhone 12 | iOS 15（最低支持版本） |
| Android | Pixel 7 | Android 14 |
| Android | Pixel 4 | Android 12（最低支持版本） |

4 台设备并行，单次 FTL 运行预算 <15 min。

### 5a.7 patrol.yaml 配置策略

```yaml
# quwoquan_app/patrol.yaml
app_name: quwoquan
android:
  app_id: com.quwoquan.app
  wait_for_app_launch_timeout: 30
ios:
  bundle_id: com.quwoquan.app
  wait_for_app_launch_timeout: 30
test_timeout: 120
retry: 1
```

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

---

## 8. 门禁全景：make gate / gate-full / gate-ftl 分层

```
make gate           ← 每次 PR（阻塞合入）
  ├── flutter test test/cloud/ test/components/ test/ui/   [L1a+b+c]
  ├── go test ./services/content-service/... -count=1      [L2]
  ├── flutter analyze                                       [静态分析]
  ├── verify_metadata_internal                              [metadata 一致性]
  └── patrol_flow 文件存在性检查（warn 级）

make gate-full      ← daily CI + pre-release（advisory → pre-release 阻塞发布）
  ├── make gate（以上全部）
  └── flutter test test/cloud/content/api_contract_runner.dart \
        --dart-define=STAGING_BASE_URL=$(STAGING_BASE_URL) \
        --dart-define=TEST_AUTH_TOKEN=$(TEST_AUTH_TOKEN)   [L3]

Firebase Test Lab   ← pre-release tag 触发（阻塞发布）
  └── patrol test test/patrol/ \
        --dart-define=ENV=staging                          [L4]
```

**Makefile targets**（根目录）：
```makefile
test-api-contract:
    @if [ -z "$(STAGING_BASE_URL)" ]; then \
        echo "[L3] WARN: STAGING_BASE_URL not set, skipping"; exit 0; \
    fi
    cd quwoquan_app && flutter test test/cloud/content/api_contract_runner.dart \
        --dart-define=STAGING_BASE_URL=$(STAGING_BASE_URL) \
        --dart-define=TEST_AUTH_TOKEN=$(TEST_AUTH_TOKEN)

gate-full: gate test-api-contract
```
