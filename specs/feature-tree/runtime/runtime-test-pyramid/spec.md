# Test Pyramid Enforcement

## 范围

为端云一体化开发建立**分层测试金字塔**，作为整个开发流程（Plan → Create → Implement → Verify → Submit）和门禁（`make gate` / `make gate-full`）的强制质量基线。

本规格文档对应 `.cursor/rules/03-testing.mdc` 的执行层约束；二者保持同步——规则更新时同步更新本 spec。

---

## 四层金字塔总览

```
        L4  UI Journey (Patrol)
            真实 iOS/Android 设备 + staging
            场景 ≤10，advisory，pre-release 阻塞发布
        ────────────────────────────────────────
        L3  API Contract (staging HTTP)
            无 UI driver，Dart HTTP client 打 staging
            场景来自 e2e.yaml[test_type: api_contract]
            advisory，daily + pre-release
        ════════════════════════════════════════  ← Mock Wall（Repository 接口边界）
        L2  Cloud Contract Tests (Go)
            testcontainers MongoDB + miniredis
            contract.yaml go_func 驱动
            每次 PR，阻塞合入
        ────────────────────────────────────────
        L1c Journey Tests (flutter_test + MockRepo)
            多屏旅程，ProviderScope 注入 Mock
            每次 PR，阻塞合入
        L1b Widget Tests (flutter_test + MockRepo)
            组件渲染 + 状态响应
            每次 PR，阻塞合入
        L1a Contract Tests (flutter_test, pure Dart)
            DTO / 错误码 / 行为格式 / UI配置
            每次 PR，阻塞合入
```

**Mock Wall 原则**：墙左侧（L1a/b/c）完全在 `flutter_test` 沙箱内，不发任何 HTTP 请求；MockRepository 实现 Repository 接口，fixture 数据从 `mock.yaml` 派生。墙右侧（L2+）守护真实存储和端云合约。

---

## 各层守护目标

### L1a — Contract Tests（已有基线）
- 守护：metadata → codegen → Dart 类型链正确性
- 具体：DTO 别名解析、错误码枚举与 `errors.yaml` 对齐、行为 payload 字段与 `behaviors.yaml` 一致、`ContentUIConfig` tab/flag key 与 `ui_config.yaml` 对齐
- 不守护：渲染、状态管理、路由

### L1b — Widget Tests（需补齐）
- 守护：单个 Widget 的渲染逻辑和状态响应
- 必须覆盖：PhotoPostCard、VideoPostCard、ArticlePostCard、CommentInputBar
- 典型断言：ui_config 控制的字段（如 `show_author_avatar`）正确驱动 Widget 显隐、likeButton 触发 Provider 状态变化
- 不守护：多屏流转、网络 I/O

### L1c — Journey Tests（需补齐）
- 守护：多屏用户旅程意图链完整性，在 `flutter_test` 中通过 `pumpWidget` + `tap` 驱动
- 必须覆盖（3 条核心旅程）：
  1. 发现页 → 点击 → 内容详情（路由传参不丢失）
  2. 点赞 → 乐观更新 → 服务器返回 429 → 回滚 + 错误 Toast
  3. 评论输入 → 提交 → MockRepo.createComment 被调用 → 评论数 +1
- 不守护：真实设备手势、系统弹窗、跨平台渲染差异

### L2 — Cloud Contract Tests（需修复）
- 守护：服务在真实存储层上的业务行为、存储副作用、事件发布
- 存储：testcontainers mongo:7（禁止 in-memory store）+ miniredis/v2
- Mock 边界：跨服务 RPC、LLM/Embedding 外部 API、媒体处理异步回调
- 驱动文件：`contract.yaml` 中每个 `go_func` 对应一个实际 Go 测试函数
- 必须覆盖：每个 `service.yaml` API endpoint ≥1 个 Go test、每个 `events.yaml` 事件 ≥1 个发布验证

### L3 — API Contract / staging HTTP（需新建 runner）
- 守护：端云数据合约不漂移（cursor 分页、错误码格式、字段可见性）
- 驱动文件：`e2e.yaml[test_type: api_contract]` 场景
- 执行方式：Dart HTTP client 发请求打 staging，用 Repository `fromJson` 解析断言
- 发现不了的 bug（交由 L4）：UI 渲染、native 交互

### L4 — UI Journey / Patrol（需新建）
- 守护：用户可感知旅程在真实 iOS/Android 设备上的一致性
- 工具：Patrol（Flutter 原生 E2E）+ Firebase Test Lab
- 场景数量：≤10 条，每条对应 `e2e.yaml[test_type: ui_journey]` 的一个 `patrol_flow`
- 场景选取原则：只覆盖 flutter_test 无法替代的行为（native 权限弹窗、软键盘、相机、推送点击）

---

## 门禁绑定（强制）

| 门禁 | 触发时机 | 包含层 | 失败行为 |
|---|---|---|---|
| `make gate` | 每次 PR | L1a + L1b + L1c + L2 | ❌ 阻塞合入 |
| `make gate-full` | daily + pre-release | 以上 + L3 | ⚠️ Advisory（pre-release 阻塞发布） |
| Firebase Test Lab | pre-release | L4 | ❌ 阻塞发布 |

---

## 约束

- L2 禁止使用 in-memory store，违反 → gate 结构检测 fail
- L1b/c 禁止在 `ProviderScope` 外直接 `new MockRepository()`
- L4 场景数量上限 10，超出需 review
- `e2e.yaml` 中 `patrol_flow` 引用的文件不存在 → `make gate` warn 级别提示
- L3 staging 环境不可用 → 跳过并记录，不阻塞 daily gate
