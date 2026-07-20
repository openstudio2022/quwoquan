# Design: runtime-test-pyramid

> Status: implemented.

## Summary

`runtime-test-pyramid` 已从历史 `T1-T4/L1-L4` 口径收敛为仓库唯一的三层测试模型：

- `local_contract`
- `api_integration`
- `user_acceptance`

设计目标不是再发明一套测试分类，而是用统一环境语义、统一 case id、统一 canonical 目录和统一门禁，
把 gamma-local / prod gray-initial 的用户旅程、页面矩阵、服务契约和本地契约串成单一真相源。

## Environment 语义

- `alpha` / `local`：`local_contract`
- `beta` / `gamma`：`api_integration`
- `gamma_local` / `prod + rollout_stage=gray_initial`：`user_acceptance`

约束：

- 生产只有 `prod` 一个环境；`gray-initial` 是 rollout stage，不是 `prod-gray`
- 发布前允许在 `prod` 的 `gray_initial` rollout stage 跑只读/幂等 `api_integration` 与 Journey/Page `user_acceptance`
- 不再新增 `T1-T4`、`L1-L4`、`contract-test` 等第二口径

## 顶层用例模型

### Journey

- `user_acceptance.<journey_id>.<scenario_id>.<case>`
- Journey 是用户旅程主真相源，覆盖欢迎/登录、内容发现消费、搜索、主页网络、社交消息、助手、
  引流回流、发布链等顶层路径

### Page

- `user_acceptance.page.<surface_id>.<state_or_action>`
- 页面清单直接来自 metadata `ui_surfaces` / `app_routes`
- 每个 surface 至少覆盖：
  - `load_success`
  - `empty_permission_error`
  - `primary_cta`
  - `trace_context`

## Reverse Binding

任何 `implemented` / `completed` 的 Journey 或 Page `user_acceptance` case，都必须反向绑定：

- 至少 1 个 `local_contract`
- 至少 1 个 `api_integration`

否则：

- acceptance 不得标记完成
- `verify-test-coverage-map` 必须失败

## Canonical 目录

### App

- `quwoquan_app/test/local_contract/**`
- `quwoquan_app/test/api_integration/**`
- `quwoquan_app/test/user_acceptance/**`

### Service

- `quwoquan_service/services/<svc>/tests/local_contract/**`
- `quwoquan_service/services/<svc>/tests/api_integration/**`

### Data

- `quwoquan_data/tests/local_contract/**`
- `quwoquan_data/tests/api_integration/**`
- `quwoquan_data/tests/user_acceptance/**`

### Ops

- `quwoquan_ops/tests/local_contract/**`
- `quwoquan_ops/acceptance/api_integration/**`
- `quwoquan_ops/acceptance/user_acceptance/**`

测试文件必须物理位于 canonical 根；不保留 bridge、旧目录或豁免入口。

## Gate Flow

- `make gate`
  - `verify-test-specs`
  - `verify-test-directory-layout`
  - `verify-test-no-fake`
  - `verify-test-coverage-map`
  - `test-local-contract`
- `make gate-smoke`
  - `make gate`
  - Alpha 固定投影的关键页面、API、导入形状与恢复契约
- `make gate-integration ENV=beta|gamma`
  - `make gate`
  - 内容数据面的真实 import、API、媒体、幂等、回滚/replay
- `make gate-release ENV=gamma|prod`
  - `make gate`
  - Gamma 真机 UAT、trace/SLO；Prod 审批、灰度与回滚

## Exit Rule

本能力关闭时，必须同时满足：

- `user_acceptance.page.*` 已落地，不再为 0
- `tests.recorded` 不再引用 legacy 测试路径
- App / Service / Data / Ops canonical 根全部可追溯
- backlog `R-TST01` / `R-TST02` 已回写关闭与验证证据
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
2. **local_contract（本迭代）**：修复 testcontainers，删除 in-memory store
3. **local_contract（本迭代）**：`flutter test` 去掉 QWQ_GATE_TESTS=1 跳过条件（现有 6 个 L1a 测试已全通过）
4. **api_integration（下一迭代）**：补全 L1b/c Widget + Journey tests，contract.yaml go_func 全部实现

---

## 8. 门禁全景：baseline / smoke / integration / release

```
make gate                           ← baseline；每次 PR，阻塞合入
  ├── metadata/codegen、目录、coverage、非功能契约
  ├── local_contract
  └── 不读取远端 URL、SLS、设备或运行输出配置

make gate-smoke                     ← alpha；可重复 smoke
  └── mock/contract 投影、关键页面/API、导入形状与错误恢复

make gate-integration ENV=beta|gamma ← 内容数据面集成
  └── full-sync、API、媒体、幂等、rollback/replay

make gate-release ENV=gamma|prod   ← 商业准出
  └── Gamma 真机 UAT、trace/SLO；Prod 审批、灰度、观察和回滚
```

所有 profile 都通过根 Makefile 和 `stackctl verify --profile` 进入；不得在
profile 之间隐式降级、替换环境或将外部依赖缺失记为通过。
